from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import text

import aicrm_next.background_jobs.broadcast_queue_worker as worker
from aicrm_next.background_jobs.broadcast_queue_worker import PostgresBroadcastQueueRepository, SafeSkippedBroadcastDispatcher, run_broadcast_queue_worker
from aicrm_next.shared.db_session import get_session_factory


class FakeRepo:
    def __init__(self, jobs: list[dict[str, Any]]) -> None:
        self.jobs = jobs
        self.sent: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        return self.jobs[:limit]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0, claim_token: str = "") -> None:
        self.sent.append({"job_id": job_id, "outbound_task_id": outbound_task_id, "sent_count": sent_count, "failed_count": failed_count, "claim_token": claim_token})

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error", claim_token: str = "") -> None:
        self.failed.append({"job_id": job_id, "error": error, "failure_type": failure_type, "claim_token": claim_token})


class Adapter:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result

    def create_private_message_task(self, payload: dict[str, Any], *, idempotency_key: str = "") -> dict[str, Any]:
        self.payload = payload
        self.idempotency_key = idempotency_key
        return dict(self.result)


class RecordingWeComClient:
    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    def create_group_message_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payload = payload
        return {"errcode": 0, "msgid": "msg-recorded"}


@pytest.fixture(autouse=True)
def _resolve_unionid_targets(monkeypatch) -> None:
    def fake_resolver(unionids: list[str]) -> tuple[list[str], list[str]]:
        return [f"wm_{str(item).removeprefix('union_')}" for item in unionids], []

    monkeypatch.setattr(worker, "_resolve_private_targets_by_unionid", fake_resolver)


def _job(**overrides: Any) -> dict[str, Any]:
    payload = {
        "channel": "wecom_private",
        "sender_userid": "HuangYouCan",
        "target_unionids": ["union_test"],
        "rendered_content": {"content_text": "hello private"},
    }
    payload.update(overrides.pop("payload", {}))
    job = {
        "id": 101,
        "source_type": "campaign",
        "source_table": "campaign_members",
        "source_id": "campaign:1:member:3",
        "idempotency_key": "campaign:1:member:3",
        "trace_id": "campaign:1:member:3",
        "channel": "wecom_private",
        "content_type": "private_message",
        "target_kind": "unionid",
        "target_unionids_json": json.dumps(["union_test"]),
        "target_count": 1,
        "content_payload": payload,
    }
    job.update(overrides)
    return job


def test_wecom_private_job_is_dispatched_and_marked_sent(monkeypatch) -> None:
    adapter = Adapter({"ok": True, "wecom_msgid": "msg-1", "result": {"msgid": "msg-1"}})
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 888)
    repo = FakeRepo([_job()])

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher(), now=datetime(2026, 6, 1, tzinfo=timezone.utc))

    assert summary["sent_ok"] == 1
    assert {key: repo.sent[0][key] for key in ("job_id", "outbound_task_id", "sent_count", "failed_count")} == {
        "job_id": 101,
        "outbound_task_id": 888,
        "sent_count": 1,
        "failed_count": 0,
    }
    assert repo.sent[0]["claim_token"]
    assert adapter.payload["sender"] == "HuangYouCan"
    assert adapter.payload["external_userids"] == ["wm_test"]


def test_wecom_private_global_execution_mode_disabled_blocks_before_adapter(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "disabled")

    def fail_adapter():
        raise AssertionError("adapter should not be built when global WeCom execution is disabled")

    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", fail_adapter)
    repo = FakeRepo([_job()])

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["sent_failed"] == 1
    assert repo.failed[0]["failure_type"] == "wecom_execution_disabled"
    assert "AICRM_WECOM_EXECUTION_MODE=disabled" in repo.failed[0]["error"]


