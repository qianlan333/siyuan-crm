from __future__ import annotations

from dataclasses import replace
import logging
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from aicrm_next.platform_foundation.push_center.capability_registry import capability_for_section
from aicrm_next.platform_foundation.push_center.section_mapper import section_for_job
from aicrm_next.shared.runtime_settings import runtime_bool, runtime_setting
from aicrm_next.shared.safe_logging import safe_log_exception

from .adapters import DEFAULT_ADAPTER_REGISTRY, ExternalEffectAdapterRegistry
from .execution_gates import (
    WECOM_EXECUTION_DISABLED_CODE,
    explicit_wecom_execution_disabled,
    is_wecom_effect_type,
    wecom_execution_disabled_message,
)
from .models import (
    WECOM_MESSAGE_GROUP_SEND,
    WEBHOOK_GENERIC_PUSH,
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
        locked_by: str = "",
    ):
        self._repo = repository or build_external_effect_repository()
        self._adapters = adapter_registry or DEFAULT_ADAPTER_REGISTRY
        self._locked_by = locked_by or f"external-effect-worker-{uuid4().hex[:8]}"

    def preview_due(self, *, batch_size: int = 10, effect_types: list[str] | None = None, test_only: bool = False) -> dict[str, Any]:
        jobs = self._repo.list_due_jobs(limit=batch_size, effect_types=effect_types, test_only=test_only)
        return {
            "ok": True,
            "items": [job.to_dict() for job in jobs],
            "counts": {
                "candidate_count": len(jobs),
                "processed_count": 0,
                "succeeded_count": 0,
                "failed_count": 0,
                "blocked_count": 0,
            },
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
                "counts": {"candidate_count": 0, "processed_count": 0, "succeeded_count": 0, "failed_count": 0, "blocked_count": 0},
                "dry_run": False,
                "test_only": bool(test_only),
                "real_external_call_executed": False,
            }
        if _enabled("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY") and not test_only:
            return {
                "ok": False,
                "error": "test_only_required",
                "items": [],
                "counts": {"candidate_count": 0, "processed_count": 0, "succeeded_count": 0, "failed_count": 0, "blocked_count": 0},
                "dry_run": False,
                "test_only": False,
                "real_external_call_executed": False,
            }

        jobs = self._repo.acquire_due_jobs(limit=batch_size, locked_by=self._locked_by, effect_types=effect_types, test_only=test_only)
        items: list[dict[str, Any]] = []
        counts = {"candidate_count": len(jobs), "processed_count": 0, "succeeded_count": 0, "failed_count": 0, "blocked_count": 0}
        real_external_call_executed = False
        for job in jobs:
            result = self.dispatch_one(job)
            items.append(result)
            counts["processed_count"] += 1
            status = str(result.get("job", {}).get("status") or "")
            if status == "succeeded":
                counts["succeeded_count"] += 1
            elif status == "blocked":
                counts["blocked_count"] += 1
            elif status.startswith("failed"):
                counts["failed_count"] += 1
            real_external_call_executed = real_external_call_executed or bool(result.get("real_external_call_executed"))
        return {
            "ok": True,
            "items": items,
            "counts": counts,
            "dry_run": False,
            "test_only": bool(test_only),
            "real_external_call_executed": real_external_call_executed,
        }

    def dispatch_one(self, job_or_id: int | ExternalEffectJob) -> dict[str, Any]:
        job = job_or_id if isinstance(job_or_id, ExternalEffectJob) else self._repo.get_job(int(job_or_id))
        if job is None:
            return {"ok": False, "error": "job_not_found", "real_external_call_executed": False}
        self._repo.mark_dispatching(job.id, locked_by=self._locked_by)
        wecom_disabled = self._block_if_wecom_execution_disabled(job)
        if wecom_disabled is not None:
            return wecom_disabled
        if _enabled("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY") and not _is_test_job(job):
            attempt = self._repo.record_attempt(
                job=job,
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary={"effect_type": job.effect_type, "test_execution_only": True},
                response_summary={"blocked": True, "real_external_call_executed": False},
                error_code="test_execution_only_required",
                error_message="AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY=1 blocks non-test jobs.",
            )
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code="test_execution_only_required",
                error_message="AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY=1 blocks non-test jobs.",
            )
            return {
                "ok": False,
                "job": updated.to_dict() if updated else job.to_dict(),
                "attempt": attempt.to_dict(),
                "real_external_call_executed": False,
            }
        capability_error = _capability_gate_error(job)
        if capability_error:
            message = (
                "Push capability is disabled by admin config."
                if capability_error == "push_capability_disabled"
                else "Push capability does not support real execution."
            )
            attempt = self._repo.record_attempt(
                job=job,
                status="failed_terminal",
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
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=capability_error,
                error_message=message,
            )
            return {
                "ok": False,
                "job": updated.to_dict() if updated else job.to_dict(),
                "attempt": attempt.to_dict(),
                "real_external_call_executed": False,
            }
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
            error_code = "adapter_exception"
            error_message = str(exc)[:500]
            attempt = self._repo.record_attempt(
                job=job,
                status="failed_retryable",
                adapter_mode=job.execution_mode or "execute",
                request_summary={
                    "effect_type": job.effect_type,
                    "adapter_name": job.adapter_name,
                    "operation": job.operation,
                    "adapter_exception": True,
                },
                response_summary={
                    "adapter_exception": True,
                    "real_external_call_executed": False,
                },
                error_code=error_code,
                error_message=error_message,
            )
            if status_for_failure(
                error_code=error_code,
                attempt_count=int(job.attempt_count or 0) + 1,
                max_attempts=int(job.max_attempts or 5),
            ) == "failed_retryable":
                updated = self._repo.mark_failed_retryable(
                    job.id,
                    attempt_id=attempt.attempt_id,
                    error_code=error_code,
                    error_message=error_message,
                    next_retry_at=next_retry_at(job.attempt_count),
                )
            else:
                updated = self._repo.mark_failed_terminal(
                    job.id,
                    attempt_id=attempt.attempt_id,
                    error_code=error_code,
                    error_message=error_message,
                )
            return {
                "ok": False,
                "job": updated.to_dict() if updated else job.to_dict(),
                "attempt": attempt.to_dict(),
                "real_external_call_executed": False,
            }
        continuation = self._run_post_success_continuations(job, dispatch_result)
        if continuation.get("applicable"):
            dispatch_result = replace(
                dispatch_result,
                response_summary={
                    **dict(dispatch_result.response_summary or {}),
                    "post_success_continuation": continuation,
                },
            )
        attempt = self._repo.record_attempt(
            job=job,
            status=dispatch_result.status,
            adapter_mode=dispatch_result.adapter_mode,
            request_summary=dispatch_result.request_summary,
            response_summary=dispatch_result.response_summary,
            error_code=dispatch_result.error_code,
            error_message=dispatch_result.error_message,
        )
        if dispatch_result.status == "succeeded":
            updated = self._repo.mark_succeeded(job.id, attempt_id=attempt.attempt_id)
        elif dispatch_result.status == "failed_retryable" and status_for_failure(
            error_code=dispatch_result.error_code,
            attempt_count=int(job.attempt_count or 0) + 1,
            max_attempts=int(job.max_attempts or 5),
        ) == "failed_retryable":
            updated = self._repo.mark_failed_retryable(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=dispatch_result.error_code,
                error_message=dispatch_result.error_message,
                next_retry_at=next_retry_at(job.attempt_count),
            )
        elif dispatch_result.status in {"failed_retryable", "failed_terminal"}:
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=dispatch_result.error_code,
                error_message=dispatch_result.error_message,
            )
        else:
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=dispatch_result.error_code or "adapter_blocked",
                error_message=dispatch_result.error_message,
            )
        return {
            "ok": dispatch_result.ok,
            "job": updated.to_dict() if updated else job.to_dict(),
            "attempt": attempt.to_dict(),
            "post_success_continuation": continuation,
            "real_external_call_executed": dispatch_result.real_external_call_executed,
        }

    def _block_if_wecom_execution_disabled(self, job: ExternalEffectJob) -> dict[str, Any] | None:
        if not is_wecom_effect_type(job.effect_type) or not explicit_wecom_execution_disabled():
            return None
        attempt = self._repo.record_attempt(
            job=job,
            status="blocked",
            adapter_mode="disabled",
            request_summary={
                "effect_type": job.effect_type,
                "adapter_name": job.adapter_name,
                "operation": job.operation,
                "target_type": job.target_type,
                "target_id": job.target_id,
                "execution_gate": WECOM_EXECUTION_DISABLED_CODE,
            },
            response_summary={
                "blocked": True,
                "execution_gate": WECOM_EXECUTION_DISABLED_CODE,
                "real_external_call_executed": False,
            },
            error_code=WECOM_EXECUTION_DISABLED_CODE,
            error_message=wecom_execution_disabled_message(),
        )
        updated = self._repo.mark_blocked(
            job.id,
            attempt_id=attempt.attempt_id,
            error_code=WECOM_EXECUTION_DISABLED_CODE,
            error_message=wecom_execution_disabled_message(),
        )
        return {
            "ok": False,
            "job": updated.to_dict() if updated else job.to_dict(),
            "attempt": attempt.to_dict(),
            "real_external_call_executed": False,
        }

    def _run_post_success_continuations(self, job: ExternalEffectJob, dispatch_result) -> dict[str, Any]:
        if dispatch_result.status != "succeeded":
            return {"applicable": False, "reason": "dispatch_not_succeeded"}
        if not _is_automation_agent_audience_webhook_job(job):
            return {"applicable": False, "reason": "not_automation_agent_audience_webhook"}
        batch_id = _automation_agent_batch_id(dispatch_result.response_summary)
        if not batch_id:
            return {"applicable": True, "ok": False, "error": "automation_agent_batch_id_missing"}
        try:
            from aicrm_next.automation_agents.worker import AutomationAgentWorker

            result = AutomationAgentWorker().run_batch_and_enqueue_broadcast_jobs(
                batch_id,
                operator="external_effect_agent_continuation",
            )
        except Exception as exc:
            safe_log_exception(
                LOGGER,
                "automation agent post-success continuation failed",
                exc,
                external_effect_job_id=int(job.id or 0),
                batch_id=batch_id,
            )
            return {"applicable": True, "ok": False, "batch_id": batch_id, "error": str(exc)[:500]}
        return {"applicable": True, **result}


def _is_automation_agent_audience_webhook_job(job: ExternalEffectJob) -> bool:
    if job.effect_type != WEBHOOK_GENERIC_PUSH:
        return False
    payload = dict(job.payload_json or {})
    url = str(payload.get("webhook_url") or payload.get("target_url") or "").strip()
    path = urlparse(url).path if url else ""
    return path.startswith("/api/ai/agents/") and path.endswith("/audience-webhook")


def _automation_agent_batch_id(response_summary: dict[str, Any] | None) -> str:
    summary = dict(response_summary or {})
    candidates = [summary.get("automation_agent_batch_id"), summary.get("batch_id")]
    response_json = summary.get("response_json") if isinstance(summary.get("response_json"), dict) else {}
    candidates.extend([response_json.get("automation_agent_batch_id"), response_json.get("batch_id")])
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value.startswith("agent_batch_"):
            return value
    return ""
