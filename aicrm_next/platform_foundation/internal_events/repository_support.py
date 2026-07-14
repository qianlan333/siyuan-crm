# ruff: noqa: F401, F811
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from aicrm_next.platform_foundation.external_calls import scrub_summary
from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.runtime import fixture_mode
from aicrm_next.shared.sensitive_data import redact_sensitive_text

from .models import (
    AUTOMATIC_PENDING_STATUSES,
    DEFAULT_TENANT_ID,
    InternalEvent,
    InternalEventConsumerAttempt,
    InternalEventConsumerRun,
    InternalEventConsumerSpec,
    InternalEventCreateRequest,
    InternalEventOutboxRecord,
    public_datetime,
    utcnow,
)

_SENSITIVE_PAYLOAD_KEYS = {"token", "secret", "password", "authorization", "access_token", "refresh_token"}
EVENT_SECTION_EVENT_TYPES: dict[str, tuple[str, ...]] = {
    "payment": ("payment.succeeded",),
    "questionnaire": ("questionnaire.submitted",),
    "broadcast": ("broadcast_task.created", "ops_plan.approved"),
    "ai_assist": ("ai_campaign.created", "ai_campaign.approved", "ai_campaign.started"),
    "customer": ("customer.phone_bound", "customer.tagged", "customer.untagged"),
    "owner_migration": ("owner_migration.executed",),
}
LEASE_TIMEOUT = timedelta(minutes=5)


def automatic_due_predicate_sql(alias: str = "r") -> str:
    return f"""
        (
            (
                {alias}.status = 'pending'
                AND ({alias}.locked_at IS NULL OR {alias}.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
            )
            OR (
                {alias}.status = 'failed_retryable'
                AND ({alias}.next_retry_at IS NULL OR {alias}.next_retry_at <= CURRENT_TIMESTAMP)
                AND ({alias}.locked_at IS NULL OR {alias}.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
            )
            OR (
                {alias}.status = 'running'
                AND {alias}.locked_at IS NOT NULL
                AND {alias}.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'
            )
        )
    """


def _run_is_automatically_due(row: dict[str, Any], *, now: datetime) -> bool:
    status = _text(row.get("status"))
    if status not in AUTOMATIC_PENDING_STATUSES and status != "running":
        return False
    locked_at = row.get("locked_at")
    locked_dt = _coerce_datetime(locked_at) if locked_at else None
    stale_or_unlocked = locked_dt is None or locked_dt <= now - LEASE_TIMEOUT
    if status == "running":
        return locked_dt is not None and locked_dt <= now - LEASE_TIMEOUT
    if not stale_or_unlocked:
        return False
    if status == "failed_retryable" and row.get("next_retry_at"):
        return _coerce_datetime(row.get("next_retry_at")) <= now
    return True


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text_value = _text(value)
        if not text_value:
            return datetime.min.replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _audit_reason(value: Any) -> str:
    return str(redact_sensitive_text(_text(value)) or "").strip()


def _trace_hash_candidates(filters: dict[str, Any]) -> list[str]:
    value = _text(filters.get("original_trace_hash") or filters.get("trace_hash"))
    if not value:
        return []
    candidates: list[str] = []
    if len(value) == 16 and all(char in "0123456789abcdefABCDEF" for char in value):
        candidates.append(value.lower())
    raw_hash = _hash_text(value)
    if raw_hash and raw_hash not in candidates:
        candidates.append(raw_hash)
    return candidates


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(data) if isinstance(data, dict) else {}
    return {}


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        if key.lower() in _SENSITIVE_PAYLOAD_KEYS:
            summary[key] = "[redacted]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
        else:
            summary[key] = type(value).__name__
    return summary


def _idempotency_key(request: InternalEventCreateRequest) -> str:
    explicit = _text(request.idempotency_key)
    if explicit:
        return explicit
    parts = [
        request.event_type,
        str(request.event_version or 1),
        request.aggregate_type,
        request.aggregate_id,
        request.subject_type,
        request.subject_id,
        request.source_command_id or request.context.request_id or request.context.trace_id,
    ]
    key = ":".join(_text(part) for part in parts if _text(part))
    return key or f"{request.event_type}:{request.aggregate_type}:{request.aggregate_id}"


