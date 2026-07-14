from __future__ import annotations

import os
from datetime import timedelta
from threading import Event, Thread
from typing import Any
from uuid import uuid4

import pytest

from aicrm_next.platform_foundation.external_effects.adapters import ExternalEffectAdapterRegistry
from aicrm_next.platform_foundation.external_effects.models import (
    WEBHOOK_GENERIC_PUSH,
    ExternalEffectDispatchResult,
    utcnow,
)
from aicrm_next.platform_foundation.external_effects.repo import (
    InMemoryExternalEffectRepository,
    SQLAlchemyExternalEffectRepository,
)
from aicrm_next.platform_foundation.external_effects.service import ExternalEffectService
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.shared.db_session import get_session_factory


def _database_url() -> str:
    return str(os.getenv("AICRM_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _plan(repo, *, key: str, adapter_name: str = "test_adapter") -> dict[str, Any]:
    return ExternalEffectService(repo).plan_effect(
        effect_type=WEBHOOK_GENERIC_PUSH,
        adapter_name=adapter_name,
        operation="post",
        target_type="test_target",
        target_id=key,
        payload={"body": {"key": key}},
        business_type="r07_test",
        business_id=key,
        source_module="tests.test_external_effect_delivery_lease",
        idempotency_key=key,
        execution_mode="execute",
        status="queued",
    )


def _registry(adapter: Any) -> ExternalEffectAdapterRegistry:
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["test_adapter"] = adapter  # type: ignore[attr-defined]
    return registry


class _StaticAdapter:
    def __init__(self, result: ExternalEffectDispatchResult) -> None:
        self.result = result
        self.calls = 0

    def dispatch(self, job) -> ExternalEffectDispatchResult:
        self.calls += 1
        return self.result


def _success_result() -> ExternalEffectDispatchResult:
    return ExternalEffectDispatchResult(
        status="succeeded",
        adapter_mode="execute",
        request_summary={"operation": "post"},
        response_summary={"status_code": 200, "real_external_call_executed": True},
        real_external_call_executed=True,
        provider_result_received=True,
    )


def test_fake_success_is_persisted_as_simulated_without_provider_success() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan(repo, key="r07-fake-simulated")
    adapter = _StaticAdapter(
        ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="fake",
            response_summary={"mode": "fake", "real_external_call_executed": False},
            real_external_call_executed=False,
        )
    )

    result = ExternalEffectWorker(repo, _registry(adapter), locked_by="worker-fake").dispatch_one(job["id"])
    updated = repo.get_job(job["id"])
    attempts = repo.list_attempts(job["id"])

    assert result["ok"] is True
    assert adapter.calls == 1
    assert updated is not None
    assert updated.status == "simulated"
    assert updated.side_effect_executed is False
    assert updated.provider_result_received is False
    assert attempts[0].status == "simulated"


def test_dry_run_is_reported_as_skipped_without_mutating_job_or_attempts() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan(repo, key="r07-dry-run-skipped")
    before = repo.get_job(job["id"])

    result = ExternalEffectWorker(repo, locked_by="worker-preview").run_due(batch_size=1, dry_run=True)

    assert result["counts"]["candidate_count"] == 1
    assert result["counts"]["skipped_count"] == 1
    assert result["counts"]["processed_count"] == 0
    assert result["items"][0]["dispatch_status"] == "skipped"
    assert result["items"][0]["preview_only"] is True
    assert result["real_external_call_executed"] is False
    assert repo.get_job(job["id"]) == before
    assert repo.list_attempts(job["id"]) == []


def test_success_requires_real_execution_and_provider_evidence() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan(repo, key="r07-success-without-evidence")
    adapter = _StaticAdapter(
        ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            response_summary={"real_external_call_executed": True},
            real_external_call_executed=True,
            provider_result_received=False,
        )
    )

    result = ExternalEffectWorker(repo, _registry(adapter), locked_by="worker-missing-evidence").dispatch_one(job["id"])
    updated = repo.get_job(job["id"])

    assert result["ok"] is False
    assert updated is not None
    assert updated.status == "unknown_after_dispatch"
    assert updated.reconciliation_required is True
    assert updated.side_effect_executed is True
    assert updated.provider_result_received is False


