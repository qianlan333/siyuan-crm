"""broadcast_jobs domain — service / repo 行为契约。

覆盖：
- enqueue_job 状态分支（queued vs waiting_approval）
- claim_due_jobs 只拉到期且 queued 的
- mark_sent / mark_failed / cancel_job / approve_job 的状态流转
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wecom_ability_service.domains.broadcast_jobs import service as queue_service


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


def _enqueue(
    *,
    scheduled_for=None,
    requires_approval=False,
    source_type="manual",
    source_id="1",
    target_users=("wm_a", "wm_b"),
    content_payload=None,
):
    return queue_service.enqueue_job(
        source_type=source_type,
        source_id=source_id,
        source_table="manual_test",
        scheduled_for=scheduled_for or datetime.now(timezone.utc),
        target_external_userids=list(target_users),
        target_summary=f"测试组 {len(target_users)} 人",
        content_type="text",
        content_payload=content_payload or {"fn_name": "send_text", "wecom_payload": {"content": "hello"}},
        content_summary="测试文案",
        requires_approval=requires_approval,
        trace_id="trace-test",
        created_by="pytest",
    )


def test_enqueue_default_status_queued(app):
    with app.app_context():
        job_id = _enqueue()
        job = queue_service.get_job(job_id)
        assert job is not None
        assert job["status"] == "queued"
        assert job["requires_approval"] is False
        assert job["target_count"] == 2
        assert job["target_external_userids"] == ["wm_a", "wm_b"]


def test_enqueue_with_approval_goes_to_waiting(app):
    with app.app_context():
        job_id = _enqueue(requires_approval=True)
        job = queue_service.get_job(job_id)
        assert job["status"] == "waiting_approval"
        assert job["requires_approval"] is True


def test_enqueue_rejects_empty_targets(app):
    with app.app_context():
        with pytest.raises(ValueError, match="target_external_userids"):
            _enqueue(target_users=())


def test_enqueue_allows_empty_targets_when_handler_resolves_later(app):
    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="workflow",
            source_id="pre-scheduled-workflow-1",
            source_table="automation_workflow_executions",
            scheduled_for=datetime.now(timezone.utc),
            target_external_userids=[],
            target_summary="workflow node=1 — ~12 人",
            content_type="private_message",
            content_payload={"workflow_id": 1, "node_id": 1, "pre_scheduled": True},
            content_summary="明日任务流",
            allow_empty_targets=True,
        )
        job = queue_service.get_job(job_id)

    assert job is not None
    assert job["target_count"] == 0
    assert job["target_external_userids"] == []
    assert job["target_summary"] == "workflow node=1 — ~12 人"


def test_enqueue_rejects_invalid_source_type(app):
    with app.app_context():
        with pytest.raises(ValueError, match="source_type"):
            _enqueue(source_type="invalid_source")


def test_claim_due_only_pulls_queued_and_due(app):
    with app.app_context():
        now = datetime.now(timezone.utc)
        due_id = _enqueue(scheduled_for=now - timedelta(minutes=1), source_id="due-1")
        future_id = _enqueue(scheduled_for=now + timedelta(hours=1), source_id="future-1")
        approval_id = _enqueue(
            scheduled_for=now - timedelta(minutes=1),
            requires_approval=True,
            source_id="appr-1",
        )

        claimed = queue_service.claim_due_jobs(limit=10, now=now)
        ids = {j["id"] for j in claimed}
        assert due_id in ids
        assert future_id not in ids
        assert approval_id not in ids
        for j in claimed:
            assert j["status"] == "claimed"


def test_claim_due_order_is_scheduled_priority_id(app):
    with app.app_context():
        now = datetime.now(timezone.utc)
        later = _enqueue(scheduled_for=now - timedelta(minutes=1), source_id="later", content_payload={"fn_name": "send_text", "wecom_payload": {"content": "later"}})
        high_priority = _enqueue(scheduled_for=now - timedelta(minutes=3), source_id="high-priority", content_payload={"fn_name": "send_text", "wecom_payload": {"content": "high"}})
        same_time_first = _enqueue(scheduled_for=now - timedelta(minutes=2), source_id="same-first", content_payload={"fn_name": "send_text", "wecom_payload": {"content": "first"}})
        same_time_second = _enqueue(scheduled_for=now - timedelta(minutes=2), source_id="same-second", content_payload={"fn_name": "send_text", "wecom_payload": {"content": "second"}})
        from wecom_ability_service.db import get_db

        get_db().execute("UPDATE broadcast_jobs SET priority = 10 WHERE id = ?", (int(high_priority),))
        get_db().execute("UPDATE broadcast_jobs SET priority = 1 WHERE id = ?", (int(same_time_second),))
        get_db().commit()

        claimed = queue_service.claim_due_jobs(limit=10, now=now)

    assert [item["id"] for item in claimed] == [high_priority, same_time_second, same_time_first, later]


def test_mark_sent_updates_status_and_records_outbound(app):
    with app.app_context():
        now = datetime.now(timezone.utc)
        job_id = _enqueue(scheduled_for=now - timedelta(minutes=1))
        queue_service.claim_due_jobs(limit=10, now=now)
        queue_service.mark_sent(job_id, outbound_task_id=987, sent_count=2)
        job = queue_service.get_job(job_id)
        assert job["status"] == "sent"
        assert job["outbound_task_id"] == 987
        assert job["sent_count"] == 2
        assert job["last_error"] == ""


def test_mark_failed_records_error(app):
    with app.app_context():
        now = datetime.now(timezone.utc)
        job_id = _enqueue(scheduled_for=now - timedelta(minutes=1))
        queue_service.claim_due_jobs(limit=10, now=now)
        queue_service.mark_failed(job_id, error="wecom api 401")
        job = queue_service.get_job(job_id)
        assert job["status"] == "failed"
        assert "wecom api 401" in job["last_error"]


def test_recover_stale_claimed_jobs_restores_only_leased_unfinished_claims(app):
    with app.app_context():
        now = datetime.now(timezone.utc)
        stale_id = _enqueue(scheduled_for=now - timedelta(minutes=20), source_id="stale")
        legacy_id = _enqueue(scheduled_for=now - timedelta(minutes=20), source_id="legacy")
        fresh_id = _enqueue(scheduled_for=now - timedelta(minutes=1), source_id="fresh")
        sent_like_id = _enqueue(scheduled_for=now - timedelta(minutes=20), source_id="sent-like")
        queue_service.claim_due_jobs(
            limit=10,
            now=now - timedelta(minutes=20),
            claim_token="pytest-lease",
        )
        from wecom_ability_service.db import get_db

        db = get_db()
        db.execute(
            "UPDATE broadcast_jobs SET claimed_at = ? WHERE id IN (?, ?, ?)",
            (
                (now - timedelta(minutes=20)).isoformat(),
                int(stale_id),
                int(legacy_id),
                int(sent_like_id),
            ),
        )
        db.execute(
            "UPDATE broadcast_jobs SET claim_token = '' WHERE id = ?",
            (int(legacy_id),),
        )
        db.commit()
        queue_service.mark_sent(sent_like_id, outbound_task_id=123, sent_count=1)
        queue_service.claim_due_jobs(limit=10, now=now)

        recovered = queue_service.recover_stale_claimed_jobs(
            older_than_seconds=900,
            now=now,
            limit=10,
        )

        requeued_ids = {
            int(item["id"])
            for item in recovered["requeued_without_outbound"]
        }
        assert stale_id in requeued_ids
        assert legacy_id not in requeued_ids
        assert fresh_id not in requeued_ids
        assert sent_like_id not in requeued_ids
        assert queue_service.get_job(stale_id)["status"] == "queued"
        assert queue_service.get_job(legacy_id)["status"] == "claimed"
        assert queue_service.get_job(fresh_id)["status"] == "claimed"
        assert queue_service.get_job(sent_like_id)["status"] == "sent"


def test_cancel_queued_job_marks_cancelled(app):
    with app.app_context():
        job_id = _enqueue()
        ok = queue_service.cancel_job(job_id, cancelled_by="alice", reason="reschedule")
        assert ok is True
        job = queue_service.get_job(job_id)
        assert job["status"] == "cancelled"
        assert job["cancelled_by"] == "alice"
        assert job["cancel_reason"] == "reschedule"


def test_cancel_already_sent_job_is_noop(app):
    with app.app_context():
        now = datetime.now(timezone.utc)
        job_id = _enqueue(scheduled_for=now - timedelta(minutes=1))
        queue_service.claim_due_jobs(limit=10, now=now)
        queue_service.mark_sent(job_id, outbound_task_id=1, sent_count=1)
        ok = queue_service.cancel_job(job_id, cancelled_by="alice", reason="oops")
        assert ok is False
        job = queue_service.get_job(job_id)
        assert job["status"] == "sent"


def test_approve_waiting_job_makes_it_queued(app):
    with app.app_context():
        job_id = _enqueue(requires_approval=True)
        ok = queue_service.approve_job(job_id, approved_by="bob")
        assert ok is True
        job = queue_service.get_job(job_id)
        assert job["status"] == "queued"
        assert job["approved_by"] == "bob"


def test_approve_non_waiting_job_is_noop(app):
    with app.app_context():
        job_id = _enqueue()
        ok = queue_service.approve_job(job_id, approved_by="bob")
        assert ok is False


def test_list_jobs_filters_by_status_and_source(app):
    with app.app_context():
        _enqueue(source_type="campaign", source_id="c1")
        _enqueue(source_type="cloud_plan", source_id="cp1", requires_approval=True)
        _enqueue(source_type="manual", source_id="m1")
        only_campaign = queue_service.list_jobs(source_types=["campaign"])
        assert {j["source_id"] for j in only_campaign} == {"c1"}
        only_waiting = queue_service.list_jobs(statuses=["waiting_approval"])
        assert {j["source_id"] for j in only_waiting} == {"cp1"}
