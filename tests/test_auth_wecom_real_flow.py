from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from aicrm_next.admin_auth.service import SESSION_COOKIE, verify_session
from aicrm_next.auth_wecom.service import verify_auth_state
from aicrm_next.main import create_app
from aicrm_next.shared.db_session import reset_engine_cache_for_tests


class FakeWeComAdminAuthClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fetch_access_token(self, *, corp_id: str, corp_secret: str) -> dict:
        self.calls.append({"method": "fetch_access_token", "corp_id": corp_id, "corp_secret": corp_secret})
        return {"errcode": 0, "access_token": "token_for_test"}

    def fetch_user_info(self, *, access_token: str, code: str) -> dict:
        self.calls.append({"method": "fetch_user_info", "access_token": access_token, "code": code})
        return {"errcode": 0, "UserId": "HuangYouCan"}


def _prepare_client(monkeypatch, tmp_path, *, real_auth_env: str = "explicit_gate") -> tuple[TestClient, FakeWeComAdminAuthClient]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'wecom_auth.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "wecom-admin-auth-test-secret")
    monkeypatch.delenv("AICRM_WECOM_ADMIN_AUTH_ENABLE_REAL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_WECOM_ADMIN_AUTH_MODE", raising=False)
    if real_auth_env == "mode_live":
        monkeypatch.setenv("AICRM_NEXT_WECOM_ADMIN_AUTH_MODE", "live")
    else:
        monkeypatch.setenv("AICRM_WECOM_ADMIN_AUTH_ENABLE_REAL", "true")
    monkeypatch.setenv("WECOM_CORP_ID", "ww-test-corp")
    monkeypatch.setenv("WECOM_AGENT_ID", "1000023")
    monkeypatch.setenv("WECOM_SECRET", "secret_for_test")
    monkeypatch.setenv("ADMIN_LOGIN_REDIRECT_URI", "https://crm.example.test/auth/wecom/callback")
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
        conn.execute(
            text(
                """
                CREATE TABLE admin_login_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER,
                    login_type TEXT NOT NULL DEFAULT '',
                    login_result TEXT NOT NULL DEFAULT '',
                    ip TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        user_id = conn.execute(
            text(
                """
                INSERT INTO admin_users (
                    wecom_userid, wecom_corpid, display_name, is_active, auth_source, login_enabled, admin_level
                )
                VALUES ('HuangYouCan', 'ww-test-corp', '黄有璨', TRUE, 'wecom_sso', TRUE, 'super_admin')
                RETURNING id
                """
            )
        ).scalar_one()
        conn.execute(
            text("INSERT INTO admin_user_roles (admin_user_id, role_code) VALUES (:id, 'super_admin')"),
            {"id": user_id},
        )

    fake_client = FakeWeComAdminAuthClient()
    monkeypatch.setattr("aicrm_next.auth_wecom.service.build_wecom_admin_auth_client", lambda: fake_client)
    return TestClient(create_app(), raise_server_exceptions=False), fake_client


def test_html_start_redirects_to_login_error_when_real_wecom_auth_is_disabled(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_WECOM_ADMIN_AUTH_ENABLE_REAL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_WECOM_ADMIN_AUTH_MODE", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")

    response = TestClient(create_app(), raise_server_exceptions=False).get(
        "/auth/wecom/start?mode=qr&next=/admin/automation-conversion",
        headers={"accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert (
        response.headers["location"]
        == "/login?next=%2Fadmin%2Fautomation-conversion&auth_error=wecom_admin_auth_not_enabled"
    )


def test_real_wecom_auth_start_accepts_live_mode_env(monkeypatch, tmp_path) -> None:
    client, _ = _prepare_client(monkeypatch, tmp_path, real_auth_env="mode_live")

    response = client.get("/auth/wecom/start?mode=qr&next=/admin/automation-conversion", follow_redirects=False)
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)

    assert response.status_code == 302
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
    assert params["appid"] == ["ww-test-corp"]
    assert params["agentid"] == ["1000023"]


def test_real_wecom_auth_start_and_callback_signs_admin_session(monkeypatch, tmp_path) -> None:
    client, fake_client = _prepare_client(monkeypatch, tmp_path)

    start = client.get("/auth/wecom/start?mode=qr&next=/admin/automation-conversion", follow_redirects=False)
    assert start.status_code == 302
    location = start.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)

    assert (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        == "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
    )
    assert params["appid"] == ["ww-test-corp"]
    assert params["agentid"] == ["1000023"]
    assert params["redirect_uri"] == ["https://crm.example.test/auth/wecom/callback"]
    assert verify_auth_state(params["state"][0])["next"] == "/admin/automation-conversion"

    callback = client.get(f"/auth/wecom/callback?code=code-from-wecom&state={params['state'][0]}", follow_redirects=False)

    assert callback.status_code == 302
    assert callback.headers["location"] == "/admin/automation-conversion"
    assert SESSION_COOKIE in callback.headers["set-cookie"]
    assert fake_client.calls == [
        {"method": "fetch_access_token", "corp_id": "ww-test-corp", "corp_secret": "secret_for_test"},
        {"method": "fetch_user_info", "access_token": "token_for_test", "code": "code-from-wecom"},
    ]

    cookie_value = callback.headers["set-cookie"].split(f"{SESSION_COOKIE}=", 1)[1].split(";", 1)[0]
    session = verify_session(cookie_value)
    assert session["login_type"] == "wecom_sso"
    assert session["wecom_userid"] == "HuangYouCan"
    assert session["roles"] == ["super_admin"]
