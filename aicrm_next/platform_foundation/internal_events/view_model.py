from __future__ import annotations

import hashlib
from typing import Any

from .models import InternalEvent, InternalEventConsumerAttempt, InternalEventConsumerRun
from .config import consumer_metadata
from .legacy_path_markers import legacy_path_marker_diagnostics
from .repository import InternalEventRepository, build_internal_event_repository
from .service import InternalEventService

ROUTE_OWNER = "ai_crm_next"

FILTER_KEYS = (
    "event_section",
    "event_type",
    "aggregate_type",
    "aggregate_id",
    "subject_type",
    "subject_id",
    "consumer_name",
    "consumer_status",
    "trace_id",
    "trace_hash",
    "original_trace_hash",
    "source_module",
    "created_from",
    "created_to",
)

_SENSITIVE_EXACT_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "password",
    "openid",
    "unionid",
    "mobile",
    "phone",
    "phone_number",
    "mobile_snapshot",
}
_SENSITIVE_KEY_FRAGMENTS = ("token", "secret", "password", "authorization", "openid", "unionid", "mobile", "phone")
_HASH_FILTER_KEYS = {"trace_hash", "original_trace_hash"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _hash16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _public_filter_value(key: str, value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if key in _HASH_FILTER_KEYS:
        return f"trace_ref:{_hash16(text)}"
    return text


def _public_filters(filters: dict[str, Any]) -> dict[str, str]:
    public: dict[str, str] = {}
    for key, value in filters.items():
        public_value = _public_filter_value(key, value)
        if public_value:
            public[key] = public_value
    return public


def internal_event_filters(params: dict[str, Any] | None = None) -> dict[str, str]:
    raw = dict(params or {})
    return {key: _text(raw.get(key)) for key in FILTER_KEYS}


def _redact(value: Any, *, key: str = "") -> Any:
    lowered = key.lower()
    if lowered in _SENSITIVE_EXACT_KEYS or any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
        return "[redacted]" if _text(value) else ""
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item, key=key) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _status_counts(runs: list[InternalEventConsumerRun]) -> dict[str, int]:
    counts = {
        "consumer_total": len(runs),
        "succeeded_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "pending_count": 0,
        "blocked_count": 0,
    }
    for run in runs:
        if run.status == "succeeded":
            counts["succeeded_count"] += 1
        elif run.status in {"failed_retryable", "failed_terminal"}:
            counts["failed_count"] += 1
        elif run.status == "skipped":
            counts["skipped_count"] += 1
        elif run.status in {"pending", "running"}:
            counts["pending_count"] += 1
        elif run.status == "blocked":
            counts["blocked_count"] += 1
    return counts


def _reconciliation_summary(
    runs: list[InternalEventConsumerRun],
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    placeholder_consumers = {
        run.consumer_name
        for run in runs
        if consumer_metadata(run.consumer_name).get("type") == "placeholder"
    }
    placeholder_count = len(placeholder_consumers)
    unresolved_count = len(
        [
            run
            for run in runs
            if run.consumer_name not in placeholder_consumers and run.status in {"pending", "running"}
        ]
    )
    external_effects = list((reconciliation or {}).get("external_effects") or [])
    derived_status = _text((reconciliation or {}).get("derived_status"))
    return {
        "derived_status": derived_status,
        "unresolved_consumer_count": unresolved_count,
        "placeholder_consumer_count": placeholder_count,
        "external_effect_count": len(external_effects),
        "external_effect_statuses": sorted({_text(item.get("job_status") or item.get("status")) for item in external_effects if _text(item.get("job_status") or item.get("status"))}),
    }


def event_list_item(
    event: InternalEvent,
    runs: list[InternalEventConsumerRun],
    reconciliation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = _reconciliation_summary(runs, reconciliation)
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "event_version": event.event_version,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "aggregate": f"{event.aggregate_type}:{event.aggregate_id}",
        "subject_type": event.subject_type,
        "subject_id": event.subject_id,
        "subject": f"{event.subject_type}:{event.subject_id}" if event.subject_type or event.subject_id else "",
        "occurred_at": event.occurred_at,
        "created_at": event.created_at,
        "source_module": event.source_module,
        "source_route": event.source_route,
        "trace_id": event.trace_id,
        "request_id": event.request_id,
        "correlation_id": event.correlation_id,
        "idempotency_key": event.idempotency_key,
        "payload_summary_json": _redact(dict(event.payload_summary_json or {})),
        "derived_status": summary["derived_status"],
        "reconciliation_summary": summary,
        **_status_counts(runs),
    }


def consumer_run_item(run: InternalEventConsumerRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "event_id": run.event_id,
        "consumer_name": run.consumer_name,
        "consumer_type": run.consumer_type,
        "status": run.status,
        "attempt_count": run.attempt_count,
        "max_attempts": run.max_attempts,
        "next_retry_at": run.next_retry_at,
        "locked_at": run.locked_at,
        "locked_by": run.locked_by,
        "last_attempt_id": run.last_attempt_id,
        "last_error_code": run.last_error_code,
        "last_error_message": run.last_error_message,
        "result_summary_json": _redact(dict(run.result_summary_json or {})),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "finished_at": run.finished_at,
        "retryable": run.status in {"failed_retryable", "failed_terminal", "blocked"},
        "skippable": run.status not in {"succeeded", "skipped"},
    }


def attempt_item(attempt: InternalEventConsumerAttempt) -> dict[str, Any]:
    return {
        "id": attempt.id,
        "attempt_id": attempt.attempt_id,
        "consumer_run_id": attempt.consumer_run_id,
        "consumer_name": attempt.consumer_name,
        "status": attempt.status,
        "request_summary_json": _redact(dict(attempt.request_summary_json or {})),
        "response_summary_json": _redact(dict(attempt.response_summary_json or {})),
        "error_code": attempt.error_code,
        "error_message": attempt.error_message,
        "error": " ".join(item for item in [attempt.error_code, attempt.error_message] if item),
        "started_at": attempt.started_at,
        "completed_at": attempt.completed_at,
    }


def build_events_payload(params: dict[str, Any] | None = None, *, repository: InternalEventRepository | None = None) -> dict[str, Any]:
    repository = repository or build_internal_event_repository()
    filters = internal_event_filters(params)
    limit = _int((params or {}).get("limit"), default=50, minimum=1, maximum=200)
    offset = _int((params or {}).get("offset"), default=0, minimum=0, maximum=100000)
    events, total = repository.list_events(filters, limit=limit, offset=offset)
    items: list[dict[str, Any]] = []
    for event in events:
        runs, _ = repository.list_consumer_runs({"event_id": event.event_id}, limit=200)
        items.append(event_list_item(event, runs))
    metrics = repository.queue_metrics({})
    return {
        "ok": True,
        "items": items,
        "total": total,
        "filters": _public_filters(filters),
        "limit": limit,
        "offset": offset,
        "counts": {
            "total": total,
            "due": metrics.get("due_count", 0),
            "failed_retryable": metrics.get("failed_retryable_count", 0),
            "failed_terminal": metrics.get("failed_terminal_count", 0),
        },
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def build_event_detail_payload(event_id: str, *, service: InternalEventService | None = None) -> dict[str, Any] | None:
    service = service or InternalEventService()
    event = service.get_event(event_id)
    if not event:
        return None
    runs, _ = service.list_consumer_runs({"event_id": event.event_id}, limit=200)
    attempts = service.list_attempts(event_id=event.event_id)
    reconciliation = service.get_event_reconciliation(event.event_id)
    summary = _reconciliation_summary(runs, reconciliation)
    return {
        "ok": True,
        "event": event_list_item(event, runs, reconciliation),
        "payload_summary_json": _redact(dict(event.payload_summary_json or {})),
        "consumer_runs": [consumer_run_item(run) for run in runs],
        "attempts": [attempt_item(attempt) for attempt in attempts],
        "reconciliation": reconciliation,
        "derived_status": summary["derived_status"],
        "reconciliation_summary": summary,
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def build_diagnostics_payload(params: dict[str, Any] | None = None, *, service: InternalEventService | None = None) -> dict[str, Any]:
    service = service or InternalEventService()
    filters = internal_event_filters(params)
    payload = service.diagnostics(filters)
    payload.update(legacy_path_marker_diagnostics())
    payload["filters"] = _public_filters(filters)
    payload["route_owner"] = ROUTE_OWNER
    payload["real_external_call_executed"] = False
    return payload
