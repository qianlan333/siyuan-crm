from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.admin_auth.service import CSRF_COOKIE, SESSION_COOKIE, sign_session
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "admin-auth-logout-test")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_logout_redirects_to_login_and_clears_next_cookie(monkeypatch) -> None:
    client = _client(monkeypatch)
    client.cookies.set(SESSION_COOKIE, sign_session({"username": "bg-admin", "login_type": "break_glass", "iat": 4_102_444_800}))

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert SESSION_COOKIE in response.headers["set-cookie"]
    assert CSRF_COOKIE in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"] or "max-age=0" in response.headers["set-cookie"].lower()


def test_logout_options_is_next_diagnostics(monkeypatch) -> None:
    response = _client(monkeypatch).options("/logout")

    assert response.status_code == 200
    assert response.json()["route"] == "/logout"
    assert response.json()["fallback_used"] is False
    assert response.json()["real_external_call_executed"] is False
