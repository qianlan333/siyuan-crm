from __future__ import annotations

import asyncio
from time import time

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from aicrm_next.admin_auth import route_policy as route_policy_module
from aicrm_next.admin_auth.route_policy import RouteRateLimiter, _csrf_error
from aicrm_next.admin_auth.session_state import SessionStateResult
from aicrm_next.admin_auth.service import CSRF_COOKIE, SESSION_COOKIE, sign_session
from aicrm_next.main import create_app
from aicrm_next.shared.signed_context import build_sidebar_owner_context_token


def _session(*roles: str, csrf_token: str = "route-policy-csrf") -> str:
    return sign_session(
        {
            "username": "policy-user",
            "display_name": "Policy User",
            "roles": list(roles),
            "login_type": "pytest",
            "iat": int(time()),
            "csrf_token": csrf_token,
        }
    )


@pytest.fixture()
def enforced_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "route-policy-internal-token")
    monkeypatch.setenv("MCP_BEARER_TOKEN", "route-policy-mcp-token")
    monkeypatch.setenv("IDENTITY_INTERNAL_API_TOKEN", "route-policy-identity-token")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _admin_client(monkeypatch: pytest.MonkeyPatch, *roles: str) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, _session(*roles))
    client.cookies.set(CSRF_COOKIE, "route-policy-csrf")
    client.headers["X-CSRF-Token"] = "route-policy-csrf"
    return client


