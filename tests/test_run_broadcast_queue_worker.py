from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aicrm_next.background_jobs.broadcast_queue_worker import run_broadcast_queue_worker


class FakeRepo:
    def __init__(self, jobs: list[dict[str, Any]] | None = None) -> None:
        self.jobs = jobs or []
        self.sent: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []

    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        return self.jobs[:limit]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0) -> None:
        self.sent.append({"job_id": job_id, "outbound_task_id": outbound_task_id, "sent_count": sent_count, "failed_count": failed_count})

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error") -> None:
        self.failed.append({"job_id": job_id, "error": error, "failure_type": failure_type})


class SuccessDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "outbound_task_id": 555, "sent_count": 3}


class FailureDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": "wecom api 401 invalid token"}


def _job() -> dict[str, Any]:
    return {"id": 1, "source_type": "manual", "target_external_userids": ["wm_a", "wm_b", "wm_c"]}


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
    assert repo.sent == [{"job_id": 1, "outbound_task_id": 555, "sent_count": 3, "failed_count": 0}]


def test_worker_marks_failed_when_dispatch_fails() -> None:
    repo = FakeRepo([_job()])

    summary = run_broadcast_queue_worker(limit=10, repo=repo, dispatcher=FailureDispatcher())

    assert summary["sent_ok"] == 0
    assert summary["sent_failed"] == 1
    assert "401" in repo.failed[0]["error"]


def test_worker_no_due_jobs_returns_empty_summary() -> None:
    summary = run_broadcast_queue_worker(limit=10, repo=FakeRepo([]), dispatcher=SuccessDispatcher())

    assert summary["claimed"] == 0
    assert summary["sent_ok"] == 0
    assert summary["sent_failed"] == 0
    assert summary["results"] == []
