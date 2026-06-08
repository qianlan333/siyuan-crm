from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.external_calls import InMemoryExternalCallAttemptRepository
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan

ROUTE_OWNER = "ai_crm_next"
ADAPTER_MODE = "real_blocked"
DEFAULT_LIMIT = 100
DEFAULT_REPLY_LIMIT = 20
DEFAULT_CAPTURE_LIMIT = 500
MAX_LIMIT = 1000


class AutomationTimerInputError(ValueError):
    pass


@dataclass(frozen=True)
class AutomationTimerCommand:
    command_id: str = field(default_factory=lambda: "cmd_automation_timer_" + uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "timer"
    actor_type: str = "timer"
    limit: int = DEFAULT_LIMIT
    batch_size: int = DEFAULT_LIMIT
    job_codes: tuple[str, ...] = ()
    dry_run: bool = True
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    command_name = "automation_conversion.timer.plan"

    def to_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "limit": self.limit,
            "batch_size": self.batch_size,
            "job_codes": list(self.job_codes),
            "dry_run": self.dry_run,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
            "requested_at": self.requested_at,
        }


@dataclass(frozen=True)
class PlanReplyMonitorCaptureCommand(AutomationTimerCommand):
    command_name = "automation_conversion.reply_monitor.capture.plan"


@dataclass(frozen=True)
class PlanReplyMonitorRunDueCommand(AutomationTimerCommand):
    command_name = "automation_conversion.reply_monitor.run_due.plan"


@dataclass(frozen=True)
class PreviewAutomationJobsRunDueCommand(AutomationTimerCommand):
    command_name = "automation_conversion.jobs.run_due.preview"


@dataclass(frozen=True)
class PlanAutomationJobsRunDueCommand(AutomationTimerCommand):
    command_name = "automation_conversion.jobs.run_due.plan"


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_external_call_attempts = InMemoryExternalCallAttemptRepository()
_command_bus = CommandBus()


def reset_timer_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _external_call_attempts, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _external_call_attempts = InMemoryExternalCallAttemptRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_timer_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_timer_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def get_timer_external_call_attempts() -> list[dict[str, Any]]:
    return [attempt.to_dict() for attempt in _external_call_attempts.list_attempts()]


def execute_automation_timer_command(command: AutomationTimerCommand) -> dict[str, Any]:
    _validate_command(command)
    platform_command = Command(
        command_name=command.command_name,
        payload=command.to_payload(),
        command_id=command.command_id,
        idempotency_key=command.idempotency_key,
        context=CommandContext(
            actor_id=command.actor_id,
            actor_type=command.actor_type,
            trace_id=command.trace_id,
            source_route=command.source_route,
            dry_run=False,
        ),
    )
    result = _command_bus.execute(platform_command)
    if result.status == "failed":
        raise AutomationTimerInputError(result.error or "automation timer command failed")
    return _response_from_result(result, dict(result.payload))


def normalize_limit(value: Any, *, default: int = DEFAULT_LIMIT) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AutomationTimerInputError("limit must be an integer") from exc
    if parsed < 1 or parsed > MAX_LIMIT:
        raise AutomationTimerInputError("limit must be between 1 and 1000")
    return parsed


def normalize_batch_size(value: Any, *, default: int = DEFAULT_LIMIT) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AutomationTimerInputError("batch_size must be an integer") from exc
    if parsed < 1 or parsed > MAX_LIMIT:
        raise AutomationTimerInputError("batch_size must be between 1 and 1000")
    return parsed


def normalize_job_codes(*values: Any) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        if value in (None, ""):
            continue
        if isinstance(value, str):
            items = value.replace(",", "\n").splitlines()
        elif isinstance(value, (list, tuple, set)):
            items = list(value)
        else:
            raise AutomationTimerInputError("job_codes must be a string or list")
        for item in items:
            code = str(item or "").strip()
            if code and code not in normalized:
                normalized.append(code)
    return tuple(normalized)


def _register_handlers() -> None:
    _command_bus.register(PlanReplyMonitorCaptureCommand.command_name, _handle_capture_plan)
    _command_bus.register(PlanReplyMonitorRunDueCommand.command_name, _handle_reply_run_due_plan)
    _command_bus.register(PreviewAutomationJobsRunDueCommand.command_name, _handle_jobs_preview)
    _command_bus.register(PlanAutomationJobsRunDueCommand.command_name, _handle_jobs_plan)


