from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.admin_auth.service import SESSION_COOKIE, sign_session
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "admin-auth-login-pages-test")
    monkeypatch.delenv("ADMIN_BREAK_GLASS_LOGIN_ENABLED", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_get_login_renders_next_page_with_wecom_links_and_form_target(monkeypatch) -> None:
    response = _client(monkeypatch).get("/login")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "后台登录" in response.text
    assert "/auth/wecom/start?mode=qr" in response.text
    assert "/auth/wecom/start?mode=oauth" in response.text
    assert 'method="post" action="/login"' in response.text
    assert "应急入口未启用" in response.text
    assert "disabled" in response.text
    assert "api.admin_login" not in response.text
    assert "本地应急入口状态" in response.text


def test_login_uses_safe_next_and_redirects_when_session_cookie_is_valid(monkeypatch) -> None:
    client = _client(monkeypatch)
    client.cookies.set(SESSION_COOKIE, sign_session({"username": "bg-admin", "login_type": "break_glass", "iat": 4_102_444_800}))

    safe = client.get("/login?next=/admin/jobs", follow_redirects=False)
    unsafe = client.get("/login?next=https://evil.example.com", follow_redirects=False)

    assert safe.status_code == 302
    assert safe.headers["location"] == "/admin/jobs"
    assert unsafe.status_code == 302
    assert unsafe.headers["location"] == "/admin"
