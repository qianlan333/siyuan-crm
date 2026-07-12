from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from starlette.requests import Request

from aicrm_next.shared.internal_service_tokens import (
    LEGACY_FALLBACK_DELETE_AFTER,
    LEGACY_FALLBACK_ENABLED_KEY,
    LEGACY_FALLBACK_OWNER,
    RUNTIME_ENVIRONMENT_KEYS,
    TOKEN_PURPOSES,
    validate_internal_service_token,
)
from aicrm_next.shared.route_ownership import load_route_manifest


ROOT = Path(__file__).resolve().parents[1]
ROUTE_MANIFEST = ROOT / "docs" / "architecture" / "route_ownership_manifest.yml"


def _clear_credentials(monkeypatch) -> None:
    for credential in TOKEN_PURPOSES.values():
        monkeypatch.delenv(credential.setting_key, raising=False)
    monkeypatch.delenv(LEGACY_FALLBACK_ENABLED_KEY, raising=False)


def test_each_internal_service_token_rejects_cross_purpose_replay(monkeypatch) -> None:
    _clear_credentials(monkeypatch)
    tokens = {purpose: f"{purpose}-only-token" for purpose in TOKEN_PURPOSES}
    for purpose, credential in TOKEN_PURPOSES.items():
        monkeypatch.setenv(credential.setting_key, tokens[purpose])

    for purpose in TOKEN_PURPOSES:
        accepted = validate_internal_service_token(purpose, tokens[purpose])
        assert accepted.ok is True
        assert accepted.service_account == TOKEN_PURPOSES[purpose].service_account
        assert accepted.used_legacy_fallback is False
        for other_purpose, other_token in tokens.items():
            if other_purpose == purpose:
                continue
            rejected = validate_internal_service_token(purpose, other_token)
            assert rejected.ok is False
            assert rejected.error == "internal_token_required"

    assert RUNTIME_ENVIRONMENT_KEYS == {
        LEGACY_FALLBACK_ENABLED_KEY,
        *(credential.setting_key for credential in TOKEN_PURPOSES.values()),
    }


def test_legacy_automation_token_fallback_is_default_off_and_explicitly_bounded(monkeypatch) -> None:
    _clear_credentials(monkeypatch)
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "legacy-shared-token")

    blocked = validate_internal_service_token("mcp", "legacy-shared-token")
    assert blocked.ok is False
    assert blocked.error == "internal_token_not_configured"

    monkeypatch.setenv(LEGACY_FALLBACK_ENABLED_KEY, "true")
    migrated = validate_internal_service_token("mcp", "legacy-shared-token")
    assert migrated.ok is True
    assert migrated.used_legacy_fallback is True
    assert LEGACY_FALLBACK_OWNER == "platform_ops"
    assert LEGACY_FALLBACK_DELETE_AFTER == "2026-08-10"


def test_every_internal_bearer_route_declares_one_exact_token_purpose() -> None:
    entries = load_route_manifest(ROUTE_MANIFEST)
    internal_routes = {
        (entry["path"], entry["route_name"]): entry["token_purpose"]
        for entry in entries
        if entry["auth_scheme"] == "internal_bearer"
    }

    assert internal_routes == {
        ("/api/archive/health", "archive_health"): "archive",
        ("/api/archive/sync", "archive_sync"): "archive",
        ("/api/automation/group-ops/broadcast", "execute_group_ops_token_broadcast"): "group_broadcast",
        ("/api/identity/resolve", "resolve_identity"): "identity",
        ("/api/internal/direct-send/wecom-private", "create_internal_direct_wecom_private_send"): "automation_worker",
        ("/api/system/runtime-route-map", "runtime_route_map"): "automation_worker",
        ("/mcp", "mcp_metadata"): "mcp",
        ("/mcp", "mcp_rpc"): "mcp",
    }
    assert set(internal_routes.values()) <= set(TOKEN_PURPOSES)


def test_non_internal_bearer_routes_declare_no_internal_token_purpose() -> None:
    entries = load_route_manifest(ROUTE_MANIFEST)

    assert all(
        entry["token_purpose"] == "none"
        for entry in entries
        if entry["auth_scheme"] != "internal_bearer"
    )


def _request_with_bearer(token: str, *, path: str = "/") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "server": ("testserver", 443),
            "client": ("127.0.0.1", 12345),
            "path": path,
            "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


def test_named_internal_entrypoints_enforce_their_declared_purpose(monkeypatch) -> None:
    from aicrm_next.main import create_app
    from aicrm_next.platform_foundation.internal_run_due_guard import validate_internal_timer_token
    from aicrm_next.platform_foundation.webhook_inbox.api import _internal_token_error as callback_token_error

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    tokens = {purpose: f"entrypoint-{purpose}-token" for purpose in TOKEN_PURPOSES}
    for purpose, credential in TOKEN_PURPOSES.items():
        monkeypatch.setenv(credential.setting_key, tokens[purpose])
    client = TestClient(create_app(), raise_server_exceptions=False)
    automation_header = {"Authorization": f"Bearer {tokens['automation_worker']}"}

    assert client.get("/mcp", headers=automation_header).status_code == 401
    assert client.get("/api/identity/resolve?external_userid=wx_ext_001", headers=automation_header).status_code == 401
    assert client.get("/api/archive/health", headers=automation_header).status_code == 401
    assert client.post("/api/automation/group-ops/broadcast", headers=automation_header, json={}).status_code == 401

    assert client.get("/mcp", headers={"Authorization": f"Bearer {tokens['mcp']}"}).status_code == 200
    assert client.get(
        "/api/identity/resolve?external_userid=wx_ext_001",
        headers={"Authorization": f"Bearer {tokens['identity']}"},
    ).status_code == 200
    assert client.get(
        "/api/archive/health",
        headers={"Authorization": f"Bearer {tokens['archive']}"},
    ).status_code != 401
    assert client.post(
        "/api/automation/group-ops/broadcast",
        headers={"Authorization": f"Bearer {tokens['group_broadcast']}"},
        json={},
    ).status_code != 401

    assert callback_token_error(_request_with_bearer(tokens["automation_worker"])) == "internal_token_required"
    assert callback_token_error(_request_with_bearer(tokens["callback"])) == ""
    assert validate_internal_timer_token(_request_with_bearer(tokens["callback"])).blocked is True
    assert validate_internal_timer_token(_request_with_bearer(tokens["automation_worker"])).blocked is False
