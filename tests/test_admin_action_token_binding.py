from __future__ import annotations

import json
import re
from time import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from aicrm_next.admin_auth.action_token import (
    build_admin_action_token_bundle,
    issue_action_token,
    validate_action_token,
    validate_action_token_for_request,
)
from aicrm_next.admin_jobs.routes import ensure_admin_action_token, validate_admin_action_token
from aicrm_next.admin_auth.service import CSRF_COOKIE, SESSION_COOKIE, sign_session
from aicrm_next.main import create_app


def _session(*, username: str = "security-admin", sid: str = "session-a") -> dict:
    return {
        "auth_source": "break_glass",
        "username": username,
        "roles": ["super_admin"],
        "sid": sid,
        "csrf_token": f"csrf-{sid}",
        "iat": 100,
    }


def _request(session: dict, *, method: str = "POST") -> Request:
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/api/admin/external-effects/jobs/7/retry",
            "raw_path": b"/api/admin/external-effects/jobs/7/retry",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
        }
    )
    request.state.admin_session = session
    request.state.route_policy = SimpleNamespace(
        capability="manage_operations",
        route_name="retry_external_effect_job",
        path="/api/admin/external-effects/jobs/{job_id}/retry",
    )
    return request


def _token(session: dict, *, now: int = 1_000) -> str:
    return issue_action_token(
        session,
        capability="manage_operations",
        method="POST",
        action="retry_external_effect_job",
        target="/api/admin/external-effects/jobs/{job_id}/retry",
        now=now,
    )


def test_action_token_accepts_only_exact_bound_context() -> None:
    session = _session()
    token = _token(session)

    result = validate_action_token(
        token,
        session,
        capability="manage_operations",
        method="POST",
        action="retry_external_effect_job",
        target="/api/admin/external-effects/jobs/{job_id}/retry",
        now=1_001,
    )

    assert result.ok is True
    assert result.claims
    assert result.claims["act"] == "retry_external_effect_job"


@pytest.mark.parametrize(
    ("session", "capability", "method", "action", "target", "error_suffix"),
    [
        (_session(username="other-admin"), "manage_operations", "POST", "retry_external_effect_job", "/api/admin/external-effects/jobs/{job_id}/retry", "sub"),
        (_session(sid="session-b"), "manage_operations", "POST", "retry_external_effect_job", "/api/admin/external-effects/jobs/{job_id}/retry", "sid"),
        (_session(), "manage_group_ops", "POST", "retry_external_effect_job", "/api/admin/external-effects/jobs/{job_id}/retry", "cap"),
        (_session(), "manage_operations", "DELETE", "retry_external_effect_job", "/api/admin/external-effects/jobs/{job_id}/retry", "m"),
        (_session(), "manage_operations", "POST", "cancel_external_effect_job", "/api/admin/external-effects/jobs/{job_id}/retry", "act"),
        (_session(), "manage_operations", "POST", "retry_external_effect_job", "/api/admin/external-effects/jobs/{job_id}/cancel", "tgt"),
    ],
)
def test_action_token_rejects_cross_context_replay(
    session: dict,
    capability: str,
    method: str,
    action: str,
    target: str,
    error_suffix: str,
) -> None:
    result = validate_action_token(
        _token(_session()),
        session,
        capability=capability,
        method=method,
        action=action,
        target=target,
        now=1_001,
    )

    assert result.ok is False
    assert result.error == f"binding_mismatch:{error_suffix}"


def test_action_token_expires_and_cannot_be_minted_for_missing_capability() -> None:
    viewer = {**_session(), "roles": ["viewer"]}
    with pytest.raises(PermissionError):
        _token(viewer)

    expired = validate_action_token(
        _token(_session(), now=1_000),
        _session(),
        capability="manage_operations",
        method="POST",
        action="retry_external_effect_job",
        target="/api/admin/external-effects/jobs/{job_id}/retry",
        now=1_601,
    )
    assert expired.ok is False
    assert expired.error == "expired"


def test_request_validation_uses_runtime_route_policy() -> None:
    session = _session()
    request = _request(session)
    token = _token(session, now=1_000)

    assert validate_action_token_for_request(request, token).ok is False

    current_token = issue_action_token(
        session,
        capability="manage_operations",
        method="POST",
        action="retry_external_effect_job",
        target="/api/admin/external-effects/jobs/{job_id}/retry",
    )
    assert validate_action_token_for_request(request, current_token).ok is True


def test_shell_bundle_contains_independent_tokens_for_each_unsafe_route() -> None:
    request = _request(_session(), method="GET")
    tokens = build_admin_action_token_bundle(request)

    retry_key = "POST /api/admin/external-effects/jobs/{job_id}/retry"
    cancel_key = "POST /api/admin/external-effects/jobs/{job_id}/cancel"
    assert tokens[retry_key]
    assert tokens[cancel_key]
    assert tokens[retry_key] != tokens[cancel_key]


def test_legacy_unbound_token_is_rejected_when_route_policy_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    request = _request(_session())

    error = validate_admin_action_token(ensure_admin_action_token(), request=request)

    assert error == "admin_action_token 无效或与当前动作不匹配"


def test_rendered_admin_page_supplies_route_bound_token_used_by_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_ROUTE_POLICY_ENFORCED", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    session = {**_session(), "iat": int(time())}
    client = TestClient(create_app(), raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, sign_session(session))
    client.cookies.set(CSRF_COOKIE, session["csrf_token"])
    client.headers["X-CSRF-Token"] = session["csrf_token"]

    page = client.get("/admin/jobs")
    match = re.search(r'<script id="aicrmAdminActionGrants" type="application/json">(.*?)</script>', page.text, re.DOTALL)
    assert page.status_code == 200
    assert match
    tokens = json.loads(match.group(1))
    token = tokens["POST /api/admin/jobs/order-identity-repair/run"]

    response = client.post(
        "/api/admin/jobs/order-identity-repair/run",
        headers={"X-Admin-Action-Token": token},
        json={},
    )

    assert response.status_code == 410
    assert response.json()["error"] == "order_identity_repair_retired"
