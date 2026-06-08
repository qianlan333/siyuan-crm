#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"

REQUIRED_FIELDS = {
    "route_pattern",
    "methods",
    "capability_owner",
    "current_runtime_owner",
    "production_behavior",
    "legacy_fallback_allowed",
    "fixture_allowed_in_production",
    "external_side_effect_risk",
    "delete_ready",
    "checker",
    "notes",
}

RUNTIME_OWNERS = {"next", "next_command", "next_adapter", "legacy_facade", "production_compat", "frontend_compat", "blocked"}
PRODUCTION_BEHAVIORS = {
    "next_exact",
    "legacy_forward",
    "guarded_preview",
    "scheduled_safe_mode",
    "fake_adapter",
    "readonly_facade",
    "local_contract_only",
    "next_command",
    "next_oauth_adapter",
    "next_read_model_only",
    "guarded_debug",
}
SIDE_EFFECT_RISKS = {"none", "guarded", "real_blocked"}

REQUIRED_ROUTE_FAMILIES = [
    "/health",
    "/api/system/health",
    "/admin",
    "/admin/customers",
    "/admin/questionnaires",
    "/admin/automation-conversion",
    "/admin/jobs",
    "/admin/wechat-pay/products",
    "/admin/wechat-pay/transactions",
    "/admin/image-library",
    "/admin/miniprogram-library",
    "/admin/attachment-library",
    "/api/customers",
    "/api/customers/{external_userid}",
    "/api/customers/{external_userid}/timeline",
    "/api/messages/{external_userid}/recent",
    "/api/admin/questionnaires*",
    "/api/h5/questionnaires*",
    "/s/{slug}",
    "/api/h5/wechat/oauth*",
    "/api/admin/automation-conversion*",
    "/api/customer-automation*",
    "/api/admin/wechat-pay*",
    "/api/admin/alipay*",
    "/api/products*",
    "/p/{page_slug}",
    "/api/orders*",
    "/api/checkout*",
    "/api/wechat-pay*",
    "/api/alipay*",
    "/api/admin/image-library*",
    "/api/admin/attachment-library*",
    "/api/admin/miniprogram-library*",
    "/wecom/external-contact/callback",
    "/api/wecom/events",
    "/mcp",
]

REAL_EXTERNAL_KEYWORDS = (
    "wechat-pay",
    "alipay",
    "checkout",
    "oauth",
    "wecom",
    "mcp",
    "openclaw",
    "callback",
    "run-due",
    "capture",
)


