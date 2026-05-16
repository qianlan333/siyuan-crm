from __future__ import annotations

import json

import pytest

from wecom_ability_service.db import get_db


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path, MCP_BEARER_TOKEN="mcp-token") as app:
        yield app


@pytest.fixture()
def client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["super_admin"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "test-admin"
        sess["admin_session_break_glass_username"] = "test-admin"
    return client


def _seed_audit_logs(app) -> None:
    with app.app_context():
        db = get_db()
        rows = [
            (
                "tester-beta",
                "update_setting",
                "app_setting",
                "WECOM_SECRET",
                json.dumps({"value": "***"}, ensure_ascii=False),
                json.dumps({"configured": True}, ensure_ascii=False),
                "2026-04-02 10:00:00",
            ),
            (
                "tester-alpha",
                "preview_mcp_sample_call",
                "mcp_sample_call",
                "create_private_message_task",
                json.dumps({"live_run": False}, ensure_ascii=False),
                json.dumps({"ok": True, "preview_only": True}, ensure_ascii=False),
                "2026-04-02 10:05:00",
            ),
            (
                "tester-gamma",
                "execute_mark",
                "customer_tag_action",
                "ext-1",
                json.dumps({"tags": []}, ensure_ascii=False),
                json.dumps({"tags": ["tag-1"]}, ensure_ascii=False),
                "2026-04-02 10:10:00",
            ),
            (
                "tester-jobs",
                "run_archive_sync",
                "jobs_console_action",
                "sync-88",
                json.dumps({"start_time": "2026-04-02 09:00:00"}, ensure_ascii=False),
                json.dumps({"status": "success"}, ensure_ascii=False),
                "2026-04-02 10:15:00",
            ),
        ]
        db.executemany(
            """
            INSERT INTO admin_operation_logs (
                operator, action_type, target_type, target_id, before_json, after_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        db.commit()


def test_admin_audit_page_renders_filters_pagination_and_detail(app, client):
    _seed_audit_logs(app)

    # /admin/audit is sunset (410)
    response = client.get(
        "/admin/audit?target_type=app_setting&sort_by=operator&sort_dir=asc&page=1&page_size=10&log_id=1"
    )
    assert response.status_code == 410


def test_api_admin_audit_logs_support_filters_sort_and_pagination(app, client):
    _seed_audit_logs(app)

    response = client.get(
        "/api/admin/audit/logs?target_type=app_setting&sort_by=operator&sort_dir=asc&page=1&page_size=10"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["audit"]["pagination"]["total"] == 1
    assert payload["audit"]["pagination"]["page_size"] == 10
    assert len(payload["audit"]["items"]) == 1
    assert payload["audit"]["items"][0]["operator"] == "tester-beta"


def test_api_admin_audit_logs_route_jobs_actions_back_to_jobs_console(app, client):
    _seed_audit_logs(app)

    response = client.get("/api/admin/audit/logs?target_type=jobs_console_action&page=1&page_size=10")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["audit"]["pagination"]["total"] == 1
    assert payload["audit"]["items"][0]["target_type"] == "jobs_console_action"
    assert payload["audit"]["items"][0]["target_href"] == "/admin/jobs"


def test_shell_topbar_renders_governance_links(client):
    response = client.get("/admin", follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MCP Preflight" not in html
    assert "Questionnaire Preflight" not in html
    assert "Runbooks" not in html


def test_admin_config_app_settings_api_requires_confirmation(client):
    response = client.put(
        "/api/admin/config/app-settings",
        json={
            "settings": {
                "WECOM_API_BASE": "https://qyapi.example.test",
            },
            "operator": "tester-governance",
        },
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "confirm is required before saving app settings"


def test_legacy_marketing_automation_admin_api_requires_login(app):
    client = app.test_client()

    response = client.get("/api/admin/marketing-automation/config")
    payload = response.get_json()

    assert response.status_code == 401
    assert payload == {"ok": False, "error": "admin login required"}


def test_legacy_marketing_automation_admin_api_uses_config_write_rbac(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["admin_session_user_id"] = 0
        sess["admin_session_wecom_userid"] = ""
        sess["admin_session_role_list"] = ["viewer"]
        sess["admin_session_login_type"] = "break_glass"
        sess["admin_session_display_name"] = "readonly-admin"
        sess["admin_session_break_glass_username"] = "readonly-admin"

    response = client.put("/api/admin/marketing-automation/config", json={"enabled": True})
    payload = response.get_json()

    assert response.status_code == 403
    assert payload == {"ok": False, "error": "permission denied"}
