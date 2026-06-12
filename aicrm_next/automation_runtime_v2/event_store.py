from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import AutomationEventInput, EVENT_TYPES, text, utcnow


def _json_text(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _dt(value: datetime | str | None) -> datetime | str:
    if value is None:
        return utcnow()
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _row(row: Any) -> dict[str, Any]:
    item = dict(row or {})
    payload = item.get("payload_json")
    if isinstance(payload, str):
        try:
            item["payload_json"] = json.loads(payload)
        except (TypeError, ValueError):
            item["payload_json"] = {}
    elif payload is None:
        item["payload_json"] = {}
    return item


def get_event(event_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM automation_event_v2 WHERE id = ? LIMIT 1", (int(event_id),)).fetchone()
    return _row(row) if row else None


def insert_event(payload: AutomationEventInput | dict[str, Any]) -> dict[str, Any]:
    source = payload if isinstance(payload, AutomationEventInput) else AutomationEventInput(**dict(payload or {}))
    if source.event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported runtime v2 event_type: {source.event_type}")
    source_id = text(source.source_id)
    source_type = text(source.source_type)
    if not source_id or not source_type:
        raise ValueError("source_type and source_id are required")
    idempotency_key = text(source.idempotency_key) or f"{source_type}:{source_id}"
    payload_json = dict(source.payload_json or {})
    event_uid = text(payload_json.get("event_uid")) or str(uuid.uuid4())
    row = get_db().execute(
        """
        INSERT INTO automation_event_v2 (
            event_uid, event_type, program_id, channel_id, binding_id, external_userid, phone,
            person_id, source_type, source_id, occurred_at, raw_occurred_at, payload_json,
            idempotency_key, status, error_message, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, 'pending', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (source_type, source_id) DO UPDATE
        SET updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            event_uid,
            source.event_type,
            source.program_id,
            source.channel_id,
            source.binding_id,
            text(source.external_userid),
            text(source.phone),
            source.person_id,
            source_type,
            source_id,
            _dt(source.occurred_at),
            _dt(source.raw_occurred_at) if source.raw_occurred_at is not None else None,
            _json_text(payload_json),
            idempotency_key,
        ),
    ).fetchone()
    return _row(row)


def update_event_status(event_id: int, status: str, error_message: str = "") -> None:
    get_db().execute(
        """
        UPDATE automation_event_v2
        SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (text(status), text(error_message), int(event_id)),
    )


def mark_ignored(event_id: int, reason: str) -> None:
    update_event_status(int(event_id), "ignored", reason)
