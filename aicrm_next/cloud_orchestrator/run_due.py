from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.external_calls import InMemoryExternalCallAttemptRepository
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan

from .campaigns_read import build_campaign_read_repository

PREVIEW_SOURCE_STATUS = "next_run_due_preview"
PLAN_SOURCE_STATUS = "next_run_due_plan"
ROUTE_OWNER = "ai_crm_next"
ADAPTER_MODE = "real_blocked"
DEFAULT_BATCH_SIZE = 200
MAX_BATCH_SIZE = 1000


class CloudCampaignRunDueInputError(ValueError):
    pass


@dataclass(frozen=True)
class CloudCampaignRunDueCommand:
    command_id: str = field(default_factory=lambda: "cmd_cloud_run_due_" + uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "timer"
    actor_type: str = "timer"
    batch_size: int = DEFAULT_BATCH_SIZE
    dry_run: bool = True
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    now: str = ""

    command_name = "cloud_orchestrator.campaign.run_due"

    def to_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "batch_size": self.batch_size,
            "dry_run": self.dry_run,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
            "requested_at": self.requested_at,
            "now": self.now,
        }


@dataclass(frozen=True)
class PreviewCloudCampaignRunDueCommand(CloudCampaignRunDueCommand):
    command_name = "cloud_orchestrator.campaign.run_due.preview"


@dataclass(frozen=True)
class PlanCloudCampaignRunDueCommand(CloudCampaignRunDueCommand):
    force_plan: bool = True
    command_name = "cloud_orchestrator.campaign.run_due.plan"

    def to_payload(self) -> dict[str, Any]:
        payload = super().to_payload()
        payload["force_plan"] = self.force_plan
        return payload


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_external_call_attempts = InMemoryExternalCallAttemptRepository()
_command_bus = CommandBus()


def reset_run_due_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _external_call_attempts, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _external_call_attempts = InMemoryExternalCallAttemptRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_run_due_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_run_due_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def get_run_due_external_call_attempts() -> list[dict[str, Any]]:
    return [attempt.to_dict() for attempt in _external_call_attempts.list_attempts()]


def execute_cloud_campaign_run_due_command(command: CloudCampaignRunDueCommand) -> dict[str, Any]:
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
        raise CloudCampaignRunDueInputError(result.error or "cloud campaign run-due command failed")
    return _response_from_result(result, dict(result.payload))


def _register_handlers() -> None:
    _command_bus.register(PreviewCloudCampaignRunDueCommand.command_name, _handle_preview)
    _command_bus.register(PlanCloudCampaignRunDueCommand.command_name, _handle_plan)


def _validate_command(command: CloudCampaignRunDueCommand) -> None:
    if not command.command_id.strip():
        raise CloudCampaignRunDueInputError("command_id is required")
    if not command.source_route.strip():
        raise CloudCampaignRunDueInputError("source_route is required")
    if int(command.batch_size) < 1 or int(command.batch_size) > MAX_BATCH_SIZE:
        raise CloudCampaignRunDueInputError("batch_size must be between 1 and 1000")


def normalize_batch_size(value: Any, *, default: int = DEFAULT_BATCH_SIZE) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CloudCampaignRunDueInputError("batch_size must be an integer") from exc
    if parsed < 1 or parsed > MAX_BATCH_SIZE:
        raise CloudCampaignRunDueInputError("batch_size must be between 1 and 1000")
    return parsed


def _repo() -> Any:
    return build_campaign_read_repository()


