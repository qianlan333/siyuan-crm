from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan

from .mutation_commands import (
    PlanCustomerTagAssignmentCommand,
    PlanQuestionnaireTagSideEffectCommand,
    PlanWeComTagMarkCommand,
    PlanWeComTagUnmarkCommand,
    WeComTagMutationCommand,
)


class WeComTagMutationInputError(ValueError):
    pass


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_command_bus = CommandBus()


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="external_user",
        target_id=str(command.payload.get("external_userid") or ""),
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "source_status": "next_command",
            "fallback_used": False,
            "adapter_mode": "real_blocked",
            "real_external_call_executed": False,
            "wecom_api_called": False,
        },
    )


def reset_wecom_tag_live_mutation_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_wecom_tag_live_mutation_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_wecom_tag_live_mutation_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def live_gate_status() -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": "next_live_gate",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "adapter_name": "wecom",
        "adapter_mode": "real_blocked",
        "real_enabled": False,
        "available": False,
        "blocked": True,
        "requires_approval": True,
        "real_external_call_executed": False,
        "wecom_api_called": False,
        "live_call_executed": False,
        "mark_tag_executed": False,
        "unmark_tag_executed": False,
    }


def execute_wecom_tag_mutation(command: WeComTagMutationCommand) -> dict[str, Any]:
    normalized = _normalize_command(command)
    platform_command = Command(
        command_name=normalized.command_name,
        payload=normalized.to_payload(),
        command_id=normalized.command_id,
        idempotency_key=normalized.idempotency_key,
        context=CommandContext(
            actor_id=normalized.actor_id,
            actor_type=normalized.actor_type,
            trace_id=normalized.trace_id,
            source_route=normalized.source_route,
            dry_run=normalized.dry_run,
        ),
    )
    result = _command_bus.execute(platform_command)
    if result.status == "failed":
        raise WeComTagMutationInputError(result.error)
    payload = dict(result.payload)
    return _response_from_result(result, payload)


def _register_handlers() -> None:
    for command_type in (
        PlanWeComTagMarkCommand,
        PlanWeComTagUnmarkCommand,
        PlanCustomerTagAssignmentCommand,
        PlanQuestionnaireTagSideEffectCommand,
    ):
        _command_bus.register(command_type.command_name, _handle_plan_mutation)


def _normalize_command(command: WeComTagMutationCommand) -> WeComTagMutationCommand:
    external_userid = str(command.external_userid or "").strip()
    tag_ids = _normalize_tag_ids(command.tag_ids)
    if not external_userid:
        raise WeComTagMutationInputError("external_userid is required")
    if not tag_ids:
        raise WeComTagMutationInputError("tag_ids is required")
    if not str(command.source_route or "").strip():
        raise WeComTagMutationInputError("source_route is required")
    return command.__class__(
        command_id=command.command_id,
        idempotency_key=str(command.idempotency_key or "").strip(),
        actor_id=str(command.actor_id or "wecom_tag_operator").strip(),
        actor_type=str(command.actor_type or "user").strip(),
        external_userid=external_userid,
        tag_ids=tag_ids,
        source_route=str(command.source_route or "").strip(),
        source_context=dict(command.source_context or {}),
        dry_run=bool(command.dry_run),
        trace_id=str(command.trace_id or "").strip(),
    )


def _handle_plan_mutation(command: Command) -> dict[str, Any]:
    effect_type = command.command_name
    external_userid = str(command.payload.get("external_userid") or "").strip()
    tag_ids = list(command.payload.get("tag_ids") or [])
    plan = _create_side_effect_plan(
        command=command,
        effect_type=effect_type,
        external_userid=external_userid,
        tag_ids=tag_ids,
        source_context=dict(command.payload.get("source_context") or {}),
    )
    return {
        "effect_type": effect_type,
        "external_userid": external_userid,
        "tag_ids": tag_ids,
        "source_context": dict(command.payload.get("source_context") or {}),
        "side_effect_plan": _plan_response(plan),
    }


def _create_side_effect_plan(
    *,
    command: Command,
    effect_type: str,
    external_userid: str,
    tag_ids: list[str],
    source_context: dict[str, Any],
) -> SideEffectPlan:
    return _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=effect_type,
        adapter_name="wecom",
        adapter_mode="real_blocked",
        target_type="external_user",
        target_id=external_userid,
        payload={
            "payload_summary": {
                "external_userid_redacted": _redact_external_userid(external_userid),
                "tag_count": len(tag_ids),
                "source": source_context.get("source") or command.context.source_route,
            },
            "external_userid": external_userid,
            "tag_ids": tag_ids,
            "source_context": source_context,
            "real_external_call_executed": False,
            "wecom_api_called": False,
        },
        status="planned",
        risk_level="high",
        requires_approval=True,
    )


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    plan_payload = dict(payload.pop("payload") or {})
    payload["payload_summary"] = plan_payload.get("payload_summary") or {}
    payload["external_userid"] = plan_payload.get("external_userid") or ""
    payload["tag_ids"] = list(plan_payload.get("tag_ids") or [])
    payload["source_context"] = dict(plan_payload.get("source_context") or {})
    payload["real_external_call_executed"] = False
    payload["wecom_api_called"] = False
    return payload


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    effect_type = str(payload.get("effect_type") or result.command_name)
    return {
        "ok": result.status in {"completed", "dry_run"},
        "command_id": result.command_id,
        "command_name": result.command_name,
        "idempotency_key": result.idempotency_key,
        "source_status": "next_command",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "adapter_mode": "real_blocked",
        "effect_type": effect_type,
        "external_userid": payload.get("external_userid") or "",
        "tag_ids": list(payload.get("tag_ids") or []),
        "side_effect_plan": payload.get("side_effect_plan") or {},
        "real_external_call_executed": False,
        "wecom_api_called": False,
        "live_call_executed": False,
        "mark_tag_executed": False,
        "unmark_tag_executed": False,
        "audit_recorded": True,
        "command_result_status": result.status,
    }


def _normalize_tag_ids(tag_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tag_ids or []:
        tag_id = str(raw or "").strip()
        if not tag_id or tag_id in seen:
            continue
        seen.add(tag_id)
        normalized.append(tag_id)
    return normalized


def _redact_external_userid(external_userid: str) -> str:
    value = str(external_userid or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


reset_wecom_tag_live_mutation_fixture_state()
