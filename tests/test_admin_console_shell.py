from __future__ import annotations

import pytest

from wecom_ability_service.db import get_db


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
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


def _seed_dashboard_data(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, updated_at)
            VALUES
                ('ext-1', '客户一', 'owner-a', '2026-04-01 10:00:00'),
                ('ext-2', '客户二', 'owner-b', '2026-04-02 09:30:00')
            """
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
            )
            VALUES
                (1, 'msg-1', 'private', 'ext-1', 'owner-a', 'owner-a', 'ext-1', 'text', 'hello', '2026-04-01 08:00:00', '{}'),
                (2, 'msg-2', 'private', 'ext-3', 'owner-c', 'owner-c', 'ext-3', 'text', 'world', '2026-04-01 08:05:00', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO group_chats (chat_id, group_name, owner_userid, member_count, status, updated_at)
            VALUES ('group-1', '测试群', 'owner-a', 3, 'active', '2026-04-02 08:00:00')
            """
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot
            )
            VALUES ('ext-3', 'signed', '已报名', '客户三', 'owner-c')
            """
        )
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (1, 'q-1', '问卷一', '问卷一标题', 'desc', false, '', '2026-04-01 09:00:00', '2026-04-02 09:00:00')
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, external_userid, follow_user_userid, matched_by,
                total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (1, 'r-1', 'ext-1', 'owner-a', 'openid', 88, '[]', '', '2026-04-02 10:30:00')
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_scrm_apply_logs (
                submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
            )
            VALUES (1, 'ext-1', 'owner-a', '[]', 'failed', 'tag apply failed', '2026-04-02 10:31:00')
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
                huangxiaocan_activation_state, class_term_no, class_term_label
            )
            VALUES
                ('13800000001', 'ext-1', '客户一', 'owner-a', true, true, 'activated', 1, '一班'),
                ('13800000002', 'ext-4', '客户四', 'owner-d', false, false, 'not_activated', 2, '二班')
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status, attempt_count, payload_json, result_json
            )
            VALUES
                ('sync_tags', 'ext-1', 'owner-a', '2026-04-02 11:00:00', 'pending', 0, '{}', '{}'),
                ('sync_tags', 'ext-4', 'owner-d', '2026-04-02 11:05:00', 'failed', 2, '{}', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO message_batches (
                batch_key, window_start, window_end, status, message_count, created_at
            )
            VALUES ('batch-1', '2026-04-02 10:00:00', '2026-04-02 10:02:59', 'pending', 6, '2026-04-02 10:03:00')
            """
        )
        db.execute(
            """
            INSERT INTO sync_runs (
                status, start_time, end_time, owner_userid, cursor, fetched_count, inserted_count,
                raw_response, error_message, created_at, finished_at
            )
            VALUES
                ('failed', '2026-04-01 09:00:00', '2026-04-01 09:10:00', 'owner-a', '', 20, 10, '{}', 'sync failed once', '2026-04-01 09:00:00', '2026-04-01 09:10:00'),
                ('success', '2026-04-02 09:00:00', '2026-04-02 09:10:00', 'owner-a', '', 30, 30, '{}', '', '2026-04-02 09:00:00', '2026-04-02 09:10:00')
            """
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_event_logs (
                corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
                payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
            )
            VALUES (
                'ww-test', 'change_external_contact', 'update_by_user', 'ext-1', 'owner-a', 1712023200, 'event-1',
                '<xml></xml>', '{}', 'failed', 1, 'callback failed', '2026-04-02 10:20:00', '2026-04-02 10:21:00'
            )
            """
        )
        db.commit()


def test_admin_console_home_renders_navigation_and_status_chips(client):
    response = client.get("/admin")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/automation-conversion")


def test_admin_dashboard_shell_context_api_returns_shell_status(client):
    response = client.get("/api/admin/dashboard/shell-context")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["shell_status"]["environment"]["label"] in {"DEV", "STAGING", "PROD"}
    assert "release_sha" in payload["shell_status"]
    assert "health" in payload["shell_status"]
    assert isinstance(payload["dashboard_cards"], list)


def test_admin_dashboard_apis_return_aggregated_metrics_and_todos(app, client):
    _seed_dashboard_data(app)

    system_response = client.get("/api/admin/dashboard/system-status")
    summary_response = client.get("/api/admin/dashboard/summary")
    todos_response = client.get("/api/admin/dashboard/todos")

    system_payload = system_response.get_json()
    summary_payload = summary_response.get_json()
    todos_payload = todos_response.get_json()

    assert system_response.status_code == 200
    assert system_payload["ok"] is True
    assert system_payload["system_status"]["database_backend"] == "postgres"
    assert system_payload["system_status"]["release_sha"] == "release-test"
    assert system_payload["system_status"]["callback_enabled"] is True
    assert system_payload["system_status"]["last_archive_sync"]["status"] == "success"
    assert system_payload["system_status"]["deferred_counts"]["pending_count"] == 1
    deferred_card = next(card for card in system_payload["system_status"]["cards"] if card["key"] == "deferred_jobs")
    assert deferred_card["value"] == 2
    assert system_payload["system_status"]["last_contacts_sync_time"] == "2026-04-02 09:30:00"

    assert summary_response.status_code == 200
    assert summary_payload["ok"] is True
    assert summary_payload["summary"]["archived_messages_total"] == 2
    assert summary_payload["summary"]["contacts_total"] == 2
    assert summary_payload["summary"]["group_chats_total"] == 1
    assert summary_payload["summary"]["customers_total"] == 3
    assert summary_payload["summary"]["questionnaire_total"] == 1
    assert summary_payload["summary"]["questionnaire_latest_submission"] == "2026-04-02 10:30:00"
    assert summary_payload["summary"]["user_ops_lead_pool_total"] == 2
    assert summary_payload["summary"]["class_user_current_total"] == 1

    assert todos_response.status_code == 200
    assert todos_payload["ok"] is True
    groups = {item["key"]: item for item in todos_payload["todos"]["groups"]}
    assert groups["pending_message_batches"]["count"] == 1
    assert groups["deferred_jobs"]["count"] == 2
    assert groups["failed_callbacks"]["count"] == 1
    assert groups["failed_sync_runs"]["count"] == 1
    assert groups["pending_message_batches"]["href"] == "/admin/jobs?tab=batches&batch_status=pending"
    assert groups["deferred_jobs"]["href"] == "/admin/jobs?tab=deferred&job_status=pending"
    assert groups["failed_callbacks"]["href"] == "/admin/jobs?tab=callbacks&callback_status=failed"
    assert groups["failed_sync_runs"]["href"] == "/admin/jobs?tab=archive&archive_status=failed"
    assert groups["failed_questionnaire_apply"]["count"] == 1
    assert groups["questionnaire_preflight"]["count"] >= 1
    assert groups["mcp_runtime"]["count"] == 1


def test_admin_console_home_redirects_to_automation_conversion_after_shell_slimming(app, client):
    _seed_dashboard_data(app)

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/automation-conversion")
