from __future__ import annotations

import pytest


def test_queue_gateway_uses_broadcast_jobs_with_empty_targets_allowed():
    from aicrm_next.integration_gateway.wecom_group_adapter import NextGroupOpsQueueGateway

    captured: dict = {}

    def fake_insert_job(**kwargs):
        captured.update(kwargs)
        return 321

    gateway = NextGroupOpsQueueGateway(insert_job_fn=fake_insert_job)
    job_id = gateway.enqueue_group_message(
        plan_id=2,
        source_id="2:webhook:5",
        scheduled_at="2026-05-25T20:00:00+08:00",
        owner_userid="owner_001",
        chat_ids=["wrOgAAA001", "wrOgAAA002"],
        content_payload={"text": {"content": "hello"}},
        content_summary="hello",
        created_by="pytest",
    )

    assert job_id == 321
    assert captured["source_type"] == "workflow"
    assert captured["source_table"] == "automation_group_ops_plans"
    assert captured["source_id"] == "2:webhook:5"
    assert captured["business_domain"] == "group_ops"
    assert captured["channel"] == "wecom_customer_group"
    assert captured["target_kind"] == "chat_id"
    assert captured["target_external_userids"] == []
    assert captured["target_count"] == 0
    assert captured["content_type"] == "wecom_customer_group"
    assert captured["content_payload"]["channel"] == "wecom_customer_group"
    assert captured["content_payload"]["chat_ids"] == ["wrOgAAA001", "wrOgAAA002"]
    assert captured["content_payload"]["sender"] == "owner_001"


def test_wecom_group_adapter_default_disabled_does_not_call_wecom(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    def fail_if_called():
        raise AssertionError("real WeCom client must not be constructed")

    result = WeComGroupMessageAdapter(mode="disabled", client_factory=fail_if_called).create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["wrOgAAA001"], "text": {"content": "hello"}},
        idempotency_key="pytest-disabled",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "wecom_group_message_disabled"


def test_wecom_group_adapter_staging_blocks_real_send(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", "true")
    result = WeComGroupMessageAdapter(mode="staging").create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["wrOgAAA001"], "text": {"content": "hello"}},
        idempotency_key="pytest-staging",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "wecom_group_message_disabled"


def test_wecom_group_adapter_rejects_empty_chat_ids(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    def fail_if_called():
        raise AssertionError("real WeCom client must not be constructed")

    with pytest.raises(ValueError, match="chat_ids is required"):
        WeComGroupMessageAdapter(mode="production", client_factory=fail_if_called).create_group_message_task(
            {"sender": "owner_001", "text": {"content": "hello"}},
            idempotency_key="pytest-empty-chat-ids",
        )


def test_wecom_group_adapter_maps_requested_chat_ids_to_official_wecom_payload(monkeypatch):
    # WeCom add_msg_template uses chat_id_list for customer-group targets; sender
    # alone expands to the member's customer scope, so internal chat_ids must not
    # leak through as an ignored field.
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    captured: dict = {}

    class FakeClient:
        def create_group_message_task(self, payload):
            captured.update(payload)
            return {"errcode": 0, "errmsg": "ok", "msgid": "msg_exact_001", "fail_list": []}

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", "true")

    result = WeComGroupMessageAdapter(mode="production", client_factory=lambda: FakeClient()).create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["chat_001"], "text": {"content": "hello"}},
        idempotency_key="pytest-exact-chat-id-list",
    )

    assert result["ok"] is True
    assert result["exact_target_verified"] is True
    assert result["requested_chat_ids"] == ["chat_001"]
    assert result["target"]["requested_chat_ids"] == ["chat_001"]
    assert captured["chat_type"] == "group"
    assert captured["sender"] == "owner_001"
    assert captured["chat_id_list"] == ["chat_001"]
    assert captured["allow_select"] is False
    assert "chat_ids" not in captured