def test_mcp_and_identity_resolve_require_internal_service_token(enforced_client: TestClient) -> None:
    missing_mcp = enforced_client.get("/mcp")
    missing_identity = enforced_client.get("/api/identity/resolve?external_userid=wx_ext_001")

    assert missing_mcp.status_code == 401
    assert missing_mcp.json()["error"] == "internal_token_required"
    assert missing_identity.status_code == 401

    assert enforced_client.get(
        "/mcp",
        headers={"Authorization": "Bearer route-policy-mcp-token"},
    ).status_code == 200
    resolved = enforced_client.get(
        "/api/identity/resolve?external_userid=wx_ext_001",
        headers={"Authorization": "Bearer route-policy-identity-token"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["identity"]["unionid"] == "unionid_001"


def test_mcp_accepts_its_scoped_service_token_without_granting_identity_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    monkeypatch.setenv("MCP_BEARER_TOKEN", "mcp-only-token")
    monkeypatch.delenv("AUTOMATION_INTERNAL_API_TOKEN", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)
    headers = {"Authorization": "Bearer mcp-only-token"}

    assert client.get("/mcp", headers=headers).status_code == 200
    identity = client.get("/api/identity/resolve?external_userid=wx_ext_001", headers=headers)
    assert identity.status_code == 503
    assert identity.json()["error"] == "internal_token_not_configured"


def test_sidebar_customer_routes_require_signed_owner_context(enforced_client: TestClient) -> None:
    missing = enforced_client.get("/api/sidebar/profile?external_userid=wx_ext_001")
    assert missing.status_code == 401
    assert missing.json()["error"] == "sidebar_context_required"

    owner_token = build_sidebar_owner_context_token(viewer_userid="ZhaoYanFang", corp_id="ww-test")
    allowed = enforced_client.get(
        "/api/sidebar/profile?external_userid=wx_ext_001&owner_userid=ZhaoYanFang",
        headers={"X-AICRM-Sidebar-Owner-Token": owner_token},
    )
    assert allowed.status_code == 200
    assert allowed.json()["route_owner"] == "ai_crm_next"

    cross_owner = enforced_client.get(
        "/api/sidebar/profile?external_userid=wx_ext_001&owner_userid=LiuXiao",
        headers={"X-AICRM-Sidebar-Owner-Token": owner_token},
    )
    assert cross_owner.status_code == 403
    assert cross_owner.json()["error"] == "sidebar_owner_scope_forbidden"


def test_sidebar_write_uses_signed_owner_and_rejects_body_impersonation(enforced_client: TestClient) -> None:
    owner_token = build_sidebar_owner_context_token(viewer_userid="ZhaoYanFang", corp_id="ww-test")
    headers = {
        "X-AICRM-Sidebar-Owner-Token": owner_token,
        "Idempotency-Key": "route-policy-sidebar-write",
    }

    rejected = enforced_client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        headers=headers,
        json={
            "external_userid": "wx_ext_001",
            "owner_userid": "LiuXiao",
            "class_term": "term-2026-07",
            "status": "active",
        },
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"] == "sidebar_owner_scope_forbidden"

    allowed = enforced_client.post(
        "/api/sidebar/lead-pool/upsert-class-term",
        headers=headers,
        json={
            "external_userid": "wx_ext_001",
            "class_term": "term-2026-07",
            "status": "active",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["ok"] is True


def test_viewer_can_read_but_cannot_write_group_ops_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _admin_client(monkeypatch, "viewer")

    listed = client.get("/api/automation/group-ops/plans")
    created = client.post(
        "/api/automation/group-ops/plans",
        json={"name": "viewer must not create", "type": "standard"},
    )

    assert listed.status_code == 200
    assert created.status_code == 403
    assert created.json()["error"] == "admin_capability_required"
    assert created.json()["required_capability"] == "manage_group_ops"


def test_automation_admin_can_use_authenticated_group_ops_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _admin_client(monkeypatch, "automation_admin")

    response = client.post(
        "/api/automation/group-ops/plans",
        json={
            "name": "authenticated compatibility plan",
            "type": "standard",
            "operatorMemberId": "HuangYouCan",
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "authenticated compatibility plan"


def test_five_principal_permission_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "principal-matrix-service-token")
    monkeypatch.setenv("IDENTITY_INTERNAL_API_TOKEN", "principal-matrix-identity-token")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    anonymous = TestClient(create_app(), raise_server_exceptions=False)
    viewer = _admin_client(monkeypatch, "viewer")
    operator = _admin_client(monkeypatch, "automation_admin")
    admin = _admin_client(monkeypatch, "super_admin")
    service = TestClient(create_app(), raise_server_exceptions=False)

    matrix = {
        "anonymous_admin_read": anonymous.get("/api/automation/group-ops/plans").status_code,
        "viewer_admin_read": viewer.get("/api/automation/group-ops/plans").status_code,
        "viewer_admin_write": viewer.post(
            "/api/automation/group-ops/plans",
            json={"name": "viewer denied", "type": "standard"},
        ).status_code,
        "operator_scoped_write": operator.post(
            "/api/automation/group-ops/plans",
            json={"name": "operator allowed", "type": "standard", "operatorMemberId": "HuangYouCan"},
        ).status_code,
        "admin_write": admin.post(
            "/api/automation/group-ops/plans",
            json={"name": "admin allowed", "type": "standard", "operatorMemberId": "HuangYouCan"},
        ).status_code,
        "service_internal_read": service.get(
            "/api/identity/resolve?external_userid=wx_ext_001",
            headers={"Authorization": "Bearer principal-matrix-identity-token"},
        ).status_code,
        "service_admin_read": service.get(
            "/api/automation/group-ops/plans",
            headers={"Authorization": "Bearer principal-matrix-service-token"},
        ).status_code,
    }

    assert matrix == {
        "anonymous_admin_read": 401,
        "viewer_admin_read": 200,
        "viewer_admin_write": 403,
        "operator_scoped_write": 201,
        "admin_write": 201,
        "service_internal_read": 200,
        "service_admin_read": 401,
    }


def test_admin_write_requires_request_csrf_not_cookie_only(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _admin_client(monkeypatch, "automation_admin")
    del client.headers["X-CSRF-Token"]

    rejected = client.post(
        "/api/automation/group-ops/plans",
        json={"name": "csrf rejected", "type": "standard"},
    )

    assert rejected.status_code == 403
    assert rejected.json()["error"] == "admin_csrf_required"


def test_multipart_form_csrf_field_is_accepted_and_body_is_cached() -> None:
    boundary = "route-policy-boundary"
    token = "multipart-csrf-token"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="csrf_token"\r\n\r\n'
        f"{token}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="upload"; filename="sample.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "sample\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/operations/actions",
            "headers": [
                (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
                (b"cookie", f"{CSRF_COOKIE}={token}".encode()),
            ],
        },
        receive,
    )

    assert asyncio.run(_csrf_error(request, {"csrf_token": token})) is None
    assert asyncio.run(request.body()) == body


def test_revoked_session_is_rejected_before_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        route_policy_module,
        "validate_admin_session_state",
        lambda _session: SessionStateResult(ok=False, error="admin_session_revoked"),
    )
    client = _admin_client(monkeypatch, "automation_admin")

    response = client.get("/api/automation/group-ops/plans")

    assert response.status_code == 401
    assert response.json()["error"] == "admin_session_revoked"


def test_rate_limiter_rejects_requests_after_profile_budget() -> None:
    limiter = RouteRateLimiter()

    assert all(
        limiter.allow(profile="auth_strict", principal="198.51.100.2", route_key="POST /login", now=10.0)
        for _ in range(20)
    )
    assert limiter.allow(
        profile="auth_strict",
        principal="198.51.100.2",
        route_key="POST /login",
        now=10.0,
    ) is False
    assert limiter.allow(
        profile="auth_strict",
        principal="198.51.100.2",
        route_key="POST /login",
        now=71.0,
    ) is True