def test_cloud_plan_recipient_message_uses_bound_sender_and_hydrates_text(monkeypatch) -> None:
    adapter = Adapter({"ok": True, "wecom_msgid": "msg-cloud", "result": {"msgid": "msg-cloud"}})
    marked: dict[str, Any] = {}
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 901)
    monkeypatch.setattr(worker, "runtime_setting", lambda key, default="": "HuangYouCan" if key == "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS" else default)
    monkeypatch.setattr(
        worker,
        "_load_cloud_plan_recipient_message",
        lambda payload: {"cloud_plan_message_id": 77, "content_text": "agent generated hello", "content_payload_json": {}, "attachments": []},
    )
    monkeypatch.setattr(worker, "_mark_cloud_plan_recipient_message_sent", lambda payload, outbound_task_id=None: marked.update({"payload": payload, "outbound_task_id": outbound_task_id}))
    repo = FakeRepo(
        [
            _job(
                source_type="cloud_plan",
                source_table="cloud_broadcast_plan_recipients",
                source_id="agent_plan:2",
                idempotency_key="cloud_plan_recipient:agent_plan:2",
                channel="wecom_private",
                content_type="cloud_plan",
                payload={
                    "plan_id": "agent_plan",
                    "recipient_id": 2,
                    "external_userid": "wm_test",
                    "message_mode": "recipient_messages",
                    "owner_userid": "WangWei",
                    "rendered_content": {},
                },
            )
        ]
    )

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher(), now=datetime(2026, 6, 1, tzinfo=timezone.utc))

    assert summary["sent_ok"] == 1
    assert adapter.payload["sender"] == "HuangYouCan"
    assert adapter.payload["text"] == {"content": "agent generated hello"}
    assert marked["payload"]["cloud_plan_message_id"] == 77
    assert marked["outbound_task_id"] == 901


def test_cloud_plan_message_loader_does_not_require_external_userid_column(monkeypatch) -> None:
    class Cursor:
        def execute(self, sql: str, params: tuple[Any, ...]) -> "Cursor":
            assert "external_userid" not in sql
            assert params == ("agent_plan", 2)
            return self

        def fetchone(self) -> dict[str, Any]:
            return {
                "id": 77,
                "recipient_id": 2,
                "content_text": "agent generated hello",
                "content_payload_json": {"miniprogram_library_ids": [1325]},
                "attachments_json": [],
            }

    @contextmanager
    def fake_connect():
        yield Cursor()

    monkeypatch.setattr(worker, "connect", fake_connect)

    message = worker._load_cloud_plan_recipient_message(
        {
            "plan_id": "agent_plan",
            "recipient_id": 2,
            "external_userid": "stale-column-value",
            "message_mode": "recipient_messages",
        }
    )

    assert message == {
        "cloud_plan_message_id": 77,
        "content_text": "agent generated hello",
        "content_payload_json": {"miniprogram_library_ids": [1325]},
        "attachments": [],
    }


def test_cloud_plan_failure_marks_recipient_and_message_failed(next_pg_schema) -> None:
    del next_pg_schema
    plan_id = "plan_failure_sync_1"
    with get_session_factory()() as session:
        session.execute(
            text(
                """
                INSERT INTO cloud_broadcast_plans (plan_id, trace_id, session_id, operator, intent)
                VALUES (:plan_id, :plan_id, 'test-session', 'tester', 'failure sync')
                """
            ),
            {"plan_id": plan_id},
        )
        recipient = session.execute(
            text(
                """
                INSERT INTO cloud_broadcast_plan_recipients (
                    plan_id, unionid, owner_userid, display_name,
                    planned_message_count, approval_status, send_status
                )
                VALUES (
                    :plan_id, 'union_failed', 'HuangYouCan', '失败客户',
                    1, 'approved', 'queued'
                )
                RETURNING id
                """
            ),
            {"plan_id": plan_id},
        ).mappings().one()
        recipient_id = int(recipient["id"])
        session.execute(
            text(
                """
                INSERT INTO cloud_broadcast_plan_recipient_messages (
                    plan_id, recipient_id, unionid, content_text, status
                )
                VALUES (:plan_id, :recipient_id, 'union_failed', 'hello', 'queued')
                """
            ),
            {"plan_id": plan_id, "recipient_id": recipient_id},
        )
        job = session.execute(
            text(
                """
                INSERT INTO broadcast_jobs (
                    source_type, source_id, source_table, status,
                    business_domain, idempotency_key, channel, target_kind,
                    target_unionids_json, target_count, content_type, content_payload
                )
                VALUES (
                    'cloud_plan', :source_id, 'cloud_broadcast_plan_recipients', 'claimed',
                    'ai_assistant', :idempotency_key, 'wecom_private', 'unionid',
                    '["union_failed"]'::jsonb, 1, 'cloud_plan', CAST(:payload AS jsonb)
                )
                RETURNING id
                """
            ),
            {
                "source_id": f"{plan_id}:{recipient_id}",
                "idempotency_key": f"cloud_plan_recipient:{plan_id}:{recipient_id}",
                "payload": json.dumps(
                    {
                        "plan_id": plan_id,
                        "recipient_id": recipient_id,
                        "unionid": "union_failed",
                        "message_mode": "recipient_messages",
                    },
                    ensure_ascii=False,
                ),
            },
        ).mappings().one()
        job_id = int(job["id"])
        session.execute(
            text("UPDATE cloud_broadcast_plan_recipients SET broadcast_job_id = :job_id WHERE id = :recipient_id"),
            {"job_id": job_id, "recipient_id": recipient_id},
        )
        session.commit()

    PostgresBroadcastQueueRepository().mark_failed(job_id, error="not external contact", failure_type="wecom_api_error")

    with get_session_factory()() as session:
        job_row = session.execute(text("SELECT status, failure_type, last_error FROM broadcast_jobs WHERE id = :job_id"), {"job_id": job_id}).mappings().one()
        recipient_row = session.execute(
            text("SELECT send_status, last_error FROM cloud_broadcast_plan_recipients WHERE id = :recipient_id"),
            {"recipient_id": recipient_id},
        ).mappings().one()
        message_row = session.execute(
            text("SELECT status, last_error FROM cloud_broadcast_plan_recipient_messages WHERE recipient_id = :recipient_id"),
            {"recipient_id": recipient_id},
        ).mappings().one()

    assert job_row["status"] == "failed_retryable"
    assert job_row["failure_type"] == "wecom_api_error"
    assert "not external contact" in job_row["last_error"]
    assert recipient_row["send_status"] == "failed"
    assert "not external contact" in recipient_row["last_error"]
    assert message_row["status"] == "failed"
    assert "not external contact" in message_row["last_error"]


