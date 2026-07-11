from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from aicrm_next.identity_contact.application import BindMobileToExternalContactCommand, ResolvePersonIdentityQuery
from aicrm_next.identity_contact.dto import BindMobileToExternalContactRequest, ResolvePersonIdentityRequest
from aicrm_next.customer_tags.local_projection import (
    project_questionnaire_tags,
    reset_customer_tag_local_projection_fixture_state,
    validate_questionnaire_tag_ids,
)
from aicrm_next.integration_gateway.wecom_channel_entry_client import (
    ProductionWeComAdapter,
    WeComApiError,
    missing_wecom_config,
)
from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.internal_events.shadow import emit_questionnaire_submitted_shadow_event, safe_emit
from aicrm_next.platform_foundation.command_bus.models import utcnow_iso
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError
from aicrm_next.shared.runtime import production_data_ready

from .domain import normalize_mobile_answer, normalize_questionnaire, score_and_tags, validate_required_answers
from .external_push import (
    QUESTIONNAIRE_EXTERNAL_PUSH_MODE,
    plan_questionnaire_external_push_effect,
)
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
    reset_customer_tag_local_projection_fixture_state()
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
    if not command.answers:
        raise QuestionnaireH5WriteInputError("answers is required")


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
        mobile_answer = _mobile_answer_from_questions(item, answers)
        if mobile_answer:
            identity_payload["mobile"] = mobile_answer
        identity_resolution_error = ""
        try:
            identity = ResolvePersonIdentityQuery()(
                ResolvePersonIdentityRequest(
                    mobile=identity_payload.get("mobile"),
                    external_userid=identity_payload.get("external_userid"),
                    openid=identity_payload.get("openid"),
                    unionid=identity_payload.get("unionid"),
                )
            )
        except Exception as exc:
            identity = None
            identity_resolution_error = str(exc)
        resolved_identity = {
            **identity_payload,
            "person_id": identity.person_id if identity else None,
            "external_userid": (identity.external_userid if identity else identity_payload.get("external_userid")) or "",
            "unionid": identity_payload.get("unionid") or (identity.unionid if identity else "") or "",
            "mobile": (identity.mobile if identity else "") or identity_payload.get("mobile") or "",
            "binding_status": identity.binding_status if identity else ("identity_resolution_unavailable" if identity_resolution_error else "unresolved"),
            "identity_map_id": identity.identity_map_id if identity else None,
            "follow_user_userid": (identity.follow_user_userid if identity else "") or identity_payload.get("follow_user_userid") or "",
            "matched_by": (identity.matched_by if identity else identity_payload.get("matched_by")) or "",
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
                "unionid": resolved_identity.get("unionid") or "",
                "mobile": resolved_identity.get("mobile") or "",
                "answers": answers,
                "answers_json": answers,
                "result_json": result,
                "source_json": source_payload,
                "diagnostics_json": {
                    "identity_resolution_error": identity_resolution_error,
                } if identity_resolution_error else {},
                "respondent_identity": identity_payload,
                "person_id": resolved_identity.get("person_id"),
                "binding_status": resolved_identity.get("binding_status") or "unresolved",
                "identity_map_id": resolved_identity.get("identity_map_id"),
                "follow_user_userid": resolved_identity.get("follow_user_userid") or "",
                "matched_by": resolved_identity.get("matched_by") or "",
                "score": score,
                "final_tags": final_tags,
                "status": "submitted",
                "updated_at": utcnow_iso(),
            }
        )
        mobile_binding = _sync_questionnaire_mobile_binding(command=command, submission=submission)
        if mobile_binding.get("ok") and not mobile_binding.get("skipped"):
            submission = {
                **submission,
                "binding_status": mobile_binding.get("binding_status") or "bound",
                "person_id": mobile_binding.get("person_id") or submission.get("person_id"),
                "mobile": mobile_binding.get("mobile") or submission.get("mobile"),
                "follow_user_userid": mobile_binding.get("owner_userid") or submission.get("follow_user_userid"),
            }
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
    internal_event = safe_emit(
        "questionnaire.submitted",
        emit_questionnaire_submitted_shadow_event,
        command=command,
        questionnaire=item,
        submission=submission,
        score=score,
        final_tags=final_tags,
    )
    external_push_mode = QUESTIONNAIRE_EXTERNAL_PUSH_MODE
    external_push_config = dict(item.get("external_push_config") or {})
    external_push_result = {
        "enabled": bool(external_push_config.get("enabled") or item.get("external_push_enabled")),
        "attempted": False,
        "ok": True,
        "reason": "queued_external_effect",
        "status": "queued",
        "mode": external_push_mode,
        "legacy_outbound_disabled": True,
        "external_effect_required": True,
        "real_external_call_executed": False,
    }
    external_effect_job = plan_questionnaire_external_push_effect(
        questionnaire=item,
        submission=submission,
        computed_result=result,
        context=command.context,
        source_command_id=command.command_id,
        source_event_id=str((external_push_result.get("log") or {}).get("id") or ""),
        idempotency_key=f"{command.idempotency_key or command.command_id}:external-effect:webhook.questionnaire_submission.push",
        mode=external_push_mode,
        external_push_result=external_push_result,
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
    real_external_call_executed = bool(tag_side_effect.get("real_external_call_executed"))
    questionnaire_projection = normalize_questionnaire(item)
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
        "completion_target": questionnaire_projection["completion_target"],
        "completion_target_enabled": questionnaire_projection["completion_target_enabled"],
        "completion_target_type": questionnaire_projection["completion_target_type"],
        "write_model_status": "submitted",
        "external_push": external_push_result,
        "external_push_mode": external_push_mode,
        "tag_apply": tag_side_effect,
        "mobile_binding": mobile_binding,
        "real_external_call_executed": real_external_call_executed,
        "side_effect_plan": _plan_response(side_effect_plan),
        "side_effects": {
            "mobile_binding": mobile_binding,
            "wecom_tag": tag_side_effect,
            "external_push": external_push_result,
        },
        "external_effect_job_id": external_effect_job.get("id") if external_effect_job else None,
        "external_effect_job_status": external_effect_job.get("status") if external_effect_job else "",
        "external_effect_job": external_effect_job,
        "internal_event_id": internal_event.get("event_id") or "",
        "internal_event_status": internal_event.get("status") or "",
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
        "follow_user_userid": str(identity.get("follow_user_userid") or identity.get("owner_userid") or "").strip(),
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
        mobile = normalize_mobile_answer(value)
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


def _sync_questionnaire_mobile_binding(*, command: Command, submission: dict[str, Any]) -> dict[str, Any]:
    external_userid = str(submission.get("external_userid") or "").strip()
    mobile = str(submission.get("mobile") or submission.get("mobile_snapshot") or "").strip()
    if not external_userid or not mobile:
        return {
            "ok": True,
            "skipped": True,
            "reason": "missing_external_userid_or_mobile",
            "external_userid": external_userid,
            "mobile": mobile,
            "source_status": "questionnaire_mobile_binding",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": False,
        }
    try:
        result = BindMobileToExternalContactCommand()(
            BindMobileToExternalContactRequest(
                external_userid=external_userid,
                mobile=mobile,
                owner_userid=str(submission.get("follow_user_userid") or "").strip(),
                bind_by_userid="questionnaire_h5_submit",
                customer_name="问卷提交用户",
                force_rebind=True,
            )
        )
    except Exception as exc:
        return {
            "ok": False,
            "skipped": False,
            "reason": "mobile_binding_failed",
            "error": str(exc),
            "external_userid": external_userid,
            "mobile": mobile,
            "source_status": "questionnaire_mobile_binding_failed",
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": False,
        }
    return {
        "ok": bool(result.get("ok", True)),
        "skipped": False,
        "reason": "",
        "external_userid": str(result.get("external_userid") or external_userid),
        "mobile": str(result.get("mobile") or mobile),
        "owner_userid": str(result.get("owner_userid") or submission.get("follow_user_userid") or ""),
        "person_id": result.get("person_id"),
        "binding_status": str(result.get("binding_status") or "bound"),
        "source_status": str(result.get("source_status") or "questionnaire_mobile_binding"),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "side_effect_executed": bool(result.get("side_effect_executed")),
        "real_external_call_executed": False,
        "command_id": command.command_id,
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
    tag_planned_effects = _questionnaire_tag_planned_effects(tag_side_effect)
    external_work_queued = external_push_result.get("status") == "queued"
    tag_apply_status = str(tag_side_effect.get("status") or "").strip()
    return _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type="questionnaire.h5.submit.side_effects",
        adapter_name="questionnaire_submit",
        adapter_mode="real_enabled" if external_push_attempted or tag_side_effect.get("wecom_api_called") else "real_mark_tag",
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
                "external_push_mode": external_push_result.get("mode") or external_push_result.get("external_push_mode") or "",
                "external_push_log_id": (external_push_result.get("log") or {}).get("id") if isinstance(external_push_result.get("log"), dict) else None,
                "questionnaire_tag_effect_type": tag_side_effect.get("effect_type") or "",
                "questionnaire_tag_apply_status": tag_apply_status,
                "questionnaire_tag_error_code": tag_side_effect.get("error_code") or "",
                "questionnaire_tag_local_projection_status": tag_side_effect.get("local_projection_status") or "",
                "questionnaire_tag_wecom_api_called": bool(tag_side_effect.get("wecom_api_called")),
                "questionnaire_tag_mark_tag_executed": bool(tag_side_effect.get("mark_tag_executed")),
            },
            "planned_effects": [
                effect
                for effect in [
                    *tag_planned_effects,
                    (
                        "external_push.executed"
                        if external_push_attempted
                        else (
                            "external_push.queued"
                            if external_push_result.get("status") == "queued"
                            else ("external_push.skipped" if external_push_config.get("enabled") else "")
                        )
                    ),
                    "automation.questionnaire_result.recorded",
                ]
                if effect
            ],
            "real_external_call_executed": external_push_attempted or bool(tag_side_effect.get("real_external_call_executed")),
            "tag_apply": tag_side_effect,
        },
        status=(
            "executed"
            if external_push_attempted or tag_apply_status == "succeeded"
            else ("failed" if tag_apply_status == "failed" else ("queued" if external_work_queued else "skipped"))
        ),
        risk_level="medium",
        requires_approval=False,
        executed_at=utcnow_iso() if external_push_attempted or tag_side_effect.get("wecom_api_called") else "",
    )


