from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aicrm_next.background_jobs.broadcast_queue_worker as worker
from aicrm_next.background_jobs.broadcast_queue_worker import PostgresBroadcastQueueRepository, run_broadcast_queue_worker


class FakeRepo:
    def __init__(self, jobs: list[dict[str, Any]] | None = None) -> None:
        self.jobs = jobs or []
        self.sent: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        return self.jobs[:limit]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0, claim_token: str = "") -> None:
        self.sent.append({"job_id": job_id, "outbound_task_id": outbound_task_id, "sent_count": sent_count, "failed_count": failed_count, "claim_token": claim_token})

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error", claim_token: str = "") -> None:
        self.failed.append({"job_id": job_id, "error": error, "failure_type": failure_type, "claim_token": claim_token})


class SuccessDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "outbound_task_id": 555, "sent_count": 3}


class FailureDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "wecom api 401 invalid token"}


def _job() -> dict[str, Any]:
    return {"id": 1, "source_type": "manual", "target_unionids_json": ["union_a", "union_b", "union_c"]}


def test_worker_dispatches_due_job_and_marks_sent() -> None:
    repo = FakeRepo([_job()])

    summary = run_broadcast_queue_worker(
        limit=10,
        repo=repo,
        dispatcher=SuccessDispatcher(),
        now=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )

    assert summary["claimed"] == 1
    assert summary["sent_ok"] == 1
    assert summary["sent_failed"] == 0
    assert repo.sent[0]["job_id"] == 1
    assert repo.sent[0]["claim_token"]


def test_worker_marks_failed_when_dispatch_fails() -> None:
    repo = FakeRepo([_job()])

    summary = run_broadcast_queue_worker(limit=10, repo=repo, dispatcher=FailureDispatcher())

    assert summary["sent_ok"] == 0
    assert summary["sent_failed"] == 1
    assert "401" in repo.failed[0]["error"]


def test_postgres_mark_failed_syncs_cloud_plan_recipient_state(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, params: tuple[Any, ...]) -> None:
            calls.append({"sql": sql, "params": params})

    monkeypatch.setattr(worker, "connect", lambda: FakeConnection())

    PostgresBroadcastQueueRepository().mark_failed(42, error="not external contact", failure_type="wecom_api_error")

    assert len(calls) == 4
    assert "UPDATE broadcast_jobs" in calls[0]["sql"]
    assert calls[0]["params"] == (False, "wecom_api_error", "not external contact", False, 300, 42, "", "")
    assert "UPDATE cloud_broadcast_plan_recipients" in calls[1]["sql"]
    assert calls[1]["params"] == ("not external contact", 42, "", "")
    assert "UPDATE cloud_broadcast_plan_recipient_messages" in calls[2]["sql"]
    assert calls[2]["params"] == ("not external contact", 42, "", "")
    assert "SET claim_token = ''" in calls[3]["sql"]
    assert calls[3]["params"] == (42, "", "")


def test_worker_no_due_jobs_returns_empty_summary() -> None:
    summary = run_broadcast_queue_worker(limit=10, repo=FakeRepo([]), dispatcher=SuccessDispatcher())

    assert summary["claimed"] == 0
    assert summary["sent_ok"] == 0
    assert summary["sent_failed"] == 0
    assert summary["results"] == []
