from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from aicrm_next.identity_contact.application import ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import ResolvePersonIdentityRequest
from aicrm_next.customer_tags.live_mutation import execute_wecom_tag_mutation
from aicrm_next.customer_tags.mutation_commands import PlanQuestionnaireTagSideEffectCommand
from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.command_bus.models import utcnow_iso
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError, blocked_production_payload
from aicrm_next.shared.runtime import production_data_ready

from .domain import score_and_tags, validate_required_answers
from .external_push import deliver_questionnaire_external_push
from .repo import QuestionnaireRepository, build_questionnaire_repository


class QuestionnaireH5WriteInputError(ValueError):
    pass


class QuestionnaireH5WriteNotFoundError(LookupError):
    pass


class QuestionnaireH5WriteProductionUnavailableError(RuntimeError):
    pass


class QuestionnaireH5AlreadySubmittedError(ValueError):
    pass


@dataclass(frozen=True)
class QuestionnaireH5SubmitCommand:
    questionnaire_slug: str
    answers: dict[str, Any] = field(default_factory=dict)
    identity: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "anonymous"
    actor_type: str = "h5_client"
    dry_run: bool = False
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)

    command_name = "questionnaire.h5.submit"

    def to_payload(self) -> dict[str, Any]:
        return {
            "questionnaire_slug": self.questionnaire_slug,
            "answers": dict(self.answers),
            "identity": dict(self.identity),
            "source": dict(self.source),
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "dry_run": self.dry_run,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True)
class QuestionnaireClientDiagnosticsCommand:
    questionnaire_slug: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    identity: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "anonymous"
    actor_type: str = "h5_client"
    dry_run: bool = False
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)

    command_name = "questionnaire.h5.client_diagnostics"

    def to_payload(self) -> dict[str, Any]:
        return {
            "questionnaire_slug": self.questionnaire_slug,
            "diagnostics": dict(self.diagnostics),
            "identity": dict(self.identity),
            "source": dict(self.source),
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "dry_run": self.dry_run,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
        }


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_diagnostics: list[dict[str, Any]] = []
_command_bus = CommandBus()


def reset_questionnaire_h5_write_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _diagnostics, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _diagnostics = []
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_questionnaire_h5_write_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_questionnaire_h5_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def get_questionnaire_h5_client_diagnostics() -> list[dict[str, Any]]:
    return [dict(item) for item in _diagnostics]


def execute_questionnaire_h5_submit(command: QuestionnaireH5SubmitCommand) -> dict[str, Any]:
    _validate_submit_command(command)
    return _execute_platform_command(command.command_name, command.to_payload(), command)


def execute_questionnaire_client_diagnostics(command: QuestionnaireClientDiagnosticsCommand) -> dict[str, Any]:
    _validate_diagnostics_command(command)
    return _execute_platform_command(command.command_name, command.to_payload(), command)


def _execute_platform_command(
    command_name: str,
    payload: dict[str, Any],
    command: QuestionnaireH5SubmitCommand | QuestionnaireClientDiagnosticsCommand,
) -> dict[str, Any]:
    platform_command = Command(
        command_name=command_name,
        payload=payload,
        command_id=command.command_id,
        idempotency_key=command.idempotency_key,
        context=CommandContext(
            actor_id=command.actor_id,
            actor_type=command.actor_type,
            trace_id=command.trace_id,
            source_route=command.source_route,
            dry_run=command.dry_run,
        ),
    )
    result = _command_bus.execute(platform_command)
    if result.status == "failed":
        error = result.error or "questionnaire h5 command failed"
        normalized_error = error.lower()
        if "already_submitted" in normalized_error:
            raise QuestionnaireH5AlreadySubmittedError("already_submitted")
        if "questionnaire not found" in normalized_error or "questionnaire disabled" in normalized_error:
            raise QuestionnaireH5WriteNotFoundError(error)
        if "production" in normalized_error or "database_url" in normalized_error or "psycopg" in normalized_error or "connection" in normalized_error:
            raise QuestionnaireH5WriteProductionUnavailableError(error)
        raise QuestionnaireH5WriteInputError(error)
    response = dict(result.payload)
    response.setdefault("write_model_status", "dry_run" if result.status == "dry_run" else "completed")
    return _response_from_result(result, response)