def _validate_command(command: AutomationTimerCommand) -> None:
    if not command.command_id.strip():
        raise AutomationTimerInputError("command_id is required")
    if not command.source_route.strip():
        raise AutomationTimerInputError("source_route is required")
    normalize_limit(command.limit)
    normalize_batch_size(command.batch_size)


def _reply_candidates(limit: int, *, operation: str) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": f"{operation}_candidate_{index + 1}",
            "target_type": "reply_monitor",
            "status": "blocked_plan_only",
            "estimated_actions": 1,
        }
        for index in range(min(limit, 1))
    ]


def _job_candidates(batch_size: int, job_codes: tuple[str, ...]) -> list[dict[str, Any]]:
    codes = job_codes or ("registered_due_jobs",)
    candidates: list[dict[str, Any]] = []
    for code in codes:
        candidates.append({"job_code": code, "status": "blocked_plan_only", "estimated_actions": 1})
        if len(candidates) >= batch_size:
            break
    return candidates


def _estimated_actions(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    count = sum(int(item.get("estimated_actions") or 0) for item in candidates)
    return {
        "planned_action_count": count,
        "runtime_execution_count": 0,
        "external_call_count": 0,
        "blocked_external_call_count": count,
    }


def _handle_capture_plan(command: Command) -> dict[str, Any]:
    limit = normalize_limit(command.payload.get("limit"), default=DEFAULT_CAPTURE_LIMIT)
    candidates = _reply_candidates(limit, operation="capture")
    plan, attempt = _plan_blocked_attempt(
        command=command,
        effect_type="automation_conversion.reply_monitor.capture",
        operation="reply_monitor.capture",
        target_type="reply_monitor_capture_candidates",
        candidates=candidates,
    )
    return _planned_payload(
        source_status="next_reply_monitor_capture_plan",
        candidates=candidates,
        plan=plan,
        attempt=attempt,
        extra={"captured_count": 0, "reply_monitor_capture_executed": False},
    )


def _handle_reply_run_due_plan(command: Command) -> dict[str, Any]:
    limit = normalize_limit(command.payload.get("limit"), default=DEFAULT_REPLY_LIMIT)
    candidates = _reply_candidates(limit, operation="reply_run_due")
    plan, attempt = _plan_blocked_attempt(
        command=command,
        effect_type="automation_conversion.reply_monitor.run_due",
        operation="reply_monitor.run_due",
        target_type="reply_monitor_due_candidates",
        candidates=candidates,
    )
    return _planned_payload(
        source_status="next_reply_monitor_run_due_plan",
        candidates=candidates,
        plan=plan,
        attempt=attempt,
        extra={"captured_count": 0, "reply_monitor_run_due_executed": False},
    )


def _handle_jobs_preview(command: Command) -> dict[str, Any]:
    batch_size = normalize_batch_size(command.payload.get("batch_size"))
    job_codes = tuple(str(code).strip() for code in command.payload.get("job_codes") or () if str(code).strip())
    candidates = _job_candidates(batch_size, job_codes)
    return {
        "source_status": "next_jobs_run_due_preview",
        "timer_status": "preview_only",
        "candidates": candidates,
        "candidate_count": len(candidates),
        "job_codes": [item["job_code"] for item in candidates],
        "estimated_actions": _estimated_actions(candidates),
        "planned_count": 0,
        "actual_enqueued_count": 0,
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
        "skipped_count": len(candidates),
        "jobs_run_due_executed": False,
        "operation_tasks_executed": 0,
        "blocked_reason": "next_plan_only_route",
    }


def _handle_jobs_plan(command: Command) -> dict[str, Any]:
    batch_size = normalize_batch_size(command.payload.get("batch_size"))
    job_codes = tuple(str(code).strip() for code in command.payload.get("job_codes") or () if str(code).strip())
    candidates = _job_candidates(batch_size, job_codes)
    plan, attempt = _plan_blocked_attempt(
        command=command,
        effect_type="automation_conversion.jobs.run_due",
        operation="jobs.run_due",
        target_type="automation_due_job_candidates",
        candidates=candidates,
    )
    return _planned_payload(
        source_status="next_jobs_run_due_plan",
        candidates=candidates,
        plan=plan,
        attempt=attempt,
        extra={"job_codes": [item["job_code"] for item in candidates], "jobs_run_due_executed": False},
    )


def _planned_payload(
    *,
    source_status: str,
    candidates: list[dict[str, Any]],
    plan: SideEffectPlan,
    attempt: Any,
    extra: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "source_status": source_status,
        "timer_status": "planned_blocked",
        "candidates": candidates,
        "candidate_count": len(candidates),
        "estimated_actions": _estimated_actions(candidates),
        "planned_count": len(candidates),
        "actual_enqueued_count": 0,
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
        "skipped_count": len(candidates),
        "operation_tasks_executed": 0,
        "blocked_reason": "next_plan_only_route",
        "side_effect_plan": _plan_response(plan),
        "external_call_attempt": attempt.to_dict(),
    }
    payload.update(extra)
    return payload


def _plan_blocked_attempt(
    *,
    command: Command,
    effect_type: str,
    operation: str,
    target_type: str,
    candidates: list[dict[str, Any]],
) -> tuple[SideEffectPlan, Any]:
    plan = _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=effect_type,
        adapter_name="automation_conversion_timer_runtime",
        adapter_mode=ADAPTER_MODE,
        target_type=target_type,
        target_id="batch",
        payload={
            "payload_summary": {
                "limit": command.payload.get("limit"),
                "batch_size": command.payload.get("batch_size"),
                "job_codes": command.payload.get("job_codes") or [],
                "candidate_count": len(candidates),
            },
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
        },
        status="blocked",
        risk_level="high",
        requires_approval=True,
    )
    attempt = _external_call_attempts.record_attempt(
        adapter_name="automation_conversion_timer_runtime",
        adapter_mode=ADAPTER_MODE,
        operation=operation,
        request_id=command.command_id,
        trace_id=command.context.trace_id,
        side_effect_plan_id=plan.side_effect_plan_id,
        status="blocked",
        request_summary={
            "limit": command.payload.get("limit"),
            "batch_size": command.payload.get("batch_size"),
            "job_codes": command.payload.get("job_codes") or [],
            "candidate_count": len(candidates),
            "dry_run": command.payload.get("dry_run", True),
        },
        response_summary={
            "blocked": True,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
        },
        error_code="real_blocked",
        error_message="Automation conversion timer is plan-only in Next safe mode.",
    )
    return plan, attempt


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["real_external_call_executed"] = False
    payload["automation_runtime_executed"] = False
    payload["wecom_send_executed"] = False
    return payload


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="automation_conversion_timer",
        target_id="batch",
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "fallback_used": False,
            "adapter_mode": ADAPTER_MODE,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
            "candidate_count": (result.payload or {}).get("candidate_count", 0),
        },
    )


