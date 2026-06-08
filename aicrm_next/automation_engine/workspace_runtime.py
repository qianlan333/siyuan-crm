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


class AutomationWorkspaceRuntimeInputError(ValueError):
    pass


@dataclass(frozen=True)
class AutomationWorkspaceRuntimeCommand:
    command_id: str = field(default_factory=lambda: "cmd_automation_workspace_" + uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "workspace_runtime"
    actor_type: str = "timer"
    program_id: int | None = None
    execution_item_id: int | None = None
    dry_run: bool = True
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    command_name = "automation_workspace.runtime.plan"

    def to_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "program_id": self.program_id,
            "execution_item_id": self.execution_item_id,
            "dry_run": self.dry_run,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
            "requested_at": self.requested_at,
        }


@dataclass(frozen=True)
class PlanAutomationOperationTasksRunDueCommand(AutomationWorkspaceRuntimeCommand):
    command_name = "automation_workspace.operation_tasks.run_due.plan"


@dataclass(frozen=True)
class PlanAutomationExecutionItemOutboundDispatchCommand(AutomationWorkspaceRuntimeCommand):
    command_name = "automation_workspace.execution_item.outbound_dispatch.plan"


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_external_call_attempts = InMemoryExternalCallAttemptRepository()
_command_bus = CommandBus()


def reset_workspace_runtime_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _external_call_attempts, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _external_call_attempts = InMemoryExternalCallAttemptRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_workspace_runtime_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_workspace_runtime_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def get_workspace_runtime_external_call_attempts() -> list[dict[str, Any]]:
    return [attempt.to_dict() for attempt in _external_call_attempts.list_attempts()]


def execute_workspace_runtime_command(command: AutomationWorkspaceRuntimeCommand) -> dict[str, Any]:
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
        raise AutomationWorkspaceRuntimeInputError(result.error or "automation workspace runtime command failed")
    return _response_from_result(result, dict(result.payload))


def normalize_program_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AutomationWorkspaceRuntimeInputError("program_id must be a positive integer") from exc
    if parsed < 1:
        raise AutomationWorkspaceRuntimeInputError("program_id must be a positive integer")
    return parsed


def normalize_execution_item_id(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AutomationWorkspaceRuntimeInputError("execution_item_id must be a positive integer") from exc
    if parsed < 1:
        raise AutomationWorkspaceRuntimeInputError("execution_item_id must be a positive integer")
    return parsed


def _register_handlers() -> None:
    _command_bus.register(PlanAutomationOperationTasksRunDueCommand.command_name, _handle_tasks_run_due_plan)
    _command_bus.register(PlanAutomationExecutionItemOutboundDispatchCommand.command_name, _handle_outbound_dispatch_plan)


def _validate_command(command: AutomationWorkspaceRuntimeCommand) -> None:
    if not command.command_id.strip():
        raise AutomationWorkspaceRuntimeInputError("command_id is required")
    if not command.source_route.strip():
        raise AutomationWorkspaceRuntimeInputError("source_route is required")
    if isinstance(command, PlanAutomationOperationTasksRunDueCommand) and command.program_id is not None:
        normalize_program_id(command.program_id)
    if isinstance(command, PlanAutomationExecutionItemOutboundDispatchCommand):
        normalize_execution_item_id(command.execution_item_id)


def _task_candidates(program_id: int | None) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": f"program_{program_id or 'all'}_operation_tasks",
            "program_id": program_id,
            "target_type": "automation_operation_task",
            "status": "blocked_plan_only",
            "estimated_actions": 1,
        }
    ]


def _outbound_candidates(execution_item_id: int) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": f"execution_item_{execution_item_id}_outbound",
            "execution_item_id": execution_item_id,
            "target_type": "automation_execution_item",
            "status": "blocked_plan_only",
            "estimated_actions": 1,
        }
    ]


