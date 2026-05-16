"""Reply-monitor data-access (阶段 4.4).

Extracted from repo.py. Covers automation_reply_monitor_config / _queue tables
used by the reply-monitor capture/dispatch pipeline. External callers keep
using ``automation_conversion.repo.X``.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (
    _db_bool,
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _json_loads,
    _normalized_text,
    _row_bool,
)


def get_reply_monitor_config() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_config
        WHERE config_key = 'default'
        LIMIT 1
        """
    )


def save_reply_monitor_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_reply_monitor_config()
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_reply_monitor_config
            SET enabled = ?,
                last_capture_cursor = ?,
                last_capture_at = ?,
                last_capture_status = ?,
                last_capture_summary_json = ?,
                last_dispatch_at = ?,
                last_dispatch_status = ?,
                last_dispatch_summary_json = ?,
                last_error = ?,
                quiet_hours_start = ?,
                quiet_hours_end = ?,
                dispatch_interval_seconds = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                int(payload.get("last_capture_cursor") or 0),
                _normalized_text(payload.get("last_capture_at")),
                _normalized_text(payload.get("last_capture_status")),
                _json_dumps(payload.get("last_capture_summary_json") or {}),
                _normalized_text(payload.get("last_dispatch_at")),
                _normalized_text(payload.get("last_dispatch_status")),
                _json_dumps(payload.get("last_dispatch_summary_json") or {}),
                _normalized_text(payload.get("last_error")),
                _normalized_text(payload.get("quiet_hours_start")),
                _normalized_text(payload.get("quiet_hours_end")),
                int(payload.get("dispatch_interval_seconds") or 0),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_reply_monitor_config (
            config_key,
            enabled,
            last_capture_cursor,
            last_capture_at,
            last_capture_status,
            last_capture_summary_json,
            last_dispatch_at,
            last_dispatch_status,
            last_dispatch_summary_json,
            last_error,
            quiet_hours_start,
            quiet_hours_end,
            dispatch_interval_seconds,
            created_at,
            updated_at
        )
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("last_capture_cursor") or 0),
            _normalized_text(payload.get("last_capture_at")),
            _normalized_text(payload.get("last_capture_status")),
            _json_dumps(payload.get("last_capture_summary_json") or {}),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("last_dispatch_status")),
            _json_dumps(payload.get("last_dispatch_summary_json") or {}),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("quiet_hours_start")),
            _normalized_text(payload.get("quiet_hours_end")),
            int(payload.get("dispatch_interval_seconds") or 0),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_reply_monitor_queue_item(queue_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE id = ?
        LIMIT 1
        """,
        (int(queue_id),),
    )


def get_active_reply_monitor_queue_item(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE external_userid = ?
          AND status IN ('pending', 'deferred_quiet_hours', 'paused')
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def insert_reply_monitor_queue_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_reply_monitor_queue (
            member_id,
            external_userid,
            owner_userid,
            status,
            message_ids_json,
            message_count,
            first_inbound_at,
            last_inbound_at,
            not_before,
            last_dispatch_at,
            error_message,
            payload_snapshot_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("owner_userid")),
            _normalized_text(payload.get("status")),
            _json_dumps(payload.get("message_ids_json") or []),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("first_inbound_at")),
            _normalized_text(payload.get("last_inbound_at")),
            _normalized_text(payload.get("not_before")),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("payload_snapshot_json") or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_reply_monitor_queue_item(queue_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_reply_monitor_queue
        SET member_id = ?,
            external_userid = ?,
            owner_userid = ?,
            status = ?,
            message_ids_json = ?,
            message_count = ?,
            first_inbound_at = ?,
            last_inbound_at = ?,
            not_before = ?,
            last_dispatch_at = ?,
            error_message = ?,
            payload_snapshot_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("owner_userid")),
            _normalized_text(payload.get("status")),
            _json_dumps(payload.get("message_ids_json") or []),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("first_inbound_at")),
            _normalized_text(payload.get("last_inbound_at")),
            _normalized_text(payload.get("not_before")),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("payload_snapshot_json") or {}),
            int(queue_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_due_reply_monitor_queue_items(*, now_text: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE status IN ('pending', 'deferred_quiet_hours')
          AND not_before <> ''
          AND not_before <= ?
        ORDER BY not_before ASC, id ASC
        LIMIT ?
        """,
        (_normalized_text(now_text), int(limit)),
    )


def list_recent_reply_monitor_queue_items(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def get_reply_monitor_queue_counts() -> dict[str, int]:
    rows = _fetchall_dicts(
        """
        SELECT status, COUNT(*) AS total
        FROM automation_reply_monitor_queue
        GROUP BY status
        """
    )
    counts = {
        "pending": 0,
        "deferred_quiet_hours": 0,
        "dispatched": 0,
        "failed": 0,
        "paused": 0,
    }
    for row in rows:
        status = _normalized_text(row.get("status"))
        if status in counts:
            counts[status] = int(row.get("total") or 0)
    counts["active_total"] = counts["pending"] + counts["deferred_quiet_hours"] + counts["paused"]
    return counts


def get_latest_reply_monitor_not_before() -> str:
    row = _fetchone_dict(
        """
        SELECT not_before
        FROM automation_reply_monitor_queue
        WHERE status IN ('pending', 'deferred_quiet_hours', 'paused')
        ORDER BY not_before DESC, id DESC
        LIMIT 1
        """
    ) or {}
    return _normalized_text(row.get("not_before"))


def deserialize_reply_monitor_config_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "enabled": _row_bool(row.get("enabled")),
        "last_capture_summary_json": _json_loads(row.get("last_capture_summary_json"), default={}),
        "last_dispatch_summary_json": _json_loads(row.get("last_dispatch_summary_json"), default={}),
    }


def deserialize_reply_monitor_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "message_ids_json": _json_loads(row.get("message_ids_json"), default=[]),
        "payload_snapshot_json": _json_loads(row.get("payload_snapshot_json"), default={}),
    }




__all__ = [
    "deserialize_reply_monitor_config_row",
    "deserialize_reply_monitor_queue_row",
    "get_active_reply_monitor_queue_item",
    "get_latest_reply_monitor_not_before",
    "get_reply_monitor_config",
    "get_reply_monitor_queue_counts",
    "get_reply_monitor_queue_item",
    "insert_reply_monitor_queue_item",
    "list_due_reply_monitor_queue_items",
    "list_recent_reply_monitor_queue_items",
    "save_reply_monitor_config",
    "update_reply_monitor_queue_item",
]
