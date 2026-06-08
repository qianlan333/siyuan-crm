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
ADAPTER_MODE_LOCAL = "local"
ADAPTER_MODE_BLOCKED = "real_blocked"
DEFAULT_ACTOR = "customer_automation_webhook"


class CustomerAutomationWebhookInputError(ValueError):
    pass


@dataclass(frozen=True)
class CustomerAutomationWebhookCommand:
    command_id: str = field(default_factory=lambda: "cmd_customer_automation_webhook_" + uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = DEFAULT_ACTOR
    actor_type: str = "system"
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dry_run: bool = True

    command_name = "customer_automation.webhook.plan"
    operation = "webhook.plan"
    effect_type = "customer_automation.webhook.plan"
    adapter_name = "customer_automation_webhook"
    adapter_mode = ADAPTER_MODE_BLOCKED
    target_type = "customer_automation_webhook"
    risk_level = "high"
    requires_approval = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
            "requested_at": self.requested_at,
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class ApplyCustomerActivationWebhookCommand(CustomerAutomationWebhookCommand):
    mobile: str = ""
    activated_at: str = ""
    source: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)

    command_name = "customer_automation.activation_webhook.apply.plan"
    operation = "activation_webhook.apply"
    effect_type = "customer_automation.activation_webhook.apply"
    adapter_name = "customer_activation_projection"
    adapter_mode = ADAPTER_MODE_LOCAL
    target_type = "customer"
    risk_level = "medium"
    requires_approval = False

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload.update(
            {
                "mobile": self.mobile,
                "activated_at": self.activated_at,
                "source": self.source,
                "raw_payload": dict(self.raw_payload or {}),
            }
        )
        return payload


@dataclass(frozen=True)
class PlanCustomerWebhookDeliveryRetryCommand(CustomerAutomationWebhookCommand):
    delivery_id: int = 0

    command_name = "customer_automation.webhook_delivery.retry.plan"
    operation = "webhook_delivery.retry"
    effect_type = "customer_automation.webhook_delivery.retry"
    adapter_name = "customer_outbound_webhook"
    target_type = "customer_automation_webhook_delivery"

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["delivery_id"] = self.delivery_id
        return payload


@dataclass(frozen=True)
class PlanCustomerWebhookDeliveryRetryDueCommand(CustomerAutomationWebhookCommand):
    limit: int = 20

    command_name = "customer_automation.webhook_delivery.retry_due.plan"
    operation = "webhook_delivery.retry_due"
    effect_type = "customer_automation.webhook_delivery.retry_due"
    adapter_name = "customer_outbound_webhook"
    target_type = "customer_automation_webhook_delivery_due_candidates"

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["limit"] = self.limit
        return payload


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_external_call_attempts = InMemoryExternalCallAttemptRepository()
_command_bus = CommandBus()


def reset_customer_webhook_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _external_call_attempts, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _external_call_attempts = InMemoryExternalCallAttemptRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_customer_webhook_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_customer_webhook_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def get_customer_webhook_external_call_attempts() -> list[dict[str, Any]]:
    return [attempt.to_dict() for attempt in _external_call_attempts.list_attempts()]


def execute_customer_webhook_command(command: CustomerAutomationWebhookCommand) -> dict[str, Any]:
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
        raise CustomerAutomationWebhookInputError(result.error or "customer automation webhook command failed")
    return _response_from_result(result, dict(result.payload))


def normalize_actor(value: Any, fallback: str = DEFAULT_ACTOR) -> str:
    actor = str(value or "").strip()
    return actor or fallback


def normalize_mobile(value: Any) -> str:
    mobile = str(value or "").strip()
    if not mobile:
        raise CustomerAutomationWebhookInputError("mobile is required")
    return mobile


def normalize_delivery_id(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CustomerAutomationWebhookInputError("delivery_id must be a positive integer") from exc
    if parsed < 1:
        raise CustomerAutomationWebhookInputError("delivery_id must be a positive integer")
    return parsed


def normalize_limit(value: Any, *, default: int = 20, maximum: int = 1000) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CustomerAutomationWebhookInputError("limit must be a positive integer") from exc
    if parsed < 1:
        raise CustomerAutomationWebhookInputError("limit must be a positive integer")
    return min(parsed, maximum)


def diagnostics_payload(source_status: str) -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": source_status,
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "allowed_methods": ["POST", "OPTIONS"],
        "adapter_mode": ADAPTER_MODE_BLOCKED,
        "real_external_call_executed": False,
        "outbound_webhook_executed": False,
        "automation_runtime_executed": False,
        "wecom_send_executed": False,
    }


