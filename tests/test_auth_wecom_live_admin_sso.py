from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from aicrm_next.admin_auth.service import SESSION_COOKIE, verify_session
from aicrm_next.auth_wecom.service import (
    WeComAdminAuthError,
    WeComAdminIdentity,
    set_wecom_admin_auth_adapter_for_tests,
)
from aicrm_next.shared.db_session import reset_engine_cache_for_tests
from aicrm_next.main import create_app


class FakeWeComAdminAuthAdapter:
    def __init__(self, *, userid: str = "root.admin", display_name: str = "Root Admin", error: bool = False) -> None:
        self.userid = userid
        self.display_name = display_name
        self.error = error
        self.calls: list[str] = []

    def exchange_code(self, code: str) -> WeComAdminIdentity:
        self.calls.append(code)
        if self.error:
            raise WeComAdminAuthError("fake adapter error", status_code=502)
        return WeComAdminIdentity(wecom_userid=self.userid, display_name=self.display_name, wecom_corpid="ww-test-corp")


@pytest.fixture()
def next_auth_client(monkeypatch, tmp_path):
    db_path = tmp_path / "auth_wecom_next.sqlite3"
    database_url = f"sqlite+pysqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AICRM_NEXT_WECOM_ADMIN_AUTH_MODE", "live")
    monkeypatch.setenv("AICRM_NEXT_ADMIN_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("SECRET_KEY", "auth-wecom-live-test")
    monkeypatch.setenv("WECOM_CORP_ID", "ww-test-corp")
    monkeypatch.setenv("WECOM_AGENT_ID", "1000002")
    monkeypatch.setenv("WECOM_SECRET", "test-secret-not-real")
    monkeypatch.setenv("ADMIN_LOGIN_REDIRECT_URI", "https://www.example.test/auth/wecom/callback")
    reset_engine_cache_for_tests()
    engine = create_engine(database_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wecom_userid TEXT NOT NULL,
                    wecom_corpid TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    auth_source TEXT NOT NULL DEFAULT 'wecom_sso',
                    last_login_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT NOT NULL DEFAULT '',
                    login_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    admin_level TEXT NOT NULL DEFAULT 'admin'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE admin_user_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER NOT NULL,
                    role_code TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(admin_user_id, role_code)
                )
                """
            )
        )
    try:
        yield TestClient(create_app()), engine
    finally:
        set_wecom_admin_auth_adapter_for_tests(None)
        reset_engine_cache_for_tests()


def _state_from_location(location: str) -> str:
    return parse_qs(urlparse(location).query).get("state", [""])[0]


def _insert_admin(engine, *, userid: str = "root.admin", active: bool = True, login_enabled: bool = True) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO admin_users (wecom_userid, wecom_corpid, display_name, is_active, login_enabled, admin_level, auth_source)
                VALUES (:userid, 'ww-test-corp', 'Root Admin', :active, :login_enabled, 'super_admin', 'wecom_sso')
                """
            ),
            {"userid": userid, "active": active, "login_enabled": login_enabled},
        )
        admin_user_id = int(result.lastrowid)
        conn.execute(
            text("INSERT INTO admin_user_roles (admin_user_id, role_code) VALUES (:id, 'super_admin')"),
            {"id": admin_user_id},
        )
        return admin_user_id


def test_auth_wecom_callback_dummy_invalid_state_is_400(next_auth_client) -> None:
    client, _ = next_auth_client

    response = client.get("/auth/wecom/callback?code=dummy-code&state=dummy-state")
    payload = response.json()

    assert response.status_code == 400
    assert payload["error_code"] == "invalid_or_expired_state"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert "external_call_blocked" not in str(payload)


