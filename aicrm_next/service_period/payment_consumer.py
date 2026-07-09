from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.internal_events.models import InternalEvent, InternalEventConsumerResult, InternalEventConsumerRun

from .application import GrantOrRenewEntitlementCommand


def _text(value: Any) -> str:
    return str(value or "").strip()


def _payload_order(event: InternalEvent) -> dict[str, Any]:
    payload = dict(event.payload_json or {})
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    return dict(order or {})


def _payload_transaction(event: InternalEvent) -> dict[str, Any]:
    payload = dict(event.payload_json or {})
    transaction = payload.get("transaction") if isinstance(payload.get("transaction"), dict) else {}
    return dict(transaction or {})


def service_period_entitlement_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    order = _payload_order(event)
    transaction = _payload_transaction(event)
    out_trade_no = _text(order.get("out_trade_no") or transaction.get("out_trade_no") or event.aggregate_id)
    if not order:
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "aggregate_id": event.aggregate_id},
            response_summary={"order_found": False},
            error_code="order_payload_missing",
            error_message="payment.succeeded event is missing order payload",
        )
    result = GrantOrRenewEntitlementCommand()(order=order, transaction=transaction)
    if result.get("reason") == "not_service_period_product":
        return InternalEventConsumerResult(
            status="skipped",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={"skipped": True, "reason": "not_service_period_product"},
            result_summary={"reason": "not_service_period_product"},
        )
    if result.get("reason") == "order_not_paid":
        return InternalEventConsumerResult(
            status="failed_retryable",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={"skipped": True, "reason": "order_not_paid"},
            error_code="order_not_paid",
            error_message="order is not paid yet",
        )
    if result.get("reason") == "missing_unionid":
        return InternalEventConsumerResult(
            status="succeeded",
            request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
            response_summary={"skipped": True, "reason": "missing_unionid"},
            result_summary={"event_type": "grant_failed_missing_unionid", "out_trade_no": out_trade_no},
        )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "out_trade_no": out_trade_no},
        response_summary={"skipped": bool(result.get("skipped")), "reason": result.get("reason", "")},
        result_summary={
            "event_type": result.get("event_type", ""),
            "out_trade_no": out_trade_no,
            "entitlement_id": (result.get("entitlement") or {}).get("id", ""),
        },
    )


__all__ = ["service_period_entitlement_consumer"]