def test_timeout_after_dispatch_becomes_unknown_and_is_not_due_again() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan(repo, key="r07-timeout-unknown")
    adapter = _StaticAdapter(
        ExternalEffectDispatchResult(
            status="failed_retryable",
            adapter_mode="execute",
            response_summary={"real_external_call_executed": True},
            error_code="timeout",
            error_message="provider response timed out",
            real_external_call_executed=True,
        )
    )

    ExternalEffectWorker(repo, _registry(adapter), locked_by="worker-timeout").dispatch_one(job["id"])
    updated = repo.get_job(job["id"])

    assert updated is not None
    assert updated.status == "unknown_after_dispatch"
    assert repo.list_due_jobs(limit=10) == []
    assert adapter.calls == 1


def test_provider_rejection_with_response_remains_safely_retryable() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan(repo, key="r07-http-500-retryable")
    adapter = _StaticAdapter(
        ExternalEffectDispatchResult(
            status="failed_retryable",
            adapter_mode="execute",
            response_summary={"status_code": 500, "real_external_call_executed": True},
            error_code="http_5xx",
            error_message="provider rejected request",
            real_external_call_executed=True,
            provider_result_received=True,
        )
    )

    ExternalEffectWorker(repo, _registry(adapter), locked_by="worker-500").dispatch_one(job["id"])
    updated = repo.get_job(job["id"])

    assert updated is not None
    assert updated.status == "failed_retryable"
    assert updated.next_retry_at
    assert updated.reconciliation_required is False


class _BlockingAdapter:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.calls = 0

    def dispatch(self, job) -> ExternalEffectDispatchResult:
        self.calls += 1
        self.entered.set()
        assert self.release.wait(timeout=5)
        return _success_result()


def test_realtime_and_worker_share_one_claim_provider_call_at_most_once() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan(repo, key="r07-concurrent-claim")
    adapter = _BlockingAdapter()
    registry = _registry(adapter)
    first_result: dict[str, Any] = {}

    def run_first() -> None:
        first_result.update(
            ExternalEffectWorker(repo, registry, locked_by="worker-a").dispatch_one(job["id"])
        )

    thread = Thread(target=run_first)
    thread.start()
    assert adapter.entered.wait(timeout=5)
    second = ExternalEffectWorker(repo, registry, locked_by="worker-b").dispatch_one(job["id"])
    adapter.release.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert first_result["job"]["status"] == "succeeded"
    assert second["error"] == "not_claimed"
    assert adapter.calls == 1
    assert len(repo.list_attempts(job["id"])) == 1


def test_explicit_dispatch_uses_shared_claim_and_may_override_future_schedule() -> None:
    repo = InMemoryExternalEffectRepository()
    job = ExternalEffectService(repo).plan_effect(
        effect_type=WEBHOOK_GENERIC_PUSH,
        adapter_name="test_adapter",
        operation="post",
        target_type="test_target",
        target_id="future-explicit-dispatch",
        idempotency_key="r07-future-explicit-dispatch",
        scheduled_at=utcnow() + timedelta(hours=1),
        status="queued",
        execution_mode="execute",
    )
    adapter = _StaticAdapter(_success_result())

    assert repo.list_due_jobs(limit=10) == []
    result = ExternalEffectWorker(repo, _registry(adapter), locked_by="trusted-explicit-worker").dispatch_one(job["id"])

    assert result["ok"] is True
    assert result["job"]["status"] == "succeeded"
    assert adapter.calls == 1


class _LoseLeaseOnCompleteRepository(InMemoryExternalEffectRepository):
    def complete_dispatch(self, *, job, result, next_retry_at=None):
        row = self._find(job.id)
        assert row is not None
        row["lease_token"] = "eel_new_owner"
        row["locked_by"] = "worker-new"
        return super().complete_dispatch(job=job, result=result, next_retry_at=next_retry_at)


def test_lost_lease_writes_neither_attempt_nor_result() -> None:
    repo = _LoseLeaseOnCompleteRepository()
    job = _plan(repo, key="r07-lost-lease")
    adapter = _StaticAdapter(_success_result())

    result = ExternalEffectWorker(repo, _registry(adapter), locked_by="worker-old").dispatch_one(job["id"])
    updated = repo.get_job(job["id"])

    assert result["error"] == "lost_lease"
    assert adapter.calls == 1
    assert repo.list_attempts(job["id"]) == []
    assert updated is not None
    assert updated.status == "dispatching"
    assert updated.lease_token == "eel_new_owner"