def test_wecom_private_adapter_canonicalizes_miniprogram_attachment(monkeypatch) -> None:
    from aicrm_next.integration_gateway.wecom_private_adapter import WeComPrivateMessageAdapter

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_PRIVATE_MESSAGE", "1")
    client = RecordingWeComClient()
    adapter = WeComPrivateMessageAdapter(mode="production", client_factory=lambda: client)

    result = adapter.create_private_message_task(
        {
            "sender": "HuangYouCan",
            "external_userids": ["wm_test"],
            "attachments": [
                {
                    "msgtype": "miniprogram",
                    "miniprogram": {
                        "appid": "wx_app_001",
                        "pagepath": "pages/article/article?lesson_id=abc",
                        "title": "Mini Card",
                        "thumb_media_id": "media_thumb_001",
                    },
                }
            ],
        },
        idempotency_key="adapter-canonical",
    )

    assert result["ok"] is True
    assert client.payload is not None
    assert client.payload["attachments"] == [
        {
            "msgtype": "miniprogram",
            "miniprogram": {
                "appid": "wx_app_001",
                "page": "pages/article/article?lesson_id=abc",
                "title": "Mini Card",
                "pic_media_id": "media_thumb_001",
            },
        }
    ]


def test_campaign_private_message_job_is_dispatched(monkeypatch) -> None:
    adapter = Adapter({"ok": True, "wecom_msgid": "msg-campaign", "result": {"msgid": "msg-campaign"}})
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 889)
    repo = FakeRepo(
        [
            _job(
                source_type="campaign",
                source_table="campaign_members",
                source_id="2745:2745:0",
                idempotency_key="campaign_member_step:2745:2745:0",
                channel="",
                target_kind="",
                content_type="private_message",
                payload={
                    "channel": "",
                    "sender_userid": "",
                    "owner_userid": "",
                    "rendered_content": {},
                    "campaign": {"owner_userid": "HuangYouCan"},
                    "step": {"content_text": "campaign private hello"},
                    "members": [{"external_contact_id": "wm_test"}],
                },
            )
        ]
    )

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["sent_ok"] == 1
    assert {key: repo.sent[0][key] for key in ("job_id", "outbound_task_id", "sent_count", "failed_count")} == {
        "job_id": 101,
        "outbound_task_id": 889,
        "sent_count": 1,
        "failed_count": 0,
    }
    assert repo.sent[0]["claim_token"]
    assert adapter.payload["sender"] == "HuangYouCan"
    assert adapter.payload["external_userids"] == ["wm_test"]
    assert adapter.payload["text"]["content"] == "campaign private hello"


