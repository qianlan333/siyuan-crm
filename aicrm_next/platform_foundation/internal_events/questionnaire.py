from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH

from .consumer_registry import DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY, InternalEventConsumerRegistry
from .legacy_path_markers import mark_legacy_path_invoked
from .models import InternalEvent, InternalEventConsumerResult, InternalEventConsumerRun

QUESTIONNAIRE_SUBMITTED_EVENT_TYPE = "questionnaire.submitted"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _payload(event: InternalEvent) -> dict[str, Any]:
    return dict(event.payload_json or {})


def _questionnaire_from_event(event: InternalEvent) -> dict[str, Any]:
    questionnaire = _payload(event).get("questionnaire")
    return dict(questionnaire or {}) if isinstance(questionnaire, dict) else {}


def _submission_from_event(event: InternalEvent) -> dict[str, Any]:
    submission = _payload(event).get("submission")
    return dict(submission or {}) if isinstance(submission, dict) else {}


def _source_from_event(event: InternalEvent) -> dict[str, Any]:
    source = _payload(event).get("source")
    return dict(source or {}) if isinstance(source, dict) else {}


def _answer_snapshots(event: InternalEvent) -> list[dict[str, Any]]:
    snapshots = _payload(event).get("answer_snapshots")
    if not isinstance(snapshots, list):
        return []
    return [dict(item) for item in snapshots if isinstance(item, dict)]


def _questionnaire_id(questionnaire: dict[str, Any], submission: dict[str, Any]) -> str:
    return _text(questionnaire.get("id") or submission.get("questionnaire_id"))


def _submission_id(event: InternalEvent, submission: dict[str, Any]) -> str:
    return _text(submission.get("submission_id") or event.aggregate_id)


def _external_push_config(questionnaire: dict[str, Any]) -> dict[str, Any]:
    config = questionnaire.get("external_push_config")
    return dict(config or {}) if isinstance(config, dict) else {}


def _external_push_enabled(questionnaire: dict[str, Any]) -> bool:
    config = _external_push_config(questionnaire)
    return _bool(config.get("enabled") or questionnaire.get("external_push_enabled"))


def _target_url(questionnaire: dict[str, Any]) -> str:
    config = _external_push_config(questionnaire)
    return _text(config.get("webhook_url") or questionnaire.get("external_push_url"))


def _bool(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() in {"1", "true", "yes", "on", "t"}


def _mark_legacy_hook(event: InternalEvent, run: InternalEventConsumerRun, *, legacy_path: str, reason: str) -> None:
    mark_legacy_path_invoked(
        legacy_path=legacy_path,
        replacement_event_type=event.event_type,
        replacement_consumer=run.consumer_name,
        source_module="platform_foundation.internal_events.questionnaire",
        source_route=f"/internal-events/{event.event_type}/{run.consumer_name}",
        aggregate_id=event.aggregate_id or event.subject_id,
        reason=reason,
    )


def _questionnaire_external_body(
    *,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    answer_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    for item in answer_snapshots:
        question_type = _text(item.get("question_type"))
        title = _text(item.get("question_title_snapshot"))
        if not title:
            continue
        if question_type == "multi_choice":
            answer: str | list[str] = [_text(value) for value in item.get("selected_option_texts_snapshot") or [] if _text(value)]
        elif question_type == "single_choice":
            values = [_text(value) for value in item.get("selected_option_texts_snapshot") or [] if _text(value)]
            answer = values[0] if values else ""
        elif question_type in {"textarea", "mobile"}:
            answer = _text(item.get("text_value"))
        else:
            continue
        answers.append({"title": title, "answer": answer})
    body: dict[str, Any] = {
        "user_id": _text(submission.get("respondent_key") or submission.get("external_userid") or submission.get("unionid") or submission.get("openid")),
        "questionnaire_title": _text(questionnaire.get("title") or questionnaire.get("name")),
        "submitted_at": _text(submission.get("submitted_at") or submission.get("created_at")),
        "phone_number": "NULL",
        "answers": answers,
    }
    for item in answer_snapshots:
        if _text(item.get("question_type")) == "mobile" and _text(item.get("text_value")):
            body["phone_number"] = _text(item.get("text_value"))
            break
    config = _external_push_config(questionnaire)
    for key in ("type", "remark"):
        value = _text(config.get(key) or questionnaire.get(f"external_push_{key}"))
        if value:
            body[key] = value
    for key in ("day", "frequency", "expires_at_ts"):
        value = config.get(key) if key in config else questionnaire.get(f"external_push_{key}")
        if value not in (None, ""):
            body[key] = int(value)
    return body


def questionnaire_projection_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    submission = _submission_from_event(event)
    submission_id = _submission_id(event, submission)
    if not submission_id:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
            response_summary={"submission_found": False},
            error_code="submission_id_missing",
            error_message="questionnaire.submitted event is missing submission_id",
        )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "submission_id": submission_id},
        response_summary={"submission_found": True, "projection": "noop"},
        result_summary={"submission_id": submission_id, "questionnaire_projection": "submitted_confirmed"},
    )


