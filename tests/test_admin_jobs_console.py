from __future__ import annotations

import json

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "admin-jobs-console.sqlite3"
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
            "AUTOMATION_INTERNAL_API_TOKEN": "internal-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _internal_headers() -> dict[str, str]:
    return {"Authorization": "Bearer internal-token"}


def _admin_action_token(client) -> str:
    client.get("/admin/jobs")
    with client.session_transaction() as sess:
        return str(sess["admin_console_action_token"])


def _seed_jobs_data(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                msgtype, content, send_time, raw_payload
            )
            VALUES
                (1, 'msg-1', 'private', 'ext-1', 'owner-a', 'owner-a', 'ext-1', 'text', 'hello batch', '2026-04-02 10:00:01', '{}'),
                (2, 'msg-2', 'private', 'ext-2', 'owner-b', 'owner-b', 'ext-2', 'text', 'world batch', '2026-04-02 10:04:01', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO sync_runs (
                status, start_time, end_time, owner_userid, cursor, fetched_count, inserted_count,
                raw_response, error_message, created_at, finished_at
            )
            VALUES
                ('failed', '2026-04-01 09:00:00', '2026-04-01 09:05:00', 'owner-a', '', 12, 8, '{}', 'sync failed once', '2026-04-01 09:00:00', '2026-04-01 09:05:00'),
                ('success', '2026-04-02 09:00:00', '2026-04-02 09:06:00', 'owner-a', '', 30, 30, '{}', '', '2026-04-02 09:00:00', '2026-04-02 09:06:00')
            """
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_event_logs (
                corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
                payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
            )
            VALUES
                ('ww-test', 'change_external_contact', 'add_external_contact', 'ext-1', 'owner-a', 1712023200, 'event-1', '<xml></xml>', '{}', 'success', 0, '', '2026-04-02 10:20:00', '2026-04-02 10:20:00'),
                ('ww-test', 'change_external_contact', 'update_by_user', 'ext-2', 'owner-b', 1712023260, 'event-2', '<xml></xml>', '{}', 'failed', 1, 'callback failed', '2026-04-02 10:21:00', '2026-04-02 10:22:00')
            """
        )
        db.execute(
            """
            INSERT INTO message_batches (
                id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
            )
            VALUES
                (1, 'batch-1', '2026-04-02 10:00:00', '2026-04-02 10:02:59', 'pending', 1, '2026-04-02 10:03:00', NULL, NULL, NULL),
                (2, 'batch-2', '2026-04-02 10:03:00', '2026-04-02 10:05:59', 'acked', 1, '2026-04-02 10:06:00', '2026-04-02 10:10:00', 'checked', 'tester-old')
            """
        )
        db.execute(
            """
            INSERT INTO message_batch_items (
                batch_id, message_id, msgid, chat_type, chat_id, external_userid, owner_userid, send_time
            )
            VALUES
                (1, 1, 'msg-1', 'private', '', 'ext-1', 'owner-a', '2026-04-02 10:00:01'),
                (2, 2, 'msg-2', 'private', '', 'ext-2', 'owner-b', '2026-04-02 10:04:01')
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status, attempt_count, payload_json, result_json
            )
            VALUES
                ('sync_tags', 'ext-1', 'owner-a', '2026-04-02 11:00:00', 'pending', 0, '{}', '{}'),
                ('sync_tags', 'ext-2', 'owner-b', '2026-04-02 11:05:00', 'failed', 2, '{}', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO outbound_webhook_deliveries (
                id, event_type, source_key, source_id, target_url, payload_json, payload_summary,
                token_configured, status, attempt_count, max_attempts, response_status_code,
                response_body_summary, last_error, last_attempted_at, next_retry_at, created_at, updated_at
            )
            VALUES
                (1, 'openclaw_focus_message', 'external_userid', 'ext-1', 'https://openclaw.local/focus', '{"external_userid":"ext-1"}', '{"external_userid":"ext-1"}', 1, 'success', 1, 3, 202, '{"ok":true}', '', '2026-04-02 12:00:00', '', '2026-04-02 12:00:00', '2026-04-02 12:00:00'),
                (2, 'questionnaire_submit', 'submission_id', 'sub-2', '', '{"mobile":"13800138000"}', '{"mobile":"13800138000"}', 0, 'failed', 0, 3, NULL, '', 'webhook_not_configured', '2026-04-02 12:10:00', '', '2026-04-02 12:10:00', '2026-04-02 12:10:00'),
                (3, 'openclaw_focus_message', 'external_userid', 'ext-3', 'https://openclaw.local/focus', '{"external_userid":"ext-3"}', '{"external_userid":"ext-3"}', 1, 'retry_scheduled', 1, 3, 500, 'server error', 'http_status_500', '2026-04-02 12:20:00', '2026-04-02 12:25:00', '2026-04-02 12:20:00', '2026-04-02 12:20:00'),
                (4, 'questionnaire_submit', 'submission_id', 'sub-4', 'https://hooks.local/q', '{"mobile":"13800138001"}', '{"mobile":"13800138001"}', 1, 'exhausted', 3, 3, 500, 'server error', 'http_status_500', '2026-04-02 12:30:00', '', '2026-04-02 12:30:00', '2026-04-02 12:30:00')
            """
        )
        db.commit()