def test_campaign_private_message_materializes_miniprogram_attachment(monkeypatch) -> None:
    adapter = Adapter({"ok": True, "wecom_msgid": "msg-campaign-mini", "result": {"msgid": "msg-campaign-mini"}})
    attachment = {
        "msgtype": "miniprogram",
        "miniprogram": {
            "appid": "wx_app_001",
            "pagepath": "pages/article/article?lesson_id=abc",
            "title": "Mini Card",
            "thumb_media_id": "media_thumb_001",
        },
    }
    recorded: dict[str, Any] = {}

    def record_outbound_task(**kwargs: Any) -> int:
        recorded["request_payload"] = kwargs["request_payload"]
        return 890

    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_resolve_private_attachments", lambda content_package: [attachment])
    monkeypatch.setattr(worker, "_record_outbound_task", record_outbound_task)
    repo = FakeRepo(
        [
            _job(
                source_type="campaign",
                source_table="campaign_members",
                source_id="2745:2745:0",
                idempotency_key="campaign_member_step:2745:2745:0",
                channel="",
                target_kind="",
                content_type="private_message",
                payload={
                    "channel": "",
                    "sender_userid": "",
                    "owner_userid": "",
                    "rendered_content": {},
                    "campaign": {"owner_userid": "HuangYouCan"},
                    "step": {
                        "content_text": "campaign private hello",
                        "content_payload_json": {"miniprogram_library_ids": [17]},
                    },
                    "members": [{"external_contact_id": "wm_test"}],
                },
            )
        ]
    )

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["sent_ok"] == 1
    expected_attachment = {
        "msgtype": "miniprogram",
        "miniprogram": {
            "appid": "wx_app_001",
            "page": "pages/article/article?lesson_id=abc",
            "title": "Mini Card",
            "pic_media_id": "media_thumb_001",
        },
    }
    assert adapter.payload["attachments"] == [expected_attachment]
    assert recorded["request_payload"]["attachments"] == [expected_attachment]


def test_campaign_private_message_allows_attachment_only_step(monkeypatch) -> None:
    adapter = Adapter({"ok": True, "wecom_msgid": "msg-campaign-mini-only", "result": {"msgid": "msg-campaign-mini-only"}})
    attachment = {
        "msgtype": "miniprogram",
        "miniprogram": {
            "appid": "wx_app_001",
            "pagepath": "pages/article/article?lesson_id=abc",
            "title": "Mini Card",
            "thumb_media_id": "media_thumb_001",
        },
    }
    recorded: dict[str, Any] = {}

    def record_outbound_task(**kwargs: Any) -> int:
        recorded["request_payload"] = kwargs["request_payload"]
        return 891

    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_resolve_private_attachments", lambda content_package: [attachment])
    monkeypatch.setattr(worker, "_record_outbound_task", record_outbound_task)
    repo = FakeRepo(
        [
            _job(
                source_type="campaign",
                source_table="campaign_members",
                source_id="2745:2745:0",
                idempotency_key="campaign_member_step:2745:2745:0",
                channel="",
                target_kind="",
                content_type="private_message",
                payload={
                    "channel": "",
                    "sender_userid": "",
                    "owner_userid": "",
                    "rendered_content": {},
                    "campaign": {"owner_userid": "HuangYouCan"},
                    "step": {
                        "content_text": "",
                        "content_payload_json": {"miniprogram_library_ids": [17]},
                    },
                    "members": [{"external_contact_id": "wm_test"}],
                },
            )
        ]
    )

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["sent_ok"] == 1
    assert adapter.payload["attachments"] == [
        {
            "msgtype": "miniprogram",
            "miniprogram": {
                "appid": "wx_app_001",
                "page": "pages/article/article?lesson_id=abc",
                "title": "Mini Card",
                "pic_media_id": "media_thumb_001",
            },
        }
    ]
    assert "text" not in adapter.payload
    assert recorded["request_payload"]["attachments"] == adapter.payload["attachments"]
    assert "text" not in recorded["request_payload"]


