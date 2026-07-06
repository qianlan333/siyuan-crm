from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.internal_events import (
    DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY,
    InternalEvent,
    InternalEventConsumerRegistry,
    InternalEventConsumerResult,
    InternalEventConsumerRun,
    PAYMENT_SUCCEEDED_EVENT_TYPES,
    QUESTIONNAIRE_SUBMITTED_EVENT_TYPE,
)

from .event_types import (
    DAILY_REFRESH_CONSUMER,
    DAILY_TICK_EVENT,
    INCREMENTAL_REFRESH_CONSUMER,
    INCREMENTAL_TICK_EVENT,
    OUTBOUND_EFFECT_CONSUMER,
    RUN_REFRESHED_EVENT,
    SOURCE_CHANGED_EVENT,
    SOURCE_POKE_CONSUMER,
)
from .outbound_service import AudienceOutboundService
from .refresh_service import AudienceRefreshService
from .repository import build_audience_repository, _text


def incremental_refresh_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    result = AudienceRefreshService().run_due("incremental", limit=_limit_from_event(event, default=20))
    return InternalEventConsumerResult(
        status="succeeded" if result.get("ok") else "failed_retryable",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary=_summary(result),
        result_summary=_summary(result),
        error_code="" if result.get("ok") else _text(result.get("error")) or "ai_audience_incremental_refresh_failed",
        error_message="" if result.get("ok") else _text(result.get("error")),
    )


def daily_refresh_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    result = AudienceRefreshService().run_due("daily", limit=_limit_from_event(event, default=20))
    return InternalEventConsumerResult(
        status="succeeded" if result.get("ok") else "failed_retryable",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary=_summary(result),
        result_summary=_summary(result),
        error_code="" if result.get("ok") else _text(result.get("error")) or "ai_audience_daily_refresh_failed",
        error_message="" if result.get("ok") else _text(result.get("error")),
    )


def source_poke_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    payload = dict(event.payload_json or {})
    source_type, source_key = _source_from_event(event, payload)
    updated_count = build_audience_repository().poke_dependencies(
        source_type=source_type,
        source_key=source_key,
    )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary={"updated_package_count": updated_count},
        result_summary={"updated_package_count": updated_count},
    )


def outbound_effect_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    payload = dict(event.payload_json or {})
    run_id = int(payload.get("run_id") or event.aggregate_id or 0) if event.event_type == RUN_REFRESHED_EVENT else 0
    member_event_id = int(payload.get("member_event_id") or event.aggregate_id or 0)
    result = AudienceOutboundService().plan_for_run(run_id) if run_id > 0 else AudienceOutboundService().plan_for_member_event(member_event_id)
    ok = bool(result.get("ok"))
    return InternalEventConsumerResult(
        status="succeeded" if ok else "failed_retryable",
        request_summary={
            "event_id": event.event_id,
            "consumer_name": run.consumer_name,
            "run_id": run_id,
            "member_event_id": member_event_id if run_id <= 0 else 0,
        },
        response_summary=_summary(result),
        result_summary=_summary(result),
        error_code="" if ok else _text(result.get("error")) or "ai_audience_outbound_plan_failed",
        error_message="" if ok else _text(result.get("error")),
    )


def register_ai_audience_event_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY
    registry.register(INCREMENTAL_TICK_EVENT, INCREMENTAL_REFRESH_CONSUMER, incremental_refresh_consumer, consumer_type="orchestration")
    registry.register(DAILY_TICK_EVENT, DAILY_REFRESH_CONSUMER, daily_refresh_consumer, consumer_type="orchestration")
    registry.register(SOURCE_CHANGED_EVENT, SOURCE_POKE_CONSUMER, source_poke_consumer, consumer_type="projection")
    registry.register("channel_entry.entered", SOURCE_POKE_CONSUMER, source_poke_consumer, consumer_type="projection")
    registry.register(QUESTIONNAIRE_SUBMITTED_EVENT_TYPE, SOURCE_POKE_CONSUMER, source_poke_consumer, consumer_type="projection")
    registry.register("external_form.submitted", SOURCE_POKE_CONSUMER, source_poke_consumer, consumer_type="projection")
    for payment_event_type in PAYMENT_SUCCEEDED_EVENT_TYPES:
        registry.register(payment_event_type, SOURCE_POKE_CONSUMER, source_poke_consumer, consumer_type="projection")
    registry.register(RUN_REFRESHED_EVENT, OUTBOUND_EFFECT_CONSUMER, outbound_effect_consumer, consumer_type="external_effect_planner")


def _limit_from_event(event: InternalEvent, *, default: int) -> int:
    payload = dict(event.payload_json or {})
    try:
        return max(1, min(int(payload.get("limit") or default), 200))
    except (TypeError, ValueError):
        return default


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key in (
        "ok",
        "refresh_kind",
        "candidate_count",
        "processed_count",
        "succeeded_count",
        "failed_count",
        "member_event_count",
        "planned_count",
        "run_id",
        "entered_count",
        "updated_count",
        "exited_count",
        "error",
        "real_external_call_executed",
    ):
        if key in payload:
            result[key] = payload.get(key)
    return result


def _source_from_event(event: InternalEvent, payload: dict[str, Any]) -> tuple[str, str]:
    source_type = _text(payload.get("source_type"))
    source_key = _text(payload.get("source_key"))
    if source_type:
        return source_type, source_key
    if event.event_type == QUESTIONNAIRE_SUBMITTED_EVENT_TYPE:
        questionnaire_id = _text(payload.get("questionnaire_id") or (payload.get("submission") or {}).get("questionnaire_id"))
        return "questionnaire_submission", f"questionnaire:{questionnaire_id}" if questionnaire_id else ""
    if event.event_type in PAYMENT_SUCCEEDED_EVENT_TYPES:
        product_code = _text(payload.get("product_code") or (payload.get("order") or {}).get("product_code"))
        return "payment", f"product:{product_code}" if product_code else ""
    if event.event_type == "channel_entry.entered":
        channel_id = _text(payload.get("channel_id"))
        return "channel_entry", f"channel:{channel_id}" if channel_id else ""
    if event.event_type == "external_form.submitted":
        form_id = _text(payload.get("form_id") or payload.get("source_key"))
        return "external_form", form_id
    return event.event_type, source_key
