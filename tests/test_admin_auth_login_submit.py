from __future__ import annotations

from fastapi.testclient import TestClient
from werkzeug.security import generate_password_hash

from aicrm_next.admin_auth.service import SESSION_COOKIE
from aicrm_next.main import create_app


def _client(monkeypatch, *, enabled: bool = False) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "admin-auth-login-submit-test")
    if enabled:
        monkeypatch.setenv("ADMIN_BREAK_GLASS_LOGIN_ENABLED", "true")
        monkeypatch.setenv("ADMIN_BREAK_GLASS_USERNAME", "bg-admin")
        monkeypatch.setenv("ADMIN_BREAK_GLASS_PASSWORD_HASH", generate_password_hash("bg-password"))
    else:
        monkeypatch.delenv("ADMIN_BREAK_GLASS_LOGIN_ENABLED", raising=False)
        monkeypatch.delenv("ADMIN_BREAK_GLASS_USERNAME", raising=False)
        monkeypatch.delenv("ADMIN_BREAK_GLASS_PASSWORD_HASH", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_invalid_or_disabled_break_glass_login_is_controlled(monkeypatch) -> None:
    response = _client(monkeypatch).post(
        "/login",
        data={"login_type": "break_glass", "username": "bg-admin", "password": "bad", "next": "/admin"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "应急账号不可用" in response.text
    assert "bad" not in response.text


def test_break_glass_success_sets_next_cookie_and_redirects_safe_next(monkeypatch) -> None:
    response = _client(monkeypatch, enabled=True).post(
        "/login",
        data={"login_type": "break_glass", "username": "bg-admin", "password": "bg-password", "next": "/admin/config"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/config"
    assert SESSION_COOKIE in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "bg-password" not in response.headers["set-cookie"]


def test_break_glass_success_rejects_open_redirect_next(monkeypatch) -> None:
    response = _client(monkeypatch, enabled=True).post(
        "/login",
        data={"login_type": "break_glass", "username": "bg-admin", "password": "bg-password", "next": "https://evil.example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/admin"
