from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tests.admin_auth_test_helpers import install_admin_session


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "admin-auth-login-pages-test")
    monkeypatch.delenv("ADMIN_BREAK_GLASS_LOGIN_ENABLED", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_get_login_renders_wecom_only_identity_entry(monkeypatch) -> None:
    response = _client(monkeypatch).get("/login")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "后台登录" in response.text
    assert "/auth/wecom/start?mode=qr" in response.text
    assert "/auth/wecom/start?mode=oauth" in response.text
    assert 'method="post" action="/login"' not in response.text
    assert "不提供本地账密入口" in response.text
    assert "配置 &gt; 后台访问" in response.text
    assert "配置 &gt; 登录与权限" not in response.text
    assert "api.admin_login" not in response.text
    assert "本地应急入口状态" not in response.text


def test_get_login_renders_wecom_auth_error(monkeypatch) -> None:
    response = _client(monkeypatch).get("/login?auth_error=wecom_admin_auth_not_enabled")

    assert response.status_code == 200
    assert "企业微信扫码登录还未启用真实授权" in response.text


def test_login_uses_safe_next_and_redirects_when_session_cookie_is_valid(monkeypatch) -> None:
    client = _client(monkeypatch)
    install_admin_session(client, "super_admin", subject="admin:wecom", principal_id="admin-wecom")

    safe = client.get("/login?next=/admin/jobs", follow_redirects=False)
    unsafe = client.get("/login?next=https://evil.example.com", follow_redirects=False)

    assert safe.status_code == 302
    assert safe.headers["location"] == "/admin/jobs"
    assert unsafe.status_code == 302
    assert unsafe.headers["location"] == "/admin"
