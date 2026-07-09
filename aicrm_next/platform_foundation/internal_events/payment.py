from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.external_effects import ExternalEffectJob, ExternalEffectService, WEBHOOK_ORDER_PAID_PUSH

from .consumer_registry import DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY, InternalEventConsumerRegistry
from .models import InternalEvent, InternalEventConsumerResult, InternalEventConsumerRun
from .repository import plan_order_paid_external_push_effect_from_db, read_wechat_pay_order_for_payment_event

PAYMENT_SUCCEEDED_EVENT_TYPE = "payment.succeeded"
TRANSACTION_PAID_EVENT_ALIAS = "transaction.paid"
PAYMENT_SUCCEEDED_EVENT_ALIAS = "payment_succeeded"
PAYMENT_SUCCEEDED_EVENT_TYPES = (
    PAYMENT_SUCCEEDED_EVENT_TYPE,
    TRANSACTION_PAID_EVENT_ALIAS,
    PAYMENT_SUCCEEDED_EVENT_ALIAS,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _order_from_event(event: InternalEvent) -> dict[str, Any]:
    payload = dict(event.payload_json or {})
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    return dict(order or {})


def _read_order_from_db(event: InternalEvent) -> dict[str, Any]:
    lookup = _text((event.payload_json or {}).get("order", {}).get("out_trade_no") if isinstance((event.payload_json or {}).get("order"), dict) else "")
    aggregate_id = _text(event.aggregate_id)
    return read_wechat_pay_order_for_payment_event(lookup=lookup, aggregate_id=aggregate_id)


def _transaction_from_event(event: InternalEvent) -> dict[str, Any]:
    payload = dict(event.payload_json or {})
    transaction = payload.get("transaction") if isinstance(payload.get("transaction"), dict) else {}
    return dict(transaction or {})


def _is_order_paid(order: dict[str, Any]) -> bool:
    return _text(order.get("status")) == "paid" or _text(order.get("trade_state")) == "SUCCESS"


def _configured_order_paid_job(external_effects: ExternalEffectService, *, out_trade_no: str, order_id: str) -> ExternalEffectJob | None:
    business_ids = [value for value in (out_trade_no, order_id) if value]
    seen: set[int] = set()
    for business_id in business_ids:
        jobs, _ = external_effects.list_jobs(
            {"effect_type": WEBHOOK_ORDER_PAID_PUSH, "business_type": "commerce_order", "business_id": business_id},
            limit=20,
        )
        for job in jobs:
            if job.id in seen:
                continue
            seen.add(job.id)
            payload = job.payload_json or {}
            if payload.get("webhook_url"):
                return job
    return None


def _plan_order_paid_external_push_from_db(
    *,
    order: dict[str, Any],
    transaction: dict[str, Any],
    event: InternalEvent,
) -> dict[str, Any] | None:
    return plan_order_paid_external_push_effect_from_db(
        order=order,
        transaction=transaction,
        domain_event_outbox_id=(event.payload_json or {}).get("domain_event_outbox_id"),
    )


def order_projection_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    order = _read_order_from_db(event) or _order_from_event(event)
    out_trade_no = _text(order.get("out_trade_no") or event.aggregate_id)
    if not order:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "aggregate_id": event.aggregate_id},
            response_summary={"order_found": False},
            error_code="order_payload_missing",
            error_message="payment.succeeded event is missing the order payload",
        )
    if not _is_order_paid(order):
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={"order_found": True, "paid": False, "status": order.get("status"), "trade_state": order.get("trade_state")},
            error_code="order_not_paid",
            error_message="order is not paid yet",
        )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
        response_summary={"order_found": True, "paid": True},
        result_summary={"order_projection": "paid_confirmed", "out_trade_no": out_trade_no},
    )


def webhook_order_paid_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    order = _order_from_event(event)
    transaction = _transaction_from_event(event)
    out_trade_no = _text(order.get("out_trade_no") or transaction.get("out_trade_no") or event.aggregate_id)
    target_id = _text(order.get("id") or out_trade_no)
    if not target_id or not out_trade_no:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "aggregate_id": event.aggregate_id},
            response_summary={"external_effect_job_created": False},
            error_code="order_identity_missing",
            error_message="order id or out_trade_no is required",
        )
    external_effects = ExternalEffectService()
    existing_job = _configured_order_paid_job(external_effects, out_trade_no=out_trade_no, order_id=_text(order.get("id")))
    if existing_job is not None:
        return InternalEventConsumerResult(
            status="succeeded",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={
                "external_effect_job_created": False,
                "external_effect_job_reused": True,
                "external_effect_job_id": existing_job.id,
                "effect_type": WEBHOOK_ORDER_PAID_PUSH,
                "execution_mode": existing_job.execution_mode,
                "status": existing_job.status,
            },
            result_summary={
                "external_effect_job_id": existing_job.id,
                "external_effect_job_reused": True,
                "effect_type": WEBHOOK_ORDER_PAID_PUSH,
            },
        )
    planned = _plan_order_paid_external_push_from_db(order=order, transaction=transaction, event=event)
    if not planned or planned.get("skipped"):
        return InternalEventConsumerResult(
            status="succeeded",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={
                "external_effect_job_created": False,
                "external_effect_job_reused": False,
                "effect_type": WEBHOOK_ORDER_PAID_PUSH,
                "skipped": True,
                "reason": (planned or {}).get("reason") or "external_push_config_unavailable",
            },
            result_summary={"external_effect_job_created": False, "effect_type": WEBHOOK_ORDER_PAID_PUSH},
        )
    job_id = planned.get("external_effect_job_id")
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
        response_summary={
            "external_effect_job_created": True,
            "external_effect_job_reused": False,
            "external_effect_job_id": job_id,
            "effect_type": WEBHOOK_ORDER_PAID_PUSH,
            "execution_mode": "execute",
            "status": "queued",
        },
        result_summary={"external_effect_job_id": job_id, "external_effect_job_reused": False, "effect_type": WEBHOOK_ORDER_PAID_PUSH},
    )


def customer_business_summary_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id},
        response_summary={"skipped": True, "reason": "summary_refresh_not_configured"},
        result_summary={"reason": "summary_refresh_not_configured"},
    )


def dnd_policy_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id},
        response_summary={"skipped": True, "reason": "dnd_policy_not_configured"},
        result_summary={"reason": "dnd_policy_not_configured"},
    )


def ai_assist_notify_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id},
        response_summary={"skipped": True, "reason": "ai_assist_notify_not_configured"},
        result_summary={"reason": "ai_assist_notify_not_configured"},
    )


def register_payment_succeeded_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY
    from aicrm_next.service_period.payment_consumer import service_period_entitlement_consumer

    for event_type in PAYMENT_SUCCEEDED_EVENT_TYPES:
        registry.register(event_type, "order_projection_consumer", order_projection_consumer, consumer_type="projection")
        registry.register(event_type, "service_period_entitlement_consumer", service_period_entitlement_consumer, consumer_type="projection")
        registry.register(event_type, "webhook_order_paid_consumer", webhook_order_paid_consumer, consumer_type="external_effect_planner")
        registry.register(event_type, "customer_business_summary_consumer", customer_business_summary_consumer, consumer_type="projection")
        registry.register(event_type, "dnd_policy_consumer", dnd_policy_consumer, consumer_type="orchestration")
        registry.register(event_type, "ai_assist_notify_consumer", ai_assist_notify_consumer, consumer_type="orchestration")
