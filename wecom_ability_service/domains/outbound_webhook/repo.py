from __future__ import annotations

import json
from typing import Any

from ...db import get_db, get_db_backend


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _db_bool(value: bool) -> bool:
    return bool(value)


def _serialize_delivery_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload_value = row.get("payload_json")
    if isinstance(payload_value, (dict, list)):
        payload_json = _json_dumps(payload_value)
    elif _normalized_text(payload_value):
        payload_json = _json_dumps(json.loads(payload_value))
    else:
        payload_json = "{}"
    return {
        "id": int(row["id"]),
        "event_type": _normalized_text(row.get("event_type")),
        "source_key": _normalized_text(row.get("source_key")),
        "source_id": _normalized_text(row.get("source_id")),
        "target_url": _normalized_text(row.get("target_url")),
        "payload_json": payload_json,
        "payload_summary": _normalized_text(row.get("payload_summary")),
        "token_configured": bool(row.get("token_configured")),
        "status": _normalized_text(row.get("status")),
        "attempt_count": int(row.get("attempt_count") or 0),
        "max_attempts": int(row.get("max_attempts") or 0),
        "response_status_code": row.get("response_status_code"),
        "response_body_summary": _normalized_text(row.get("response_body_summary")),
        "last_error": _normalized_text(row.get("last_error")),
        "last_attempted_at": _normalized_text(row.get("last_attempted_at")),
        "next_retry_at": _normalized_text(row.get("next_retry_at")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def create_outbound_webhook_delivery(
    *,
    event_type: str,
    source_key: str,
    source_id: str,
    target_url: str,
    payload_json: dict[str, Any],
    payload_summary: str,
    token_configured: bool,
    max_attempts: int,
) -> dict[str, Any]:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO outbound_webhook_deliveries (
            event_type,
            source_key,
            source_id,
            target_url,
            payload_json,
            payload_summary,
            token_configured,
            status,
            attempt_count,
            max_attempts,
            response_status_code,
            response_body_summary,
            last_error,
            last_attempted_at,
            next_retry_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, NULL, '', '', '', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(event_type),
            _normalized_text(source_key),
            _normalized_text(source_id),
            _normalized_text(target_url),
            _json_dumps(payload_json or {}),
            _normalized_text(payload_summary),
            _db_bool(token_configured),
            int(max_attempts),
        ),
    ).fetchone()
    db.commit()
    return _serialize_delivery_row(row) or {}


def update_outbound_webhook_delivery(
    delivery_id: int,
    *,
    target_url: str,
    token_configured: bool,
    status: str,
    attempt_count: int,
    response_status_code: int | None,
    response_body_summary: str,
    last_error: str,
    last_attempted_at: str,
    next_retry_at: str,
) -> dict[str, Any]:
    db = get_db()
    row = db.execute(
        """
        UPDATE outbound_webhook_deliveries
        SET target_url = ?,
            token_configured = ?,
            status = ?,
            attempt_count = ?,
            response_status_code = ?,
            response_body_summary = ?,
            last_error = ?,
            last_attempted_at = ?,
            next_retry_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(target_url),
            _db_bool(token_configured),
            _normalized_text(status),
            int(attempt_count),
            response_status_code,
            _normalized_text(response_body_summary),
            _normalized_text(last_error),
            _normalized_text(last_attempted_at),
            _normalized_text(next_retry_at),
            int(delivery_id),
        ),
    ).fetchone()
    db.commit()
    return _serialize_delivery_row(row) or {}


def get_outbound_webhook_delivery(delivery_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT *
        FROM outbound_webhook_deliveries
        WHERE id = ?
        LIMIT 1
        """,
        (int(delivery_id),),
    ).fetchone()
    return _serialize_delivery_row(row)


def list_outbound_webhook_deliveries(
    *,
    event_type: str = "",
    status: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if _normalized_text(event_type):
        filters.append("event_type = ?")
        params.append(_normalized_text(event_type))
    if _normalized_text(status):
        filters.append("status = ?")
        params.append(_normalized_text(status))
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = get_db().execute(
        f"""
        SELECT *
        FROM outbound_webhook_deliveries
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_serialize_delivery_row(row) or {} for row in rows]


def list_due_outbound_webhook_deliveries(*, now_text: str, limit: int = 20) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT *
        FROM outbound_webhook_deliveries
        WHERE status = 'retry_scheduled'
          AND next_retry_at <> ''
          AND next_retry_at <= ?
        ORDER BY next_retry_at ASC, id ASC
        LIMIT ?
        """,
        (_normalized_text(now_text), max(1, min(int(limit), 200))),
    ).fetchall()
    return [_serialize_delivery_row(row) or {} for row in rows]


def get_outbound_webhook_delivery_counts() -> dict[str, int]:
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
            COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0) AS success_count,
            COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count,
            COALESCE(SUM(CASE WHEN status = 'retry_scheduled' THEN 1 ELSE 0 END), 0) AS retry_scheduled_count,
            COALESCE(SUM(CASE WHEN status = 'exhausted' THEN 1 ELSE 0 END), 0) AS exhausted_count
        FROM outbound_webhook_deliveries
        """
    ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0) if row else 0,
        "pending_count": int(row["pending_count"] or 0) if row else 0,
        "success_count": int(row["success_count"] or 0) if row else 0,
        "failed_count": int(row["failed_count"] or 0) if row else 0,
        "retry_scheduled_count": int(row["retry_scheduled_count"] or 0) if row else 0,
        "exhausted_count": int(row["exhausted_count"] or 0) if row else 0,
    }