def test_wecom_group_adapter_fails_when_exact_target_cannot_be_verified(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    class FakeClient:
        def create_group_message_task(self, payload):
            return {"errcode": 0, "errmsg": "ok", "fail_list": []}

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", "true")

    result = WeComGroupMessageAdapter(mode="production", client_factory=lambda: FakeClient()).create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["chat_001"], "text": {"content": "hello"}},
        idempotency_key="pytest-no-msgid",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is True
    assert result["exact_target_required"] is True
    assert result["exact_target_verified"] is False
    assert result["requested_chat_ids"] == ["chat_001"]
    assert result["error_code"] == "wecom_group_exact_target_not_verified"


def test_wecom_group_adapter_fails_when_wecom_returns_errcode(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    class FakeClient:
        def create_group_message_task(self, payload):
            return {"errcode": 40058, "errmsg": "invalid request parameter"}

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", "true")

    result = WeComGroupMessageAdapter(mode="production", client_factory=lambda: FakeClient()).create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["chat_001"], "text": {"content": "hello"}},
        idempotency_key="pytest-errcode",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is True
    assert result["exact_target_verified"] is False
    assert result["error_code"] == "wecom_group_message_api_error"
    assert result["error_message"] == "invalid request parameter"


def test_wecom_group_adapter_fails_when_wecom_rejects_some_chat_ids(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    class FakeClient:
        def create_group_message_task(self, payload):
            return {
                "errcode": 0,
                "errmsg": "ok",
                "msgid": "msg_partial_001",
                "fail_list": ["chat_002"],
            }

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", "true")

    result = WeComGroupMessageAdapter(mode="production", client_factory=lambda: FakeClient()).create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["chat_001", "chat_002"], "text": {"content": "hello"}},
        idempotency_key="pytest-partial-fail-list",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is True
    assert result["exact_target_required"] is True
    assert result["exact_target_verified"] is False
    assert result["requested_chat_ids"] == ["chat_001", "chat_002"]
    assert result["failed_chat_ids"] == ["chat_002"]
    assert result["failed_chat_count"] == 1
    assert result["wecom_msgid"] == "msg_partial_001"
    assert result["error_code"] == "wecom_group_message_partial_failure"


def test_wecom_group_adapter_maps_native_client_error(monkeypatch):
    from aicrm_next.integration_gateway.wecom_customer_group_client import WeComCustomerGroupClientError
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    class FakeClient:
        def create_group_message_task(self, payload):
            raise WeComCustomerGroupClientError(
                "token request failed",
                stage="token",
                payload={"errcode": 40014, "errmsg": "invalid token"},
                error_code="wecom_group_client_token_error",
            )

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", "true")

    result = WeComGroupMessageAdapter(mode="production", client_factory=lambda: FakeClient()).create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["chat_001"], "text": {"content": "hello"}},
        idempotency_key="pytest-client-error",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is True
    assert result["result"] == {"errcode": 40014, "errmsg": "invalid token"}
    assert result["error_code"] == "wecom_group_client_token_error"


def test_wecom_group_adapter_production_without_guard_is_blocked(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    monkeypatch.delenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", raising=False)

    result = WeComGroupMessageAdapter(mode="production").create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["wrOgAAA001"], "text": {"content": "hello"}},
        idempotency_key="pytest-production-guard",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "production_guard_failed"


