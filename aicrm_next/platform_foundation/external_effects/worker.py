from __future__ import annotations

from dataclasses import replace
import logging
from typing import Any
from uuid import uuid4

from aicrm_next.platform_foundation.push_center.capability_registry import capability_for_section
from aicrm_next.platform_foundation.push_center.section_mapper import section_for_job
from aicrm_next.shared.runtime_settings import runtime_bool, runtime_setting
from aicrm_next.shared.safe_logging import safe_log_exception

from .adapters import DEFAULT_ADAPTER_REGISTRY, ExternalEffectAdapterRegistry
from .continuations import (
    EMPTY_EXTERNAL_EFFECT_CONTINUATION_REGISTRY,
    ExternalEffectContinuationRegistry,
)
from .execution_gates import (
    is_wecom_effect_type,
    typed_wecom_execution_block_reason,
    wecom_execution_disabled_message,
)
from .execution_policy import normalize_dispatch_result
from .models import (
    WECOM_MESSAGE_GROUP_SEND,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)
from .repo import ExternalEffectRepository, build_external_effect_repository
from .retry_policy import next_retry_at, status_for_failure

LOGGER = logging.getLogger(__name__)


def _enabled(name: str) -> bool:
    return runtime_bool(name)


def _is_test_job(job: ExternalEffectJob) -> bool:
    payload = dict(job.payload_json or {})
    return payload.get("execution_scope") == "test_loopback" or payload.get("is_test") is True


def _capability_gate_error(job: ExternalEffectJob) -> str:
    payload = dict(job.payload_json or {})
    if payload.get("bypass_push_capability") is True:
        return ""
    capability = capability_for_section(section_for_job(job))
    if capability is None:
        return ""
    if not capability.supports_real_execution:
        return "push_capability_readonly"
    if not capability.toggleable:
        return ""
    value = runtime_setting(capability.setting_key, "__aicrm_missing__")
    if value == "__aicrm_missing__":
        return ""
    if str(value or "").strip().lower() not in {"1", "true", "yes", "y", "on"}:
        return "push_capability_disabled"
    return ""


