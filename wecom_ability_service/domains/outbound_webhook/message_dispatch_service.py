from __future__ import annotations

from typing import Any

import requests

from . import repo
from .service import (
    STATUS_EXHAUSTED,
    STATUS_FAILED,
    STATUS_RETRY_SCHEDULED,
    STATUS_SUCCESS,
    _delivery_snapshot,
    _event_config,
    _event_webhook_url,
    _iso_now,
    _next_retry_at,
    _normalized_text,
    _payload_summary,
    _request_headers,
    _response_body_summary,
    _retry_enabled,
    _retry_max_attempts,
    _setting_int,
    _setting_text,
    _truncate_text,
    outbound_webhook_logger,
)


def _attempt_delivery(delivery: dict[str, Any]) -> dict[str, Any]:
    snapshot = _delivery_snapshot(delivery)
    config = _event_config(snapshot["event_type"])
    webhook_url = _event_webhook_url(config)
    webhook_token = _setting_text(config["token_key"])
    timeout = _setting_int(config["timeout_key"], default=int(config["default_timeout"]), minimum=1)
    now_text = _iso_now()
    if not webhook_url:
        updated = repo.update_outbound_webhook_delivery(
            int(snapshot["id"]),
            target_url="",
            token_configured=bool(webhook_token),
            status=STATUS_FAILED,
            attempt_count=int(snapshot["attempt_count"]),
            response_status_code=None,
            response_body_summary="",
            last_error="webhook_not_configured",
            last_attempted_at=now_text,
            next_retry_at="",
        )
        return {
            "ok": False,
            "sent": False,
            "reason": "webhook_not_configured",
            "delivery": _delivery_snapshot(updated),
        }

    next_attempt = int(snapshot["attempt_count"]) + 1
    # NOTE: this dispatcher already has its own DB-driven retry scheduler
    # (``next_retry_at`` / ``max_attempts``), so we wrap with retry_max=0 —
    # we want the circuit breaker only, not double retries.
    from ...infra.http_client import OutboundHttpError, get_outbound_client

    webhook_client = get_outbound_client(
        "outbound_webhook_delivery",
        timeout=float(timeout),
        retry_max=0,
    )
    try:
        try:
            response = webhook_client.post(
                webhook_url,
                json=snapshot["payload"],
                headers=_request_headers(webhook_token),
            )
        except OutboundHttpError as exc:
            # Pass the upstream message through unchanged — callers / tests
            # match against the original error string.
            original_message = str(exc.cause) if exc.cause else str(exc)
            raise requests.RequestException(original_message) from exc
        status_code = int(response.status_code)
        response_summary = _response_body_summary(response)
        if 200 <= status_code < 300:
            updated = repo.update_outbound_webhook_delivery(
                int(snapshot["id"]),
                target_url=webhook_url,
                token_configured=bool(webhook_token),
                status=STATUS_SUCCESS,
                attempt_count=next_attempt,
                response_status_code=status_code,
                response_body_summary=response_summary,
                last_error="",
                last_attempted_at=now_text,
                next_retry_at="",
            )
            outbound_webhook_logger.info(
                "outbound webhook success delivery_id=%s event_type=%s status_code=%s attempt=%s",
                snapshot["id"],
                snapshot["event_type"],
                status_code,
                next_attempt,
            )
            return {
                "ok": True,
                "sent": True,
                "status_code": status_code,
                "delivery": _delivery_snapshot(updated),
            }
        last_error = f"http_status_{status_code}"
        retryable = _retry_enabled() and next_attempt < int(snapshot["max_attempts"] or 0)
        updated = repo.update_outbound_webhook_delivery(
            int(snapshot["id"]),
            target_url=webhook_url,
            token_configured=bool(webhook_token),
            status=STATUS_RETRY_SCHEDULED if retryable else STATUS_EXHAUSTED,
            attempt_count=next_attempt,
            response_status_code=status_code,
            response_body_summary=response_summary,
            last_error=last_error,
            last_attempted_at=now_text,
            next_retry_at=_next_retry_at(now_text) if retryable else "",
        )
        outbound_webhook_logger.warning(
            "outbound webhook non-2xx delivery_id=%s event_type=%s status_code=%s attempt=%s retryable=%s",
            snapshot["id"],
            snapshot["event_type"],
            status_code,
            next_attempt,
            retryable,
        )
        return {
            "ok": False,
            "sent": False,
            "status_code": status_code,
            "reason": last_error,
            "delivery": _delivery_snapshot(updated),
        }
    except requests.RequestException as exc:
        retryable = _retry_enabled() and next_attempt < int(snapshot["max_attempts"] or 0)
        updated = repo.update_outbound_webhook_delivery(
            int(snapshot["id"]),
            target_url=webhook_url,
            token_configured=bool(webhook_token),
            status=STATUS_RETRY_SCHEDULED if retryable else STATUS_EXHAUSTED,
            attempt_count=next_attempt,
            response_status_code=None,
            response_body_summary="",
            last_error=_truncate_text(str(exc), maximum=500),
            last_attempted_at=now_text,
            next_retry_at=_next_retry_at(now_text) if retryable else "",
        )
        outbound_webhook_logger.exception(
            "outbound webhook failed delivery_id=%s event_type=%s attempt=%s retryable=%s",
            snapshot["id"],
            snapshot["event_type"],
            next_attempt,
            retryable,
        )
        return {
            "ok": False,
            "sent": False,
            "reason": str(exc),
            "delivery": _delivery_snapshot(updated),
        }


