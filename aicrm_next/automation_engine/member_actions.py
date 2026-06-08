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
DEFAULT_ACTOR = "automation_member_actions"


class AutomationMemberActionInputError(ValueError):
    pass


@dataclass(frozen=True)
class GetAutomationMemberDetailQuery:
    external_contact_id: str = ""
    phone: str = ""
    source_route: str = "/api/admin/automation-conversion/member"
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class AutomationMemberActionCommand:
    command_id: str = field(default_factory=lambda: "cmd_automation_member_" + uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = DEFAULT_ACTOR
    actor_type: str = "user"
    external_contact_id: str = ""
    phone: str = ""
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dry_run: bool = True

    action_key = "member_action"
    command_name = "automation_member.action.plan"
    effect_type = "automation.member.action"
    risk_level = "medium"
    adapter_name = "automation_member_actions"
    requires_approval = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "external_contact_id": self.external_contact_id,
            "phone": self.phone,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
            "requested_at": self.requested_at,
            "dry_run": self.dry_run,
            "action_key": self.action_key,
        }


@dataclass(frozen=True)
class PutAutomationMemberInPoolCommand(AutomationMemberActionCommand):
    action_key = "put_in_pool"
    command_name = "automation_member.put_in_pool.plan"
    effect_type = "automation.member.put_in_pool"


@dataclass(frozen=True)
class RemoveAutomationMemberFromPoolCommand(AutomationMemberActionCommand):
    action_key = "remove_from_pool"
    command_name = "automation_member.remove_from_pool.plan"
    effect_type = "automation.member.remove_from_pool"


@dataclass(frozen=True)
class SetAutomationMemberFocusCommand(AutomationMemberActionCommand):
    action_key = "set_focus"
    command_name = "automation_member.set_focus.plan"
    effect_type = "automation.member.set_focus"


@dataclass(frozen=True)
class SetAutomationMemberNormalCommand(AutomationMemberActionCommand):
    action_key = "set_normal"
    command_name = "automation_member.set_normal.plan"
    effect_type = "automation.member.set_normal"


@dataclass(frozen=True)
class MarkAutomationMemberWonCommand(AutomationMemberActionCommand):
    action_key = "mark_won"
    command_name = "automation_member.mark_won.plan"
    effect_type = "automation.member.mark_won"


@dataclass(frozen=True)
class UnmarkAutomationMemberWonCommand(AutomationMemberActionCommand):
    action_key = "unmark_won"
    command_name = "automation_member.unmark_won.plan"
    effect_type = "automation.member.unmark_won"


@dataclass(frozen=True)
class PlanAutomationMemberOpenClawPushCommand(AutomationMemberActionCommand):
    action_key = "openclaw_push"
    command_name = "automation_member.openclaw_push.plan"
    effect_type = "automation.member.push_openclaw"
    risk_level = "high"
    adapter_name = "openclaw"
    requires_approval = True


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_external_call_attempts = InMemoryExternalCallAttemptRepository()
_command_bus = CommandBus()


def reset_member_actions_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _external_call_attempts, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _external_call_attempts = InMemoryExternalCallAttemptRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_member_actions_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_member_actions_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def get_member_actions_external_call_attempts() -> list[dict[str, Any]]:
    return [attempt.to_dict() for attempt in _external_call_attempts.list_attempts()]


def normalize_identity(*, external_contact_id: Any = "", phone: Any = "") -> dict[str, str]:
    identity = {
        "external_contact_id": str(external_contact_id or "").strip(),
        "phone": str(phone or "").strip(),
    }
    if not identity["external_contact_id"] and not identity["phone"]:
        raise AutomationMemberActionInputError("external_contact_id or phone is required")
    return identity


def normalize_actor(value: Any, fallback: str = DEFAULT_ACTOR) -> str:
    actor = str(value or "").strip()
    return actor or fallback


def read_automation_member_detail(query: GetAutomationMemberDetailQuery) -> dict[str, Any]:
    identity = normalize_identity(external_contact_id=query.external_contact_id, phone=query.phone)
    detail = _empty_detail(identity)
    return {
        "ok": True,
        "detail": detail,
        "source_status": "next_automation_member_read",
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "degraded": True,
        "status": "empty_read_model",
        "real_external_call_executed": False,
    }


def execute_member_action_command(command: AutomationMemberActionCommand) -> dict[str, Any]:
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
        raise AutomationMemberActionInputError(result.error or "automation member action command failed")
    return _response_from_result(result, dict(result.payload))


def diagnostics_payload(source_status: str = "next_command") -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": source_status,
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "allowed_methods": ["POST", "OPTIONS"],
        "adapter_mode": ADAPTER_MODE,
        "real_external_call_executed": False,
        "automation_runtime_executed": False,
        "openclaw_push_executed": False,
        "wecom_send_executed": False,
    }


def _register_handlers() -> None:
    for command_cls in (
        PutAutomationMemberInPoolCommand,
        RemoveAutomationMemberFromPoolCommand,
        SetAutomationMemberFocusCommand,
        SetAutomationMemberNormalCommand,
        MarkAutomationMemberWonCommand,
        UnmarkAutomationMemberWonCommand,
        PlanAutomationMemberOpenClawPushCommand,
    ):
        _command_bus.register(command_cls.command_name, _handle_action_plan)


def _validate_command(command: AutomationMemberActionCommand) -> None:
    if not command.command_id.strip():
        raise AutomationMemberActionInputError("command_id is required")
    if not command.source_route.strip():
        raise AutomationMemberActionInputError("source_route is required")
    normalize_identity(external_contact_id=command.external_contact_id, phone=command.phone)