def _audit_event_for(command_id: str) -> dict[str, Any]:
    for event in reversed(get_timer_audit_events()):
        if event.get("command_id") == command_id:
            return event
    return {}


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    source_status = str(payload.pop("source_status", "") or "next_jobs_run_due_plan")
    response = {
        "ok": result.status == "completed",
        "command_id": result.command_id,
        "command_name": result.command_name,
        "idempotency_key": result.idempotency_key,
        "source_status": source_status,
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "adapter_mode": ADAPTER_MODE,
        "real_external_call_executed": False,
        "automation_runtime_executed": False,
        "wecom_send_executed": False,
        "audit_recorded": True,
        "audit_event": _audit_event_for(result.command_id),
        "command_result_status": result.status,
        "actor": {"id": result.actor_id, "type": result.actor_type},
        "source_route": result.source_route,
        "trace_id": result.trace_id,
        "dry_run": bool(result.payload.get("dry_run", True)),
    }
    response.update(payload)
    return response


def diagnostics_payload(source_status: str) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": source_status,
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "adapter_mode": ADAPTER_MODE,
        "allowed_methods": ["POST", "OPTIONS"],
        "real_external_call_executed": False,
        "automation_runtime_executed": False,
        "wecom_send_executed": False,
        "reply_monitor_capture_executed": False,
        "reply_monitor_run_due_executed": False,
        "jobs_run_due_executed": False,
        "side_effect_plan": {
            "adapter_name": "automation_conversion_timer_runtime",
            "adapter_mode": ADAPTER_MODE,
            "requires_approval": True,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
            "payload_summary": {},
        },
    }


reset_timer_fixture_state()