def questionnaire_webhook_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    _mark_legacy_hook(
        event,
        run,
        legacy_path="questionnaire.legacy_webhook_external_push",
        reason="questionnaire_webhook_replaced_by_internal_event_consumer",
    )
    questionnaire = _questionnaire_from_event(event)
    submission = _submission_from_event(event)
    submission_id = _submission_id(event, submission)
    questionnaire_id = _questionnaire_id(questionnaire, submission)
    business_id = questionnaire_id or _text(questionnaire.get("slug"))
    if not submission_id or not business_id:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "submission_id": submission_id},
            response_summary={"external_effect_job_created": False},
            error_code="questionnaire_identity_missing",
            error_message="submission_id and questionnaire_id are required",
        )
    external_effects = ExternalEffectService()
    existing_job = external_effects.find_existing_job(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        target_type="questionnaire_submission",
        target_id=submission_id,
        business_type="questionnaire",
        business_id=business_id,
    )
    if existing_job is not None:
        return InternalEventConsumerResult(
            status="succeeded",
            request_summary={"event_id": event.event_id, "submission_id": submission_id},
            response_summary={
                "external_effect_job_created": False,
                "external_effect_job_reused": True,
                "external_effect_job_id": existing_job.id,
                "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
                "execution_mode": existing_job.execution_mode,
                "status": existing_job.status,
            },
            result_summary={
                "external_effect_job_id": existing_job.id,
                "external_effect_job_reused": True,
                "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            },
        )
    if not _external_push_enabled(questionnaire) or not _target_url(questionnaire):
        return InternalEventConsumerResult(
            status="skipped",
            request_summary={"event_id": event.event_id, "submission_id": submission_id},
            response_summary={
                "skipped": True,
                "reason": "questionnaire_external_push_not_configured",
                "external_effect_job_created": False,
            },
            result_summary={"reason": "questionnaire_external_push_not_configured"},
        )
    body = _questionnaire_external_body(
        questionnaire=questionnaire,
        submission=submission,
        answer_snapshots=_answer_snapshots(event),
    )
    source = _source_from_event(event)
    target_url = _target_url(questionnaire)
    job = external_effects.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id=submission_id,
        business_type="questionnaire",
        business_id=business_id,
        payload={
            "webhook_url": target_url,
            "body": body,
            "signature": {
                "enabled": False,
                "alg": "hmac-sha256",
                "header": "X-AICRM-External-Effect-Signature",
            },
            "internal_event_id": event.event_id,
        },
        payload_summary={
            "questionnaire_id": int(questionnaire_id or 0),
            "slug": _text(questionnaire.get("slug")),
            "submission_id": submission_id,
            "external_push_mode": "queue",
            "target_url_present": bool(target_url),
            "body_type": "dict",
            "answer_count": len(body.get("answers") or []),
            "phone_number_present": bool(body.get("phone_number") and body.get("phone_number") != "NULL"),
            "user_id_present": bool(_text(body.get("user_id"))),
            "internal_event_id": event.event_id,
        },
        context=CommandContext(
            actor_id="internal_event_consumer",
            actor_type="system",
            request_id=event.request_id or _text(source.get("command_id")),
            trace_id=event.trace_id,
            source_route="/internal-events/questionnaire.submitted/questionnaire_webhook_consumer",
        ),
        source_module="platform_foundation.internal_events.questionnaire",
        source_event_id=event.event_id,
        source_command_id=_text(source.get("command_id") or event.source_command_id),
        risk_level="medium",
        requires_approval=False,
        execution_mode="execute",
        status="queued",
        idempotency_key=f"questionnaire.submitted:{submission_id}:external-effect:{WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH}",
    )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "submission_id": submission_id},
        response_summary={
            "external_effect_job_created": True,
            "external_effect_job_reused": False,
            "external_effect_job_id": job.get("id"),
            "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            "execution_mode": job.get("execution_mode"),
            "status": job.get("status"),
        },
        result_summary={
            "external_effect_job_id": job.get("id"),
            "external_effect_job_reused": False,
            "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        },
    )


def questionnaire_tag_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    _mark_legacy_hook(
        event,
        run,
        legacy_path="questionnaire.legacy_tag_side_effect",
        reason="questionnaire_tag_hook_replaced_by_internal_event_consumer",
    )
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary={"skipped": True, "reason": "questionnaire_tag_side_effect_already_planned_or_not_configured"},
        result_summary={"reason": "questionnaire_tag_side_effect_already_planned_or_not_configured"},
    )


def automation_questionnaire_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    _mark_legacy_hook(
        event,
        run,
        legacy_path="questionnaire.legacy_automation_trigger",
        reason="questionnaire_automation_hook_replaced_by_internal_event_consumer",
    )
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary={"skipped": True, "reason": "automation_questionnaire_not_configured"},
        result_summary={"reason": "automation_questionnaire_not_configured"},
    )


def customer_summary_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary={"skipped": True, "reason": "customer_summary_not_configured"},
        result_summary={"reason": "customer_summary_not_configured"},
    )


def register_questionnaire_event_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY
    registry.register(QUESTIONNAIRE_SUBMITTED_EVENT_TYPE, "questionnaire_projection_consumer", questionnaire_projection_consumer, consumer_type="projection")
    registry.register(QUESTIONNAIRE_SUBMITTED_EVENT_TYPE, "questionnaire_webhook_consumer", questionnaire_webhook_consumer, consumer_type="external_effect_planner")
    registry.register(QUESTIONNAIRE_SUBMITTED_EVENT_TYPE, "questionnaire_tag_consumer", questionnaire_tag_consumer, consumer_type="orchestration")
    registry.register(QUESTIONNAIRE_SUBMITTED_EVENT_TYPE, "automation_questionnaire_consumer", automation_questionnaire_consumer, consumer_type="orchestration")
    registry.register(QUESTIONNAIRE_SUBMITTED_EVENT_TYPE, "customer_summary_consumer", customer_summary_consumer, consumer_type="projection")
