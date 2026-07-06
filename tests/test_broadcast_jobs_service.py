from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from aicrm_next.background_jobs import broadcast_queue_worker
from aicrm_next.background_jobs.broadcast_queue_worker import PostgresBroadcastQueueRepository, run_broadcast_queue_worker


class FakeBroadcastRepo:
    def __init__(self) -> None:
        self.jobs = [
            {
                "id": 101,
                "source_type": "manual",
                "target_unionids_json": ["union_a", "union_b"],
                "scheduled_for": datetime.now(timezone.utc) - timedelta(minutes=1),
            }
        ]
        self.sent: list[dict[str, Any]] = []
        self.failed: list[dict[str, Any]] = []
        self.claims: list[dict[str, Any]] = []

    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        self.claims.append({"limit": limit, "now": now, "claim_token": claim_token, "lease_seconds": lease_seconds})
        return self.jobs[:limit]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0, claim_token: str = "") -> None:
        self.sent.append({"job_id": job_id, "outbound_task_id": outbound_task_id, "sent_count": sent_count, "failed_count": failed_count, "claim_token": claim_token})

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error", claim_token: str = "") -> None:
        self.failed.append({"job_id": job_id, "error": error, "failure_type": failure_type, "claim_token": claim_token})


class FakeDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "outbound_task_id": 8801, "sent_count": len(job["target_unionids_json"])}


class SkippedDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "status": "skipped", "reason": "adapter_disabled"}


class SometimesBrokenDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        if int(job["id"]) == 101:
            raise RuntimeError("temporary wecom failure")
        return {"ok": True, "outbound_task_id": 8802, "sent_count": len(job["target_unionids_json"])}


def test_broadcast_worker_claims_due_jobs_and_marks_sent() -> None:
    repo = FakeBroadcastRepo()

    result = run_broadcast_queue_worker(limit=10, repo=repo, dispatcher=FakeDispatcher())

    assert result["ok"] is True
    assert result["claimed"] == 1
    assert result["sent_ok"] == 1
    assert result["sent_failed"] == 0
    assert repo.sent == [{"job_id": 101, "outbound_task_id": 8801, "sent_count": 2, "failed_count": 0, "claim_token": repo.claims[0]["claim_token"]}]
    assert repo.claims[0]["lease_seconds"] > 0


def test_broadcast_worker_records_structured_skip_without_external_send() -> None:
    repo = FakeBroadcastRepo()

    result = run_broadcast_queue_worker(limit=10, repo=repo, dispatcher=SkippedDispatcher())

    assert result["ok"] is True
    assert result["skipped"] == 1
    assert result["sent_failed"] == 1
    assert repo.failed == [{"job_id": 101, "error": "adapter_disabled", "failure_type": "next_native_dispatch_skipped", "claim_token": repo.claims[0]["claim_token"]}]


def test_broadcast_worker_continues_after_per_job_dispatch_exception() -> None:
    repo = FakeBroadcastRepo()
    repo.jobs.append(
        {
            "id": 102,
            "source_type": "manual",
            "target_unionids_json": ["union_c"],
            "scheduled_for": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
    )

    result = run_broadcast_queue_worker(limit=10, repo=repo, dispatcher=SometimesBrokenDispatcher())

    assert result["ok"] is True
    assert result["claimed"] == 2
    assert result["sent_failed"] == 1
    assert result["sent_ok"] == 1
    assert repo.failed == [{"job_id": 101, "error": "temporary wecom failure", "failure_type": "handler_exception", "claim_token": repo.claims[0]["claim_token"]}]
    assert repo.sent == [{"job_id": 102, "outbound_task_id": 8802, "sent_count": 1, "failed_count": 0, "claim_token": repo.claims[0]["claim_token"]}]


def test_postgres_broadcast_claim_reclaims_expired_and_retryable_jobs(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append({"sql": sql, "params": params})
            return SimpleNamespace(fetchall=lambda: [])

    monkeypatch.setattr(broadcast_queue_worker, "connect", lambda: FakeConn())

    PostgresBroadcastQueueRepository().claim_due_jobs(
        limit=5,
        now=datetime(2026, 7, 4, tzinfo=timezone.utc),
        claim_token="claim-token",
        lease_seconds=900,
    )

    sql = calls[0]["sql"]
    assert "status = 'queued'" in sql
    assert "status = 'claimed'" in sql
    assert "lease_expires_at <= %s" in sql
    assert "status = 'failed_retryable'" in sql
    assert "next_retry_at IS NULL OR next_retry_at <= %s" in sql


def test_broadcast_worker_rejects_invalid_limit() -> None:
    result = run_broadcast_queue_worker(limit=0, repo=FakeBroadcastRepo(), dispatcher=FakeDispatcher())

    assert result["ok"] is False
    assert result["errors"][0]["code"] == "invalid_limit"
