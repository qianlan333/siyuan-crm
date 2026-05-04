from __future__ import annotations

import json

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "admin-governance-phase6.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "MCP_BEARER_TOKEN": "mcp-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


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

    response = client.get(
        "/admin/audit?target_type=app_setting&sort_by=operator&sort_dir=asc&page=1&page_size=10&log_id=1"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "操作记录" in html
    assert "筛选条件" in html
    assert "复制当前筛选链接" in html
    assert "WECOM_SECRET" in html
    assert "tester-beta" in html
    assert "查看详情" in html


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


def test_admin_system_page_renders_runbooks_and_legacy_strategy(client):
    response = client.get("/admin/system")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "常用入口" in html
    assert "重要操作提醒" in html
    assert "/admin/audit" in html
    assert "/admin/user-ops/ui" not in html


def test_shell_topbar_renders_governance_links(client):
    response = client.get("/admin")
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