def _public_event(row: dict[str, Any] | None) -> InternalEvent | None:
    if not row:
        return None
    payload = dict(row)
    for key in ("payload_json", "payload_summary_json"):
        payload[key] = _json_obj(payload.get(key))
    for key in ("occurred_at", "created_at"):
        payload[key] = public_datetime(payload.get(key))
    payload["id"] = int(payload.get("id") or 0)
    payload["event_version"] = int(payload.get("event_version") or 1)
    return InternalEvent(**payload)


def _public_run(row: dict[str, Any] | None) -> InternalEventConsumerRun | None:
    if not row:
        return None
    payload = dict(row)
    payload["result_summary_json"] = _json_obj(payload.get("result_summary_json"))
    for key in ("next_retry_at", "locked_at", "created_at", "updated_at", "finished_at"):
        payload[key] = public_datetime(payload.get(key))
    payload["id"] = int(payload.get("id") or 0)
    payload["attempt_count"] = int(payload.get("attempt_count") or 0)
    payload["max_attempts"] = int(payload.get("max_attempts") or 0)
    return InternalEventConsumerRun(**payload)


def _public_attempt(row: dict[str, Any] | None) -> InternalEventConsumerAttempt | None:
    if not row:
        return None
    payload = dict(row)
    for key in ("request_summary_json", "response_summary_json"):
        payload[key] = _json_obj(payload.get(key))
    for key in ("started_at", "completed_at"):
        payload[key] = public_datetime(payload.get(key))
    payload["id"] = int(payload.get("id") or 0)
    payload["consumer_run_id"] = int(payload.get("consumer_run_id") or 0)
    return InternalEventConsumerAttempt(**payload)


def _public_outbox(row: dict[str, Any] | None) -> InternalEventOutboxRecord | None:
    if not row:
        return None
    payload = dict(row)
    for key in ("payload_json", "payload_summary_json"):
        payload[key] = _json_obj(payload.get(key))
    for key in ("occurred_at", "next_retry_at", "locked_at", "created_at", "updated_at", "relayed_at"):
        payload[key] = public_datetime(payload.get(key))
    for key in ("id", "event_version", "attempt_count", "max_attempts"):
        payload[key] = int(payload.get(key) or 0)
    return InternalEventOutboxRecord(**payload)


def _consumer_specs_payload(consumers: list[InternalEventConsumerSpec]) -> list[InternalEventConsumerSpec]:
    unique: dict[str, InternalEventConsumerSpec] = {}
    for consumer in consumers:
        name = _text(consumer.consumer_name)
        if not name:
            continue
        unique[name] = InternalEventConsumerSpec(
            consumer_name=name,
            consumer_type=_text(consumer.consumer_type) or "projection",
            max_attempts=max(1, int(consumer.max_attempts or 5)),
        )
    return list(unique.values())


