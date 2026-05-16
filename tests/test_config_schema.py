from __future__ import annotations

import re

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.infra.config_schema import (
    CONFIG_SCHEMA,
    build_config_checklist,
    get_all_schema_keys,
    validate_config,
)


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(
        tmp_path,
        SECRET_KEY="test-secret-key",
        ADMIN_AUTH_MODE="wecom_sso",
    ) as application:
        yield application


@pytest.fixture()
def client(app):
    from wecom_ability_service.domains.admin_auth import save_admin_user
    with app.app_context():
        save_admin_user(
            {
                "wecom_userid": "root.admin",
                "wecom_corpid": app.config["WECOM_CORP_ID"],
                "display_name": "Root Admin",
                "role_codes": ["super_admin"],
                "is_active": "1",
            },
            operator="test-suite",
        )
    c = app.test_client()
    with c.session_transaction() as session:
        session["admin_session_user_id"] = 1
        session["admin_session_wecom_userid"] = "root.admin"
        session["admin_session_role_list"] = ["super_admin"]
        session["admin_session_login_type"] = "wecom_qr"
        session["admin_session_display_name"] = "Root Admin"
    return c


def _setup_action_token(client) -> str:
    response = client.get("/setup/wizard")
    html = response.get_data(as_text=True)
    match = re.search(r'name="admin_action_token" value="([^"]+)"', html)
    assert response.status_code == 200
    assert match
    return match.group(1)


def test_config_schema_has_required_groups():
    assert "wecom_base" in CONFIG_SCHEMA
    assert "wecom_callback" in CONFIG_SCHEMA
    assert CONFIG_SCHEMA["wecom_base"]["required"] is True


def test_validate_config_catches_missing_required():
    errors = validate_config({})
    required_keys = {e["key"] for e in errors}
    assert "WECOM_CORP_ID" in required_keys
    assert "WECOM_CALLBACK_TOKEN" in required_keys


def test_validate_config_passes_with_all_required():
    settings = {
        "WECOM_CORP_ID": "ww-test",
        "WECOM_SECRET": "secret",
        "WECOM_AGENT_ID": "1000",
        "WECOM_CONTACT_SECRET": "contact-secret",
        "WECOM_DEFAULT_OWNER_USERID": "admin",
        "WECOM_CALLBACK_TOKEN": "token",
        "WECOM_CALLBACK_AES_KEY": "key",
    }
    errors = validate_config(settings)
    assert len(errors) == 0


def test_validate_config_catches_bad_integer():
    errors = validate_config({
        "WECOM_CORP_ID": "ww-test",
        "WECOM_SECRET": "s",
        "WECOM_AGENT_ID": "1000",
        "WECOM_CONTACT_SECRET": "cs",
        "WECOM_DEFAULT_OWNER_USERID": "a",
        "WECOM_CALLBACK_TOKEN": "t",
        "WECOM_CALLBACK_AES_KEY": "k",
        "WECOM_ARCHIVE_TIMEOUT": "not-a-number",
    })
    int_errors = [e for e in errors if e["key"] == "WECOM_ARCHIVE_TIMEOUT"]
    assert len(int_errors) == 1
    assert "整数" in int_errors[0]["error"]


def test_build_config_checklist():
    settings = {"WECOM_CORP_ID": "ww-test"}
    checklist = build_config_checklist(settings)
    assert len(checklist) > 0
    base_group = next(g for g in checklist if g["group_key"] == "wecom_base")
    assert base_group["complete"] is False
    corp_field = next(f for f in base_group["fields"] if f["key"] == "WECOM_CORP_ID")
    assert corp_field["configured"] is True


def test_get_all_schema_keys():
    keys = get_all_schema_keys()
    assert "WECOM_CORP_ID" in keys
    assert "REDIS_URL" in keys
    assert len(keys) > 20


def test_setup_wizard_page_renders(client):
    resp = client.get("/setup/wizard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "企业微信基础配置" in html
    assert "企业ID" in html


def test_setup_wizard_requires_admin_login(app):
    anonymous = app.test_client()
    resp = anonymous.get("/setup/wizard")
    save_resp = anonymous.post("/setup/wizard/save", data={})

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert save_resp.status_code == 302
    assert "/login" in save_resp.headers["Location"]


def test_config_checklist_page_renders(client):
    resp = client.get("/admin/config/checklist")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "配置检查清单" in html


def test_setup_wizard_save_persists_settings(client, app):
    action_token = _setup_action_token(client)
    resp = client.post("/setup/wizard/save", data={
        "admin_action_token": action_token,
        "setting__WECOM_CORP_ID": "ww-new-corp",
        "setting__WECOM_SECRET": "new-secret",
        "setting__WECOM_AGENT_ID": "2000",
        "setting__WECOM_CONTACT_SECRET": "new-contact-secret",
        "setting__WECOM_DEFAULT_OWNER_USERID": "admin01",
        "setting__WECOM_CALLBACK_TOKEN": "new-token",
        "setting__WECOM_CALLBACK_AES_KEY": "new-aes-key",
        "operator": "test-operator",
    })
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "配置已保存成功" in html

    with app.app_context():
        from wecom_ability_service.infra.settings import get_setting
        assert get_setting("WECOM_CORP_ID") == "ww-new-corp"
        assert get_setting("WECOM_AGENT_ID") == "2000"
        audit = get_db().execute(
            """
            SELECT operator
            FROM admin_operation_logs
            WHERE target_type = 'app_setting' AND target_id = 'WECOM_CORP_ID'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert audit["operator"] == "test-operator"


def test_setup_wizard_save_skips_empty_secrets(client, app):
    with app.app_context():
        from wecom_ability_service.infra.settings import set_settings
        set_settings({"WECOM_SECRET": "original-secret"})

    action_token = _setup_action_token(client)
    resp = client.post("/setup/wizard/save", data={
        "admin_action_token": action_token,
        "setting__WECOM_CORP_ID": "ww-test",
        "setting__WECOM_SECRET": "",
        "setting__WECOM_AGENT_ID": "1000",
        "setting__WECOM_CONTACT_SECRET": "cs",
        "setting__WECOM_DEFAULT_OWNER_USERID": "admin",
        "setting__WECOM_CALLBACK_TOKEN": "t",
        "setting__WECOM_CALLBACK_AES_KEY": "k",
        "operator": "test",
    })
    assert resp.status_code == 200

    with app.app_context():
        from wecom_ability_service.infra.settings import get_setting
        assert get_setting("WECOM_SECRET") == "original-secret"
