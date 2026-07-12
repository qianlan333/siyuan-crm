#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "docs" / "architecture" / "route_ownership_manifest.yml"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _methods(entry: dict[str, Any]) -> set[str]:
    return {str(method).upper() for method in entry.get("methods") or []}


def _is_write(entry: dict[str, Any]) -> bool:
    return bool(_methods(entry) - SAFE_METHODS)


def _starts(path: str, *prefixes: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def _admin_capability(entry: dict[str, Any]) -> str:
    path = str(entry["path"])
    owner = str(entry["capability_owner"])
    write = _is_write(entry)
    if not write:
        if owner == "admin_config" or path.startswith("/admin/config"):
            return "manage_config"
        if any(marker in path for marker in ("/export", "/identity/", "/messages", "/archive")):
            return "read_customer"
        return "admin_read"
    if owner == "admin_config":
        if "login-access" in path or "admin-user" in path:
            return "manage_admin"
        return "manage_config"
    if owner == "questionnaire":
        return "manage_questionnaire"
    if owner in {"automation_engine", "cloud_orchestrator", "growth_orchestration"}:
        return "manage_group_ops" if "group-ops" in path else "manage_automation"
    if owner in {"automation_agents", "ai_audience_ops", "ai_assist"}:
        return "manage_automation"
    if owner in {"customer_tags", "customer_read_model", "sidebar_write", "identity_contact", "owner_migration"}:
        return "manage_customer"
    if owner in {"media_library", "send_content"}:
        return "manage_content"
    if owner in {"commerce", "service_period", "public_product"}:
        return "refund" if "refund" in path else "manage_commerce"
    if owner in {"message_archive", "ops_enrollment"}:
        return "send_message"
    return "manage_operations"


def _pii_level(entry: dict[str, Any]) -> str:
    path = str(entry["path"]).lower()
    owner = str(entry["capability_owner"])
    if any(marker in path for marker in ("message", "archive", "questionnaire", "identity", "customer", "user", "sidebar")):
        return "sensitive"
    if any(marker in path for marker in ("order", "payment", "refund", "wechat-pay", "alipay", "service-period")):
        return "financial"
    if owner in {"customer_tags", "owner_migration", "ops_enrollment"}:
        return "customer"
    if path.startswith(("/admin", "/api/admin", "/setup")):
        return "internal"
    return "none"


def _callback_auth(entry: dict[str, Any]) -> str:
    path = str(entry["path"])
    if path.startswith(("/wecom/external-contact/callback", "/api/wecom/events")):
        return "provider_signature"
    if "/group-ops/webhooks/" in path:
        return "webhook_bearer"
    if any(marker in path for marker in ("wechat-pay", "alipay", "wechat-shop")) and "notify" in path:
        return "provider_signature"
    if path.startswith("/auth/wecom/callback") or path.startswith("/api/sidebar/oauth/callback") or "oauth/callback" in path:
        return "oauth_state"
    if "test-receiver" in path:
        return "path_token"
    return "scoped_bearer"


def _policy_for(entry: dict[str, Any]) -> dict[str, Any]:
    path = str(entry["path"])
    owner = str(entry["capability_owner"])
    write = _is_write(entry)

    if path in {"/login", "/logout"}:
        return _policy("admin", "public", "public", "public", _pii_level(entry), False, "auth_strict")

    if _starts(path, "/admin", "/api/admin", "/setup"):
        return _policy(
            "admin",
            "admin_session",
            _admin_capability(entry),
            "global",
            _pii_level(entry),
            write,
            "authenticated",
        )

    if path == "/api/automation/group-ops/broadcast":
        return _policy(
            "external_integration",
            "internal_bearer",
            "external_write",
            "service",
            _pii_level(entry),
            False,
            "integration",
            token_purpose="group_broadcast",
        )

    if path.startswith("/api/automation/group-ops/") and "/webhooks/" not in path:
        return _policy(
            "admin",
            "admin_session",
            "manage_group_ops" if write else "admin_read",
            "global",
            _pii_level(entry),
            write,
            "authenticated",
        )

    if _starts(path, "/api/sidebar"):
        if path.startswith("/api/sidebar/oauth/"):
            return _policy("sidebar", "oauth_state", "sidebar_read", "self", "none", False, "public_strict")
        if path == "/api/sidebar/jssdk-config":
            return _policy("sidebar", "public", "sidebar_bootstrap", "self", "none", False, "public_strict")
        return _policy(
            "sidebar",
            "sidebar_signed_context",
            "sidebar_write" if write else "sidebar_read",
            "owner",
            _pii_level(entry),
            False,
            "authenticated",
        )

    if path.startswith("/sidebar/"):
        return _policy("sidebar", "public", "sidebar_bootstrap", "self", "none", False, "public_strict")

    callback_markers = ("callback", "notify", "/webhooks/", "activation-webhook", "test-receiver")
    if path in {"/api/wecom/events"} or any(marker in path for marker in callback_markers):
        return _policy(
            "callback",
            _callback_auth(entry),
            "callback_receive",
            "single_resource",
            _pii_level(entry),
            False,
            "callback_burst",
        )

    public_prefixes = (
        "/api/h5",
        "/s",
        "/p",
        "/pay",
        "/r",
        "/radar/view",
        "/api/products",
        "/api/checkout",
        "/api/orders",
        "/api/wechat-pay",
        "/api/alipay",
        "/api/wechat-shop",
    )
    if _starts(path, *public_prefixes):
        blocked_write = str(entry.get("route_name") or "").endswith(("blocked_write", "unknown", "unknown_child"))
        if path.startswith("/api/h5/questionnaires/") and "/result/" in path:
            return _policy(
                "public_h5",
                "path_token",
                "public_result_read",
                "single_resource",
                "sensitive",
                False,
                "public_strict",
            )
        return _policy(
            "public_h5",
            "public",
            "public_blocked" if blocked_write else "public",
            "single_resource",
            _pii_level(entry),
            False,
            "public_strict" if write else "public_standard",
        )

    if path in {"/health", "/api/system/health"}:
        return _policy("external_integration", "public", "health_read", "public", "none", False, "health")

    if path == "/api/system/runtime-route-map":
        return _policy(
            "internal_worker",
            "internal_bearer",
            "internal_read",
            "service",
            "internal",
            False,
            "internal",
            token_purpose="automation_worker",
        )

    if path == "/mcp":
        return _policy(
            "external_integration",
            "internal_bearer",
            "external_write" if write else "external_read",
            "service",
            "sensitive",
            False,
            "internal",
            token_purpose="mcp",
        )

    if path == "/api/identity/resolve":
        return _policy(
            "external_integration",
            "internal_bearer",
            "external_write" if write else "external_read",
            "service",
            "sensitive",
            False,
            "internal",
            token_purpose="identity",
        )

    if path.startswith(("/api/customers", "/api/users", "/api/messages")):
        return _policy(
            "external_integration",
            "admin_session",
            "send_message" if write else "read_customer",
            "global",
            "sensitive",
            write,
            "authenticated",
        )

    if _starts(path, "/api/archive"):
        return _policy(
            "internal_worker",
            "internal_bearer",
            "internal_execute" if write else "internal_read",
            "service",
            _pii_level(entry),
            False,
            "internal",
            token_purpose="archive",
        )

    if _starts(path, "/api/internal"):
        return _policy(
            "internal_worker",
            "internal_bearer",
            "internal_execute" if write else "internal_read",
            "service",
            _pii_level(entry),
            False,
            "internal",
            token_purpose="automation_worker",
        )

    external_prefixes = (
        "/api/external",
        "/api/ai",
        "/api/ai-assist",
        "/api/customer-automation",
    )
    if _starts(path, *external_prefixes):
        return _policy(
            "external_integration",
            "scoped_bearer",
            "external_write" if write else "external_read",
            "service",
            _pii_level(entry),
            False,
            "integration",
        )

    if owner == "auth_wecom" or path.startswith("/auth/wecom"):
        return _policy("admin", "oauth_state", "public", "public", "none", False, "auth_strict")

    if path == "/{filename}" and entry.get("route_name") == "wechat_domain_verification_file":
        return _policy(
            "external_integration",
            "public",
            "public",
            "public",
            "none",
            False,
            "public_strict",
        )

    raise ValueError(f"unclassified route policy: {','.join(sorted(_methods(entry)))} {path} {entry.get('route_name')}")


def _policy(
    audience: str,
    auth_scheme: str,
    capability: str,
    access_scope: str,
    pii_level: str,
    csrf: bool,
    rate_limit: str,
    *,
    token_purpose: str = "none",
) -> dict[str, Any]:
    return {
        "audience": audience,
        "auth_scheme": auth_scheme,
        "capability": capability,
        "access_scope": access_scope,
        "pii_level": pii_level,
        "csrf": csrf,
        "rate_limit": rate_limit,
        "token_purpose": token_purpose,
    }


def update_manifest(path: Path, *, check: bool) -> int:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    routes = raw.get("routes") if isinstance(raw, dict) else None
    if not isinstance(routes, list):
        raise SystemExit("route ownership manifest must contain a routes list")
    changed = 0
    for entry in routes:
        if not isinstance(entry, dict):
            raise SystemExit("route ownership manifest entries must be mappings")
        expected = _policy_for(entry)
        expected_requires_auth = expected["auth_scheme"] not in {"public", "oauth_state", "provider_signature", "path_token"}
        for key, value in {"requires_auth": expected_requires_auth, **expected}.items():
            if entry.get(key) != value:
                changed += 1
                entry[key] = value
    if check:
        if changed:
            raise SystemExit(f"route policy manifest drift: {changed} field values differ; run with --write")
        print(f"route policy manifest ok: {len(routes)} routes")
        return 0
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    print(f"updated {len(routes)} route policies ({changed} field values changed)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return update_manifest(args.manifest, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