def _audit_hook(command: Command, result: CommandResult) -> None:
    payload = result.payload if isinstance(result.payload, dict) else {}
    target_id = str(payload.get("submission_id") or payload.get("diagnostic_id") or command.payload.get("questionnaire_slug") or "")
    real_external_call_executed = bool(payload.get("real_external_call_executed"))
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="questionnaire_h5",
        target_id=target_id,
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "questionnaire_slug": command.payload.get("questionnaire_slug") or "",
            "fallback_used": False,
            "real_external_call_executed": real_external_call_executed,
        },
    )


def _register_handlers() -> None:
    _command_bus.register(QuestionnaireH5SubmitCommand.command_name, _handle_submit)
    _command_bus.register(QuestionnaireClientDiagnosticsCommand.command_name, _handle_diagnostics)


def _validate_submit_command(command: QuestionnaireH5SubmitCommand) -> None:
    if not command.command_id.strip():
        raise QuestionnaireH5WriteInputError("command_id is required")
    if not command.questionnaire_slug.strip():
        raise QuestionnaireH5WriteInputError("questionnaire_slug is required")
    if not command.source_route.strip():
        raise QuestionnaireH5WriteInputError("source_route is required")
    if not isinstance(command.answers, dict):
        raise QuestionnaireH5WriteInputError("answers must be an object")


def _validate_diagnostics_command(command: QuestionnaireClientDiagnosticsCommand) -> None:
    if not command.command_id.strip():
        raise QuestionnaireH5WriteInputError("command_id is required")
    if not command.questionnaire_slug.strip():
        raise QuestionnaireH5WriteInputError("questionnaire_slug is required")
    if not command.source_route.strip():
        raise QuestionnaireH5WriteInputError("source_route is required")
    if not isinstance(command.diagnostics, dict):
        raise QuestionnaireH5WriteInputError("diagnostics must be an object")


def _repo() -> QuestionnaireRepository:
    try:
        return build_questionnaire_repository()
    except RepositoryProviderError as exc:
        raise QuestionnaireH5WriteProductionUnavailableError(str(exc)) from exc
    except Exception as exc:
        if production_data_ready():
            raise QuestionnaireH5WriteProductionUnavailableError(str(exc)) from exc
        raise


def _handle_submit(command: Command) -> dict[str, Any]:
    payload = dict(command.payload)
    slug = str(payload.get("questionnaire_slug") or "").strip()
    answers = dict(payload.get("answers") or {})
    identity_payload = _identity_payload(payload.get("identity"))
    source_payload = dict(payload.get("source") or {})
    repo = _repo()
    try:
        item = repo.get_questionnaire_by_slug(slug)
        if not item:
            raise NotFoundError("questionnaire not found")
        if not bool(item.get("enabled", True)):
            raise NotFoundError("questionnaire disabled")
        validate_required_answers(item, answers)
        if not identity_payload.get("mobile"):
            mobile_answer = _mobile_answer_from_questions(item, answers)
            if mobile_answer:
                identity_payload["mobile"] = mobile_answer
        identity = ResolvePersonIdentityQuery()(
            ResolvePersonIdentityRequest(
                mobile=identity_payload.get("mobile"),
                external_userid=identity_payload.get("external_userid"),
                openid=identity_payload.get("openid"),
                unionid=identity_payload.get("unionid"),
            )
        )
        resolved_identity = {
            **identity_payload,
            "person_id": identity.person_id if identity else None,
            "external_userid": (identity.external_userid if identity else identity_payload.get("external_userid")) or "",
            "mobile": (identity.mobile if identity else identity_payload.get("mobile")) or "",
            "binding_status": identity.binding_status if identity else "unresolved",
        }
        if repo.find_submission_for_identity(int(item["id"]), resolved_identity):
            raise ContractError("already_submitted")
        score, final_tags = score_and_tags(item, answers)
        result = {
            "score": score,
            "final_tags": final_tags,
            "result_message": "提交成功",
        }
        submission = repo.create_submission(
            {
                "questionnaire_id": int(item["id"]),
                "slug": item["slug"],
                "respondent_key": identity_payload.get("respondent_key") or "",
                "external_userid": resolved_identity.get("external_userid") or "",
                "openid": identity_payload.get("openid") or "",
                "unionid": identity_payload.get("unionid") or "",
                "mobile": resolved_identity.get("mobile") or "",
                "answers": answers,
                "answers_json": answers,
                "result_json": result,
                "source_json": source_payload,
                "diagnostics_json": {},
                "respondent_identity": identity_payload,
                "person_id": resolved_identity.get("person_id"),
                "binding_status": resolved_identity.get("binding_status") or "unresolved",
                "score": score,
                "final_tags": final_tags,
                "status": "submitted",
                "updated_at": utcnow_iso(),
            }
        )
    except NotFoundError:
        raise
    except ContractError:
        raise
    except RepositoryProviderError as exc:
        raise QuestionnaireH5WriteProductionUnavailableError(str(exc)) from exc
    except Exception as exc:
        if production_data_ready():
            raise QuestionnaireH5WriteProductionUnavailableError(str(exc)) from exc
        raise
    external_push_result = deliver_questionnaire_external_push(
        repo=repo,
        questionnaire=item,
        submission=submission,
        computed_result=result,
    )
    tag_side_effect = _plan_questionnaire_tag_side_effect(
        command=command,
        questionnaire=item,
        submission=submission,
        final_tags=final_tags,
    )
    side_effect_plan = _create_submit_side_effect_plan(
        command=command,
        questionnaire=item,
        submission=submission,
        final_tags=final_tags,
        external_push_result=external_push_result,
        tag_side_effect=tag_side_effect,
    )
    real_external_call_executed = bool(external_push_result.get("attempted"))
    return {
        "ok": True,
        "success": True,
        "submission_id": submission["submission_id"],
        "questionnaire_id": int(item["id"]),
        "slug": item["slug"],
        "identity": _public_identity(submission),
        "external_userid": submission.get("external_userid") or "",
        "openid": submission.get("openid") or "",
        "unionid": submission.get("unionid") or "",
        "mobile": submission.get("mobile") or "",
        "person_id": submission.get("person_id"),
        "binding_status": submission.get("binding_status") or "unresolved",
        "result": result,
        "score": score,
        "final_tags": final_tags,
        "redirect_url": item.get("redirect_url") or f"/s/{item['slug']}/submitted",
        "write_model_status": "submitted",
        "external_push": external_push_result,
        "real_external_call_executed": real_external_call_executed,
        "side_effect_plan": _plan_response(side_effect_plan),
        "side_effects": {
            "wecom_tag": tag_side_effect,
            "external_push": external_push_result,
        },
    }