class InternalEventRepository:
    def create_event(self, request: InternalEventCreateRequest) -> InternalEvent:
        raise NotImplementedError

    def create_event_with_consumer_runs(
        self,
        request: InternalEventCreateRequest,
        consumers: list[InternalEventConsumerSpec],
    ) -> tuple[InternalEvent, list[InternalEventConsumerRun]]:
        raise NotImplementedError

    def get_event(self, event_id: str) -> InternalEvent | None:
        raise NotImplementedError

    def list_events(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[InternalEvent], int]:
        raise NotImplementedError

    def create_consumer_run(
        self,
        *,
        event: InternalEvent,
        consumer_name: str,
        consumer_type: str = "projection",
        max_attempts: int = 5,
    ) -> InternalEventConsumerRun:
        raise NotImplementedError

    def list_consumer_runs(self, filters: dict[str, Any] | None = None, *, limit: int = 100, offset: int = 0) -> tuple[list[InternalEventConsumerRun], int]:
        raise NotImplementedError

    def get_consumer_run(self, event_id: str, consumer_name: str) -> InternalEventConsumerRun | None:
        raise NotImplementedError

    def get_consumer_run_by_id(self, run_id: int) -> InternalEventConsumerRun | None:
        raise NotImplementedError

    def acquire_consumer_run(
        self,
        *,
        event_id: str,
        consumer_name: str,
        locked_by: str,
        force: bool = False,
    ) -> InternalEventConsumerRun | None:
        raise NotImplementedError

    def list_attempts(self, consumer_run_id: int | None = None, *, event_id: str = "") -> list[InternalEventConsumerAttempt]:
        raise NotImplementedError

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def list_due_runs(
        self,
        *,
        limit: int = 50,
        event_types: list[str] | None = None,
        consumer_names: list[str] | None = None,
        event_consumers: list[tuple[str, str]] | None = None,
    ) -> list[InternalEventConsumerRun]:
        raise NotImplementedError

    def acquire_due_runs(
        self,
        *,
        limit: int = 50,
        locked_by: str,
        event_types: list[str] | None = None,
        consumer_names: list[str] | None = None,
        event_consumers: list[tuple[str, str]] | None = None,
    ) -> list[InternalEventConsumerRun]:
        raise NotImplementedError

    def mark_running(
        self,
        run_id: int,
        *,
        locked_by: str,
        expected_lease_token: str = "",
    ) -> InternalEventConsumerRun | None:
        raise NotImplementedError

    def mark_result(
        self,
        run_id: int,
        *,
        status: str,
        attempt_id: str,
        result_summary: dict[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
        next_retry_at: datetime | None = None,
        expected_lease_token: str = "",
    ) -> InternalEventConsumerRun | None:
        raise NotImplementedError

    def complete_consumer_attempt(
        self,
        *,
        run: InternalEventConsumerRun,
        status: str,
        request_summary: dict[str, Any],
        response_summary: dict[str, Any],
        result_summary: dict[str, Any] | None = None,
        error_code: str = "",
        error_message: str = "",
        next_retry_at: datetime | None = None,
    ) -> tuple[InternalEventConsumerRun, InternalEventConsumerAttempt] | None:
        raise NotImplementedError

    def retry_consumer_run(
        self,
        event_id: str,
        consumer_name: str,
        *,
        actor_id: str,
        actor_type: str,
        reason: str,
    ) -> tuple[InternalEventConsumerRun, InternalEventConsumerAttempt] | None:
        raise NotImplementedError

    def skip_consumer_run(
        self,
        event_id: str,
        consumer_name: str,
        *,
        actor_id: str = "",
        actor_type: str = "",
        reason: str = "",
    ) -> tuple[InternalEventConsumerRun, InternalEventConsumerAttempt] | None:
        raise NotImplementedError

    def record_attempt(
        self,
        *,
        run: InternalEventConsumerRun,
        status: str,
        request_summary: dict[str, Any],
        response_summary: dict[str, Any],
        error_code: str = "",
        error_message: str = "",
    ) -> InternalEventConsumerAttempt:
        raise NotImplementedError

    def enqueue_outbox(self, request: InternalEventCreateRequest) -> InternalEventOutboxRecord:
        raise NotImplementedError

    def list_due_outbox(self, *, limit: int = 50) -> list[InternalEventOutboxRecord]:
        raise NotImplementedError

    def acquire_due_outbox(self, *, limit: int = 50, locked_by: str) -> list[InternalEventOutboxRecord]:
        raise NotImplementedError

    def relay_outbox(
        self,
        outbox: InternalEventOutboxRecord,
        consumers: list[InternalEventConsumerSpec],
    ) -> tuple[InternalEventOutboxRecord, InternalEvent, list[InternalEventConsumerRun]] | None:
        raise NotImplementedError

    def mark_outbox_failure(
        self,
        outbox: InternalEventOutboxRecord,
        *,
        error_code: str,
        error_message: str,
        next_retry_at: datetime | None,
    ) -> InternalEventOutboxRecord | None:
        raise NotImplementedError

    def outbox_metrics(self) -> dict[str, Any]:
        raise NotImplementedError
