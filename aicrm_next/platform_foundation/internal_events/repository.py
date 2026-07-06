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
from aicrm_next.shared.runtime import fixture_mode, production_data_ready, raw_database_url

from .models import (
    DEFAULT_TENANT_ID,
    InternalEvent,
    InternalEventConsumerAttempt,
    InternalEventConsumerRun,
    InternalEventCreateRequest,
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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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


def read_wechat_pay_order_for_payment_event(*, lookup: str, aggregate_id: str) -> dict[str, Any]:
    if not production_data_ready():
        return {}
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(raw_database_url(), row_factory=dict_row) as conn:
            if lookup:
                row = conn.execute("SELECT * FROM wechat_pay_orders WHERE out_trade_no = %s LIMIT 1", (lookup,)).fetchone()
                if row:
                    return dict(row)
            if aggregate_id:
                row = conn.execute("SELECT * FROM wechat_pay_orders WHERE id::text = %s OR out_trade_no = %s LIMIT 1", (aggregate_id, aggregate_id)).fetchone()
                if row:
                    return dict(row)
    except Exception:
        return {}
    return {}


def plan_order_paid_external_push_effect_from_db(
    *,
    order: dict[str, Any],
    transaction: dict[str, Any],
    domain_event_outbox_id: Any,
) -> dict[str, Any] | None:
    if not production_data_ready():
        return None
    try:
        import psycopg
        from psycopg.rows import dict_row

        from aicrm_next.commerce.external_push_admin import plan_order_paid_external_push_effect

        with psycopg.connect(raw_database_url(), row_factory=dict_row) as conn:
            result = plan_order_paid_external_push_effect(
                conn,
                order=order,
                transaction=transaction,
                outbox={"id": domain_event_outbox_id},
                source_module="platform_foundation.internal_events.payment",
                source_route="/internal-events/payment.succeeded/webhook_order_paid_consumer",
            )
            conn.commit()
            return result
    except Exception:
        return None


class InternalEventRepository:
    def create_event(self, request: InternalEventCreateRequest) -> InternalEvent:
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

    def mark_running(self, run_id: int, *, locked_by: str) -> InternalEventConsumerRun | None:
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
    ) -> InternalEventConsumerRun | None:
        raise NotImplementedError

    def retry_consumer_run(self, event_id: str, consumer_name: str) -> InternalEventConsumerRun | None:
        raise NotImplementedError

    def skip_consumer_run(self, event_id: str, consumer_name: str, *, reason: str = "") -> tuple[InternalEventConsumerRun, InternalEventConsumerAttempt] | None:
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