def test_auth_wecom_start_blocked_mode_controlled_response(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_WECOM_ADMIN_AUTH_MODE", "blocked")
    client = TestClient(create_app())

    response = client.get("/auth/wecom/start?mode=qr&next=/admin")

    assert response.status_code == 503
    assert response.json()["error_code"] == "auth_wecom_blocked"


def test_auth_wecom_start_live_redirects_to_authorize_url(next_auth_client) -> None:
    client, _ = next_auth_client

    response = client.get("/auth/wecom/start?mode=qr&next=/admin/config", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("https://open.work.weixin.qq.com/wwopen/sso/qrConnect")
    assert "ww-test-corp" in location
    assert "test-secret" not in location
    assert _state_from_location(location)


def test_auth_wecom_start_live_rejects_open_redirect(next_auth_client) -> None:
    client, engine = next_auth_client
    _insert_admin(engine, userid="root.admin")
    set_wecom_admin_auth_adapter_for_tests(FakeWeComAdminAuthAdapter(userid="root.admin"))

    response = client.get("/auth/wecom/start?mode=oauth&next=https://evil.example/path", follow_redirects=False)
    state = _state_from_location(response.headers["Location"])
    callback = client.get(f"/auth/wecom/callback?code=mock-code&state={state}", follow_redirects=False)

    assert callback.status_code == 302
    assert callback.headers["Location"] == "/admin"


def test_auth_wecom_callback_live_success_sets_next_admin_session_cookie(next_auth_client) -> None:
    client, engine = next_auth_client
    _insert_admin(engine, userid="root.admin")
    adapter = FakeWeComAdminAuthAdapter(userid="root.admin")
    set_wecom_admin_auth_adapter_for_tests(adapter)
    start = client.get("/auth/wecom/start?mode=qr&next=/admin/config", follow_redirects=False)
    state = _state_from_location(start.headers["Location"])

    response = client.get(f"/auth/wecom/callback?code=mock-code&state={state}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/config"
    assert SESSION_COOKIE in response.headers["set-cookie"]
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert adapter.calls == ["mock-code"]
    cookie_value = response.headers["set-cookie"].split(f"{SESSION_COOKIE}=", 1)[1].split(";", 1)[0]
    payload = verify_session(cookie_value)
    assert payload
    assert payload["wecom_userid"] == "root.admin"
    assert payload["roles"] == ["super_admin"]


def test_auth_wecom_callback_live_unknown_admin_denied(next_auth_client) -> None:
    client, _ = next_auth_client
    set_wecom_admin_auth_adapter_for_tests(FakeWeComAdminAuthAdapter(userid="unknown.admin"))
    start = client.get("/auth/wecom/start?mode=qr&next=/admin", follow_redirects=False)
    state = _state_from_location(start.headers["Location"])

    response = client.get(f"/auth/wecom/callback?code=mock-code&state={state}")

    assert response.status_code == 403
    assert response.json()["error_code"] == "admin_login_denied"


def test_auth_wecom_callback_live_disabled_admin_denied(next_auth_client) -> None:
    client, engine = next_auth_client
    _insert_admin(engine, userid="disabled.admin", active=False, login_enabled=True)
    set_wecom_admin_auth_adapter_for_tests(FakeWeComAdminAuthAdapter(userid="disabled.admin"))
    start = client.get("/auth/wecom/start?mode=qr&next=/admin", follow_redirects=False)
    state = _state_from_location(start.headers["Location"])

    response = client.get(f"/auth/wecom/callback?code=mock-code&state={state}")

    assert response.status_code == 403
    assert response.json()["error_code"] == "admin_login_denied"


def test_auth_wecom_callback_live_adapter_error_is_redacted(next_auth_client) -> None:
    client, engine = next_auth_client
    _insert_admin(engine, userid="root.admin")
    set_wecom_admin_auth_adapter_for_tests(FakeWeComAdminAuthAdapter(error=True))
    start = client.get("/auth/wecom/start?mode=qr&next=/admin", follow_redirects=False)
    state = _state_from_location(start.headers["Location"])

    response = client.get(f"/auth/wecom/callback?code=super-secret-code&state={state}")
    payload = response.json()

    assert response.status_code == 502
    assert payload["error_code"] == "wecom_code_exchange_failed"
    assert "super-secret-code" not in str(payload)


def test_auth_wecom_options_keep_diagnostics(next_auth_client) -> None:
    client, _ = next_auth_client

    for path in ["/auth/wecom/start", "/auth/wecom/callback"]:
        response = client.options(path)
        payload = response.json()
        assert response.status_code == 200
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
