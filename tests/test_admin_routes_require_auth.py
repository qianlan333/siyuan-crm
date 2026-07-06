from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.admin_auth.service import CSRF_COOKIE, SESSION_COOKIE, sign_session
from aicrm_next.main import create_app
from tools.check_admin_route_auth import check_admin_route_auth_gate


def _admin_cookie(*, csrf_token: str = "pytest-csrf-token") -> str:
    return sign_session(
        {
            "username": "pytest-admin",
            "display_name": "Pytest Admin",
            "roles": ["super_admin"],
            "login_type": "pytest",
            "iat": 4_102_444_800,
            "csrf_token": csrf_token,
        }
    )


def test_admin_api_routes_require_session_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/admin/channels")

    assert response.status_code == 401
    assert response.json()["error"] == "admin_auth_required"


def test_admin_pages_redirect_to_login_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/admin/api-docs", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login?next=/admin/api-docs"


def test_setup_wizard_redirects_to_login_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/setup/wizard", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login?next=/setup/wizard"


def test_admin_session_allows_protected_route_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    client = TestClient(create_app(), raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, _admin_cookie())

    response = client.get("/api/admin/channels")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_sidebar_routes_do_not_use_admin_session_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/sidebar/profile?external_userid=wx_ext_001&owner_userid=ZhaoYanFang")

    assert response.status_code == 200
    assert response.json()["route_owner"] == "ai_crm_next"


def test_public_routes_remain_public_when_admin_auth_is_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    client = TestClient(create_app(), raise_server_exceptions=False)

    assert client.get("/health").status_code == 200
    assert client.get("/login").status_code == 200
    assert client.get("/api/sidebar/jssdk-config").status_code == 400
    assert client.get("/sidebar/bind-mobile").status_code == 200


def test_admin_write_routes_require_session_bound_csrf_when_enforced(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_ADMIN_AUTH_ENFORCED", "true")
    csrf_token = "csrf-token-for-admin-write"
    client = TestClient(create_app(), raise_server_exceptions=False)
    client.cookies.set(SESSION_COOKIE, _admin_cookie(csrf_token=csrf_token))

    missing = client.post("/api/admin/jobs/order-identity-repair/run", json={})
    assert missing.status_code == 403
    assert missing.json()["error"] == "admin_csrf_required"

    client.cookies.set(CSRF_COOKIE, csrf_token)
    passed_csrf = client.post("/api/admin/jobs/order-identity-repair/run", json={})
    assert passed_csrf.status_code == 401
    assert passed_csrf.json()["error"] != "admin_csrf_required"


def test_admin_route_auth_checker_passes() -> None:
    assert check_admin_route_auth_gate() == []