class SQLAlchemyInternalEventRepository(InternalEventRepository):
    def __init__(self, session_factory: Callable[[], Session] | None = None):
        self._session_factory = session_factory or get_session_factory()

    def _one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            return dict(row) if row else None

    def _all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            return [dict(row) for row in rows]

    def _write_one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            session.commit()
            return dict(row) if row else None

    def _write_all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            session.commit()
            return [dict(row) for row in rows]

    def create_event(self, request: InternalEventCreateRequest) -> InternalEvent:
        key = _idempotency_key(request)
        occurred_at = request.occurred_at or utcnow()
        payload_summary = dict(request.payload_summary or {}) or _payload_summary(request.payload)
        tenant_id = _text(request.tenant_id) or DEFAULT_TENANT_ID
        row = self._write_one(
            """
            INSERT INTO internal_event (
                tenant_id, event_id, event_type, event_version, aggregate_type, aggregate_id,
                subject_type, subject_id, idempotency_key, actor_id, actor_type,
                source_module, source_route, source_command_id, trace_id, request_id,
                correlation_id, occurred_at, payload_json, payload_summary_json, created_at
            )
            VALUES (
                :tenant_id, :event_id, :event_type, :event_version, :aggregate_type, :aggregate_id,
                :subject_type, :subject_id, :idempotency_key, :actor_id, :actor_type,
                :source_module, :source_route, :source_command_id, :trace_id, :request_id,
                :correlation_id, CAST(:occurred_at AS timestamptz), CAST(:payload_json AS jsonb),
                CAST(:payload_summary_json AS jsonb), CURRENT_TIMESTAMP
            )
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING *
            """,
            {
                "tenant_id": tenant_id,
                "event_id": "iev_" + uuid4().hex,
                "event_type": _text(request.event_type),
                "event_version": int(request.event_version or 1),
                "aggregate_type": _text(request.aggregate_type),
                "aggregate_id": _text(request.aggregate_id),
                "subject_type": _text(request.subject_type),
                "subject_id": _text(request.subject_id),
                "idempotency_key": key,
                "actor_id": _text(request.context.actor_id),
                "actor_type": _text(request.context.actor_type) or "system",
                "source_module": _text(request.source_module),
                "source_route": _text(request.context.source_route),
                "source_command_id": _text(request.source_command_id),
                "trace_id": _text(request.context.trace_id),
                "request_id": _text(request.context.request_id),
                "correlation_id": _text(request.correlation_id),
                "occurred_at": public_datetime(occurred_at),
                "payload_json": _json_dumps(request.payload),
                "payload_summary_json": _json_dumps(payload_summary),
            },
        )
        event = _public_event(row)
        if event:
            return event
        existing = self._one(
            "SELECT * FROM internal_event WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key LIMIT 1",
            {"tenant_id": tenant_id, "idempotency_key": key},
        )
        event = _public_event(existing)
        if event is None:
            raise RuntimeError("internal event idempotent create failed")
        return event

    def get_event(self, event_id: str) -> InternalEvent | None:
        return _public_event(self._one("SELECT * FROM internal_event WHERE event_id = :event_id LIMIT 1", {"event_id": _text(event_id)}))

    def list_events(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[InternalEvent], int]:
        filters = dict(filters or {})
        clauses: list[str] = []
        params: dict[str, Any] = {}
        event_section = _text(filters.get("event_section"))
        for key in ("event_type", "aggregate_type", "aggregate_id", "subject_type", "subject_id", "trace_id", "idempotency_key", "source_module"):
            value = _text(filters.get(key))
            if value:
                clauses.append(f"{key} = :{key}")
                params[key] = value
        if event_section and not _text(filters.get("event_type")):
            known_types = sorted({event_type for values in EVENT_SECTION_EVENT_TYPES.values() for event_type in values})
            section_types = list(EVENT_SECTION_EVENT_TYPES.get(event_section, ()))
            if section_types:
                clauses.append("event_type = ANY(:event_section_types)")
                params["event_section_types"] = section_types
            elif event_section == "other" and known_types:
                clauses.append("NOT (event_type = ANY(:known_event_section_types))")
                params["known_event_section_types"] = known_types
        trace_hashes = _trace_hash_candidates(filters)
        if trace_hashes:
            trace_clauses: list[str] = []
            for index, trace_hash in enumerate(trace_hashes):
                param_key = f"original_trace_hash_{index}"
                trace_clauses.append(
                    f"""
                    (
                        payload_json -> 'broadcast_task' ->> 'original_trace_hash' = :{param_key}
                        OR payload_json -> 'broadcast_task' ->> 'trace_id_hash' = :{param_key}
                    )
                    """
                )
                params[param_key] = trace_hash
            clauses.append(
                "(" + " OR ".join(trace_clauses) + ")"
            )
        if _text(filters.get("created_from")):
            clauses.append("created_at >= CAST(:created_from AS timestamptz)")
            params["created_from"] = _text(filters.get("created_from"))
        if _text(filters.get("created_to")):
            clauses.append("created_at <= CAST(:created_to AS timestamptz)")
            params["created_to"] = _text(filters.get("created_to"))
        if _text(filters.get("consumer_name")):
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM internal_event_consumer_run r
                    WHERE r.event_id = internal_event.event_id
                      AND r.consumer_name = :consumer_name
                )
                """
            )
            params["consumer_name"] = _text(filters.get("consumer_name"))
        if _text(filters.get("consumer_status")):
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM internal_event_consumer_run r
                    WHERE r.event_id = internal_event.event_id
                      AND r.status = :consumer_status
                )
                """
            )
            params["consumer_status"] = _text(filters.get("consumer_status"))
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        count_row = self._one(f"SELECT COUNT(*) AS total FROM internal_event {where}", params)
        rows = self._all(
            f"""
            SELECT *
            FROM internal_event
            {where}
            ORDER BY occurred_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """,
            {**params, "limit": max(1, min(int(limit or 50), 200)), "offset": max(0, int(offset or 0))},
        )
        return [event for row in rows if (event := _public_event(row)) is not None], int((count_row or {}).get("total") or 0)

    def create_consumer_run(
        self,
        *,
        event: InternalEvent,
        consumer_name: str,
        consumer_type: str = "projection",
        max_attempts: int = 5,
    ) -> InternalEventConsumerRun:
        row = self._write_one(
            """
            INSERT INTO internal_event_consumer_run (
                tenant_id, event_id, consumer_name, consumer_type, status,
                attempt_count, max_attempts, created_at, updated_at
            )
            VALUES (
                :tenant_id, :event_id, :consumer_name, :consumer_type, 'pending',
                0, :max_attempts, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (tenant_id, event_id, consumer_name) DO NOTHING
            RETURNING *
            """,
            {
                "tenant_id": event.tenant_id,
                "event_id": event.event_id,
                "consumer_name": _text(consumer_name),
                "consumer_type": _text(consumer_type) or "projection",
                "max_attempts": max(1, int(max_attempts or 5)),
            },
        )
        run = _public_run(row)
        if run:
            return run
        existing = self._one(
            """
            SELECT *
            FROM internal_event_consumer_run
            WHERE tenant_id = :tenant_id AND event_id = :event_id AND consumer_name = :consumer_name
            LIMIT 1
            """,
            {"tenant_id": event.tenant_id, "event_id": event.event_id, "consumer_name": _text(consumer_name)},
        )
        run = _public_run(existing)
        if run is None:
            raise RuntimeError("internal event consumer run idempotent create failed")
        return run

    def list_consumer_runs(self, filters: dict[str, Any] | None = None, *, limit: int = 100, offset: int = 0) -> tuple[list[InternalEventConsumerRun], int]:
        filters = dict(filters or {})
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for key in ("event_id", "consumer_name", "consumer_type", "status"):
            value = _text(filters.get(key))
            if value:
                clauses.append(f"r.{key} = :{key}")
                params[key] = value
        event_type = _text(filters.get("event_type"))
        if event_type:
            clauses.append("e.event_type = :event_type")
            params["event_type"] = event_type
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        count_row = self._one(
            f"""
            SELECT COUNT(*) AS total
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            {where}
            """,
            params,
        )
        rows = self._all(
            f"""
            SELECT r.*
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            {where}
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT :limit OFFSET :offset
            """,
            {**params, "limit": max(1, min(int(limit or 100), 200)), "offset": max(0, int(offset or 0))},
        )
        return [run for row in rows if (run := _public_run(row)) is not None], int((count_row or {}).get("total") or 0)

    def get_consumer_run(self, event_id: str, consumer_name: str) -> InternalEventConsumerRun | None:
        return _public_run(
            self._one(
                "SELECT * FROM internal_event_consumer_run WHERE event_id = :event_id AND consumer_name = :consumer_name LIMIT 1",
                {"event_id": _text(event_id), "consumer_name": _text(consumer_name)},
            )
        )

    def get_consumer_run_by_id(self, run_id: int) -> InternalEventConsumerRun | None:
        return _public_run(self._one("SELECT * FROM internal_event_consumer_run WHERE id = :run_id LIMIT 1", {"run_id": int(run_id)}))

    def acquire_consumer_run(
        self,
        *,
        event_id: str,
        consumer_name: str,
        locked_by: str,
        force: bool = False,
    ) -> InternalEventConsumerRun | None:
        allowed_statuses = (
            "'pending','failed_retryable','failed_terminal','blocked','succeeded','skipped'"
            if force
            else "'pending','failed_retryable','failed_terminal','blocked'"
        )
        retry_guard = (
            ""
            if force
            else "AND (r.status <> 'failed_retryable' OR r.next_retry_at IS NULL OR r.next_retry_at <= CURRENT_TIMESTAMP)"
        )
        row = self._write_one(
            f"""
            WITH target AS (
                SELECT r.id
                FROM internal_event_consumer_run r
                WHERE r.event_id = :event_id
                  AND r.consumer_name = :consumer_name
                  AND r.status IN ({allowed_statuses})
                  AND (r.locked_at IS NULL OR r.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                  {retry_guard}
                ORDER BY r.created_at ASC, r.id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE internal_event_consumer_run r
            SET locked_at = CURRENT_TIMESTAMP,
                locked_by = :locked_by,
                updated_at = CURRENT_TIMESTAMP
            FROM target
            WHERE r.id = target.id
            RETURNING r.*
            """,
            {
                "event_id": _text(event_id),
                "consumer_name": _text(consumer_name),
                "locked_by": _text(locked_by),
            },
        )
        return _public_run(row)

    def list_attempts(self, consumer_run_id: int | None = None, *, event_id: str = "") -> list[InternalEventConsumerAttempt]:
        params: dict[str, Any] = {}
        where = ""
        if consumer_run_id is not None:
            where = "WHERE a.consumer_run_id = :consumer_run_id"
            params["consumer_run_id"] = int(consumer_run_id)
        elif _text(event_id):
            where = "WHERE r.event_id = :event_id"
            params["event_id"] = _text(event_id)
        rows = self._all(
            f"""
            SELECT a.*
            FROM internal_event_consumer_attempt a
            JOIN internal_event_consumer_run r ON r.id = a.consumer_run_id
            {where}
            ORDER BY a.id ASC
            """,
            params,
        )
        return [attempt for row in rows if (attempt := _public_attempt(row)) is not None]

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = dict(filters or {})
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if _text(filters.get("event_type")):
            clauses.append("e.event_type = :event_type")
            params["event_type"] = _text(filters.get("event_type"))
        if filters.get("event_types"):
            event_types = [_text(item) for item in filters.get("event_types") or [] if _text(item)]
            if event_types:
                clauses.append("e.event_type = ANY(:event_types)")
                params["event_types"] = event_types
        if _text(filters.get("consumer_name")):
            clauses.append("r.consumer_name = :consumer_name")
            params["consumer_name"] = _text(filters.get("consumer_name"))
        if filters.get("consumer_names"):
            consumer_names = [_text(item) for item in filters.get("consumer_names") or [] if _text(item)]
            if consumer_names:
                clauses.append("r.consumer_name = ANY(:consumer_names)")
                params["consumer_names"] = consumer_names
        pair_clause = self._event_consumer_pair_clause(filters.get("event_consumers"), params)
        if pair_clause:
            clauses.append(pair_clause)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        due_predicate = """
            r.status IN ('pending', 'failed_retryable', 'failed_terminal', 'blocked')
            AND (r.status <> 'failed_retryable' OR r.next_retry_at IS NULL OR r.next_retry_at <= CURRENT_TIMESTAMP)
            AND (r.locked_at IS NULL OR r.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
        """
        row = self._one(
            f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE {due_predicate}
                ) AS due_count,
                COUNT(*) FILTER (WHERE r.status = 'failed_retryable') AS failed_retryable_count,
                COUNT(*) FILTER (WHERE r.status = 'failed_terminal') AS failed_terminal_count,
                COALESCE(
                    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - MIN(r.created_at) FILTER (
                        WHERE r.status = 'pending'
                          AND (r.next_retry_at IS NULL OR r.next_retry_at <= CURRENT_TIMESTAMP)
                    )),
                    0
                ) AS oldest_pending_age_seconds
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            {where}
            """,
            params,
        ) or {}
        by_event_type = self._all(
            f"""
            SELECT e.event_type, COUNT(*) AS due_count
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            {where}
            {"AND" if where else "WHERE"} {due_predicate}
            GROUP BY e.event_type
            ORDER BY e.event_type ASC
            """,
            params,
        )
        by_consumer = self._all(
            f"""
            SELECT r.consumer_name, COUNT(*) AS due_count
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            {where}
            {"AND" if where else "WHERE"} {due_predicate}
            GROUP BY r.consumer_name
            ORDER BY r.consumer_name ASC
            """,
            params,
        )
        return {
            "due_count": int(row.get("due_count") or 0),
            "failed_retryable_count": int(row.get("failed_retryable_count") or 0),
            "failed_terminal_count": int(row.get("failed_terminal_count") or 0),
            "oldest_pending_age_seconds": int(float(row.get("oldest_pending_age_seconds") or 0)),
            "due_count_by_event_type": {_text(item.get("event_type")): int(item.get("due_count") or 0) for item in by_event_type},
            "due_count_by_consumer": {_text(item.get("consumer_name")): int(item.get("due_count") or 0) for item in by_consumer},
        }

    def list_due_runs(
        self,
        *,
        limit: int = 50,
        event_types: list[str] | None = None,
        consumer_names: list[str] | None = None,
        event_consumers: list[tuple[str, str]] | None = None,
    ) -> list[InternalEventConsumerRun]:
        filters, params = self._due_filters(event_types=event_types, consumer_names=consumer_names, event_consumers=event_consumers)
        rows = self._all(
            f"""
            SELECT r.*
            FROM internal_event_consumer_run r
            JOIN internal_event e ON e.event_id = r.event_id
            WHERE {filters}
            ORDER BY COALESCE(r.next_retry_at, r.created_at) ASC, r.id ASC
            LIMIT :limit
            """,
            {**params, "limit": max(1, min(int(limit or 50), 200))},
        )
        return [run for row in rows if (run := _public_run(row)) is not None]

    def acquire_due_runs(
        self,
        *,
        limit: int = 50,
        locked_by: str,
        event_types: list[str] | None = None,
        consumer_names: list[str] | None = None,
        event_consumers: list[tuple[str, str]] | None = None,
    ) -> list[InternalEventConsumerRun]:
        filters, params = self._due_filters(event_types=event_types, consumer_names=consumer_names, event_consumers=event_consumers)
        rows = self._write_all(
            f"""
            WITH due AS (
                SELECT r.id
                FROM internal_event_consumer_run r
                JOIN internal_event e ON e.event_id = r.event_id
                WHERE {filters}
                ORDER BY COALESCE(r.next_retry_at, r.created_at) ASC, r.id ASC
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE internal_event_consumer_run r
            SET locked_at = CURRENT_TIMESTAMP,
                locked_by = :locked_by,
                updated_at = CURRENT_TIMESTAMP
            FROM due
            WHERE r.id = due.id
            RETURNING r.*
            """,
            {**params, "limit": max(1, min(int(limit or 50), 200)), "locked_by": _text(locked_by)},
        )
        return [run for row in rows if (run := _public_run(row)) is not None]

    def mark_running(self, run_id: int, *, locked_by: str) -> InternalEventConsumerRun | None:
        return self._update(run_id, "status = 'running', locked_by = :locked_by, locked_at = CURRENT_TIMESTAMP", {"locked_by": _text(locked_by)})

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
    ) -> InternalEventConsumerRun | None:
        status = _text(status)
        if status not in {"succeeded", "failed_retryable", "failed_terminal", "blocked", "skipped"}:
            status = "blocked"
        finished_sql = ", finished_at = CURRENT_TIMESTAMP" if status in {"succeeded", "failed_terminal", "blocked", "skipped"} else ", finished_at = NULL"
        retry_sql = "next_retry_at = CAST(:next_retry_at AS timestamptz)," if status == "failed_retryable" and next_retry_at else "next_retry_at = NULL,"
        return self._update(
            run_id,
            f"""
            status = :status,
            attempt_count = attempt_count + 1,
            {retry_sql}
            locked_by = '',
            locked_at = NULL,
            last_attempt_id = :attempt_id,
            last_error_code = :error_code,
            last_error_message = :error_message,
            result_summary_json = CAST(:result_summary AS jsonb)
            {finished_sql}
            """,
            {
                "status": status,
                "attempt_id": _text(attempt_id),
                "error_code": _text(error_code),
                "error_message": _text(error_message),
                "next_retry_at": public_datetime(next_retry_at) if next_retry_at else None,
                "result_summary": _json_dumps(scrub_summary(result_summary or {})),
            },
        )

    def retry_consumer_run(self, event_id: str, consumer_name: str) -> InternalEventConsumerRun | None:
        run = self.get_consumer_run(event_id, consumer_name)
        if not run or run.status not in {"failed_retryable", "failed_terminal", "blocked"}:
            return None
        return self._update(
            run.id,
            """
            status = 'pending',
            next_retry_at = CURRENT_TIMESTAMP,
            locked_by = '',
            locked_at = NULL,
            last_error_code = '',
            last_error_message = '',
            finished_at = NULL
            """,
            {},
        )

    def skip_consumer_run(self, event_id: str, consumer_name: str, *, reason: str = "") -> tuple[InternalEventConsumerRun, InternalEventConsumerAttempt] | None:
        run = self.get_consumer_run(event_id, consumer_name)
        if not run or run.status in {"succeeded", "skipped"}:
            return None
        attempt = self.record_attempt(
            run=run,
            status="skipped",
            request_summary={"manual_skip": True, "event_id": event_id, "consumer_name": consumer_name},
            response_summary={"skipped": True, "reason": _text(reason)},
            error_code="manual_skip",
            error_message=_text(reason),
        )
        updated = self.mark_result(run.id, status="skipped", attempt_id=attempt.attempt_id, result_summary={"skipped": True, "reason": _text(reason)})
        if updated is None:
            return None
        return updated, attempt

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
        attempt_id = "iea_" + uuid4().hex
        row = self._write_one(
            """
            INSERT INTO internal_event_consumer_attempt (
                attempt_id, consumer_run_id, consumer_name, status,
                request_summary_json, response_summary_json, error_code, error_message,
                started_at, completed_at
            )
            VALUES (
                :attempt_id, :consumer_run_id, :consumer_name, :status,
                CAST(:request_summary AS jsonb), CAST(:response_summary AS jsonb),
                :error_code, :error_message, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING *
            """,
            {
                "attempt_id": attempt_id,
                "consumer_run_id": int(run.id),
                "consumer_name": run.consumer_name,
                "status": _text(status) or "skipped",
                "request_summary": _json_dumps(scrub_summary(request_summary or {})),
                "response_summary": _json_dumps(scrub_summary(response_summary or {})),
                "error_code": _text(error_code),
                "error_message": _text(error_message),
            },
        )
        attempt = _public_attempt(row)
        if attempt is None:
            raise RuntimeError("internal event consumer attempt insert failed")
        return attempt

    def _due_filters(
        self,
        *,
        event_types: list[str] | None,
        consumer_names: list[str] | None,
        event_consumers: list[tuple[str, str]] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        filters = [
            "r.status IN ('pending', 'failed_retryable', 'failed_terminal', 'blocked')",
            "(r.status <> 'failed_retryable' OR r.next_retry_at IS NULL OR r.next_retry_at <= CURRENT_TIMESTAMP)",
            "(r.locked_at IS NULL OR r.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')",
        ]
        params: dict[str, Any] = {}
        if event_types:
            filters.append("e.event_type = ANY(:event_types)")
            params["event_types"] = [_text(item) for item in event_types if _text(item)]
        if consumer_names:
            filters.append("r.consumer_name = ANY(:consumer_names)")
            params["consumer_names"] = [_text(item) for item in consumer_names if _text(item)]
        pair_clause = self._event_consumer_pair_clause(event_consumers, params)
        if pair_clause:
            filters.append(pair_clause)
        return " AND ".join(filters), params

    def _event_consumer_pair_clause(self, event_consumers: Any, params: dict[str, Any]) -> str:
        pairs: list[tuple[str, str]] = []
        for item in event_consumers or []:
            if isinstance(item, str) and ":" in item:
                event_type, consumer_name = item.split(":", 1)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                event_type, consumer_name = item
            else:
                continue
            event_type = _text(event_type)
            consumer_name = _text(consumer_name)
            if event_type and consumer_name:
                pairs.append((event_type, consumer_name))
        clauses: list[str] = []
        for index, (event_type, consumer_name) in enumerate(pairs):
            event_key = f"pair_event_type_{index}"
            consumer_key = f"pair_consumer_name_{index}"
            params[event_key] = event_type
            params[consumer_key] = consumer_name
            clauses.append(f"(e.event_type = :{event_key} AND r.consumer_name = :{consumer_key})")
        return "(" + " OR ".join(clauses) + ")" if clauses else ""

    def _update(self, run_id: int, set_sql: str, params: dict[str, Any]) -> InternalEventConsumerRun | None:
        row = self._write_one(
            f"""
            UPDATE internal_event_consumer_run
            SET {set_sql},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :run_id
            RETURNING *
            """,
            {**params, "run_id": int(run_id)},
        )
        return _public_run(row)


class InMemoryInternalEventRepository(InternalEventRepository):
    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._runs: list[dict[str, Any]] = []
        self._attempts: list[dict[str, Any]] = []
        self._next_event_id = 1
        self._next_run_id = 1
        self._next_attempt_id = 1

    def create_event(self, request: InternalEventCreateRequest) -> InternalEvent:
        tenant_id = _text(request.tenant_id) or DEFAULT_TENANT_ID
        key = _idempotency_key(request)
        for row in self._events:
            if row["tenant_id"] == tenant_id and row["idempotency_key"] == key:
                event = _public_event(row)
                assert event is not None
                return event
        now = utcnow()
        payload_summary = dict(request.payload_summary or {}) or _payload_summary(request.payload)
        row = {
            "id": self._next_event_id,
            "tenant_id": tenant_id,
            "event_id": "iev_" + uuid4().hex,
            "event_type": _text(request.event_type),
            "event_version": int(request.event_version or 1),
            "aggregate_type": _text(request.aggregate_type),
            "aggregate_id": _text(request.aggregate_id),
            "subject_type": _text(request.subject_type),
            "subject_id": _text(request.subject_id),
            "idempotency_key": key,
            "actor_id": _text(request.context.actor_id),
            "actor_type": _text(request.context.actor_type) or "system",
            "source_module": _text(request.source_module),
            "source_route": _text(request.context.source_route),
            "source_command_id": _text(request.source_command_id),
            "trace_id": _text(request.context.trace_id),
            "request_id": _text(request.context.request_id),
            "correlation_id": _text(request.correlation_id),
            "occurred_at": public_datetime(request.occurred_at or now),
            "payload_json": dict(request.payload or {}),
            "payload_summary_json": payload_summary,
            "created_at": public_datetime(now),
        }
        self._next_event_id += 1
        self._events.append(row)
        event = _public_event(row)
        assert event is not None
        return event

    def get_event(self, event_id: str) -> InternalEvent | None:
        for row in self._events:
            if row.get("event_id") == _text(event_id):
                return _public_event(row)
        return None

    def list_events(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[InternalEvent], int]:
        rows = list(self._filtered_events(filters or {}))
        rows.sort(key=lambda row: (row.get("occurred_at") or "", int(row.get("id") or 0)), reverse=True)
        total = len(rows)
        window = rows[max(0, int(offset or 0)) : max(0, int(offset or 0)) + max(1, min(int(limit or 50), 200))]
        return [event for row in window if (event := _public_event(row)) is not None], total

    def create_consumer_run(
        self,
        *,
        event: InternalEvent,
        consumer_name: str,
        consumer_type: str = "projection",
        max_attempts: int = 5,
    ) -> InternalEventConsumerRun:
        consumer_name = _text(consumer_name)
        for row in self._runs:
            if row["tenant_id"] == event.tenant_id and row["event_id"] == event.event_id and row["consumer_name"] == consumer_name:
                run = _public_run(row)
                assert run is not None
                return run
        now = public_datetime(utcnow())
        row = {
            "id": self._next_run_id,
            "tenant_id": event.tenant_id,
            "event_id": event.event_id,
            "consumer_name": consumer_name,
            "consumer_type": _text(consumer_type) or "projection",
            "status": "pending",
            "attempt_count": 0,
            "max_attempts": max(1, int(max_attempts or 5)),
            "next_retry_at": "",
            "locked_at": "",
            "locked_by": "",
            "last_attempt_id": "",
            "last_error_code": "",
            "last_error_message": "",
            "result_summary_json": {},
            "created_at": now,
            "updated_at": now,
            "finished_at": "",
        }
        self._next_run_id += 1
        self._runs.append(row)
        run = _public_run(row)
        assert run is not None
        return run

    def list_consumer_runs(self, filters: dict[str, Any] | None = None, *, limit: int = 100, offset: int = 0) -> tuple[list[InternalEventConsumerRun], int]:
        rows = list(self._filtered_runs(filters or {}))
        rows.sort(key=lambda row: (row.get("created_at") or "", int(row.get("id") or 0)), reverse=True)
        total = len(rows)
        window = rows[max(0, int(offset or 0)) : max(0, int(offset or 0)) + max(1, min(int(limit or 100), 200))]
        return [run for row in window if (run := _public_run(row)) is not None], total

    def get_consumer_run(self, event_id: str, consumer_name: str) -> InternalEventConsumerRun | None:
        for row in self._runs:
            if row.get("event_id") == _text(event_id) and row.get("consumer_name") == _text(consumer_name):
                return _public_run(row)
        return None

    def get_consumer_run_by_id(self, run_id: int) -> InternalEventConsumerRun | None:
        return _public_run(self._find_run(run_id))

    def acquire_consumer_run(
        self,
        *,
        event_id: str,
        consumer_name: str,
        locked_by: str,
        force: bool = False,
    ) -> InternalEventConsumerRun | None:
        now = utcnow()
        stale_cutoff = now - timedelta(minutes=5)
        allowed_statuses = (
            {"pending", "failed_retryable", "failed_terminal", "blocked", "succeeded", "skipped"}
            if force
            else {"pending", "failed_retryable", "failed_terminal", "blocked"}
        )
        for row in self._runs:
            if row.get("event_id") != _text(event_id) or row.get("consumer_name") != _text(consumer_name):
                continue
            if row.get("status") not in allowed_statuses:
                return None
            locked_at = self._dt(row.get("locked_at")) if row.get("locked_at") else datetime.min.replace(tzinfo=timezone.utc)
            if locked_at > stale_cutoff:
                return None
            if not force and row.get("status") == "failed_retryable" and row.get("next_retry_at"):
                if self._dt(row.get("next_retry_at")) > now:
                    return None
            row["locked_at"] = public_datetime(now)
            row["locked_by"] = _text(locked_by)
            row["updated_at"] = public_datetime(now)
            return _public_run(row)
        return None

    def list_attempts(self, consumer_run_id: int | None = None, *, event_id: str = "") -> list[InternalEventConsumerAttempt]:
        rows = list(self._attempts)
        if consumer_run_id is not None:
            rows = [row for row in rows if int(row.get("consumer_run_id") or 0) == int(consumer_run_id)]
        elif _text(event_id):
            run_ids = {int(row.get("id") or 0) for row in self._runs if row.get("event_id") == _text(event_id)}
            rows = [row for row in rows if int(row.get("consumer_run_id") or 0) in run_ids]
        rows.sort(key=lambda row: int(row.get("id") or 0))
        return [attempt for row in rows if (attempt := _public_attempt(row)) is not None]

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utcnow()
        rows = list(self._filtered_runs(filters or {}))
        event_type_set = {_text(item) for item in (filters or {}).get("event_types") or [] if _text(item)}
        consumer_set = {_text(item) for item in (filters or {}).get("consumer_names") or [] if _text(item)}
        pair_set = self._event_consumer_pair_set((filters or {}).get("event_consumers"))
        if event_type_set:
            rows = [row for row in rows if (self.get_event(row.get("event_id") or "") or InternalEvent()).event_type in event_type_set]
        if consumer_set:
            rows = [row for row in rows if _text(row.get("consumer_name")) in consumer_set]
        if pair_set:
            rows = [
                row
                for row in rows
                if ((self.get_event(row.get("event_id") or "") or InternalEvent()).event_type, _text(row.get("consumer_name"))) in pair_set
            ]
        due_rows = [
            row
            for row in rows
            if row.get("status") in {"pending", "failed_retryable", "failed_terminal", "blocked"}
            and (row.get("status") != "failed_retryable" or not row.get("next_retry_at") or self._dt(row.get("next_retry_at")) <= now)
            and (not row.get("locked_at") or self._dt(row.get("locked_at")) <= now - timedelta(minutes=5))
        ]
        pending_due = [row for row in due_rows if row.get("status") == "pending"]
        oldest = min((self._dt(row.get("created_at")) for row in pending_due), default=None)
        by_event_type: dict[str, int] = {}
        by_consumer: dict[str, int] = {}
        for row in due_rows:
            event_type = (self.get_event(row.get("event_id") or "") or InternalEvent()).event_type
            consumer_name = _text(row.get("consumer_name"))
            by_event_type[event_type] = by_event_type.get(event_type, 0) + 1
            by_consumer[consumer_name] = by_consumer.get(consumer_name, 0) + 1
        return {
            "due_count": len(due_rows),
            "failed_retryable_count": len([row for row in rows if row.get("status") == "failed_retryable"]),
            "failed_terminal_count": len([row for row in rows if row.get("status") == "failed_terminal"]),
            "oldest_pending_age_seconds": max(0, int((now - oldest).total_seconds())) if oldest else 0,
            "due_count_by_event_type": dict(sorted(by_event_type.items())),
            "due_count_by_consumer": dict(sorted(by_consumer.items())),
        }

    def list_due_runs(
        self,
        *,
        limit: int = 50,
        event_types: list[str] | None = None,
        consumer_names: list[str] | None = None,
        event_consumers: list[tuple[str, str]] | None = None,
    ) -> list[InternalEventConsumerRun]:
        now = utcnow()
        event_type_set = {_text(item) for item in event_types or [] if _text(item)}
        consumer_set = {_text(item) for item in consumer_names or [] if _text(item)}
        pair_set = self._event_consumer_pair_set(event_consumers)
        rows = [
            row
            for row in self._runs
            if row.get("status") in {"pending", "failed_retryable", "failed_terminal", "blocked"}
            and (not consumer_set or row.get("consumer_name") in consumer_set)
            and (not event_type_set or (self.get_event(row.get("event_id") or "") or InternalEvent()).event_type in event_type_set)
            and (not pair_set or ((self.get_event(row.get("event_id") or "") or InternalEvent()).event_type, _text(row.get("consumer_name"))) in pair_set)
            and (row.get("status") != "failed_retryable" or not row.get("next_retry_at") or self._dt(row.get("next_retry_at")) <= now)
            and (not row.get("locked_at") or self._dt(row.get("locked_at")) <= now - timedelta(minutes=5))
        ]
        rows.sort(key=lambda row: (row.get("next_retry_at") or row.get("created_at") or "", int(row.get("id") or 0)))
        return [run for row in rows[: max(1, min(int(limit or 50), 200))] if (run := _public_run(row)) is not None]

    def acquire_due_runs(
        self,
        *,
        limit: int = 50,
        locked_by: str,
        event_types: list[str] | None = None,
        consumer_names: list[str] | None = None,
        event_consumers: list[tuple[str, str]] | None = None,
    ) -> list[InternalEventConsumerRun]:
        runs = self.list_due_runs(limit=limit, event_types=event_types, consumer_names=consumer_names, event_consumers=event_consumers)
        now = public_datetime(utcnow())
        for run in runs:
            row = self._find_run(run.id)
            if row:
                row["locked_at"] = now
                row["locked_by"] = _text(locked_by)
                row["updated_at"] = now
        return [run for run_id in [run.id for run in runs] if (run := self.get_consumer_run_by_id(run_id)) is not None]

    def mark_running(self, run_id: int, *, locked_by: str) -> InternalEventConsumerRun | None:
        return self._mutate(run_id, status="running", locked_by=_text(locked_by), locked_at=public_datetime(utcnow()))

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
    ) -> InternalEventConsumerRun | None:
        status = _text(status)
        if status not in {"succeeded", "failed_retryable", "failed_terminal", "blocked", "skipped"}:
            status = "blocked"
        row = self._find_run(run_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        finished_at = public_datetime(utcnow()) if status in {"succeeded", "failed_terminal", "blocked", "skipped"} else ""
        return self._mutate(
            run_id,
            status=status,
            next_retry_at=public_datetime(next_retry_at) if status == "failed_retryable" and next_retry_at else "",
            locked_by="",
            locked_at="",
            last_attempt_id=_text(attempt_id),
            last_error_code=_text(error_code),
            last_error_message=_text(error_message),
            result_summary_json=scrub_summary(result_summary or {}),
            finished_at=finished_at,
        )

    def retry_consumer_run(self, event_id: str, consumer_name: str) -> InternalEventConsumerRun | None:
        run = self.get_consumer_run(event_id, consumer_name)
        if not run or run.status not in {"failed_retryable", "failed_terminal", "blocked"}:
            return None
        return self._mutate(
            run.id,
            status="pending",
            next_retry_at=public_datetime(utcnow()),
            locked_by="",
            locked_at="",
            last_error_code="",
            last_error_message="",
            finished_at="",
        )

    def skip_consumer_run(self, event_id: str, consumer_name: str, *, reason: str = "") -> tuple[InternalEventConsumerRun, InternalEventConsumerAttempt] | None:
        run = self.get_consumer_run(event_id, consumer_name)
        if not run or run.status in {"succeeded", "skipped"}:
            return None
        attempt = self.record_attempt(
            run=run,
            status="skipped",
            request_summary={"manual_skip": True, "event_id": event_id, "consumer_name": consumer_name},
            response_summary={"skipped": True, "reason": _text(reason)},
            error_code="manual_skip",
            error_message=_text(reason),
        )
        updated = self.mark_result(run.id, status="skipped", attempt_id=attempt.attempt_id, result_summary={"skipped": True, "reason": _text(reason)})
        if updated is None:
            return None
        return updated, attempt

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
        now = public_datetime(utcnow())
        row = {
            "id": self._next_attempt_id,
            "attempt_id": "iea_" + uuid4().hex,
            "consumer_run_id": int(run.id),
            "consumer_name": run.consumer_name,
            "status": _text(status) or "skipped",
            "request_summary_json": scrub_summary(request_summary or {}),
            "response_summary_json": scrub_summary(response_summary or {}),
            "error_code": _text(error_code),
            "error_message": _text(error_message),
            "started_at": now,
            "completed_at": now,
        }
        self._next_attempt_id += 1
        self._attempts.append(row)
        attempt = _public_attempt(row)
        assert attempt is not None
        return attempt

    def _filtered_events(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self._events)
        event_section = _text(filters.get("event_section"))
        for key in ("event_type", "aggregate_type", "aggregate_id", "subject_type", "subject_id", "trace_id", "idempotency_key", "source_module"):
            value = _text(filters.get(key))
            if value:
                rows = [row for row in rows if _text(row.get(key)) == value]
        if event_section and not _text(filters.get("event_type")):
            known_types = {event_type for values in EVENT_SECTION_EVENT_TYPES.values() for event_type in values}
            section_types = set(EVENT_SECTION_EVENT_TYPES.get(event_section, ()))
            if section_types:
                rows = [row for row in rows if _text(row.get("event_type")) in section_types]
            elif event_section == "other":
                rows = [row for row in rows if _text(row.get("event_type")) not in known_types]
        trace_hashes = set(_trace_hash_candidates(filters))
        if trace_hashes:
            rows = [
                row
                for row in rows
                if _text(
                    (((row.get("payload_json") or {}).get("broadcast_task") or {}).get("original_trace_hash"))
                    or (((row.get("payload_json") or {}).get("broadcast_task") or {}).get("trace_id_hash"))
                )
                in trace_hashes
            ]
        if _text(filters.get("created_from")):
            created_from = self._dt(filters.get("created_from"))
            rows = [row for row in rows if self._dt(row.get("created_at")) >= created_from]
        if _text(filters.get("created_to")):
            created_to = self._dt(filters.get("created_to"))
            rows = [row for row in rows if self._dt(row.get("created_at")) <= created_to]
        consumer_name = _text(filters.get("consumer_name"))
        if consumer_name:
            event_ids = {row.get("event_id") for row in self._runs if row.get("consumer_name") == consumer_name}
            rows = [row for row in rows if row.get("event_id") in event_ids]
        consumer_status = _text(filters.get("consumer_status"))
        if consumer_status:
            event_ids = {row.get("event_id") for row in self._runs if row.get("status") == consumer_status}
            rows = [row for row in rows if row.get("event_id") in event_ids]
        return rows

    def _filtered_runs(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self._runs)
        event_type = _text(filters.get("event_type"))
        for key in ("event_id", "consumer_name", "consumer_type", "status"):
            value = _text(filters.get(key))
            if value:
                rows = [row for row in rows if _text(row.get(key)) == value]
        if event_type:
            rows = [row for row in rows if (self.get_event(row.get("event_id") or "") or InternalEvent()).event_type == event_type]
        return rows

    def _event_consumer_pair_set(self, event_consumers: Any) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for item in event_consumers or []:
            if isinstance(item, str) and ":" in item:
                event_type, consumer_name = item.split(":", 1)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                event_type, consumer_name = item
            else:
                continue
            event_type = _text(event_type)
            consumer_name = _text(consumer_name)
            if event_type and consumer_name:
                pairs.add((event_type, consumer_name))
        return pairs

    def _find_run(self, run_id: int) -> dict[str, Any] | None:
        for row in self._runs:
            if int(row.get("id") or 0) == int(run_id):
                return row
        return None

    def _mutate(self, run_id: int, **changes: Any) -> InternalEventConsumerRun | None:
        row = self._find_run(run_id)
        if not row:
            return None
        row.update(changes)
        row["updated_at"] = public_datetime(utcnow())
        return _public_run(row)

    def _dt(self, value: Any) -> datetime:
        text_value = _text(value)
        if not text_value:
            return datetime.min.replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)


_fixture_repo = InMemoryInternalEventRepository()


def reset_internal_event_fixture_state() -> None:
    global _fixture_repo
    _fixture_repo = InMemoryInternalEventRepository()


def build_internal_event_repository() -> InternalEventRepository:
    if fixture_mode():
        return _fixture_repo
    return SQLAlchemyInternalEventRepository()