class _FailResultPersistenceRepository(InMemoryExternalEffectRepository):
    def complete_dispatch(self, *, job, result, next_retry_at=None):
        raise RuntimeError("injected result persistence failure")


def test_provider_success_then_result_persistence_failure_is_unknown_not_retried() -> None:
    repo = _FailResultPersistenceRepository()
    job = _plan(repo, key="r07-result-persistence-failure")
    adapter = _StaticAdapter(_success_result())

    result = ExternalEffectWorker(repo, _registry(adapter), locked_by="worker-persist").dispatch_one(job["id"])
    updated = repo.get_job(job["id"])

    assert result["error"] == "result_persistence_failed"
    assert adapter.calls == 1
    assert updated is not None
    assert updated.status == "unknown_after_dispatch"
    assert updated.reconciliation_required is True
    assert repo.list_due_jobs(limit=10) == []
    assert repo.list_attempts(job["id"]) == []


def test_stale_dispatching_is_quarantined_instead_of_requeued() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan(repo, key="r07-stale-dispatching")
    claimed = repo.acquire_job(job["id"], locked_by="worker-crashed")
    assert claimed is not None
    row = repo._find(job["id"])
    assert row is not None
    row["lease_expires_at"] = "2000-01-01T00:00:00Z"

    count = repo.quarantine_stale_dispatching()
    updated = repo.get_job(job["id"])

    assert count == 1
    assert updated is not None
    assert updated.status == "unknown_after_dispatch"
    assert updated.reconciliation_required is True
    assert repo.list_due_jobs(limit=10) == []


def test_unknown_dispatch_requires_explicit_duplicate_risk_acknowledgement_to_retry() -> None:
    repo = InMemoryExternalEffectRepository()
    service = ExternalEffectService(repo)
    job = _plan(repo, key="r07-unknown-manual-retry")
    claimed = repo.acquire_job(job["id"], locked_by="worker-unknown")
    assert claimed is not None
    updated = repo.mark_dispatch_unknown(
        job=claimed,
        error_code="timeout",
        error_message="provider result unknown",
        side_effect_executed=True,
    )
    assert updated is not None

    assert service.retry(job["id"]) is None
    assert service.retry(job["id"], actor="operator", reason="checked provider") is None
    assert service.retry(job["id"], actor="", reason="checked provider", confirm_duplicate_risk=True) is None
    assert service.enqueue(job["id"]) is None
    assert service.approve(job["id"]) is None
    assert repo.get_job(job["id"]).status == "unknown_after_dispatch"  # type: ignore[union-attr]

    retried = service.retry(
        job["id"],
        actor="operator",
        reason="provider confirms no delivery",
        confirm_duplicate_risk=True,
    )

    assert retried is not None
    assert retried.status == "queued"
    attempts = repo.list_attempts(job["id"])
    assert len(attempts) == 1
    assert attempts[0].status == "skipped"
    assert attempts[0].adapter_mode == "manual_retry_authorization"
    assert attempts[0].request_summary_json["confirm_duplicate_risk"] is True
    assert attempts[0].response_summary_json["real_external_call_executed"] is False


@pytest.mark.skipif(not _database_url(), reason="PostgreSQL integration database is not configured")
def test_postgres_concurrent_claim_has_one_winner_and_lease_cas() -> None:
    database_url = _database_url()
    repo = SQLAlchemyExternalEffectRepository(get_session_factory(database_url))
    key = "r07-postgres-claim-" + uuid4().hex
    job = _plan(repo, key=key)
    results: list[Any] = []

    def claim(worker: str) -> None:
        results.append(repo.acquire_job(job["id"], locked_by=worker))

    first = Thread(target=claim, args=("pg-worker-a",))
    second = Thread(target=claim, args=("pg-worker-b",))
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    winners = [item for item in results if item is not None]
    assert len(winners) == 1
    winner = winners[0]
    completed = repo.complete_dispatch(job=winner, result=_success_result())
    assert completed is not None
    updated, attempt = completed
    assert updated.status == "succeeded"
    assert updated.side_effect_executed is True
    assert updated.provider_result_received is True
    assert attempt.status == "succeeded"