def send_outbound_webhook(
    *,
    event_type: str,
    payload: dict[str, Any],
    source_key: str = "",
    source_id: str = "",
) -> dict[str, Any]:
    """Internal owner for outbound delivery creation + first-attempt dispatch."""

    config = _event_config(event_type)
    webhook_url = _event_webhook_url(config)
    webhook_token = _setting_text(config["token_key"])
    delivery = repo.create_outbound_webhook_delivery(
        event_type=_normalized_text(event_type),
        source_key=_normalized_text(source_key),
        source_id=_normalized_text(source_id),
        target_url=webhook_url,
        payload_json=dict(payload or {}),
        payload_summary=_payload_summary(dict(payload or {})),
        token_configured=bool(webhook_token),
        max_attempts=_retry_max_attempts(),
    )
    return _attempt_delivery(delivery)


def retry_outbound_webhook_delivery(delivery_id: int) -> dict[str, Any]:
    """Internal owner for explicit retry requests."""

    delivery = repo.get_outbound_webhook_delivery(int(delivery_id))
    if not delivery:
        raise LookupError("delivery not found")
    if _normalized_text(delivery.get("status")) == STATUS_SUCCESS:
        raise ValueError("delivery already succeeded")
    return _attempt_delivery(delivery)


def run_due_outbound_webhook_retries(*, limit: int = 20) -> dict[str, Any]:
    """Internal owner for due retry batch execution."""

    now_text = _iso_now()
    due_deliveries = repo.list_due_outbound_webhook_deliveries(now_text=now_text, limit=limit)
    results = [_attempt_delivery(item) for item in due_deliveries]
    success_count = sum(1 for item in results if bool(item.get("ok")))
    return {
        "ok": True,
        "count": len(results),
        "scanned_count": len(due_deliveries),
        "retried_count": len(results),
        "success_count": success_count,
        "failed_count": len(results) - success_count,
        "deliveries": results,
    }


def list_outbound_webhook_deliveries(
    *,
    event_type: str = "",
    status: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Internal owner for delivery list/read model queries."""

    rows = repo.list_outbound_webhook_deliveries(
        event_type=_normalized_text(event_type),
        status=_normalized_text(status),
        limit=limit,
    )
    items = [_delivery_snapshot(row) for row in rows]
    return {
        "items": items,
        "count": len(items),
        "filters": {
            "event_type": _normalized_text(event_type),
            "status": _normalized_text(status),
            "limit": max(1, min(int(limit), 200)),
        },
    }


def get_outbound_webhook_delivery_counts() -> dict[str, int]:
    """Internal owner for delivery aggregate counters."""

    return repo.get_outbound_webhook_delivery_counts()


__all__ = [
    "get_outbound_webhook_delivery_counts",
    "list_outbound_webhook_deliveries",
    "retry_outbound_webhook_delivery",
    "run_due_outbound_webhook_retries",
    "send_outbound_webhook",
]