def test_campaign_private_message_job_with_complete_fields_is_dispatched(monkeypatch) -> None:
    adapter = Adapter({"ok": True, "wecom_msgid": "msg-campaign-complete", "result": {"msgid": "msg-campaign-complete"}})
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 892)
    repo = FakeRepo(
        [
            _job(
                source_type="campaign",
                source_table="campaign_members",
                content_type="private_message",
                channel="wecom_private",
                target_kind="unionid",
                payload={
                    "channel": "wecom_private",
                    "target_kind": "unionid",
                    "rendered_content": {},
                    "campaign": {"owner_userid": "HuangYouCan"},
                    "step": {"content_text": "campaign complete fields"},
                },
            )
        ]
    )

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["sent_ok"] == 1
    assert adapter.payload["text"]["content"] == "campaign complete fields"


def test_campaign_private_message_material_resolve_failure_is_not_sent(monkeypatch) -> None:
    adapter = Adapter({"ok": True, "wecom_msgid": "msg-should-not-send", "result": {"msgid": "msg-should-not-send"}})
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_resolve_private_attachments", lambda content_package: (_ for _ in ()).throw(RuntimeError("miniprogram_resolve_failed:id=17:missing_thumb_media_id")))
    repo = FakeRepo(
        [
            _job(
                source_type="campaign",
                source_table="campaign_members",
                source_id="2745:2745:0",
                channel="",
                target_kind="",
                content_type="private_message",
                payload={
                    "channel": "",
                    "sender_userid": "",
                    "rendered_content": {},
                    "campaign": {"owner_userid": "HuangYouCan"},
                    "step": {
                        "content_text": "campaign private hello",
                        "content_payload_json": {"miniprogram_library_ids": [17]},
                    },
                },
            )
        ]
    )

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["sent_failed"] == 1
    assert repo.failed[0]["failure_type"] == "material_resolve_failed"
    assert repo.failed[0]["error"] == "miniprogram_resolve_failed:id=17:missing_thumb_media_id"
    assert not hasattr(adapter, "payload")


def test_wecom_private_sender_missing_is_validation_failed() -> None:
    repo = FakeRepo([_job(payload={"sender_userid": ""})])

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["sent_failed"] == 1
    assert repo.failed[0]["failure_type"] == "validation_failed"
    assert repo.failed[0]["error"] == "sender_userid_missing"


def test_wecom_private_target_missing_is_validation_failed() -> None:
    repo = FakeRepo([_job(target_unionids_json="[]", target_count=0, payload={"target_unionids": []})])

    run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert repo.failed[0]["failure_type"] == "validation_failed"
    assert repo.failed[0]["error"] == "target_unionids_missing"


def test_wecom_private_target_count_mismatch_is_validation_failed() -> None:
    repo = FakeRepo([_job(target_count=2)])

    run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert repo.failed[0]["failure_type"] == "validation_failed"
    assert repo.failed[0]["error"] == "target_count_mismatch"


def test_wecom_private_content_or_attachment_missing_is_validation_failed() -> None:
    repo = FakeRepo([_job(payload={"rendered_content": {"content_text": ""}})])

    run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert repo.failed[0]["failure_type"] == "validation_failed"
    assert repo.failed[0]["error"] == "content_text_or_attachment_missing"


def test_wecom_private_before_external_call_failure(monkeypatch) -> None:
    adapter = Adapter({"ok": False, "error_code": "before_external_call", "error_message": "disabled"})
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 889)
    repo = FakeRepo([_job()])

    run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert repo.failed[0]["failure_type"] == "before_external_call"
    assert repo.failed[0]["error"] == "disabled"


def test_wecom_private_external_known_failure(monkeypatch) -> None:
    adapter = Adapter({"ok": False, "error_code": "external_call_failed_known", "error_message": "invalid external_userid"})
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 890)
    repo = FakeRepo([_job()])

    run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert repo.failed[0]["failure_type"] == "external_call_failed_known"
    assert repo.failed[0]["error"] == "invalid external_userid"


def test_wecom_private_no_longer_returns_dispatcher_missing(monkeypatch) -> None:
    adapter = Adapter({"ok": False, "error_code": "external_call_unknown", "error_message": "timeout"})
    monkeypatch.setattr("aicrm_next.integration_gateway.wecom_private_adapter.build_wecom_private_message_adapter", lambda: adapter)
    monkeypatch.setattr(worker, "_record_outbound_task", lambda **kwargs: 891)
    repo = FakeRepo([_job()])

    summary = run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert summary["results"][0]["reason"] != "next_native_dispatcher_missing"
    assert repo.failed[0]["failure_type"] == "external_call_unknown"
