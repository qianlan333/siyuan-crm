from __future__ import annotations

from typing import Any

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import repo
from wecom_ability_service.domains.automation_conversion.service import run_due_reply_monitor
from tools import check_reply_monitor_run_due_readiness as readiness_checker

from _automation_conversion_v1_helpers import (
    _configure_reply_monitor,
    _seed_archived_message,
    _seed_automation_member,
    _seed_contact,
)


def test_reply_monitor_run_due_treats_invalid_phone_as_item_failure(app, monkeypatch):
    _configure_reply_monitor(
        app,
        enabled=True,
        last_capture_cursor=0,
        quiet_hours_start="00:00",
        quiet_hours_end="00:00",
    )
    app.config["LAOHUANG_CHAT_ENABLED"] = "true"
    app.config["LAOHUANG_CHAT_WEBHOOK_URL"] = "https://www.youcangogogo.com/api/webhook/crm/chat"
    app.config["LAOHUANG_CHAT_WEBHOOK_TOKEN"] = "test-chat-token"
    _seed_due_reply_monitor_item(app, external_userid="wm_bad_phone_001", phone="bad-phone", seq=1001)
    _seed_due_reply_monitor_item(app, external_userid="wm_good_phone_001", phone="13900009301", seq=1002)

    requests_seen: list[dict[str, Any]] = []

    def _fake_post(url, json=None, **kwargs):
        requests_seen.append({"url": url, "json": dict(json or {})})
        if (json or {}).get("phone") == "bad-phone":
            return _LaoHuangRejectedResponse()
        return _LaoHuangAcceptedResponse()

    monkeypatch.setattr("wecom_ability_service.infra.http_client.requests.post", _fake_post)
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.laohuang_chat_service.get_customer_messages_payload",
        _fake_customer_messages_payload,
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:00")

    with app.app_context():
        before_send_records = _table_count("user_ops_send_records")
        before_outbound_tasks = _table_count("outbound_tasks")
        result = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system", limit=10)
        rows = get_db().execute(
            """
            SELECT external_userid, status, error_message
            FROM automation_reply_monitor_queue
            ORDER BY id ASC
            """
        ).fetchall()
        after_send_records = _table_count("user_ops_send_records")
        after_outbound_tasks = _table_count("outbound_tasks")

    assert result["ok"] is True
    assert result["partial_failed"] is True
    assert result["status"] == "partial_failed"
    assert result["error_code"] == "reply_monitor_item_failed"
    assert result["processed_count"] == 2
    assert result["success_count"] == 1
    assert result["failed_count"] == 1
    assert result["failed_items"][0]["external_userid"] == "wm_bad_phone_001"
    assert "invalid phone" in result["failed_items"][0]["error_message"]
    assert [dict(row) for row in rows] == [
        {"external_userid": "wm_bad_phone_001", "status": "failed", "error_message": '{"detail":"invalid phone"}'},
        {"external_userid": "wm_good_phone_001", "status": "dispatched", "error_message": ""},
    ]
    assert [item["json"]["phone"] for item in requests_seen] == ["bad-phone", "13900009301"]
    assert after_send_records == before_send_records
    assert after_outbound_tasks == before_outbound_tasks


def test_reply_monitor_run_due_api_returns_2xx_for_item_level_invalid_phone(app, client, monkeypatch):
    _configure_reply_monitor(
        app,
        enabled=True,
        last_capture_cursor=0,
        quiet_hours_start="00:00",
        quiet_hours_end="00:00",
    )
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "internal-token"
    app.config["LAOHUANG_CHAT_ENABLED"] = "true"
    app.config["LAOHUANG_CHAT_WEBHOOK_URL"] = "https://www.youcangogogo.com/api/webhook/crm/chat"
    _seed_due_reply_monitor_item(app, external_userid="wm_api_bad_phone_001", phone="bad-phone", seq=1011)

    monkeypatch.setattr("wecom_ability_service.infra.http_client.requests.post", lambda *args, **kwargs: _LaoHuangRejectedResponse())
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.laohuang_chat_service.get_customer_messages_payload",
        _fake_customer_messages_payload,
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:00")

    response = client.post(
        "/api/admin/automation-conversion/reply-monitor/run-due",
        json={"limit": 10},
        headers={"Authorization": "Bearer internal-token"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["partial_failed"] is True
    assert payload["failed_count"] == 1
    assert payload["error_code"] == "reply_monitor_item_failed"


def test_reply_monitor_run_due_readiness_checker_returns_ok():
    result = readiness_checker.run_check()

    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["item_level_failure_policy"] is True
    assert result["systemd_compatible_2xx_policy"] is True
    assert result["send_side_effect_sentinel_covered"] is True
    assert result["timers_enabled_by_this_change"] is False


def _seed_due_reply_monitor_item(app, *, external_userid: str, phone: str, seq: int) -> None:
    _seed_contact(app, external_userid=external_userid, mobile=phone if phone.isdigit() else "", owner_userid="sales_01", customer_name=external_userid)
    _seed_automation_member(
        app,
        external_contact_id=external_userid,
        phone=phone,
        owner_staff_id="sales_01",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        decision_source="manual",
    )
    message_id = _seed_archived_message(
        app,
        msgid=f"msg-{external_userid}",
        seq=seq,
        external_userid=external_userid,
        owner_userid="sales_01",
        sender=external_userid,
        receiver="sales_01",
        content="我想了解课程",
        send_time="2026-04-10 08:59:00",
    )
    with app.app_context():
        member = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ? LIMIT 1",
            (external_userid,),
        ).fetchone()
        repo.insert_reply_monitor_queue_item(
            {
                "member_id": int(member["id"]),
                "external_userid": external_userid,
                "owner_userid": "sales_01",
                "status": "pending",
                "message_ids_json": [message_id],
                "message_count": 1,
                "first_inbound_at": "2026-04-10 08:59:00",
                "last_inbound_at": "2026-04-10 08:59:00",
                "not_before": "2026-04-10 09:00:00",
                "last_dispatch_at": "",
                "error_message": "",
                "payload_snapshot_json": {},
            }
        )
        get_db().commit()


def _fake_customer_messages_payload(*, external_userid="", mobile="", limit=20, fetch_all=False):
    return {
        "external_userid": external_userid,
        "mobile": mobile,
        "count": 2,
        "messages": [
            {"sender": external_userid, "content": "用户消息", "send_time": "2026-04-10 08:58:00"},
            {"sender": "sales_01", "content": "员工回复", "send_time": "2026-04-10 08:58:30"},
        ],
    }


def _table_count(table_name: str) -> int:
    return int(get_db().execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])


class _LaoHuangRejectedResponse:
    ok = False
    status_code = 400
    text = '{"detail":"invalid phone"}'

    def json(self):
        return {"detail": "invalid phone"}


class _LaoHuangAcceptedResponse:
    ok = True
    status_code = 200
    text = '{"ok":true,"status":"accepted","task_id":"lh-task-valid-phone"}'

    def json(self):
        return {"ok": True, "status": "accepted", "task_id": "lh-task-valid-phone"}
