from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any
from uuid import uuid4


from aicrm_next.platform_foundation.external_calls import scrub_summary

from .models import (
    DEFAULT_TENANT_ID,
    ExternalEffectAttempt,
    ExternalEffectCreateRequest,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
    ExternalEffectTestReceipt,
    public_datetime,
    utcnow,
)

from .repo import (
    ExternalEffectRepository,
    _idempotency_key,
    _initial_status,
    _payload_summary,
    _public_attempt,
    _public_job,
    _public_receipt,
    _safe_error_message,
    _text,
)


class InMemoryExternalEffectRepository(ExternalEffectRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: list[dict[str, Any]] = []
        self._attempts: list[dict[str, Any]] = []
        self._receipts: list[dict[str, Any]] = []
        self._next_id = 1
        self._next_attempt_id = 1
        self._next_receipt_id = 1

    def create_job(self, request: ExternalEffectCreateRequest) -> ExternalEffectJob:
        key = _idempotency_key(request)
        tenant_id = _text(request.tenant_id) or DEFAULT_TENANT_ID
        for row in self._jobs:
            if row["tenant_id"] == tenant_id and row["idempotency_key"] == key:
                job = _public_job({**row, "created_on_plan": False})
                assert job is not None
                return job
        now = utcnow()
        payload_summary = dict(request.payload_summary or {}) or _payload_summary(request.payload)
        row = {
            "id": self._next_id,
            "tenant_id": tenant_id,
            "effect_type": _text(request.effect_type),
            "adapter_name": _text(request.adapter_name),
            "operation": _text(request.operation),
            "target_type": _text(request.target_type),
            "target_id": _text(request.target_id),
            "business_type": _text(request.business_type),
            "business_id": _text(request.business_id),
            "source_module": _text(request.source_module),
            "source_route": _text(request.context.source_route),
            "source_event_id": _text(request.source_event_id),
            "source_command_id": _text(request.source_command_id),
            "trace_id": _text(request.context.trace_id),
            "request_id": _text(request.context.request_id),
            "correlation_id": _text(request.correlation_id),
            "idempotency_key": key,
            "actor_id": _text(request.context.actor_id),
            "actor_type": _text(request.context.actor_type) or "system",
            "risk_level": _text(request.risk_level) or "medium",
            "requires_approval": bool(request.requires_approval),
            "execution_mode": _text(request.execution_mode) or "execute",
            "payload_json": dict(request.payload or {}),
            "payload_summary_json": payload_summary,
            "status": _initial_status(request),
            "priority": int(request.priority or 100),
            "scheduled_at": public_datetime(request.scheduled_at or now),
            "attempt_count": 0,
            "max_attempts": int(request.max_attempts or 5),
            "next_retry_at": "",
            "locked_at": "",
            "locked_by": "",
            "lease_token": "",
            "lease_expires_at": "",
            "dispatch_started_at": "",
            "last_attempt_id": "",
            "last_error_code": "",
            "last_error_message": "",
            "side_effect_executed": False,
            "provider_result_received": False,
            "result_summary_json": {},
            "reconciliation_required": False,
            "created_at": public_datetime(now),
            "updated_at": public_datetime(now),
            "approved_at": "",
            "executed_at": "",
            "completed_at": "",
            "cancelled_at": "",
        }
        self._next_id += 1
        self._jobs.append(row)
        job = _public_job({**row, "created_on_plan": True})
        assert job is not None
        return job

    def get_job(self, job_id: int) -> ExternalEffectJob | None:
        return _public_job(self._find(job_id))

    def list_jobs(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[ExternalEffectJob], int]:
        filters = dict(filters or {})
        rows = list(self._jobs)
        for key in (
            "effect_type",
            "status",
            "target_type",
            "target_id",
            "business_type",
            "business_id",
            "trace_id",
            "source_event_id",
            "source_module",
        ):
            value = _text(filters.get(key))
            if value:
                rows = [row for row in rows if _text(row.get(key)) == value]
        rows.sort(key=lambda row: (row.get("created_at") or "", int(row.get("id") or 0)), reverse=True)
        total = len(rows)
        window = rows[max(0, int(offset or 0)) : max(0, int(offset or 0)) + max(1, min(int(limit or 50), 200))]
        return [job for row in window if (job := _public_job(row)) is not None], total

    def list_attempts(self, job_id: int) -> list[ExternalEffectAttempt]:
        return [attempt for row in self._attempts if int(row.get("job_id") or 0) == int(job_id) if (attempt := _public_attempt(row)) is not None]

    def list_attempts_for_jobs(self, job_ids: list[int]) -> dict[int, list[ExternalEffectAttempt]]:
        normalized = sorted({int(job_id) for job_id in job_ids})
        grouped: dict[int, list[ExternalEffectAttempt]] = {job_id: [] for job_id in normalized}
        allowed = set(normalized)
        for row in self._attempts:
            job_id = int(row.get("job_id") or 0)
            if job_id not in allowed:
                continue
            attempt = _public_attempt(row)
            if attempt is not None:
                grouped[job_id].append(attempt)
        return grouped

    def count_jobs(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        items = [job for row in self._filtered_rows(filters or {}) if (job := _public_job(row)) is not None]
        by_status: dict[str, int] = {}
        for item in items:
            by_status[item.status] = by_status.get(item.status, 0) + 1
        total = sum(by_status.values())
        return {
            "total": total,
            "by_status": by_status,
            "planned": by_status.get("planned", 0),
            "queued": by_status.get("queued", 0),
            "blocked": by_status.get("blocked", 0),
            "simulated": by_status.get("simulated", 0),
            "unknown_after_dispatch": by_status.get("unknown_after_dispatch", 0),
            "failed": by_status.get("failed_retryable", 0) + by_status.get("failed_terminal", 0),
            "succeeded": by_status.get("succeeded", 0),
            "cancelled": by_status.get("cancelled", 0),
        }

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utcnow()
        rows = self._filtered_rows(filters or {})
        due_rows = [
            row
            for row in rows
            if row.get("status") in {"queued", "failed_retryable"}
            and self._dt(row.get("scheduled_at")) <= now
            and (not row.get("next_retry_at") or self._dt(row.get("next_retry_at")) <= now)
            and (not row.get("lease_expires_at") or self._dt(row.get("lease_expires_at")) <= now)
        ]
        queued_due = [row for row in due_rows if row.get("status") == "queued"]
        retry_due = [row for row in due_rows if row.get("status") == "failed_retryable"]
        return {
            "eligible_due_count": len(due_rows),
            "dispatching_count": len([row for row in rows if row.get("status") == "dispatching"]),
            "stale_dispatching_count": len(
                [row for row in rows if row.get("status") == "dispatching" and row.get("lease_expires_at") and self._dt(row.get("lease_expires_at")) <= now]
            ),
            "unknown_after_dispatch_count": len([row for row in rows if row.get("status") == "unknown_after_dispatch"]),
            "simulated_count": len([row for row in rows if row.get("status") == "simulated"]),
            "reconciliation_required_count": len([row for row in rows if row.get("reconciliation_required")]),
            "dispatching_without_active_lease_count": len(
                [row for row in rows if row.get("status") == "dispatching" and (not row.get("lease_token") or not row.get("lease_expires_at"))]
            ),
            "lease_on_non_dispatching_count": len(
                [row for row in rows if row.get("status") != "dispatching" and (row.get("lease_token") or row.get("lease_expires_at"))]
            ),
            "succeeded_without_evidence_count": len(
                [
                    row
                    for row in rows
                    if row.get("status") == "succeeded"
                    and (
                        (not row.get("side_effect_executed") and (row.get("result_summary_json") or {}).get("internal_side_effect_executed") is not True)
                        or not row.get("provider_result_received")
                    )
                ]
            ),
            "simulated_recorded_as_succeeded_count": len(
                [
                    row
                    for row in rows
                    if row.get("status") == "succeeded"
                    and not row.get("side_effect_executed")
                    and _text((row.get("result_summary_json") or {}).get("mode") or (row.get("result_summary_json") or {}).get("adapter_mode")).lower()
                    in {"fake", "fixture", "simulated", "test_fake"}
                ]
            ),
            "failed_retryable_count": len([row for row in rows if row.get("status") == "failed_retryable"]),
            "failed_terminal_count": len([row for row in rows if row.get("status") == "failed_terminal"]),
            "oldest_queued_age_seconds": self._oldest_age_seconds(queued_due, now, "scheduled_at"),
            "oldest_failed_retryable_age_seconds": self._oldest_age_seconds(retry_due, now, "next_retry_at", fallback_key="scheduled_at"),
        }

    def list_due_jobs(self, *, limit: int = 50, effect_types: list[str] | None = None, test_only: bool = False) -> list[ExternalEffectJob]:
        now = utcnow()
        type_set = {_text(item) for item in effect_types or [] if _text(item)}
        rows = [
            row
            for row in self._jobs
            if row.get("status") in {"queued", "failed_retryable"}
            and (not type_set or row.get("effect_type") in type_set)
            and (not test_only or (row.get("payload_json") or {}).get("execution_scope") == "test_loopback")
            and self._dt(row.get("scheduled_at")) <= now
            and (not row.get("next_retry_at") or self._dt(row.get("next_retry_at")) <= now)
            and (not row.get("lease_expires_at") or self._dt(row.get("lease_expires_at")) <= now)
        ]
        rows.sort(key=lambda row: (int(row.get("priority") or 100), row.get("scheduled_at") or "", int(row.get("id") or 0)))
        return [job for row in rows[: max(1, min(int(limit or 50), 200))] if (job := _public_job(row)) is not None]

    def acquire_due_jobs(
        self,
        *,
        limit: int = 50,
        locked_by: str,
        effect_types: list[str] | None = None,
        test_only: bool = False,
        lease_seconds: int = 300,
    ) -> list[ExternalEffectJob]:
        with self._lock:
            jobs = self.list_due_jobs(limit=limit, effect_types=effect_types, test_only=test_only)
            current = utcnow()
            now = public_datetime(current)
            expires_at = public_datetime(current + timedelta(seconds=max(30, min(int(lease_seconds or 300), 3600))))
            lease_prefix = "eel_" + uuid4().hex
            for job in jobs:
                row = self._find(job.id)
                if row:
                    row["status"] = "dispatching"
                    row["lease_token"] = f"{lease_prefix}-{job.id}"
                    row["lease_expires_at"] = expires_at
                    row["dispatch_started_at"] = now
                    row["locked_at"] = now
                    row["locked_by"] = _text(locked_by)
                    row["updated_at"] = now
            return [job for job_id in [job.id for job in jobs] if (job := self.get_job(job_id)) is not None]

    def acquire_job(self, job_id: int, *, locked_by: str, lease_seconds: int = 300) -> ExternalEffectJob | None:
        with self._lock:
            row = self._find(job_id)
            now = utcnow()
            if (
                not row
                or row.get("status") not in {"queued", "failed_retryable"}
                or (row.get("lease_expires_at") and self._dt(row.get("lease_expires_at")) > now)
            ):
                return None
            now_text = public_datetime(now)
            row.update(
                {
                    "status": "dispatching",
                    "lease_token": f"eel_{uuid4().hex}-{int(job_id)}",
                    "lease_expires_at": public_datetime(now + timedelta(seconds=max(30, min(int(lease_seconds or 300), 3600)))),
                    "dispatch_started_at": now_text,
                    "locked_at": now_text,
                    "locked_by": _text(locked_by),
                    "updated_at": now_text,
                }
            )
            return _public_job(row)

    def get_active_claim(self, job_id: int, *, lease_token: str) -> ExternalEffectJob | None:
        with self._lock:
            row = self._find(job_id)
            if (
                not row
                or row.get("status") != "dispatching"
                or _text(row.get("lease_token")) != _text(lease_token)
                or not row.get("lease_expires_at")
                or self._dt(row.get("lease_expires_at")) <= utcnow()
            ):
                return None
            return _public_job(row)

    def quarantine_stale_dispatching(self) -> int:
        with self._lock:
            current = utcnow()
            count = 0
            for row in self._jobs:
                if row.get("status") != "dispatching" or not row.get("lease_expires_at") or self._dt(row.get("lease_expires_at")) > current:
                    continue
                now = public_datetime(current)
                row.update(
                    {
                        "status": "unknown_after_dispatch",
                        "reconciliation_required": True,
                        "last_error_code": "lease_expired_after_dispatch",
                        "last_error_message": "Dispatch lease expired; reconcile provider outcome before retry.",
                        "lease_token": "",
                        "lease_expires_at": "",
                        "locked_by": "",
                        "locked_at": "",
                        "completed_at": now,
                        "updated_at": now,
                    }
                )
                count += 1
            return count

    def complete_dispatch(
        self,
        *,
        job: ExternalEffectJob,
        result: ExternalEffectDispatchResult,
        next_retry_at: datetime | None = None,
    ) -> tuple[ExternalEffectJob, ExternalEffectAttempt] | None:
        allowed = {
            "succeeded",
            "simulated",
            "unknown_after_dispatch",
            "failed_retryable",
            "failed_terminal",
            "blocked",
        }
        status = _text(result.status)
        with self._lock:
            row = self._find(job.id)
            if (
                status not in allowed
                or not row
                or row.get("status") != "dispatching"
                or not _text(job.lease_token)
                or _text(row.get("lease_token")) != _text(job.lease_token)
            ):
                return None
            response_summary = {
                **dict(result.response_summary or {}),
                "real_external_call_executed": bool(result.real_external_call_executed),
                "provider_result_received": bool(result.provider_result_received),
            }
            attempt = self.record_attempt(
                job=job,
                status=status,
                adapter_mode=result.adapter_mode,
                request_summary=dict(result.request_summary or {}),
                response_summary=response_summary,
                error_code=result.error_code,
                error_message=result.error_message,
            )
            now = public_datetime(utcnow())
            row.update(
                {
                    "status": status,
                    "attempt_count": int(row.get("attempt_count") or 0) + 1,
                    "next_retry_at": public_datetime(next_retry_at) if status == "failed_retryable" and next_retry_at else "",
                    "last_attempt_id": attempt.attempt_id,
                    "last_error_code": _text(result.error_code),
                    "last_error_message": _safe_error_message(result.error_message),
                    "side_effect_executed": bool(result.real_external_call_executed),
                    "provider_result_received": bool(result.provider_result_received),
                    "result_summary_json": scrub_summary(response_summary),
                    "reconciliation_required": status == "unknown_after_dispatch",
                    "lease_token": "",
                    "lease_expires_at": "",
                    "locked_by": "",
                    "locked_at": "",
                    "executed_at": now if status == "succeeded" else row.get("executed_at") or "",
                    "completed_at": now if status in {"succeeded", "simulated", "unknown_after_dispatch", "failed_terminal", "blocked"} else "",
                    "updated_at": now,
                }
            )
            updated = _public_job(row)
            return (updated, attempt) if updated else None

    def mark_dispatch_unknown(
        self,
        *,
        job: ExternalEffectJob,
        error_code: str,
        error_message: str,
        side_effect_executed: bool = True,
        provider_result_received: bool = False,
    ) -> ExternalEffectJob | None:
        with self._lock:
            row = self._find(job.id)
            if not row or row.get("status") != "dispatching" or not _text(job.lease_token) or _text(row.get("lease_token")) != _text(job.lease_token):
                return None
            now = public_datetime(utcnow())
            row.update(
                {
                    "status": "unknown_after_dispatch",
                    "reconciliation_required": True,
                    "side_effect_executed": bool(side_effect_executed),
                    "provider_result_received": bool(provider_result_received),
                    "last_error_code": _text(error_code) or "result_persistence_failed",
                    "last_error_message": _safe_error_message(error_message),
                    "lease_token": "",
                    "lease_expires_at": "",
                    "locked_by": "",
                    "locked_at": "",
                    "completed_at": now,
                    "updated_at": now,
                }
            )
            return _public_job(row)

    def mark_dispatching(self, job_id: int, *, locked_by: str) -> ExternalEffectJob | None:
        return self.acquire_job(job_id, locked_by=locked_by)

    def mark_succeeded(self, job_id: int, *, attempt_id: str) -> ExternalEffectJob | None:
        now = public_datetime(utcnow())
        return self._mutate(
            job_id,
            status="succeeded",
            last_attempt_id=_text(attempt_id),
            locked_by="",
            locked_at="",
            lease_token="",
            lease_expires_at="",
            executed_at=now,
            completed_at=now,
        )

    def mark_simulated(self, job_id: int, *, attempt_id: str, result_summary: dict[str, Any]) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        return self._mutate(
            job_id,
            status="simulated",
            last_attempt_id=_text(attempt_id),
            side_effect_executed=False,
            provider_result_received=False,
            result_summary_json=scrub_summary(result_summary or {}),
            reconciliation_required=False,
            locked_by="",
            locked_at="",
            lease_token="",
            lease_expires_at="",
            completed_at=public_datetime(utcnow()),
        )

    def mark_failed_retryable(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str, next_retry_at: datetime) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        return self._mutate(
            job_id,
            status="failed_retryable",
            next_retry_at=public_datetime(next_retry_at),
            last_attempt_id=_text(attempt_id),
            last_error_code=_text(error_code),
            last_error_message=_safe_error_message(error_message),
            locked_by="",
            locked_at="",
            lease_token="",
            lease_expires_at="",
        )

    def mark_failed_terminal(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        return self._mutate(
            job_id,
            status="failed_terminal",
            last_attempt_id=_text(attempt_id),
            last_error_code=_text(error_code),
            last_error_message=_safe_error_message(error_message),
            locked_by="",
            locked_at="",
            lease_token="",
            lease_expires_at="",
            completed_at=public_datetime(utcnow()),
        )

    def mark_blocked(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        return self._mutate(
            job_id,
            status="blocked",
            last_attempt_id=_text(attempt_id),
            last_error_code=_text(error_code),
            last_error_message=_safe_error_message(error_message),
            locked_by="",
            locked_at="",
            lease_token="",
            lease_expires_at="",
            completed_at=public_datetime(utcnow()),
        )

    def cancel_job(self, job_id: int) -> ExternalEffectJob | None:
        now = public_datetime(utcnow())
        return self._mutate(job_id, status="cancelled", locked_by="", locked_at="", lease_token="", lease_expires_at="", cancelled_at=now, completed_at=now)

    def enqueue_job(self, job_id: int, *, allow_unknown_after_dispatch: bool = False) -> ExternalEffectJob | None:
        with self._lock:
            row = self._find(job_id)
            allowed = {"planned", "approved", "queued", "failed_retryable", "failed_terminal", "blocked"}
            if allow_unknown_after_dispatch:
                allowed.add("unknown_after_dispatch")
            if not row or row.get("status") not in allowed:
                return None
            return self._mutate(
                job_id,
                status="queued",
                locked_by="",
                locked_at="",
                lease_token="",
                lease_expires_at="",
                next_retry_at=public_datetime(utcnow()),
                reconciliation_required=False,
                completed_at="",
            )

    def approve_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._mutate(
            job_id,
            status="queued",
            approved_at=public_datetime(utcnow()),
            locked_by="",
            locked_at="",
            lease_token="",
            lease_expires_at="",
            next_retry_at=public_datetime(utcnow()),
            reconciliation_required=False,
        )

    def record_attempt(
        self,
        *,
        job: ExternalEffectJob,
        status: str,
        adapter_mode: str,
        request_summary: dict[str, Any],
        response_summary: dict[str, Any],
        error_code: str = "",
        error_message: str = "",
    ) -> ExternalEffectAttempt:
        now = public_datetime(utcnow())
        row = {
            "id": self._next_attempt_id,
            "attempt_id": "eea_" + __import__("uuid").uuid4().hex,
            "job_id": int(job.id),
            "adapter_name": job.adapter_name,
            "adapter_mode": _text(adapter_mode) or "none",
            "operation": job.operation,
            "trace_id": job.trace_id,
            "request_id": job.request_id,
            "status": _text(status) or "skipped",
            "request_summary_json": scrub_summary(request_summary or {}),
            "response_summary_json": scrub_summary(response_summary or {}),
            "error_code": _text(error_code),
            "error_message": _safe_error_message(error_message),
            "started_at": now,
            "completed_at": now,
        }
        self._next_attempt_id += 1
        self._attempts.append(row)
        attempt = _public_attempt(row)
        assert attempt is not None
        return attempt

    def get_job_by_event_id(self, event_id: str) -> ExternalEffectJob | None:
        normalized_event_id = _text(event_id)
        for row in self._jobs:
            payload = row.get("payload_json") or {}
            if row.get("idempotency_key") == normalized_event_id and payload.get("execution_scope") == "test_loopback":
                return _public_job(row)
        return None

    def create_test_receipt(
        self,
        *,
        event_id: str,
        job: ExternalEffectJob,
        request_method: str,
        request_path: str,
        headers_summary: dict[str, Any],
        payload_summary: dict[str, Any],
        payload_hash: str,
        body_json: dict[str, Any],
        signature_valid: bool | None,
        response_status: int,
    ) -> ExternalEffectTestReceipt:
        now = public_datetime(utcnow())
        row = {
            "id": self._next_receipt_id,
            "receipt_id": "eer_" + __import__("uuid").uuid4().hex,
            "event_id": _text(event_id),
            "job_id": int(job.id),
            "effect_type": job.effect_type,
            "trace_id": job.trace_id,
            "idempotency_key": job.idempotency_key,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "business_type": job.business_type,
            "business_id": job.business_id,
            "request_method": _text(request_method) or "POST",
            "request_path": _text(request_path),
            "headers_summary_json": scrub_summary(headers_summary or {}),
            "payload_summary_json": scrub_summary(payload_summary or {}),
            "payload_hash": _text(payload_hash),
            "body_json": dict(body_json or {}),
            "signature_valid": signature_valid,
            "response_status": int(response_status or 200),
            "received_at": now,
        }
        self._next_receipt_id += 1
        self._receipts.append(row)
        receipt = _public_receipt(row)
        assert receipt is not None
        return receipt

    def list_test_receipts(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[ExternalEffectTestReceipt], int]:
        filters = dict(filters or {})
        rows = list(self._receipts)
        for key in ("job_id", "effect_type", "trace_id", "event_id"):
            value = _text(filters.get(key))
            if value:
                rows = [row for row in rows if _text(row.get(key)) == value]
        rows.sort(key=lambda row: (row.get("received_at") or "", int(row.get("id") or 0)), reverse=True)
        total = len(rows)
        window = rows[max(0, int(offset or 0)) : max(0, int(offset or 0)) + max(1, min(int(limit or 50), 200))]
        return [receipt for row in window if (receipt := _public_receipt(row)) is not None], total

    def get_test_receipt(self, receipt_id: str) -> ExternalEffectTestReceipt | None:
        for row in self._receipts:
            if row.get("receipt_id") == _text(receipt_id):
                return _public_receipt(row)
        return None

    def test_receipt_metrics(self) -> dict[str, Any]:
        now = utcnow()
        recent = [row for row in self._receipts if self._dt(row.get("received_at")) >= now - timedelta(hours=24)]
        latest = max((self._dt(row.get("received_at")) for row in self._receipts), default=None)
        return {
            "test_receipt_count_24h": len(recent),
            "latest_test_receipt_at": public_datetime(latest) if latest else "",
            "loopback_eligible_job_count": len(self.list_due_jobs(limit=200, test_only=True)),
            "non_test_execution_blocked_count": len([row for row in self._jobs if row.get("last_error_code") == "test_execution_only_required"]),
            "real_external_call_executed_to_test_receiver_count": len([row for row in recent if 200 <= int(row.get("response_status") or 0) < 300]),
        }

    def list_record_only_jobs(self, *, limit: int = 100) -> list[ExternalEffectJob]:
        rows = [
            row
            for row in self._jobs
            if int(row.get("attempt_count") or 0) == 0
            and row.get("status") not in {"succeeded", "failed_retryable", "failed_terminal", "cancelled", "expired", "dispatching"}
            and (row.get("execution_mode") in {"shadow", "plan_only", "disabled", "execute_dryrun"} or row.get("status") == "planned")
        ]
        rows.sort(key=lambda row: (row.get("created_at") or "", int(row.get("id") or 0)))
        return [job for row in rows[: max(1, min(int(limit or 100), 1000))] if (job := _public_job(row)) is not None]

    def _find(self, job_id: int) -> dict[str, Any] | None:
        for row in self._jobs:
            if int(row.get("id") or 0) == int(job_id):
                return row
        return None

    def _filtered_rows(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self._jobs)
        for key in (
            "effect_type",
            "status",
            "target_type",
            "target_id",
            "business_type",
            "business_id",
            "trace_id",
            "source_event_id",
            "source_module",
        ):
            value = _text(filters.get(key))
            if value:
                rows = [row for row in rows if _text(row.get(key)) == value]
        completed_from = _text(filters.get("completed_from"))
        if completed_from:
            cutoff = self._dt(completed_from)
            rows = [row for row in rows if row.get("completed_at") and self._dt(row.get("completed_at")) >= cutoff]
        return rows

    def _mutate(self, job_id: int, **changes: Any) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if not row:
            return None
        row.update(changes)
        row["updated_at"] = public_datetime(utcnow())
        return _public_job(row)

    def _dt(self, value: Any) -> datetime:
        text_value = _text(value)
        if not text_value:
            return datetime.min.replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _oldest_age_seconds(self, rows: list[dict[str, Any]], now: datetime, key: str, *, fallback_key: str = "") -> int:
        if not rows:
            return 0
        oldest = min(self._dt(row.get(key) or row.get(fallback_key)) for row in rows)
        return max(0, int((now - oldest).total_seconds()))