def _register_handlers() -> None:
    _command_bus.register(ApplyCustomerActivationWebhookCommand.command_name, _handle_activation_apply)
    _command_bus.register(PlanCustomerWebhookDeliveryRetryCommand.command_name, _handle_delivery_retry)
    _command_bus.register(PlanCustomerWebhookDeliveryRetryDueCommand.command_name, _handle_delivery_retry_due)


def _validate_command(command: CustomerAutomationWebhookCommand) -> None:
    if not command.command_id.strip():
        raise CustomerAutomationWebhookInputError("command_id is required")
    if not command.source_route.strip():
        raise CustomerAutomationWebhookInputError("source_route is required")
    if isinstance(command, ApplyCustomerActivationWebhookCommand):
        normalize_mobile(command.mobile)
    if isinstance(command, PlanCustomerWebhookDeliveryRetryCommand):
        normalize_delivery_id(command.delivery_id)
    if isinstance(command, PlanCustomerWebhookDeliveryRetryDueCommand):
        normalize_limit(command.limit)


def _handle_activation_apply(command: Command) -> dict[str, Any]:
    mobile = normalize_mobile(command.payload.get("mobile"))
    candidate = {
        "candidate_id": f"mobile:{mobile}",
        "target_type": "customer_activation",
        "status": "local_projection_only",
        "estimated_actions": 1,
    }
    plan = _create_plan(
        command=command,
        command_cls=ApplyCustomerActivationWebhookCommand,
        target_id=mobile,
        candidates=[candidate],
        status="planned",
        extra_summary={
            "mobile_present": True,
            "source": command.payload.get("source") or "",
            "activated_at_present": bool(command.payload.get("activated_at")),
        },
    )
    return _planned_payload(
        source_status="next_customer_activation_webhook",
        status="planned_local_only",
        candidates=[candidate],
        plan=plan,
        attempt=None,
        extra={
            "mobile": mobile,
            "customer_automation_applied": "local_only",
            "outbound_webhook_executed": False,
        },
    )


def _handle_delivery_retry(command: Command) -> dict[str, Any]:
    delivery_id = normalize_delivery_id(command.payload.get("delivery_id"))
    candidate = {
        "candidate_id": f"delivery:{delivery_id}",
        "delivery_id": delivery_id,
        "target_type": "customer_automation_webhook_delivery",
        "status": "blocked_plan_only",
        "estimated_actions": 1,
    }
    plan = _create_plan(
        command=command,
        command_cls=PlanCustomerWebhookDeliveryRetryCommand,
        target_id=str(delivery_id),
        candidates=[candidate],
        status="blocked",
        extra_summary={"delivery_id": delivery_id},
    )
    attempt = _record_blocked_attempt(
        command=command,
        command_cls=PlanCustomerWebhookDeliveryRetryCommand,
        plan=plan,
        request_summary={"delivery_id": delivery_id},
    )
    return _planned_payload(
        source_status="next_customer_webhook_retry_plan",
        status="planned_blocked",
        candidates=[candidate],
        plan=plan,
        attempt=attempt,
        extra={
            "delivery_id": delivery_id,
            "delivery": {"id": delivery_id, "status": "blocked_plan_only"},
            "outbound_webhook_executed": False,
            "retried_count": 0,
        },
    )


def _handle_delivery_retry_due(command: Command) -> dict[str, Any]:
    limit = normalize_limit(command.payload.get("limit"))
    candidate = {
        "candidate_id": f"due_batch:{limit}",
        "limit": limit,
        "target_type": "customer_automation_webhook_delivery_due_candidates",
        "status": "blocked_plan_only",
        "estimated_actions": limit,
    }
    plan = _create_plan(
        command=command,
        command_cls=PlanCustomerWebhookDeliveryRetryDueCommand,
        target_id=f"due:{limit}",
        candidates=[candidate],
        status="blocked",
        extra_summary={"limit": limit},
    )
    attempt = _record_blocked_attempt(
        command=command,
        command_cls=PlanCustomerWebhookDeliveryRetryDueCommand,
        plan=plan,
        request_summary={"limit": limit},
    )
    return _planned_payload(
        source_status="next_customer_webhook_retry_due_plan",
        status="planned_blocked",
        candidates=[candidate],
        plan=plan,
        attempt=attempt,
        extra={
            "limit": limit,
            "outbound_webhook_executed": False,
            "retried_count": 0,
        },
    )