def test_admin_jobs_page_renders_real_sections_not_placeholder(app, client, monkeypatch):
    _seed_jobs_data(app)
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service.run_archive_health_check",
        lambda: {"ok": True, "sdk_loaded": True},
    )

    response = client.get("/admin/jobs")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "同步与任务总览" in html
    assert "聊天同步" in html
    assert "回调状态" in html
    assert "消息批次" in html
    assert "待处理作业" in html
    assert "Webhook 投递" in html
    assert "同步与任务面板待接入" not in html


def test_admin_jobs_batches_tab_renders_batch_detail_and_messages(app, client):
    _seed_jobs_data(app)

    response = client.get("/admin/jobs?tab=batches&batch_id=1")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "批次详情" in html
    assert "批次内消息" in html
    assert "hello batch" in html
    assert "确认这个批次已处理" in html


def test_admin_jobs_ack_batch_updates_status_and_writes_audit(app, client):
    _seed_jobs_data(app)
    action_token = _admin_action_token(client)

    response = client.post(
        "/admin/jobs/actions",
        data={
            "admin_action_token": action_token,
            "return_tab": "batches",
            "action": "ack-message-batch",
            "batch_id": "1",
            "batch_status": "pending",
            "batch_limit": "20",
            "ack_note": "checked from jobs console",
            "operator": "tester-jobs",
            "confirm": "1",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "操作已完成，结果与审计已刷新。" in html

    with app.app_context():
        batch = get_db().execute(
            "SELECT status, ack_note, acked_by FROM message_batches WHERE id = 1"
        ).fetchone()
        audit = get_db().execute(
            """
            SELECT operator, action_type, target_type, target_id
            FROM admin_operation_logs
            WHERE target_type = 'jobs_console_action'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert batch["status"] == "acked"
        assert batch["ack_note"] == "checked from jobs console"
        assert batch["acked_by"] == "tester-jobs"
        assert audit["operator"] == "tester-jobs"
        assert audit["action_type"] == "ack_message_batch"
        assert audit["target_id"] == "1"


def test_admin_jobs_archive_sync_action_uses_confirm_and_writes_audit(app, client, monkeypatch):
    _seed_jobs_data(app)
    action_token = _admin_action_token(client)
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service.run_manual_archive_sync",
        lambda **kwargs: {
            "ok": True,
            "sync_run": {
                "id": 88,
                "status": "success",
                "fetched_count": 9,
                "inserted_count": 8,
                "has_more": False,
                "next_cursor": "",
                "last_seq": 123,
            },
        },
    )

    response = client.post(
        "/admin/jobs/actions",
        data={
            "admin_action_token": action_token,
            "return_tab": "archive",
            "action": "run-archive-sync",
            "start_time": "2026-04-02 09:00:00",
            "end_time": "2026-04-02 09:10:00",
            "owner_userid": "owner-a",
            "cursor": "",
            "operator": "tester-archive",
            "confirm": "1",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "操作已完成，结果与审计已刷新。" in html
    assert '"id": 88' in html

    with app.app_context():
        audit = get_db().execute(
            """
            SELECT operator, action_type, target_type, target_id
            FROM admin_operation_logs
            WHERE target_type = 'jobs_console_action'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert audit["operator"] == "tester-archive"
        assert audit["action_type"] == "run_archive_sync"
        assert audit["target_id"] == "88"


def test_admin_jobs_archive_sync_page_defaults_to_preview_and_writes_preview_audit(app, client):
    _seed_jobs_data(app)
    action_token = _admin_action_token(client)

    response = client.post(
        "/admin/jobs/actions",
        data={
            "admin_action_token": action_token,
            "return_tab": "archive",
            "action": "run-archive-sync",
            "start_time": "2026-04-02 09:00:00",
            "end_time": "2026-04-02 09:10:00",
            "owner_userid": "owner-a",
            "cursor": "cursor-a",
            "operator": "tester-preview",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "这里会先展示操作预览，确认后才会真正执行同步。" in html
    assert '"preview_only": true' in html
    assert '"cursor": "cursor-a"' in html

    with app.app_context():
        audit = get_db().execute(
            """
            SELECT operator, action_type, target_type, target_id
            FROM admin_operation_logs
            WHERE target_type = 'jobs_console_action'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert audit["operator"] == "tester-preview"
        assert audit["action_type"] == "preview_archive_sync"
        assert audit["target_id"] == "archive_sync"


def test_admin_jobs_run_deferred_jobs_action_writes_audit(app, client, monkeypatch):
    _seed_jobs_data(app)
    action_token = _admin_action_token(client)
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service._run_user_ops_deferred_jobs_payload",
        lambda limit: {
            "ok": True,
            "limit": limit,
            "scanned_count": 2,
            "success_count": 1,
            "failed_count": 1,
            "items": [],
        },
    )

    response = client.post(
        "/admin/jobs/actions",
        data={
            "admin_action_token": action_token,
            "return_tab": "deferred",
            "action": "run-deferred-jobs",
            "limit": "5",
            "operator": "tester-deferred",
            "confirm": "1",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "操作已完成，结果与审计已刷新。" in html
    assert '"limit": 5' in html

    with app.app_context():
        audit = get_db().execute(
            """
            SELECT operator, action_type, target_type, target_id
            FROM admin_operation_logs
            WHERE target_type = 'jobs_console_action'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert audit["operator"] == "tester-deferred"
        assert audit["action_type"] == "run_deferred_jobs"
        assert audit["target_id"] == "limit:5"


def test_api_admin_jobs_summary_and_read_panels(app, client, monkeypatch):
    _seed_jobs_data(app)
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service.run_archive_health_check",
        lambda: {"ok": True, "sdk_loaded": True},
    )

    summary_response = client.get("/api/admin/jobs/summary")
    archive_response = client.get("/api/admin/jobs/archive-sync?archive_status=success")
    callbacks_response = client.get("/api/admin/jobs/callbacks?callback_status=failed")
    batches_response = client.get("/api/admin/jobs/message-batches?batch_status=pending")
    deferred_response = client.get("/api/admin/jobs/deferred-jobs?job_status=pending")

    assert summary_response.status_code == 200
    assert summary_response.get_json()["ok"] is True
    assert len(summary_response.get_json()["summary"]["summary_cards"]) == 5

    archive_payload = archive_response.get_json()
    assert archive_response.status_code == 200
    assert archive_payload["ok"] is True
    assert archive_payload["archive_sync"]["filters"]["status"] == "success"
    assert archive_payload["archive_sync"]["items"][0]["status"] == "success"

    callbacks_payload = callbacks_response.get_json()
    assert callbacks_response.status_code == 200
    assert callbacks_payload["callbacks"]["filters"]["process_status"] == "failed"
    assert callbacks_payload["callbacks"]["items"][0]["process_status"] == "failed"

    batches_payload = batches_response.get_json()
    assert batches_response.status_code == 200
    assert batches_payload["message_batches"]["filters"]["status"] == "pending"
    assert batches_payload["message_batches"]["items"][0]["status"] == "pending"

    deferred_payload = deferred_response.get_json()
    assert deferred_response.status_code == 200
    assert deferred_payload["deferred_jobs"]["filters"]["status"] == "pending"
    assert deferred_payload["deferred_jobs"]["items"][0]["status"] == "pending"


def test_admin_jobs_webhooks_tab_renders_filters_statuses_and_retry_actions(app, client):
    _seed_jobs_data(app)

    response = client.get("/admin/jobs?tab=webhooks&webhook_status=retry_scheduled&webhook_event_type=openclaw_focus_message")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Webhook 投递状态" in html
    assert "执行到期重试" in html
    assert "待自动重试" in html
    assert "未配置" not in html
    assert "重试" in html
    assert "Payload 摘要" in html
    assert "OpenClaw 焦点消息" in html


def test_admin_jobs_retry_webhook_delivery_action_writes_audit(app, client, monkeypatch):
    _seed_jobs_data(app)
    action_token = _admin_action_token(client)
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service.retry_outbound_webhook_delivery",
        lambda delivery_id: {
            "ok": True,
            "sent": True,
            "delivery": {
                "id": delivery_id,
                "status": "success",
                "attempt_count": 2,
                "response_status_code": 202,
            },
        },
    )

    response = client.post(
        "/admin/jobs/actions",
        data={
            "admin_action_token": action_token,
            "return_tab": "webhooks",
            "action": "retry-webhook-delivery",
            "delivery_id": "3",
            "operator": "tester-webhook-retry",
            "confirm": "1",
            "webhook_event_type": "openclaw_focus_message",
            "webhook_status": "retry_scheduled",
            "webhook_limit": "20",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "操作已完成，结果与审计已刷新。" in html
    assert '"status": "success"' in html

    with app.app_context():
        audit = get_db().execute(
            """
            SELECT operator, action_type, target_id
            FROM admin_operation_logs
            WHERE target_type = 'jobs_console_action'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert audit["operator"] == "tester-webhook-retry"
        assert audit["action_type"] == "retry_webhook_delivery"
        assert audit["target_id"] == "3"


def test_api_admin_jobs_webhook_deliveries_and_run_retries(app, client, monkeypatch):
    _seed_jobs_data(app)

    list_response = client.get(
        "/api/admin/jobs/webhook-deliveries?webhook_event_type=questionnaire_submit&webhook_status=failed&webhook_limit=10"
    )
    list_payload = list_response.get_json()

    assert list_response.status_code == 200
    assert list_payload["ok"] is True
    assert list_payload["webhook_deliveries"]["filters"]["event_type"] == "questionnaire_submit"
    assert list_payload["webhook_deliveries"]["filters"]["status"] == "failed"
    assert list_payload["webhook_deliveries"]["items"][0]["delivery_state_label"] == "未配置"

    missing_confirm = client.post(
        "/api/admin/jobs/webhook-deliveries/run",
        headers=_internal_headers(),
        json={"limit": 5, "operator": "tester-api"},
    )
    assert missing_confirm.status_code == 400
    assert missing_confirm.get_json()["error"] == "执行 webhook 自动重试前请先勾选确认"

    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service.run_due_outbound_webhook_retries",
        lambda limit: {
            "ok": True,
            "count": 2,
            "scanned_count": 2,
            "retried_count": 2,
            "success_count": 1,
            "failed_count": 1,
            "deliveries": [],
        },
    )
    run_response = client.post(
        "/api/admin/jobs/webhook-deliveries/run",
        headers=_internal_headers(),
        json={"limit": 5, "operator": "tester-api", "confirm": True},
    )
    run_payload = run_response.get_json()

    assert run_response.status_code == 200
    assert run_payload["ok"] is True
    assert run_payload["scanned_count"] == 2
    assert run_payload["success_count"] == 1


def test_api_admin_jobs_message_batch_detail_and_ack(app, client):
    _seed_jobs_data(app)

    detail_response = client.get("/api/admin/jobs/message-batches/1")
    detail_payload = detail_response.get_json()

    assert detail_response.status_code == 200
    assert detail_payload["ok"] is True
    assert detail_payload["message_batch"]["batch"]["id"] == 1
    assert detail_payload["message_batch"]["messages"][0]["content"] == "hello batch"

    missing_confirm = client.post(
        "/api/admin/jobs/message-batches/1/ack",
        headers=_internal_headers(),
        json={"ack_note": "checked by api", "operator": "tester-api"},
    )
    assert missing_confirm.status_code == 400
    assert missing_confirm.get_json()["error"] == "确认消息批次前请先勾选确认"

    ack_response = client.post(
        "/api/admin/jobs/message-batches/1/ack",
        headers=_internal_headers(),
        json={"ack_note": "checked by api", "operator": "tester-api", "confirm": True},
    )
    ack_payload = ack_response.get_json()

    assert ack_response.status_code == 200
    assert ack_payload["ok"] is True
    assert ack_payload["batch"]["status"] == "acked"


def test_api_admin_jobs_archive_sync_run_supports_preview_and_execute(app, client, monkeypatch):
    _seed_jobs_data(app)

    preview_response = client.post(
        "/api/admin/jobs/archive-sync/run",
        headers=_internal_headers(),
        json={
            "start_time": "2026-04-02 09:00:00",
            "end_time": "2026-04-02 09:10:00",
            "owner_userid": "owner-a",
            "cursor": "cursor-x",
            "operator": "tester-api-preview",
        },
    )
    preview_payload = preview_response.get_json()

    assert preview_response.status_code == 200
    assert preview_payload["ok"] is True
    assert preview_payload["preview_only"] is True
    assert preview_payload["request"]["cursor"] == "cursor-x"

    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service.run_manual_archive_sync",
        lambda **kwargs: {
            "ok": True,
            "sync_run": {
                "id": 99,
                "status": "success",
                "fetched_count": 5,
                "inserted_count": 5,
                "has_more": False,
                "next_cursor": "",
                "last_seq": 321,
            },
        },
    )
    execute_response = client.post(
        "/api/admin/jobs/archive-sync/run",
        headers=_internal_headers(),
        json={
            "start_time": "2026-04-02 09:00:00",
            "end_time": "2026-04-02 09:10:00",
            "owner_userid": "owner-a",
            "operator": "tester-api-run",
            "confirm": True,
        },
    )
    execute_payload = execute_response.get_json()

    assert execute_response.status_code == 200
    assert execute_payload["ok"] is True
    assert execute_payload["sync_run"]["id"] == 99


def test_api_admin_jobs_deferred_jobs_run_requires_confirm_and_returns_summary(app, client, monkeypatch):
    _seed_jobs_data(app)

    missing_confirm = client.post(
        "/api/admin/jobs/deferred-jobs/run",
        headers=_internal_headers(),
        json={"limit": 3, "operator": "tester-api"},
    )
    assert missing_confirm.status_code == 400
    assert missing_confirm.get_json()["error"] == "执行待处理作业前请先勾选确认"

    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_jobs.service._run_user_ops_deferred_jobs_payload",
        lambda limit: {
            "ok": True,
            "limit": limit,
            "scanned_count": 2,
            "success_count": 2,
            "failed_count": 0,
            "items": [],
        },
    )
    response = client.post(
        "/api/admin/jobs/deferred-jobs/run",
        headers=_internal_headers(),
        json={"limit": 3, "operator": "tester-api", "confirm": True},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["limit"] == 3


def test_api_admin_jobs_action_endpoints_reject_invalid_internal_token(app, client):
    _seed_jobs_data(app)

    response = client.post(
        "/api/admin/jobs/webhook-deliveries/run",
        headers={"Authorization": "Bearer wrong-token"},
        json={"limit": 3, "operator": "tester-api", "confirm": True},
    )

    assert response.status_code == 401
    assert response.get_json() == {"ok": False, "error": "invalid internal token"}


def test_admin_jobs_actions_require_console_action_token(app, client):
    _seed_jobs_data(app)

    response = client.post(
        "/admin/jobs/actions",
        data={
            "return_tab": "webhooks",
            "action": "retry-webhook-delivery",
            "delivery_id": "3",
            "operator": "tester-webhook-retry",
            "confirm": "1",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "后台动作令牌无效，请刷新页面后重试" in html