def _handle_diagnostics(command: Command) -> dict[str, Any]:
    payload = dict(command.payload)
    slug = str(payload.get("questionnaire_slug") or "").strip()
    repo = _repo()
    questionnaire_id = None
    resolved = False
    try:
        item = repo.get_questionnaire_by_slug(slug)
        if item:
            questionnaire_id = int(item["id"])
            resolved = True
    except Exception as exc:
        if production_data_ready():
            raise QuestionnaireH5WriteProductionUnavailableError(str(exc)) from exc
        raise
    diagnostic_id = f"diag_{uuid4().hex[:12]}"
    record = {
        "diagnostic_id": diagnostic_id,
        "questionnaire_id": questionnaire_id,
        "slug": slug,
        "resolved": resolved,
        "diagnostics_json": dict(payload.get("diagnostics") or {}),
        "identity": _identity_payload(payload.get("identity")),
        "source_json": dict(payload.get("source") or {}),
        "created_at": utcnow_iso(),
    }
    _diagnostics.append(record)
    _audit_ledger.record_event(
        event_type="questionnaire.h5.client_diagnostics.recorded",
        actor_id=command.context.actor_id,
        actor_type=command.context.actor_type,
        target_type="questionnaire_h5_diagnostic",
        target_id=diagnostic_id,
        source_route=command.context.source_route,
        command_id=command.command_id,
        trace_id=command.context.trace_id,
        payload={
            "questionnaire_slug": slug,
            "resolved": resolved,
            "fallback_used": False,
            "real_external_call_executed": False,
        },
    )
    return {
        "ok": True,
        "diagnostic_id": diagnostic_id,
        "questionnaire_id": questionnaire_id,
        "slug": slug,
        "resolved": resolved,
        "unresolved_slug": not resolved,
        "write_model_status": "diagnostic_recorded",
    }


def _identity_payload(raw: Any) -> dict[str, Any]:
    identity = dict(raw or {}) if isinstance(raw, dict) else {}
    return {
        "external_userid": str(identity.get("external_userid") or "").strip(),
        "openid": str(identity.get("openid") or "").strip(),
        "unionid": str(identity.get("unionid") or "").strip(),
        "mobile": str(identity.get("mobile") or "").strip(),
        "respondent_key": str(identity.get("respondent_key") or "").strip(),
    }