def _create_plan(
    *,
    command: Command,
    command_cls: type[CustomerAutomationWebhookCommand],
    target_id: str,
    candidates: list[dict[str, Any]],
    status: str,
    extra_summary: dict[str, Any],
) -> SideEffectPlan:
    return _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=command_cls.effect_type,
        adapter_name=command_cls.adapter_name,
        adapter_mode=command_cls.adapter_mode,
        target_type=command_cls.target_type,
        target_id=target_id,
        payload={
            "payload_summary": {
                "candidate_count": len(candidates),
                "estimated_action_count": _estimated_action_count(candidates),
                **extra_summary,
            },
            "real_external_call_executed": False,
            "outbound_webhook_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
        },
        status=status,
        risk_level=command_cls.risk_level,
        requires_approval=command_cls.requires_approval,
    )


def _record_blocked_attempt(
    *,
    command: Command,
    command_cls: type[CustomerAutomationWebhookCommand],
    plan: SideEffectPlan,
    request_summary: dict[str, Any],
) -> Any:
    return _external_call_attempts.record_attempt(
        adapter_name=command_cls.adapter_name,
        adapter_mode=command_cls.adapter_mode,
        operation=command_cls.operation,
        request_id=command.command_id,
        trace_id=command.context.trace_id,
        side_effect_plan_id=plan.side_effect_plan_id,
        status="blocked",
        request_summary={**request_summary, "dry_run": command.payload.get("dry_run", True)},
        response_summary={
            "blocked": True,
            "real_external_call_executed": False,
            "outbound_webhook_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
        },
        error_code="real_blocked",
        error_message="Customer automation webhook delivery is plan-only in Next safe mode.",
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
    estimated = _estimated_action_count(candidates)
    payload: dict[str, Any] = {
        "source_status": source_status,
        "status": status,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "estimated_actions": {
            "planned_action_count": estimated,
            "external_call_count": 0,
            "blocked_external_call_count": 0 if attempt is None else estimated,
            "local_projection_count": estimated if attempt is None else 0,
        },
        "planned_count": len(candidates),
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
        "skipped_count": 0 if attempt is None else len(candidates),
        "side_effect_plan": _plan_response(plan),
    }
    if attempt is not None:
        payload["external_call_attempt"] = attempt.to_dict()
    payload.update(extra)
    return payload


def _estimated_action_count(candidates: list[dict[str, Any]]) -> int:
    return sum(int(item.get("estimated_actions") or 0) for item in candidates)


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["real_external_call_executed"] = False
    payload["outbound_webhook_executed"] = False
    payload["automation_runtime_executed"] = False
    payload["wecom_send_executed"] = False
    return payload


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="customer_automation_webhook",
        target_id=str((command.payload or {}).get("delivery_id") or (command.payload or {}).get("mobile") or "due_batch"),
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "fallback_used": False,
            "adapter_mode": (result.payload or {}).get("side_effect_plan", {}).get("adapter_mode", ADAPTER_MODE_BLOCKED),
            "real_external_call_executed": False,
            "outbound_webhook_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
            "source_status": (result.payload or {}).get("source_status", ""),
        },
    )


def _audit_event_for(command_id: str) -> dict[str, Any]:
    for event in reversed(get_customer_webhook_audit_events()):
        if event.get("command_id") == command_id:
            return event
    return {}


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    response = {
        "ok": result.status == "completed",
        "command_id": result.command_id,
        "command_name": result.command_name,
        "idempotency_key": result.idempotency_key,
        "source_status": str(payload.pop("source_status", "") or "next_customer_webhook_plan"),
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "adapter_mode": str((payload.get("side_effect_plan") or {}).get("adapter_mode") or ADAPTER_MODE_BLOCKED),
        "real_external_call_executed": False,
        "outbound_webhook_executed": False,
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


reset_customer_webhook_fixture_state()