def _due_candidates(batch_size: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        repo = _repo()
        campaigns, _total = repo.list_campaigns(limit=batch_size, offset=0)
    except Exception as exc:
        return [], {"candidate_generation_status": "degraded", "error": str(exc)}

    candidates: list[dict[str, Any]] = []
    for campaign in campaigns:
        campaign_code = str(campaign.get("campaign_code") or "").strip()
        if not campaign_code:
            continue
        try:
            members_payload = repo.list_members(campaign_code, status="pending", limit=batch_size, offset=0) or {}
            steps_payload = repo.list_steps(campaign_code) or {}
        except Exception as exc:
            candidates.append(
                {
                    "campaign_code": campaign_code,
                    "campaign_id": campaign.get("id"),
                    "status": "degraded",
                    "error": str(exc),
                    "estimated_actions": 0,
                }
            )
            continue
        members = list(members_payload.get("members") or members_payload.get("rows") or [])
        steps = list(steps_payload.get("steps") or [])
        if not members:
            continue
        next_step = steps[0] if steps else {}
        for member in members:
            candidates.append(
                {
                    "campaign_code": campaign_code,
                    "campaign_id": campaign.get("id"),
                    "member_id": member.get("member_id"),
                    "external_contact_id": member.get("external_contact_id"),
                    "member_status": member.get("status"),
                    "current_step_index": member.get("current_step_index"),
                    "next_step_index": next_step.get("step_index", 0),
                    "next_due_at": member.get("next_due_at") or "",
                    "estimated_actions": 1,
                }
            )
            if len(candidates) >= batch_size:
                return candidates, {"candidate_generation_status": "ready"}
    return candidates, {"candidate_generation_status": "ready"}


def _estimated_actions(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    count = sum(int(item.get("estimated_actions") or 0) for item in candidates)
    return {
        "planned_message_count": count,
        "runtime_execution_count": 0,
        "wecom_send_count": 0,
        "blocked_external_call_count": count,
    }


def _handle_preview(command: Command) -> dict[str, Any]:
    batch_size = normalize_batch_size(command.payload.get("batch_size"))
    candidates, diagnostics = _due_candidates(batch_size)
    return {
        "source_status": PREVIEW_SOURCE_STATUS,
        "run_due_status": "preview_only",
        "candidates": candidates,
        "candidate_count": len(candidates),
        "estimated_actions": _estimated_actions(candidates),
        "dry_run": True,
        "planned_count": 0,
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
        "skipped_count": len(candidates),
        **diagnostics,
    }


def _handle_plan(command: Command) -> dict[str, Any]:
    batch_size = normalize_batch_size(command.payload.get("batch_size"))
    candidates, diagnostics = _due_candidates(batch_size)
    plan = _create_run_due_side_effect_plan(command=command, candidates=candidates, diagnostics=diagnostics)
    attempt = _external_call_attempts.record_attempt(
        adapter_name="cloud_orchestrator_runtime",
        adapter_mode=ADAPTER_MODE,
        operation="campaign.run_due",
        request_id=command.command_id,
        trace_id=command.context.trace_id,
        side_effect_plan_id=plan.side_effect_plan_id,
        status="blocked",
        request_summary={
            "batch_size": batch_size,
            "candidate_count": len(candidates),
            "dry_run": command.payload.get("dry_run", True),
        },
        response_summary={
            "blocked": True,
            "real_external_call_executed": False,
            "campaign_runtime_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
        },
        error_code="real_blocked",
        error_message="Cloud campaign run-due is plan-only in Next safe mode.",
    )
    return {
        "source_status": PLAN_SOURCE_STATUS,
        "run_due_status": "planned_blocked",
        "candidates": candidates,
        "candidate_count": len(candidates),
        "estimated_actions": _estimated_actions(candidates),
        "dry_run": bool(command.payload.get("dry_run", True)),
        "force_plan": bool(command.payload.get("force_plan", True)),
        "processed_count": 0,
        "planned_count": len(candidates),
        "sent_count": 0,
        "failed_count": 0,
        "skipped_count": len(candidates),
        "side_effect_plan": _plan_response(plan),
        "external_call_attempt": attempt.to_dict(),
        **diagnostics,
    }


def _create_run_due_side_effect_plan(*, command: Command, candidates: list[dict[str, Any]], diagnostics: dict[str, Any]) -> SideEffectPlan:
    return _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type="cloud_orchestrator.campaign.run_due",
        adapter_name="cloud_orchestrator_runtime",
        adapter_mode=ADAPTER_MODE,
        target_type="cloud_campaign_due_candidates",
        target_id="batch",
        payload={
            "payload_summary": {
                "batch_size": command.payload.get("batch_size"),
                "candidate_count": len(candidates),
                "candidate_generation_status": diagnostics.get("candidate_generation_status"),
            },
            "real_external_call_executed": False,
            "campaign_runtime_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
        },
        status="blocked",
        risk_level="high",
        requires_approval=True,
    )


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["real_external_call_executed"] = False
    payload["campaign_runtime_executed"] = False
    payload["automation_runtime_executed"] = False
    payload["wecom_send_executed"] = False
    return payload


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="cloud_campaign_due_candidates",
        target_id="batch",
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "fallback_used": False,
            "adapter_mode": ADAPTER_MODE,
            "real_external_call_executed": False,
            "campaign_runtime_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
            "candidate_count": (result.payload or {}).get("candidate_count", 0),
        },
    )


def _audit_event_for(command_id: str) -> dict[str, Any]:
    for event in reversed(get_run_due_audit_events()):
        if event.get("command_id") == command_id:
            return event
    return {}


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    source_status = str(payload.pop("source_status", "") or PLAN_SOURCE_STATUS)
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
        "campaign_runtime_executed": False,
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


def diagnostics_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "source_status": PLAN_SOURCE_STATUS,
        "route_owner": ROUTE_OWNER,
        "fallback_used": False,
        "adapter_mode": ADAPTER_MODE,
        "allowed_methods": ["POST", "OPTIONS"],
        "real_external_call_executed": False,
        "campaign_runtime_executed": False,
        "automation_runtime_executed": False,
        "wecom_send_executed": False,
        "side_effect_plan": {
            "effect_type": "cloud_orchestrator.campaign.run_due",
            "adapter_name": "cloud_orchestrator_runtime",
            "adapter_mode": ADAPTER_MODE,
            "requires_approval": True,
            "real_external_call_executed": False,
            "campaign_runtime_executed": False,
            "automation_runtime_executed": False,
            "wecom_send_executed": False,
            "payload_summary": {},
        },
    }


reset_run_due_fixture_state()