def _mobile_answer_from_questions(questionnaire: dict[str, Any], answers: dict[str, Any]) -> str:
    for question in questionnaire.get("questions") or []:
        if str(question.get("type") or "").strip() != "mobile":
            continue
        value = answers.get(str(question.get("id")))
        if isinstance(value, list):
            value = "、".join(str(item) for item in value if item not in (None, ""))
        mobile = str(value or "").strip()
        if mobile:
            return mobile
    return ""


def _public_identity(submission: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_userid": submission.get("external_userid") or "",
        "openid": submission.get("openid") or "",
        "unionid": submission.get("unionid") or "",
        "mobile": submission.get("mobile") or "",
        "binding_status": submission.get("binding_status") or "unresolved",
        "anonymous": not any(
            submission.get(key)
            for key in ["external_userid", "openid", "unionid", "mobile", "person_id"]
        ),
    }


def _create_submit_side_effect_plan(
    *,
    command: Command,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    final_tags: list[str],
    external_push_result: dict[str, Any],
    tag_side_effect: dict[str, Any],
) -> SideEffectPlan:
    external_push_config = dict(questionnaire.get("external_push_config") or {})
    external_push_attempted = bool(external_push_result.get("attempted"))
    return _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type="questionnaire.h5.submit.side_effects",
        adapter_name="questionnaire_submit",
        adapter_mode="real_enabled" if external_push_attempted else "real_blocked",
        target_type="questionnaire_submission",
        target_id=str(submission.get("submission_id") or ""),
        payload={
            "payload_summary": {
                "questionnaire_id": int(questionnaire["id"]),
                "slug": questionnaire.get("slug") or "",
                "submission_id": submission.get("submission_id") or "",
                "final_tag_count": len(final_tags),
                "external_push_configured": bool(external_push_config.get("enabled")),
                "external_push_attempted": external_push_attempted,
                "external_push_status": external_push_result.get("status") or "",
                "external_push_log_id": (external_push_result.get("log") or {}).get("id") if isinstance(external_push_result.get("log"), dict) else None,
                "questionnaire_tag_effect_type": tag_side_effect.get("effect_type") or "",
            },
            "planned_effects": [
                effect
                for effect in [
                    "wecom.tag.plan" if final_tags else "",
                    "external_push.executed" if external_push_attempted else ("external_push.skipped" if external_push_config.get("enabled") else ""),
                    "automation.questionnaire_result.plan",
                ]
                if effect
            ],
            "real_external_call_executed": external_push_attempted,
        },
        status="executed" if external_push_attempted else "planned",
        risk_level="medium",
        requires_approval=not external_push_attempted,
        executed_at=utcnow_iso() if external_push_attempted else "",
    )


def _plan_questionnaire_tag_side_effect(
    *,
    command: Command,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    final_tags: list[str],
) -> dict[str, Any]:
    external_userid = str(submission.get("external_userid") or "").strip()
    if not external_userid or not final_tags:
        return {
            "ok": True,
            "source_status": "next_command",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "effect_type": "questionnaire.tag.apply",
            "adapter_mode": "real_blocked",
            "real_external_call_executed": False,
            "wecom_api_called": False,
            "skipped": True,
            "reason": "missing_external_userid_or_tags",
        }
    return execute_wecom_tag_mutation(
        PlanQuestionnaireTagSideEffectCommand(
            idempotency_key=f"{command.idempotency_key or command.command_id}:questionnaire-tag-apply",
            actor_id="questionnaire_h5_submit",
            actor_type="system",
            external_userid=external_userid,
            tag_ids=final_tags,
            source_route=command.context.source_route or "/api/h5/questionnaires/{slug}/submit",
            source_context={
                "source": "questionnaire_h5_submit",
                "questionnaire_id": int(questionnaire["id"]),
                "submission_id": submission.get("submission_id") or "",
                "slug": questionnaire.get("slug") or "",
            },
            trace_id=command.context.trace_id,
        )
    )


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    payload["real_external_call_executed"] = bool((payload.get("payload") or {}).get("real_external_call_executed"))
    payload["requires_approval"] = bool(payload.get("requires_approval"))
    return payload


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    real_external_call_executed = bool(payload.get("real_external_call_executed"))
    payload.update(
        {
            "command_name": result.command_name,
            "command_id": result.command_id,
            "source_status": "next_command",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": real_external_call_executed,
            "audit_recorded": True,
        }
    )
    return payload


reset_questionnaire_h5_write_fixture_state()