def test_group_sync_adapter_fake_filters_owner_without_real_wecom(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupChatSyncAdapter

    def fail_if_called():
        raise AssertionError("real WeCom client must not be constructed")

    result = WeComGroupChatSyncAdapter(mode="fake", client_factory=fail_if_called).list_group_chats(owner_userid="owner_001", limit=10)

    assert result["ok"] is True
    assert result["side_effect_executed"] is False
    assert {item["owner_userid"] for item in result["groups"]} == {"owner_001"}

    detail = WeComGroupChatSyncAdapter(mode="fake", client_factory=fail_if_called).get_group_chat("wrOgAAA001", owner_userid="owner_001")
    assert detail["ok"] is True
    assert detail["side_effect_executed"] is False
    assert detail["group"]["chat_id"] == "wrOgAAA001"


def test_group_sync_adapter_production_without_guard_is_blocked(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupChatSyncAdapter

    monkeypatch.delenv("AICRM_ENABLE_REAL_WECOM_GROUP_SYNC", raising=False)
    result = WeComGroupChatSyncAdapter(mode="production").list_group_chats(owner_userid="owner_001", limit=10)

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "production_guard_failed"


def test_group_sync_adapter_production_uses_native_client_without_legacy_app_context(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupChatSyncAdapter

    context = {"list_called": False, "detail_called": False}

    class FakeClient:
        def list_group_chats(self, payload):
            context["list_called"] = True
            assert payload["owner_filter"] == {"userid_list": ["owner_live"]}
            return {"group_chat_list": [{"chat_id": "live_chat_001"}], "next_cursor": ""}

        def get_group_chat(self, chat_id, need_name=1):
            context["detail_called"] = True
            assert chat_id == "live_chat_001"
            assert need_name == 1
            return {
                "group_chat": {
                    "chat_id": "live_chat_001",
                    "name": "真实客户群",
                    "owner": "owner_live",
                    "admin_list": [{"userid": "admin_live"}],
                    "member_list": [{"userid": "owner_live", "type": 1}, {"external_userid": "wm_live", "type": 2}],
                }
            }

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_SYNC", "true")

    result = WeComGroupChatSyncAdapter(mode="production", client_factory=lambda: FakeClient()).list_group_chats(owner_userid="owner_live", limit=10)

    assert result["ok"] is True
    assert result["side_effect_executed"] is True
    assert context["list_called"] is True
    assert context["detail_called"] is True
    assert result["groups"] == [
        {
            "chat_id": "live_chat_001",
            "group_name": "真实客户群",
            "owner_userid": "owner_live",
            "owner_name": "owner_live",
            "admin_userids": ["admin_live"],
            "internal_member_count": 1,
            "external_member_count": 1,
            "status": "active",
        }
    ]


def test_group_ops_queue_stats_counts_only_group_ops_jobs():
    from aicrm_next.integration_gateway.wecom_group_adapter import NextGroupOpsQueueStatsGateway

    gateway = NextGroupOpsQueueStatsGateway(
        list_jobs_fn=lambda: [
            {"id": 1, "source_table": "automation_group_ops_plans", "content_payload": {"channel": "wecom_customer_group"}},
            {"id": 2, "source_table": "other", "content_payload": {"channel": "text"}},
            {"id": 3, "source_table": "other", "content_payload": {"channel": "wecom_customer_group"}},
        ],
    )

    assert gateway.count_group_ops_queue() == 2


def test_broadcast_handler_reuses_existing_outbound_intent_without_dispatch(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    def fail_dispatch(*args, **kwargs):
        raise AssertionError("existing outbound intent must not dispatch again")

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_group_task_with_intent",
        fail_dispatch,
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.get_outbound_task",
        lambda task_id: {
            "id": task_id,
            "response_payload": {
                "ok": True,
                "exact_target_required": True,
                "exact_target_verified": True,
                "requested_chat_ids": ["wrOgAAA001", "wrOgAAA002"],
            },
        },
    )
    result = execute_job(
        {
            "id": 66,
            "source_type": "workflow",
            "outbound_task_id": 778,
            "content_payload": {
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001", "wrOgAAA002"],
                "text": {"content": "hello"},
            },
        }
    )

    assert result["ok"] is True
    assert result["outbound_task_id"] == 778
    assert result["sent_count"] == 2


def test_broadcast_handler_dispatches_group_channel_once(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    calls: list[dict] = []

    def fake_dispatch(task_type, payload, **kwargs):
        calls.append({"task_type": task_type, "payload": payload, **kwargs})
        return {"task_id": 779}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_group_task_with_intent",
        fake_dispatch,
    )
    result = execute_job(
        {
            "id": 67,
            "source_type": "workflow",
            "content_payload": {
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001"],
                "text": {"content": "hello"},
            },
        }
    )

    assert result["ok"] is True
    assert result["outbound_task_id"] == 779
    assert len(calls) == 1
    assert calls[0]["task_type"] == "broadcast_job/group_ops"
    assert calls[0]["broadcast_job_id"] == 67


def test_broadcast_handler_fails_existing_group_outbound_without_exact_target(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.get_outbound_task",
        lambda task_id: {
            "id": task_id,
            "response_payload": {
                "ok": True,
                "exact_target_required": True,
                "exact_target_verified": False,
                "requested_chat_ids": ["wrOgAAA001"],
            },
        },
    )

    result = execute_job(
        {
            "id": 68,
            "source_type": "workflow",
            "outbound_task_id": 780,
            "content_payload": {
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001"],
                "text": {"content": "hello"},
            },
        }
    )

    assert result["ok"] is False
    assert "exact target not verified" in result["error"]


def test_group_ops_worker_fake_mode_marks_sent_without_side_effect(app, monkeypatch):
    import json
    import sys
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import run_broadcast_queue_worker as worker  # type: ignore[import-not-found]

    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "fake")
    monkeypatch.delenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", raising=False)

    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="workflow",
            source_id="1:node:10:due:20260528T0200Z:groups:test",
            source_table="automation_group_ops_plans",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=[],
            target_summary="1 customer groups",
            content_type="wecom_customer_group",
            content_payload={
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001"],
                "text": {"content": "hello"},
            },
            content_summary="hello",
            allow_empty_targets=True,
        )

        summary = worker.run(batch_size=1)
        job = queue_service.get_job(job_id)
        outbound = get_db().execute(
            "SELECT response_payload FROM outbound_tasks WHERE id = ?",
            (int(job["outbound_task_id"]),),
        ).fetchone()
        payload = outbound["response_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

    assert summary["sent_ok"] == 1
    assert job["status"] == "sent"
    assert payload["mode"] == "fake"
    assert payload["side_effect_executed"] is False
    assert payload["requested_chat_ids"] == ["wrOgAAA001"]
    assert payload["exact_target_required"] is True
    assert payload["exact_target_verified"] is True


def test_group_ops_worker_fails_when_exact_target_cannot_be_verified(app, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from wecom_ability_service.domains.broadcast_jobs import service as queue_service

    import sys
    from pathlib import Path

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import run_broadcast_queue_worker as worker  # type: ignore[import-not-found]

    class UnverifiedAdapter:
        def create_group_message_task(self, payload, *, idempotency_key=""):
            return {
                "ok": True,
                "mode": "production",
                "side_effect_executed": True,
                "exact_target_required": True,
                "exact_target_verified": False,
                "requested_chat_ids": list(payload.get("chat_ids") or []),
                "target": {"requested_chat_ids": list(payload.get("chat_ids") or [])},
                "result": {"errcode": 0, "errmsg": "ok", "msgid": "msg_unverified"},
            }

    monkeypatch.setattr(
        "aicrm_next.integration_gateway.wecom_group_adapter.build_wecom_group_message_adapter",
        lambda: UnverifiedAdapter(),
    )

    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="workflow",
            source_id="1:node:10:due:20260528T0200Z:groups:unverified",
            source_table="automation_group_ops_plans",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=[],
            target_summary="1 customer groups",
            content_type="wecom_customer_group",
            content_payload={
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001"],
                "text": {"content": "hello"},
            },
            content_summary="hello",
            allow_empty_targets=True,
        )

        summary = worker.run(batch_size=1)
        job = queue_service.get_job(job_id)

    assert summary["sent_ok"] == 0
    assert summary["sent_failed"] == 1
    assert job["status"] == "failed"
    assert "exact target not verified" in job["last_error"]
    assert "wrOgAAA001" in job["last_error"]
