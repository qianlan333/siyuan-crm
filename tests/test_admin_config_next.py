from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from aicrm_next.main import create_app
from aicrm_next.shared.db_session import reset_engine_cache_for_tests


ROOT = Path(__file__).resolve().parents[1]


def _prepare_client(monkeypatch, tmp_path) -> TestClient:
    db_path = tmp_path / "admin_config_next.sqlite3"
    database_url = f"sqlite+pysqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "admin-config-next-test")
    monkeypatch.setenv("WECOM_CORP_ID", "ww-env-corp")
    reset_engine_cache_for_tests()
    engine = create_engine(database_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE admin_operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator TEXT NOT NULL DEFAULT '',
                    action_type TEXT NOT NULL DEFAULT '',
                    target_type TEXT NOT NULL DEFAULT '',
                    target_id TEXT NOT NULL DEFAULT '',
                    before_json TEXT NOT NULL DEFAULT '{}',
                    after_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
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
        conn.execute(
            text(
                """
                CREATE TABLE mcp_tool_settings (
                    tool_name TEXT PRIMARY KEY,
                    tool_group TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    description_override TEXT NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    visible_in_console BOOLEAN NOT NULL DEFAULT TRUE,
                    show_sample_args BOOLEAN NOT NULL DEFAULT FALSE,
                    show_sample_output BOOLEAN NOT NULL DEFAULT FALSE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE questionnaires (
                    id INTEGER PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    is_disabled BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE questionnaire_questions (
                    id INTEGER PRIMARY KEY,
                    questionnaire_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    required BOOLEAN NOT NULL DEFAULT FALSE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE questionnaire_options (
                    id INTEGER PRIMARY KEY,
                    question_id INTEGER NOT NULL,
                    option_text TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE marketing_automation_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    automation_key TEXT NOT NULL UNIQUE,
                    automation_name TEXT NOT NULL DEFAULT '',
                    target_event TEXT NOT NULL DEFAULT 'signup_success',
                    channel_type TEXT NOT NULL DEFAULT 'text_message',
                    status TEXT NOT NULL DEFAULT 'active',
                    do_not_start_after_hour INTEGER NOT NULL DEFAULT 23,
                    config_payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE marketing_automation_question_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    automation_config_id INTEGER NOT NULL,
                    questionnaire_id INTEGER,
                    question_id INTEGER,
                    rule_code TEXT NOT NULL DEFAULT '',
                    rule_name TEXT NOT NULL DEFAULT '',
                    answer_match_type TEXT NOT NULL DEFAULT 'any_of',
                    answer_match_value_json TEXT NOT NULL DEFAULT '[]',
                    score_delta INTEGER NOT NULL DEFAULT 0,
                    segment_hint TEXT NOT NULL DEFAULT '',
                    stage_hint TEXT NOT NULL DEFAULT '',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    rule_payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("INSERT INTO app_settings (key, value) VALUES ('WECOM_SECRET', 'super-secret-value')"))
        conn.execute(text("INSERT INTO questionnaires (id, slug, name, title) VALUES (81, 'signup-test', '报名问卷', '报名问卷')"))
        conn.execute(
            text(
                """
                INSERT INTO questionnaire_questions (id, questionnaire_id, type, title, required, sort_order)
                VALUES
                    (811, 81, 'single_choice', '你想咨询什么课程？', TRUE, 1),
                    (812, 81, 'multi_choice', '你关注哪些服务？', FALSE, 2)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO questionnaire_options (id, question_id, option_text, sort_order)
                VALUES
                    (8111, 811, 'AI 课程', 1),
                    (8112, 811, '私域运营', 2),
                    (8121, 812, '训练营', 1)
                """
            )
        )
    return TestClient(create_app(), raise_server_exceptions=False)


def _token(html: str) -> str:
    match = re.search(r'name="admin_action_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


def _db_url(monkeypatch) -> str:
    return str(__import__("os").environ["DATABASE_URL"])


def _scalar(database_url: str, sql: str, params: dict | None = None):
    engine = create_engine(database_url, future=True)
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


def test_admin_config_pages_are_next_owned_and_nonblank(monkeypatch, tmp_path) -> None:
    client = _prepare_client(monkeypatch, tmp_path)

    for path, marker in [
        ("/admin/config", "配置中心"),
        ("/admin/config/app-settings", "系统设置"),
        ("/admin/config/login-access", "登录与权限"),
        ("/admin/config/checklist", "配置检查清单"),
        ("/setup/wizard", "系统配置向导"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert marker in response.text
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        assert "X-AICRM-Compatibility-Facade" not in response.text

    wecom_tags_alias = client.get("/admin/config/wecom-tags", follow_redirects=False)
    assert wecom_tags_alias.status_code == 302
    assert wecom_tags_alias.headers["location"] == "/admin/wecom-tags"
    assert "X-AICRM-Compatibility-Facade" not in wecom_tags_alias.headers


def test_app_settings_api_masks_secrets_and_save_is_idempotent(monkeypatch, tmp_path) -> None:
    client = _prepare_client(monkeypatch, tmp_path)
    token = _token(client.get("/admin/config/app-settings").text)

    masked_response = client.get("/api/admin/config/app-settings")
    assert masked_response.status_code == 200
    text_payload = masked_response.text
    assert "super-secret-value" not in text_payload
    assert "sup***ue" in text_payload

    save_payload = {
        "admin_action_token": token,
        "confirm": True,
        "operator": "next-test",
        "settings": {"WECOM_CORP_ID": "ww-next-corp", "WECOM_SECRET": ""},
    }
    first = client.put("/api/admin/config/app-settings", json=save_payload)
    second = client.put("/api/admin/config/app-settings", json=save_payload)

    assert first.status_code == 200
    assert first.json()["source_status"] == "next_command"
    assert first.json()["fallback_used"] is False
    assert first.json()["real_external_call_executed"] is False
    assert first.json()["changed_count"] == 1
    assert second.status_code == 200
    assert second.json()["changed_count"] == 0
    database_url = _db_url(monkeypatch)
    assert _scalar(database_url, "SELECT value FROM app_settings WHERE key = 'WECOM_CORP_ID'") == "ww-next-corp"
    assert _scalar(database_url, "SELECT value FROM app_settings WHERE key = 'WECOM_SECRET'") == "super-secret-value"
    assert _scalar(database_url, "SELECT COUNT(*) FROM admin_operation_logs WHERE target_type = 'app_setting' AND target_id = 'WECOM_CORP_ID'") == 1


def test_app_settings_save_requires_clear_token_and_confirm_errors(monkeypatch, tmp_path) -> None:
    client = _prepare_client(monkeypatch, tmp_path)

    missing_token = client.put("/api/admin/config/app-settings", json={"confirm": True, "settings": {"WECOM_CORP_ID": "ww"}})
    missing_confirm = client.put(
        "/api/admin/config/app-settings",
        json={"admin_action_token": _token(client.get("/admin/config/app-settings").text), "settings": {"WECOM_CORP_ID": "ww"}},
    )

    assert missing_token.status_code == 400
    assert "admin_action_token" in missing_token.json()["error"]
    assert missing_confirm.status_code == 400
    assert "confirm is required" in missing_confirm.json()["error"]


def test_setup_wizard_saves_and_repeated_submit_is_noop(monkeypatch, tmp_path) -> None:
    client = _prepare_client(monkeypatch, tmp_path)
    token = _token(client.get("/setup/wizard").text)
    payload = {
        "admin_action_token": token,
        "operator": "wizard-test",
        "setting__WECOM_CORP_ID": "ww-wizard",
        "setting__WECOM_SECRET": "",
        "setting__WECOM_AGENT_ID": "1000",
        "setting__WECOM_CONTACT_SECRET": "contact",
        "setting__WECOM_DEFAULT_OWNER_USERID": "owner",
        "setting__WECOM_CALLBACK_TOKEN": "callback",
        "setting__WECOM_CALLBACK_AES_KEY": "aes",
    }

    first = client.post("/setup/wizard/save", data=payload)
    second = client.post("/setup/wizard/save", data=payload)

    assert first.status_code == 200
    assert "配置已保存成功" in first.text
    assert second.status_code == 200
    assert "配置已保存成功" in second.text
    database_url = _db_url(monkeypatch)
    assert _scalar(database_url, "SELECT value FROM app_settings WHERE key = 'WECOM_AGENT_ID'") == "1000"
    assert _scalar(database_url, "SELECT COUNT(*) FROM admin_operation_logs WHERE target_type = 'app_setting' AND target_id = 'WECOM_AGENT_ID'") == 1


def test_login_access_save_and_directory_refresh_do_not_call_wecom(monkeypatch, tmp_path) -> None:
    client = _prepare_client(monkeypatch, tmp_path)
    token = _token(client.get("/admin/config/login-access").text)

    refresh = client.post("/admin/config/login-access/directory/refresh", data={"admin_action_token": token}, follow_redirects=False)
    save = client.post(
        "/admin/config/login-access/save",
        data={
            "admin_action_token": token,
            "wecom_userid": "root.admin",
            "wecom_corpid": "ww-next-corp",
            "display_name": "Root Admin",
            "auth_source": "wecom_sso",
            "is_active": "1",
            "login_enabled": "1",
            "admin_level": "admin",
            "role_codes": ["config_admin", "viewer"],
            "operator": "access-test",
        },
        follow_redirects=False,
    )

    assert refresh.status_code == 302
    assert "real_external" not in refresh.headers.get("location", "")
    assert save.status_code == 302
    database_url = _db_url(monkeypatch)
    assert _scalar(database_url, "SELECT COUNT(*) FROM admin_users WHERE wecom_userid = 'root.admin'") == 1
    assert _scalar(database_url, "SELECT COUNT(*) FROM admin_user_roles WHERE role_code = 'config_admin'") == 1
    assert _scalar(database_url, "SELECT COUNT(*) FROM admin_operation_logs WHERE target_type = 'admin_user'") == 1


def test_mcp_tool_settings_api_is_next_owned_and_audited(monkeypatch, tmp_path) -> None:
    client = _prepare_client(monkeypatch, tmp_path)

    page = client.get("/admin/config/mcp-tools", follow_redirects=False)
    before = client.get("/api/admin/config/mcp-tools")
    save = client.post(
        "/api/admin/config/mcp-tools",
        json={
            "tool_name": "resolve_customer",
            "tool_group": "crm",
            "display_name": "Resolve Customer",
            "description_override": "disabled for test",
            "enabled": False,
            "visible_in_console": True,
            "show_sample_args": False,
            "show_sample_output": False,
            "sort_order": 99,
            "operator": "mcp-test",
        },
    )
    after = client.get("/api/admin/config/mcp-tools")

    assert page.status_code == 302
    assert page.headers["location"] == "/admin/api-docs"
    assert before.status_code == 200
    assert before.json()["source_status"] == "next_read_model"
    assert "resolve_customer" in {row["tool_name"] for row in before.json()["config"]["rows"]}
    assert save.status_code == 200
    assert save.json()["source_status"] == "next_command"
    assert save.json()["fallback_used"] is False
    assert save.json()["real_external_call_executed"] is False
    assert save.json()["item"]["enabled"] is False
    resolve_row = next(row for row in after.json()["config"]["rows"] if row["tool_name"] == "resolve_customer")
    assert resolve_row["enabled"] is False
    assert resolve_row["description_override"] == "disabled for test"
    database_url = _db_url(monkeypatch)
    assert _scalar(database_url, "SELECT COUNT(*) FROM mcp_tool_settings WHERE tool_name = 'resolve_customer' AND enabled = 0") == 1
    assert _scalar(database_url, "SELECT COUNT(*) FROM admin_operation_logs WHERE target_type = 'mcp_tool_setting' AND target_id = 'resolve_customer'") == 1


def test_signup_conversion_config_alias_is_next_owned_and_audited(monkeypatch, tmp_path) -> None:
    client = _prepare_client(monkeypatch, tmp_path)

    initial = client.get("/api/admin/config/marketing-automation/signup-conversion")
    assert initial.status_code == 200
    assert initial.json()["config"]["configured"] is False
    assert initial.json()["source_status"] == "next_read_model"
    assert "X-AICRM-Compatibility-Facade" not in initial.headers

    payload = {
        "operator": "marketing-config-test",
        "enabled": True,
        "questionnaire_id": 81,
        "core_threshold": 2,
        "top_threshold": 5,
        "day_start_hour": 8,
        "quiet_hour_start": 22,
        "timezone": "Asia/Shanghai",
        "silent_threshold_days_by_pool": {
            "new_user": 3,
            "inactive_normal": 4,
            "inactive_focus": 5,
            "active_normal": 6,
            "active_focus": 7,
        },
        "question_rules": [
            {"questionnaire_question_id": 811, "hit_option_ids_json": [8111, 8112], "sort_order": 1},
            {"questionnaire_question_id": 812, "hit_option_ids_json": [8121], "sort_order": 2},
        ],
    }
    saved = client.put("/api/admin/config/marketing-automation/signup-conversion", json=payload)
    loaded = client.get("/api/admin/config/marketing-automation/signup-conversion")

    assert saved.status_code == 200
    assert saved.json()["source_status"] == "next_command"
    assert saved.json()["fallback_used"] is False
    assert saved.json()["real_external_call_executed"] is False
    assert saved.json()["config"]["configured"] is True
    assert saved.json()["config"]["questionnaire_id"] == 81
    assert saved.json()["config"]["core_threshold"] == 2
    assert saved.json()["config"]["top_threshold"] == 5
    assert saved.json()["config"]["question_rules"][0]["question_title"] == "你想咨询什么课程？"
    assert loaded.json()["config"]["silent_threshold_days_by_pool"]["inactive_focus"] == 5
    database_url = _db_url(monkeypatch)
    assert _scalar(database_url, "SELECT COUNT(*) FROM marketing_automation_configs WHERE automation_key = 'signup_conversion_v1'") == 1
    assert _scalar(database_url, "SELECT COUNT(*) FROM marketing_automation_question_rules WHERE automation_config_id = 1") == 2
    assert (
        _scalar(
            database_url,
            "SELECT COUNT(*) FROM admin_operation_logs WHERE target_type = 'marketing_automation_config' AND target_id = 'signup_conversion_v1'",
        )
        == 1
    )


def test_admin_config_routes_no_longer_forward_to_legacy_facade() -> None:
    source = (ROOT / "aicrm_next/frontend_compat/legacy_routes.py").read_text(encoding="utf-8")
    assert "admin_config_legacy_facade" not in source
    assert '"/admin/config"' not in source
    admin_config_source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "aicrm_next/admin_config").glob("*.py"))
    assert "legacy_flask_facade" not in admin_config_source
    assert "forward_to_legacy_flask" not in admin_config_source
    assert "wecom_ability_service" not in admin_config_source
