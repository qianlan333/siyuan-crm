from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wecom_ability_service.domains.broadcast_jobs import repo as queue_repo
from wecom_ability_service.domains.broadcast_jobs import service as queue_service


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


def test_business_domain_resolution_covers_supported_sources():
    for source_type in ("campaign", "sop", "workflow", "operation_task", "focus_send", "deferred"):
        assert queue_service.resolve_broadcast_business_domain(source_type=source_type) == "automation_ops"

    assert queue_service.resolve_broadcast_business_domain(source_type="cloud_plan") == "ai_assistant"
    assert queue_service.resolve_broadcast_business_domain(source_type="manual") == "manual"
    assert queue_service.resolve_broadcast_business_domain(source_table="automation_group_ops_plans", source_type="workflow") == "group_ops"
    assert queue_service.resolve_broadcast_business_domain(source_type="workflow", content_payload={"channel": "wecom_customer_group"}) == "group_ops"
    assert queue_service.resolve_broadcast_business_domain(source_type="new_source") == "unknown"


def test_channel_and_target_kind_resolution():
    assert queue_service.resolve_broadcast_channel(content_payload={"channel": "wecom_customer_group"}) == "wecom_customer_group"
    assert queue_service.resolve_broadcast_channel(target_chat_id="chat-1") == "wecom_customer_group"
    assert queue_service.resolve_broadcast_channel(target_external_userid="wm_1") == "wecom_private"
    assert queue_service.resolve_broadcast_channel() == "unknown"

    assert queue_service.resolve_broadcast_target_kind(target_chat_id="chat-1") == "chat_id"
    assert queue_service.resolve_broadcast_target_kind(target_external_userid="wm_1") == "external_userid"
    assert queue_service.resolve_broadcast_target_kind(
        content_payload={"sendable_targets": [{"external_userid": "wm_1"}, {"chat_id": "chat-1"}]}
    ) == "mixed"
    assert queue_service.resolve_broadcast_target_kind(content_payload={"dynamic_targeting": {"segment": "due"}}) == "dynamic"
    assert queue_service.resolve_broadcast_target_kind() == "unknown"


def test_idempotency_key_generation_is_stable_and_non_random():
    now = datetime(2026, 5, 28, 10, 0, tzinfo=timezone.utc)

    explicit = queue_service.build_broadcast_job_idempotency_key({"idempotencyKey": "caller:key"})
    cloud_a = queue_service.build_broadcast_job_idempotency_key({"source_type": "cloud_plan", "source_id": "plan-1", "scheduled_for": now})
    cloud_b = queue_service.build_broadcast_job_idempotency_key({"source_type": "cloud_plan", "source_id": "plan-1", "scheduled_for": now + timedelta(hours=1)})
    group_key = queue_service.build_broadcast_job_idempotency_key(
        {
            "source_type": "workflow",
            "source_table": "automation_group_ops_plans",
            "source_id": "2:webhook:5",
            "scheduled_for": now,
            "content_payload": {"node_id": 8},
        }
    )

    assert explicit == "caller:key"
    assert cloud_a == "cloud_plan:plan-1"
    assert cloud_b == cloud_a
    assert group_key == "group_ops:2:webhook:5:2026-05-28T10:00:00+00:00:8"
    assert queue_service.build_broadcast_job_idempotency_key({"source_type": "manual"}) is None
    assert queue_service.build_broadcast_job_idempotency_key({"source_type": "manual"}) == queue_service.build_broadcast_job_idempotency_key({"source_type": "manual"})


def test_enqueue_broadcast_job_standardizes_metadata_and_writes_event(app):
    with app.app_context():
        result = queue_service.enqueue_broadcast_job(
            {
                "source_type": "workflow",
                "source_table": "automation_group_ops_plans",
                "source_id": "plan-1:node-2",
                "scheduled_for": datetime.now(timezone.utc),
                "target_external_userids": [],
                "target_summary": "2 groups",
                "content_type": "wecom_customer_group",
                "content_payload": {"channel": "wecom_customer_group", "chat_ids": ["chat-1", "chat-2"]},
                "content_summary": "hello groups",
                "requires_approval": True,
                "allow_empty_targets": True,
                "created_by": "pytest",
            }
        )
        job = result["job"]
        events = queue_repo.list_broadcast_job_events(int(job["id"]))

    assert result["status"] == "created"
    assert job["status"] == "waiting_approval"
    assert job["business_domain"] == "group_ops"
    assert job["channel"] == "wecom_customer_group"
    assert job["target_kind"] == "chat_id"
    assert job["idempotency_key"].startswith("group_ops:plan-1:node-2:")
    assert events[0]["event_type"] == "enqueued"
    assert events[0]["to_status"] == "waiting_approval"
    assert events[0]["event_payload"]["business_domain"] == "group_ops"
    assert "content_payload" not in events[0]["event_payload"]