def _questionnaire_tag_planned_effects(tag_side_effect: dict[str, Any]) -> list[str]:
    if not tag_side_effect:
        return []
    effects: list[str] = []
    local_status = str(tag_side_effect.get("local_projection_status") or "").strip()
    tag_status = str(tag_side_effect.get("status") or "").strip()
    if local_status == "updated":
        effects.append("wecom.tag.contact_tags_mirror.updated")
    elif local_status == "skipped":
        effects.append("wecom.tag.contact_tags_mirror.skipped")
    elif local_status:
        effects.append(f"wecom.tag.contact_tags_mirror.{local_status}")
    if tag_status == "succeeded":
        effects.append("wecom.tag.mark_tag.succeeded")
    elif tag_status == "failed":
        effects.append("wecom.tag.mark_tag.failed")
    elif tag_status == "skipped":
        effects.append("wecom.tag.mark_tag.skipped")
    return effects


def _plan_questionnaire_tag_side_effect(
    *,
    command: Command,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    final_tags: list[str],
) -> dict[str, Any]:
    return _execute_questionnaire_tag_apply(
        command=command,
        questionnaire=questionnaire,
        submission=submission,
        final_tags=final_tags,
    )


def _execute_questionnaire_tag_apply(
    *,
    command: Command,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    final_tags: list[str],
) -> dict[str, Any]:
    external_userid = str(submission.get("external_userid") or "").strip()
    unionid = str(submission.get("unionid") or "").strip()
    follow_user_userid = str(submission.get("follow_user_userid") or "").strip()
    tag_validation = validate_questionnaire_tag_ids(final_tags)
    tag_ids = list(tag_validation.get("tag_ids") or [])
    base = {
        "ok": False,
        "source_status": "tag_apply",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "effect_type": "questionnaire.tag.apply",
        "adapter_mode": "real_mark_tag",
        "execution_mode": "execute",
        "requires_approval": False,
        "external_userid": external_userid,
        "follow_user_userid": follow_user_userid,
        "tag_ids": tag_ids,
        "wecom_api_called": False,
        "real_external_call_executed": False,
        "mark_tag_executed": False,
        "local_projection": {},
        "local_projection_updated": False,
        "local_projection_status": "skipped",
        "contact_tags_mirror_status": "skipped",
        "external_effect_status": "",
        "external_effect_job": None,
        "external_effect_job_id": None,
    }
    if not tag_ids or tag_validation.get("ok") is False:
        return {
            **base,
            "status": "failed",
            "error_code": "tag_ids_missing",
            "error_message": "Questionnaire final_tags are empty or invalid.",
            "reason": "tag_ids_missing",
            "tag_validation": tag_validation,
            "skipped": False,
        }
    if not external_userid:
        return {
            **base,
            "status": "failed",
            "error_code": "missing_external_userid",
            "error_message": "external_userid is required for WeCom mark_tag.",
            "reason": "missing_external_userid",
            "skipped": False,
        }
    if not follow_user_userid:
        return {
            **base,
            "status": "failed",
            "error_code": "owner_userid_missing",
            "error_message": "follow_user_userid is required for WeCom mark_tag.",
            "reason": "owner_userid_missing",
            "skipped": False,
        }
    missing = missing_wecom_config()
    if missing:
        return {
            **base,
            "status": "failed",
            "error_code": "missing_wecom_config",
            "error_message": "missing_wecom_config:" + ",".join(missing),
            "missing_config": missing,
            "reason": "missing_wecom_config",
            "skipped": False,
        }
    request_payload = {
        "userid": follow_user_userid,
        "external_userid": external_userid,
        "add_tag": tag_ids,
    }
    try:
        response = ProductionWeComAdapter().mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            add_tags=tag_ids,
            remove_tags=[],
        )
    except Exception as exc:
        error = _questionnaire_tag_error(exc)
        return {
            **base,
            "status": "failed",
            "error_code": error["error_code"],
            "error_message": error["error_message"],
            "reason": error["error_code"],
            "retryable": bool(error.get("retryable")),
            "wecom_api_called": bool(error.get("wecom_api_called")),
            "real_external_call_executed": bool(error.get("wecom_api_called")),
            "request_payload": request_payload,
            "response_summary": error.get("response_summary") or {},
            "skipped": False,
        }
    projection_idempotency_key = f"{command.idempotency_key or command.command_id}:questionnaire-tag-local-projection"
    local_projection = project_questionnaire_tags(
        unionid=unionid,
        external_userid=external_userid,
        owner_userid=follow_user_userid,
        tag_ids=tag_ids,
        source="questionnaire_h5_submit",
        questionnaire_id=int(questionnaire["id"]),
        submission_id=str(submission.get("submission_id") or ""),
        idempotency_key=projection_idempotency_key,
    )
    return {
        **base,
        "ok": True,
        "status": "succeeded",
        "error_code": "",
        "error_message": "",
        "reason": "",
        "retryable": False,
        "wecom_api_called": True,
        "real_external_call_executed": True,
        "mark_tag_executed": True,
        "request_payload": request_payload,
        "wecom_response": dict(response or {}),
        "response_summary": {
            "errcode": int((response or {}).get("errcode") or 0) if isinstance(response, dict) else 0,
            "errmsg_present": bool(str((response or {}).get("errmsg") or "").strip()) if isinstance(response, dict) else False,
        },
        "local_projection": local_projection,
        "local_projection_updated": bool(local_projection.get("local_projection_updated")),
        "local_projection_status": local_projection.get("local_projection_status") or "skipped",
        "contact_tags_mirror_status": local_projection.get("local_projection_status") or "skipped",
        "skipped": False,
    }


def _questionnaire_tag_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, WeComApiError):
        payload = dict(exc.payload or {})
        errcode = int(payload.get("errcode") or 0)
        if errcode:
            return {
                "error_code": f"wecom_error_{errcode}",
                "error_message": str(payload.get("errmsg") or exc.message or exc)[:500],
                "retryable": errcode in {-1, 42001, 45009, 45011},
                "wecom_api_called": True,
                "response_summary": {
                    "errcode": errcode,
                    "errmsg_present": bool(str(payload.get("errmsg") or "").strip()),
                },
            }
        return {
            "error_code": "network_error",
            "error_message": str(exc.message or exc)[:500],
            "retryable": True,
            "wecom_api_called": True,
            "response_summary": {},
        }
    return {
        "error_code": "network_error",
        "error_message": str(exc)[:500],
        "retryable": True,
        "wecom_api_called": True,
        "response_summary": {},
    }


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