class ExternalEffectWorker:
    def __init__(
        self,
        repository: ExternalEffectRepository | None = None,
        adapter_registry: ExternalEffectAdapterRegistry | None = None,
        *,
        continuation_registry: ExternalEffectContinuationRegistry | None = None,
        locked_by: str = "",
        lease_seconds: int = 300,
    ):
        self._repo = repository or build_external_effect_repository()
        self._adapters = adapter_registry or DEFAULT_ADAPTER_REGISTRY
        self._continuations = continuation_registry or EMPTY_EXTERNAL_EFFECT_CONTINUATION_REGISTRY
        self._locked_by = locked_by or f"external-effect-worker-{uuid4().hex[:8]}"
        self._lease_seconds = max(30, min(int(lease_seconds or 300), 3600))

    @staticmethod
    def _empty_counts(*, candidate_count: int = 0) -> dict[str, int]:
        return {
            "candidate_count": int(candidate_count),
            "processed_count": 0,
            "succeeded_count": 0,
            "simulated_count": 0,
            "skipped_count": 0,
            "unknown_after_dispatch_count": 0,
            "failed_count": 0,
            "blocked_count": 0,
            "lost_lease_count": 0,
        }

    def preview_due(self, *, batch_size: int = 10, effect_types: list[str] | None = None, test_only: bool = False) -> dict[str, Any]:
        jobs = self._repo.list_due_jobs(limit=batch_size, effect_types=effect_types, test_only=test_only)
        counts = self._empty_counts(candidate_count=len(jobs))
        counts["skipped_count"] = len(jobs)
        return {
            "ok": True,
            "items": [
                {
                    **job.to_dict(),
                    "dispatch_status": "skipped",
                    "preview_only": True,
                }
                for job in jobs
            ],
            "counts": counts,
            "dry_run": True,
            "test_only": bool(test_only),
            "real_external_call_executed": False,
        }

    def run_due(self, *, batch_size: int = 10, dry_run: bool = True, effect_types: list[str] | None = None, test_only: bool = False) -> dict[str, Any]:
        if dry_run:
            payload = self.preview_due(batch_size=batch_size, effect_types=effect_types, test_only=test_only)
            payload["dry_run"] = True
            return payload
        if WECOM_MESSAGE_GROUP_SEND in set(effect_types or []) and int(batch_size or 0) != 1:
            return {
                "ok": False,
                "error": "batch_size_one_required",
                "items": [],
                "counts": self._empty_counts(),
                "dry_run": False,
                "test_only": bool(test_only),
                "real_external_call_executed": False,
            }
        if _enabled("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY") and not test_only:
            return {
                "ok": False,
                "error": "test_only_required",
                "items": [],
                "counts": self._empty_counts(),
                "dry_run": False,
                "test_only": False,
                "real_external_call_executed": False,
            }

        quarantined_count = self._repo.quarantine_stale_dispatching()
        jobs = self._repo.acquire_due_jobs(
            limit=batch_size,
            locked_by=self._locked_by,
            effect_types=effect_types,
            test_only=test_only,
            lease_seconds=self._lease_seconds,
        )
        items: list[dict[str, Any]] = []
        counts = self._empty_counts(candidate_count=len(jobs))
        counts["unknown_after_dispatch_count"] = int(quarantined_count)
        real_external_call_executed = False
        for job in jobs:
            result = self._dispatch_claimed(job)
            items.append(result)
            counts["processed_count"] += 1
            status = str(result.get("job", {}).get("status") or "")
            if status == "succeeded":
                counts["succeeded_count"] += 1
            elif status == "simulated":
                counts["simulated_count"] += 1
            elif status == "unknown_after_dispatch":
                counts["unknown_after_dispatch_count"] += 1
            elif status == "blocked":
                counts["blocked_count"] += 1
            elif status.startswith("failed"):
                counts["failed_count"] += 1
            if result.get("error") == "lost_lease":
                counts["lost_lease_count"] += 1
            real_external_call_executed = real_external_call_executed or bool(result.get("real_external_call_executed"))
        ok = not any(counts[key] for key in ("unknown_after_dispatch_count", "failed_count", "blocked_count", "lost_lease_count"))
        return {
            "ok": ok,
            "exit_code": 0 if ok else 1,
            "items": items,
            "counts": counts,
            "quarantined_stale_dispatching_count": int(quarantined_count),
            "dry_run": False,
            "test_only": bool(test_only),
            "real_external_call_executed": real_external_call_executed,
        }

    def dispatch_one(self, job_or_id: int | ExternalEffectJob) -> dict[str, Any]:
        job_id = int(job_or_id.id if isinstance(job_or_id, ExternalEffectJob) else job_or_id)
        existing = self._repo.get_job(job_id)
        if existing is None:
            return {"ok": False, "error": "job_not_found", "real_external_call_executed": False}
        claimed = self._repo.acquire_job(job_id, locked_by=self._locked_by, lease_seconds=self._lease_seconds)
        if claimed is None:
            current = self._repo.get_job(job_id)
            return {
                "ok": False,
                "error": "not_claimed",
                "job": current.to_dict() if current else existing.to_dict(),
                "real_external_call_executed": False,
            }
        return self._dispatch_claimed(claimed)

    def _dispatch_claimed(self, job: ExternalEffectJob) -> dict[str, Any]:
        active = self._repo.get_active_claim(job.id, lease_token=job.lease_token)
        if active is None:
            return {
                "ok": False,
                "error": "lost_lease",
                "job": (self._repo.get_job(job.id) or job).to_dict(),
                "real_external_call_executed": False,
            }
        job = active
        dispatch_result = self._block_if_wecom_execution_disabled(job)
        if dispatch_result is None and _enabled("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY") and not _is_test_job(job):
            dispatch_result = ExternalEffectDispatchResult(
                status="blocked",
                adapter_mode=job.execution_mode or "execute",
                request_summary={"effect_type": job.effect_type, "test_execution_only": True},
                response_summary={"blocked": True, "real_external_call_executed": False},
                error_code="test_execution_only_required",
                error_message="AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY=1 blocks non-test jobs.",
            )
        capability_error = _capability_gate_error(job)
        if dispatch_result is None and capability_error:
            message = (
                "Push capability is disabled by admin config."
                if capability_error == "push_capability_disabled"
                else "Push capability does not support real execution."
            )
            dispatch_result = ExternalEffectDispatchResult(
                status="blocked",
                adapter_mode=job.execution_mode or "execute",
                request_summary={
                    "effect_type": job.effect_type,
                    "business_type": job.business_type,
                    "section": section_for_job(job),
                    "capability_gate": capability_error,
                },
                response_summary={"blocked": True, "real_external_call_executed": False},
                error_code=capability_error,
                error_message=message,
            )
        if dispatch_result is None:
            try:
                dispatch_result = self._adapters.get(job.adapter_name).dispatch(job)
            except Exception as exc:
                safe_log_exception(
                    LOGGER,
                    "external effect adapter dispatch raised",
                    exc,
                    external_effect_job_id=int(job.id or 0),
                    effect_type=job.effect_type,
                    adapter_name=job.adapter_name,
                )
                dispatch_result = ExternalEffectDispatchResult(
                    status="unknown_after_dispatch",
                    adapter_mode=job.execution_mode or "execute",
                    request_summary={
                        "effect_type": job.effect_type,
                        "adapter_name": job.adapter_name,
                        "operation": job.operation,
                        "dispatch_started": True,
                    },
                    response_summary={
                        "adapter_exception": True,
                        "provider_result_received": False,
                    },
                    error_code="adapter_exception",
                    error_message=str(exc)[:500],
                    real_external_call_executed=False,
                    provider_result_received=False,
                )

        dispatch_result = normalize_dispatch_result(job, dispatch_result)
        continuation = self._run_post_success_continuations(job, dispatch_result)
        if continuation.get("applicable"):
            dispatch_result = replace(
                dispatch_result,
                response_summary={
                    **dict(dispatch_result.response_summary or {}),
                    "post_success_continuation": continuation,
                },
            )
            if not continuation.get("ok"):
                dispatch_result = replace(
                    dispatch_result,
                    status="unknown_after_dispatch",
                    error_code="post_success_continuation_unknown",
                    error_message=str(continuation.get("error") or "Post-success continuation did not complete."),
                )

        if (
            dispatch_result.status == "failed_retryable"
            and status_for_failure(
                error_code=dispatch_result.error_code,
                attempt_count=int(job.attempt_count or 0) + 1,
                max_attempts=int(job.max_attempts or 5),
            )
            != "failed_retryable"
        ):
            dispatch_result = replace(dispatch_result, status="failed_terminal")

        retry_at = None
        if dispatch_result.status == "failed_retryable":
            retry_at = next_retry_at(
                job.attempt_count,
                retry_after_seconds=(dispatch_result.response_summary or {}).get("retry_after_seconds"),
            )

        try:
            completed = self._repo.complete_dispatch(job=job, result=dispatch_result, next_retry_at=retry_at)
        except Exception as exc:
            safe_log_exception(
                LOGGER,
                "external effect result persistence failed",
                exc,
                external_effect_job_id=int(job.id or 0),
                effect_type=job.effect_type,
            )
            try:
                updated = self._repo.mark_dispatch_unknown(
                    job=job,
                    error_code="result_persistence_failed",
                    error_message=str(exc)[:500],
                    side_effect_executed=dispatch_result.real_external_call_executed,
                    provider_result_received=dispatch_result.provider_result_received,
                )
            except Exception as mark_exc:
                safe_log_exception(
                    LOGGER,
                    "external effect unknown-result persistence failed",
                    mark_exc,
                    external_effect_job_id=int(job.id or 0),
                )
                updated = None
            return {
                "ok": False,
                "error": "result_persistence_failed",
                "job": updated.to_dict() if updated else job.to_dict(),
                "post_success_continuation": continuation,
                "real_external_call_executed": dispatch_result.real_external_call_executed,
            }
        if completed is None:
            current = self._repo.get_job(job.id)
            return {
                "ok": False,
                "error": "lost_lease",
                "job": current.to_dict() if current else job.to_dict(),
                "post_success_continuation": continuation,
                "real_external_call_executed": dispatch_result.real_external_call_executed,
            }
        updated, attempt = completed
        return {
            "ok": updated.status in {"succeeded", "simulated"},
            "job": updated.to_dict(),
            "attempt": attempt.to_dict(),
            "post_success_continuation": continuation,
            "real_external_call_executed": dispatch_result.real_external_call_executed,
        }

    def _block_if_wecom_execution_disabled(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult | None:
        if not is_wecom_effect_type(job.effect_type):
            return None
        block_code = typed_wecom_execution_block_reason(job.effect_type)
        if not block_code:
            return None
        block_message = wecom_execution_disabled_message(effect_type=job.effect_type)
        return ExternalEffectDispatchResult(
            status="blocked",
            adapter_mode="disabled",
            request_summary={
                "effect_type": job.effect_type,
                "adapter_name": job.adapter_name,
                "operation": job.operation,
                "target_type": job.target_type,
                "target_id": job.target_id,
                "execution_gate": block_code,
            },
            response_summary={
                "blocked": True,
                "execution_gate": block_code,
                "real_external_call_executed": False,
            },
            error_code=block_code,
            error_message=block_message,
        )

    def _run_post_success_continuations(self, job: ExternalEffectJob, dispatch_result) -> dict[str, Any]:
        if dispatch_result.status != "succeeded":
            return {"applicable": False, "reason": "dispatch_not_succeeded"}
        return self._continuations.run(job, dispatch_result)