def _estimated_actions(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    count = sum(int(item.get("estimated_actions") or 0) for item in candidates)
    return {
        "planned_action_count": count,
        "runtime_execution_count": 0,
        "outbound_dispatch_count": 0,
        "blocked_external_call_count": count,
    }


def _handle_tasks_run_due_plan(command: Command) -> dict[str, Any]:
    program_id = normalize_program_id(command.payload.get("program_id"))
    candidates = _task_candidates(program_id)
    plan, attempt = _plan_blocked_attempt(
        command=command,
        effect_type="automation.operation_tasks.run_due",
        operation="operation_tasks.run_due",
        target_type="automation_operation_task_due_candidates",
        target_id=f"program:{program_id}" if program_id else "program:all",
        candidates=candidates,
    )
    return _planned_payload(
        source_status="next_automation_tasks_run_due_plan",
        status="planned_blocked",
        candidates=candidates,
        plan=plan,
        attempt=attempt,
        extra={
            "program_id": program_id,
            "operation_tasks_executed": False,
            "bazhuayu_send_executed": False,
        },
    )


def _handle_outbound_dispatch_plan(command: Command) -> dict[str, Any]:
    execution_item_id = normalize_execution_item_id(command.payload.get("execution_item_id"))
    candidates = _outbound_candidates(execution_item_id)
    plan, attempt = _plan_blocked_attempt(
        command=command,
        effect_type="automation.execution_item.send_via_bazhuayu",
        operation="execution_item.outbound_dispatch",
        target_type="automation_execution_item",
        target_id=str(execution_item_id),
        candidates=candidates,
    )
    return _planned_payload(
        source_status="next_bazhuayu_dispatch_plan",
        status="planned_blocked",
        candidates=candidates,
        plan=plan,
        attempt=attempt,
        extra={
            "execution_item_id": execution_item_id,
            "operation_tasks_executed": False,
            "bazhuayu_send_executed": False,
        },
    )


def _planned_payload(
    *,
    source_status: str,
    status: str,
    candidates: list[dict[str, Any]],
    plan: SideEffectPlan,
    attempt: Any,
    extra: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "source_status": source_status,
        "status": status,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "estimated_actions": _estimated_actions(candidates),
        "planned_count": len(candidates),
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
        "skipped_count": len(candidates),
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
    target_id: str,
    candidates: list[dict[str, Any]],
) -> tuple[SideEffectPlan, Any]:
    plan = _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=effect_type,
        adapter_name="automation_workspace_runtime",
        adapter_mode=ADAPTER_MODE,
        target_type=target_type,
        target_id=target_id,
        payload={
            "payload_summary": {
                "program_id": command.payload.get("program_id"),
                "execution_item_id": command.payload.get("execution_item_id"),
                "candidate_count": len(candidates),
            },
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "operation_tasks_executed": False,
            "bazhuayu_send_executed": False,
            "wecom_send_executed": False,
        },
        status="blocked",
        risk_level="high",
        requires_approval=True,
    )
    attempt = _external_call_attempts.record_attempt(
        adapter_name="automation_workspace_runtime",
        adapter_mode=ADAPTER_MODE,
        operation=operation,
        request_id=command.command_id,
        trace_id=command.context.trace_id,
        side_effect_plan_id=plan.side_effect_plan_id,
        status="blocked",
        request_summary={
            "program_id": command.payload.get("program_id"),
            "execution_item_id": command.payload.get("execution_item_id"),
            "candidate_count": len(candidates),
            "dry_run": command.payload.get("dry_run", True),
        },
        response_summary={
            "blocked": True,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "operation_tasks_executed": False,
            "bazhuayu_send_executed": False,
            "wecom_send_executed": False,
        },
        error_code="real_blocked",
        error_message="Automation workspace runtime is plan-only in Next safe mode.",
    )
    return plan, attempt


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["real_external_call_executed"] = False
    payload["automation_runtime_executed"] = False
    payload["operation_tasks_executed"] = False
    payload["bazhuayu_send_executed"] = False
    payload["wecom_send_executed"] = False
    return payload


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="automation_workspace_runtime",
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
            "operation_tasks_executed": False,
            "bazhuayu_send_executed": False,
            "wecom_send_executed": False,
            "candidate_count": (result.payload or {}).get("candidate_count", 0),
        },
    )


def _audit_event_for(command_id: str) -> dict[str, Any]:
    for event in reversed(get_workspace_runtime_audit_events()):
        if event.get("command_id") == command_id:
            return event
    return {}


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    source_status = str(payload.pop("source_status", "") or "next_automation_tasks_run_due_plan")
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
        "operation_tasks_executed": False,
        "bazhuayu_send_executed": False,
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
        "operation_tasks_executed": False,
        "bazhuayu_send_executed": False,
        "wecom_send_executed": False,
        "side_effect_plan": {
            "adapter_name": "automation_workspace_runtime",
            "adapter_mode": ADAPTER_MODE,
            "requires_approval": True,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "operation_tasks_executed": False,
            "bazhuayu_send_executed": False,
            "wecom_send_executed": False,
            "payload_summary": {},
        },
    }


reset_workspace_runtime_fixture_state()