def test_enqueue_duplicate_idempotency_key_returns_existing_job(app):
    payload = {
        "source_type": "cloud_plan",
        "source_id": "plan-dup",
        "source_table": "cloud_broadcast_plans",
        "scheduled_for": datetime.now(timezone.utc),
        "target_external_userids": ["wm_1"],
        "target_summary": "1 user",
        "content_type": "cloud_plan",
        "content_payload": {"plan_id": "plan-dup"},
        "content_summary": "plan",
    }
    with app.app_context():
        first = queue_service.enqueue_broadcast_job(payload)
        second = queue_service.enqueue_broadcast_job({**payload, "scheduled_for": datetime.now(timezone.utc) + timedelta(hours=1)})
        jobs = queue_service.list_jobs(source_types=["cloud_plan"])

    assert first["status"] == "created"
    assert second["status"] == "duplicate"
    assert second["job"]["id"] == first["job"]["id"]
    assert len(jobs) == 1


def test_legacy_enqueue_job_still_works_and_claims(app):
    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="manual",
            source_id="legacy-1",
            source_table="manual_test",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=["wm_1"],
            target_summary="1 user",
            content_type="text",
            content_payload={"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
            content_summary="hi",
        )
        claimed = queue_service.claim_due_jobs(limit=10, now=datetime.now(timezone.utc))
        job = queue_service.get_job(job_id)
        events = queue_repo.list_broadcast_job_events(job_id)

    assert job_id > 0
    assert claimed[0]["id"] == job_id
    assert job["status"] == "claimed"
    assert [event["event_type"] for event in events] == ["enqueued", "claimed"]


def test_failure_type_and_events_are_safe(app):
    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="manual",
            source_id="failure-1",
            source_table="manual_test",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=["wm_secret"],
            target_summary="1 user",
            content_type="text",
            content_payload={"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
            content_summary="hi",
        )
        queue_service.claim_due_jobs(limit=10, now=datetime.now(timezone.utc))
        queue_service.mark_failed(job_id, error="external_userid wm_secret token abc", failure_type="external_call_failed_known")
        job = queue_service.get_job(job_id)
        events = queue_repo.list_broadcast_job_events(job_id)

    assert job["status"] == "failed"
    assert job["failure_type"] == "external_call_failed_known"
    failed_event = events[-1]
    assert failed_event["event_type"] == "failed"
    assert failed_event["event_payload"]["failure_type"] == "external_call_failed_known"
    assert "wm_secret" not in failed_event["event_payload"]["error_summary"]
    assert "content_payload" not in failed_event["event_payload"]


def test_mark_failed_defaults_failure_type_to_unknown(app):
    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="manual",
            source_id="failure-default",
            source_table="manual_test",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=["wm_1"],
            target_summary="1 user",
            content_type="text",
            content_payload={"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
            content_summary="hi",
        )
        queue_service.claim_due_jobs(limit=10, now=datetime.now(timezone.utc))
        queue_service.mark_failed(job_id, error="plain failure")
        job = queue_service.get_job(job_id)

    assert job["failure_type"] == "unknown"


def test_events_cover_approve_sent_cancel_and_event_failure_is_non_blocking(app, monkeypatch):
    with app.app_context():
        waiting = queue_service.enqueue_job(
            source_type="manual",
            source_id="approval-1",
            source_table="manual_test",
            scheduled_for=datetime.now(timezone.utc),
            target_external_userids=["wm_1"],
            target_summary="1 user",
            content_type="text",
            content_payload={"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
            content_summary="hi",
            requires_approval=True,
        )
        assert queue_service.approve_job(waiting, approved_by="alice") is True
        queued = queue_service.enqueue_job(
            source_type="manual",
            source_id="cancel-1",
            source_table="manual_cancel",
            scheduled_for=datetime.now(timezone.utc),
            target_external_userids=["wm_2"],
            target_summary="1 user",
            content_type="text",
            content_payload={"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
            content_summary="hi",
        )
        assert queue_service.cancel_job(queued, cancelled_by="alice", reason="reschedule") is True
        due = queue_service.enqueue_job(
            source_type="manual",
            source_id="sent-1",
            source_table="manual_sent",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=["wm_3"],
            target_summary="1 user",
            content_type="text",
            content_payload={"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
            content_summary="hi",
        )
        queue_service.claim_due_jobs(limit=10, now=datetime.now(timezone.utc))
        queue_service.mark_sent(due, outbound_task_id=123, sent_count=1)
        approved_events = [event["event_type"] for event in queue_repo.list_broadcast_job_events(waiting)]
        cancelled_events = [event["event_type"] for event in queue_repo.list_broadcast_job_events(queued)]
        sent_events = [event["event_type"] for event in queue_repo.list_broadcast_job_events(due)]

        def fail_event_insert(**kwargs):
            raise RuntimeError("event store down")

        monkeypatch.setattr(queue_repo, "insert_broadcast_job_event", fail_event_insert)
        safe_id = queue_service.enqueue_job(
            source_type="manual",
            source_id="event-failure",
            source_table="manual_event_failure",
            scheduled_for=datetime.now(timezone.utc),
            target_external_userids=["wm_4"],
            target_summary="1 user",
            content_type="text",
            content_payload={"fn_name": "send_text", "wecom_payload": {"content": "hi"}},
            content_summary="hi",
        )
        safe_job = queue_service.get_job(safe_id)

    assert "approved" in approved_events
    assert "cancelled" in cancelled_events
    assert "sent" in sent_events
    assert safe_job["status"] == "queued"