@contextmanager
def production_route_inventory_env():
    keys = {
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"),
        "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
    }
    os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "1"
    os.environ.pop("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", None)
    os.environ.setdefault("DATABASE_URL", "postgresql://manifest:manifest@127.0.0.1:1/aicrm_manifest")
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    try:
        yield
    finally:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or MANIFEST
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*", ".*")
    escaped = re.sub(r"\\\{[^{}]+:path\\\}", ".*", escaped)
    escaped = re.sub(r"\\\{[^{}]+\\\}", "[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def _matches(pattern: str, route_path: str) -> bool:
    return bool(_pattern_to_regex(pattern).match(route_path))


def _route_matches_manifest(route_path: str, record: dict[str, Any]) -> bool:
    return _matches(str(record["route_pattern"]), route_path) or _matches(route_path, str(record["route_pattern"]))


def collect_app_routes() -> list[dict[str, Any]]:
    with production_route_inventory_env():
        module = importlib.import_module("aicrm_next.main")
        app = module.create_app()
    routes: list[dict[str, Any]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = sorted((getattr(route, "methods", None) or set()) - {"HEAD"} | ({"HEAD"} if "HEAD" in (getattr(route, "methods", None) or set()) else set()))
        endpoint = getattr(route, "endpoint", None)
        module_name = getattr(endpoint, "__module__", "") if endpoint else ""
        if path:
            routes.append(
                {
                    "path": path,
                    "methods": methods,
                    "endpoint_module": module_name,
                    "is_production_compat": module_name == "aicrm_next.production_compat.api",
                    "is_catch_all": "{path:path}" in path,
                }
            )
    return routes


def _record_by_pattern(records: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
    return next((record for record in records if record.get("route_pattern") == pattern), None)


def _manifest_record_for_route(records: list[dict[str, Any]], route_path: str) -> dict[str, Any] | None:
    matches = [record for record in records if _route_matches_manifest(route_path, record)]
    if not matches:
        return None
    if "{path:path}" in route_path:
        wildcard_matches = [record for record in matches if "*" in str(record["route_pattern"]) or "{path:path}" in str(record["route_pattern"])]
        if wildcard_matches:
            matches = wildcard_matches
    return sorted(matches, key=lambda item: len(str(item["route_pattern"]).replace("*", "")), reverse=True)[0]


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    manifest = load_manifest()
    records = manifest.get("routes") or []
    routes = collect_app_routes()
    route_paths = [route["path"] for route in routes]

    if not records:
        blockers.append("manifest has no routes")

    for idx, record in enumerate(records):
        missing = sorted(REQUIRED_FIELDS - set(record))
        if missing:
            blockers.append(f"record[{idx}] missing fields: {missing}")
            continue
        if not isinstance(record["methods"], list) or not record["methods"]:
            blockers.append(f"{record['route_pattern']} methods must be a non-empty list")
        if record["current_runtime_owner"] not in RUNTIME_OWNERS:
            blockers.append(f"{record['route_pattern']} invalid current_runtime_owner={record['current_runtime_owner']}")
        if record["production_behavior"] not in PRODUCTION_BEHAVIORS:
            blockers.append(f"{record['route_pattern']} invalid production_behavior={record['production_behavior']}")
        if record["external_side_effect_risk"] not in SIDE_EFFECT_RISKS:
            blockers.append(f"{record['route_pattern']} invalid external_side_effect_risk={record['external_side_effect_risk']}")
        if record["fixture_allowed_in_production"] is not False:
            blockers.append(f"{record['route_pattern']} fixture_allowed_in_production must be false")
        if not (ROOT / str(record["checker"])).exists():
            warnings.append(f"{record['route_pattern']} checker does not exist: {record['checker']}")

    for family in REQUIRED_ROUTE_FAMILIES:
        record = _record_by_pattern(records, family)
        if not record:
            blockers.append(f"required route family missing from manifest: {family}")
            continue
        if not any(_route_matches_manifest(path, record) for path in route_paths):
            blockers.append(f"manifest route family does not match current app route: {family}")

    production_compat_catch_alls = [
        route for route in routes if route["is_production_compat"] and (route["is_catch_all"] or route["path"] in {"/wecom/external-contact/callback", "/api/wecom/events"})
    ]
    missing_production_compat = []
    for route in production_compat_catch_alls:
        record = _manifest_record_for_route(records, route["path"])
        if not record:
            missing_production_compat.append(route["path"])
        elif record["current_runtime_owner"] not in {"production_compat", "next", "next_command"}:
            blockers.append(
                f"production_compat route {route['path']} matched non-compatible owner {record['current_runtime_owner']}"
            )
    if missing_production_compat:
        blockers.append(f"production_compat catch-all routes missing manifest coverage: {missing_production_compat}")

    real_side_effect_violations = []
    for record in records:
        route_pattern = str(record.get("route_pattern", "")).lower()
        notes = str(record.get("notes", "")).lower()
        risky = any(keyword in route_pattern or keyword in notes for keyword in REAL_EXTERNAL_KEYWORDS)
        if risky and str(record.get("production_behavior", "")).lower() == "real":
            real_side_effect_violations.append(record["route_pattern"])
    if real_side_effect_violations:
        blockers.append(f"real external side-effect routes cannot be production_behavior=real: {real_side_effect_violations}")

    for route_pattern in ["/admin/customers", "/admin/questionnaires"]:
        record = _record_by_pattern(records, route_pattern)
        if not record:
            continue
        behavior = str(record["production_behavior"])
        notes = str(record.get("notes") or "").lower()
        if behavior not in {"readonly_facade", "next_read_model_only"} and "production_postgres" not in notes:
            blockers.append(f"{route_pattern} must be readonly_facade, next_read_model_only, or explicitly production_postgres")
        if record["fixture_allowed_in_production"] is not False:
            blockers.append(f"{route_pattern} must not allow fixture data in production")

    mcp = _record_by_pattern(records, "/mcp")
    if not mcp:
        blockers.append("/mcp manifest record missing")
    else:
        owner = str(mcp.get("capability_owner", ""))
        combined = f"{owner} {mcp.get('notes', '')}"
        if owner != "aicrm_next.integration_gateway":
            blockers.append("/mcp capability_owner must be aicrm_next.integration_gateway")
        if "openclaw_service" in combined and "not an owner" not in combined and "must not be reintroduced" not in combined:
            blockers.append("/mcp must not be owned by openclaw_service")

    try:
        manifest_path = str(MANIFEST.relative_to(ROOT))
    except ValueError:
        manifest_path = str(MANIFEST)

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "manifest_path": manifest_path,
        "route_count": len(routes),
        "manifest_route_count": len(records),
        "production_compat_catch_all_count": len(production_compat_catch_alls),
        "production_compat_catch_alls": [route["path"] for route in production_compat_catch_alls],
        "required_route_families": REQUIRED_ROUTE_FAMILIES,
    }


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Production Route Ownership Manifest Check",
            "",
            f"- ok: {result['ok']}",
            f"- manifest_route_count: {result['manifest_route_count']}",
            f"- app_route_count: {result['route_count']}",
            f"- production_compat_catch_all_count: {result['production_compat_catch_all_count']}",
            "",
            "## Blockers",
        ]
        lines.extend(f"- {item}" for item in result["blockers"] or ["none"])
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {item}" for item in result["warnings"] or ["none"])
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AI-CRM Next production route ownership manifest.")
    parser.add_argument("--output-md")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = build_report()
    write_outputs(result, args.output_md, args.output_json)
    print(json.dumps({"ok": result["ok"], "blockers": result["blockers"], "warnings": result["warnings"]}, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
