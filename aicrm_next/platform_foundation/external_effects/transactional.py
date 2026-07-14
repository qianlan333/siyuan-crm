from __future__ import annotations

import json
from typing import Any

from .models import DEFAULT_TENANT_ID, ExternalEffectCreateRequest, ExternalEffectJob, public_datetime, utcnow
from .repo import _idempotency_key, _initial_status, _payload_summary, _public_job


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str, separators=(",", ":"))


def enqueue_transactional_external_effect_job(conn: Any, request: ExternalEffectCreateRequest) -> ExternalEffectJob:
    """Insert an External Effect job through the caller-owned transaction.

    The helper deliberately never commits or rolls back. This lets a business
    record, its audit event, and the durable provider continuation share one
    PostgreSQL durability boundary.
    """

    tenant_id = str(request.tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    idempotency_key = _idempotency_key(request)
    payload_summary = dict(request.payload_summary or {}) or _payload_summary(request.payload)
    row = conn.execute(
        """
        INSERT INTO external_effect_job (
            tenant_id, effect_type, adapter_name, operation, target_type, target_id,
            business_type, business_id, source_module, source_route, source_event_id,
            source_command_id, trace_id, request_id, correlation_id, idempotency_key,
            actor_id, actor_type, risk_level, requires_approval, execution_mode,
            payload_json, payload_summary_json, status, priority, scheduled_at,
            attempt_count, max_attempts, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb, %s, %s, %s::timestamptz,
            0, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
        RETURNING *
        """,
        (
            tenant_id,
            str(request.effect_type or "").strip(),
            str(request.adapter_name or "").strip(),
            str(request.operation or "").strip(),
            str(request.target_type or "").strip(),
            str(request.target_id or "").strip(),
            str(request.business_type or "").strip(),
            str(request.business_id or "").strip(),
            str(request.source_module or "").strip(),
            str(request.context.source_route or "").strip(),
            str(request.source_event_id or "").strip(),
            str(request.source_command_id or "").strip(),
            str(request.context.trace_id or "").strip(),
            str(request.context.request_id or "").strip(),
            str(request.correlation_id or "").strip(),
            idempotency_key,
            str(request.context.actor_id or "").strip(),
            str(request.context.actor_type or "system").strip() or "system",
            str(request.risk_level or "medium").strip() or "medium",
            bool(request.requires_approval),
            str(request.execution_mode or "execute").strip() or "execute",
            _json(request.payload),
            _json(payload_summary),
            _initial_status(request),
            int(request.priority or 100),
            public_datetime(request.scheduled_at or utcnow()),
            int(request.max_attempts or 5),
        ),
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT * FROM external_effect_job WHERE tenant_id = %s AND idempotency_key = %s LIMIT 1",
            (tenant_id, idempotency_key),
        ).fetchone()
    job = _public_job(dict(row)) if row else None
    if job is None:
        raise RuntimeError("transactional external effect idempotent create failed")
    return job


__all__ = ["enqueue_transactional_external_effect_job"]
