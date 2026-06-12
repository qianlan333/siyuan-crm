from __future__ import annotations

from datetime import datetime, timezone

from aicrm_next.background_jobs.broadcast_queue_worker import run_broadcast_queue_worker


class EmptyRepo:
    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict]:
        return []

    def mark_sent(self, job_id: int, *, outbound_task_id=None, sent_count: int = 0, failed_count: int = 0) -> None:
        raise AssertionError("no job should be sent")

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error") -> None:
        raise AssertionError("no job should fail")


def test_send_task_worker_empty_queue_is_successful_noop() -> None:
    result = run_broadcast_queue_worker(
        limit=10,
        repo=EmptyRepo(),
        dispatcher=object(),
        now=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert result["claimed"] == 0
    assert result["sent_ok"] == 0
    assert result["errors"] == []