def _empty_detail(identity: dict[str, str]) -> dict[str, Any]:
    external_contact_id = identity["external_contact_id"]
    phone = identity["phone"]
    member = {
        "id": "",
        "external_contact_id": external_contact_id,
        "external_userid": external_contact_id,
        "phone": phone,
        "mobile": phone,
        "in_pool": False,
        "current_pool": "removed",
        "current_pool_label": "已移出",
        "current_stage": "removed",
        "current_stage_label": "已移出",
        "current_target": "",
        "current_target_label": "无",
        "follow_type": "normal",
        "won": False,
    }
    return {
        "member": member,
        "questionnaire": {"status": "", "status_label": "待提交", "result_label": ""},
        "latest_manual_action": {},
        "last_ai_push_at": "",
        "ai_cooldown_remaining_seconds": 0,
        "actions": {
            "put_in_pool": {"enabled": True},
            "remove_from_pool": {"enabled": False},
            "set_focus": {"enabled": True},
            "set_normal": {"enabled": False},
            "mark_won": {"enabled": False},
            "unmark_won": {"enabled": False},
            "push_openclaw": {"enabled": True},
        },
        "source_status": "next_automation_member_read",
        "degraded": True,
    }


def _handle_action_plan(command: Command) -> dict[str, Any]:
    action_key = str(command.payload.get("action_key") or "member_action")
    command_cls = _command_class_for_name(command.command_name)
    identity = normalize_identity(
        external_contact_id=command.payload.get("external_contact_id"),
        phone=command.payload.get("phone"),
    )
    plan, attempt = _create_blocked_plan(command=command, command_cls=command_cls, identity=identity, action_key=action_key)
    return {
        "source_status": "next_command",
        "status": "planned_blocked",
        "action": action_key,
        "external_contact_id": identity["external_contact_id"],
        "phone": identity["phone"],
        "planned_count": 1,
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
        "skipped_count": 1,
        "accepted": False,
        "side_effect_plan": _plan_response(plan),
        "external_call_attempt": attempt.to_dict(),
        "openclaw_push_executed": False,
        "wecom_send_executed": False,
    }


def _command_class_for_name(command_name: str) -> type[AutomationMemberActionCommand]:
    for command_cls in (
        PutAutomationMemberInPoolCommand,
        RemoveAutomationMemberFromPoolCommand,
        SetAutomationMemberFocusCommand,
        SetAutomationMemberNormalCommand,
        MarkAutomationMemberWonCommand,
        UnmarkAutomationMemberWonCommand,
        PlanAutomationMemberOpenClawPushCommand,
    ):
        if command_cls.command_name == command_name:
            return command_cls
    return AutomationMemberActionCommand


def _create_blocked_plan(
    *,
    command: Command,
    command_cls: type[AutomationMemberActionCommand],
    identity: dict[str, str],
    action_key: str,
) -> tuple[SideEffectPlan, Any]:
    target_id = identity["external_contact_id"] or identity["phone"]
    plan = _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=command_cls.effect_type,
        adapter_name=command_cls.adapter_name,
        adapter_mode=ADAPTER_MODE,
        target_type="automation_member",
        target_id=target_id,
        payload={
            "payload_summary": {
                "external_contact_id": identity["external_contact_id"],
                "phone_present": bool(identity["phone"]),
                "action": action_key,
            },
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "openclaw_push_executed": False,
            "wecom_send_executed": False,
        },
        status="blocked",
        risk_level=command_cls.risk_level,
        requires_approval=command_cls.requires_approval,
    )
    attempt = _external_call_attempts.record_attempt(
        adapter_name=command_cls.adapter_name,
        adapter_mode=ADAPTER_MODE,
        operation=action_key,
        request_id=command.command_id,
        trace_id=command.context.trace_id,
        side_effect_plan_id=plan.side_effect_plan_id,
        status="blocked",
        request_summary={
            "external_contact_id": identity["external_contact_id"],
            "phone_present": bool(identity["phone"]),
            "action": action_key,
            "dry_run": command.payload.get("dry_run", True),
        },
        response_summary={
            "blocked": True,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "openclaw_push_executed": False,
            "wecom_send_executed": False,
        },
        error_code="real_blocked",
        error_message="Automation member action is plan-only in Next safe mode.",
    )
    return plan, attempt


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["real_external_call_executed"] = False
    payload["automation_runtime_executed"] = False
    payload["openclaw_push_executed"] = False
    payload["wecom_send_executed"] = False
    return payload


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="automation_member",
        target_id=str((command.payload or {}).get("external_contact_id") or (command.payload or {}).get("phone") or ""),
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "action": (command.payload or {}).get("action_key"),
            "fallback_used": False,
            "adapter_mode": ADAPTER_MODE,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
            "openclaw_push_executed": False,
            "wecom_send_executed": False,
        },
    )


def _audit_event_for(command_id: str) -> dict[str, Any]:
    for event in reversed(get_member_actions_audit_events()):
        if event.get("command_id") == command_id:
            return event
    return {}


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    response = {
        "ok": result.status == "completed",
        "command_id": result.command_id,
        "command_name": result.command_name,
        "idempotency_key": result.idempotency_key,
        "source_status": str(payload.pop("source_status", "") or "next_command"),
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "adapter_mode": ADAPTER_MODE,
        "real_external_call_executed": False,
        "automation_runtime_executed": False,
        "openclaw_push_executed": False,
        "wecom_send_executed": False,
        "audit_recorded": True,
        "audit_event": _audit_event_for(result.command_id),
        "command_result_status": result.status,
        "actor": {"id": result.actor_id, "type": result.actor_type},
    }
    response.update(payload)
    return response


reset_member_actions_fixture_state()
