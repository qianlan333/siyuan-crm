from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aicrm_next.background_jobs.broadcast_queue_worker as worker
from aicrm_next.background_jobs.broadcast_queue_worker import SafeSkippedBroadcastDispatcher, run_broadcast_queue_worker


class FakeRepo:
    def __init__(self, jobs: list[dict[str, Any]]) -> None:
        self.jobs = jobs
        self.sent: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        return self.jobs[:limit]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0) -> None:
        self.sent.append({"job_id": job_id, "outbound_task_id": outbound_task_id, "sent_count": sent_count, "failed_count": failed_count})

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error") -> None:
        self.failed.append({"job_id": job_id, "error": error, "failure_type": failure_type})


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


def _job(**overrides: Any) -> dict[str, Any]:
    payload = {
        "channel": "wecom_private",
        "sender_userid": "HuangYouCan",
        "target_external_userids": ["wm_test"],
        "rendered_content": {"content_text": "hello private"},
    }
    payload.update(overrides.pop("payload", {}))
    job = {
        "id": 101,
        "source_type": "automation_runtime_v2",
        "source_id": "v2:event:1:task:2:member:3",
        "idempotency_key": "v2:event:1:task:2:member:3",
        "trace_id": "v2:event:1:task:2:member:3",
        "channel": "wecom_private",
        "target_kind": "external_userid",
        "target_external_userids": json.dumps(["wm_test"]),
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
    assert repo.sent == [{"job_id": 101, "outbound_task_id": 888, "sent_count": 1, "failed_count": 0}]
    assert adapter.payload["sender"] == "HuangYouCan"
    assert adapter.payload["external_userids"] == ["wm_test"]


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
    assert repo.sent == [{"job_id": 101, "outbound_task_id": 889, "sent_count": 1, "failed_count": 0}]
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
                target_kind="external_userid",
                payload={
                    "channel": "wecom_private",
                    "target_kind": "external_userid",
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
    repo = FakeRepo([_job(target_external_userids="[]", target_count=0, payload={"target_external_userids": []})])

    run_broadcast_queue_worker(repo=repo, dispatcher=SafeSkippedBroadcastDispatcher())

    assert repo.failed[0]["failure_type"] == "validation_failed"
    assert repo.failed[0]["error"] == "target_external_userids_missing"


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
