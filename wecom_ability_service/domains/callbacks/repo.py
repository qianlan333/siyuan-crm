from __future__ import annotations

import json
from typing import Any

from ...db import get_db


def get_external_contact_event_log_by_key(event_key: str):
    return get_db().execute(
        """
        SELECT id, process_status, retry_count
        FROM wecom_external_contact_event_logs
        WHERE event_key = ?
        """,
        (event_key,),
    ).fetchone()


def touch_external_contact_event_log(event_log_id: int) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE wecom_external_contact_event_logs
        SET updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(event_log_id),),
    )
    db.commit()


def insert_external_contact_event_log(
    *,
    corp_id: str,
    event_type: str,
    change_type: str,
    external_userid: str,
    user_id: str,
    event_time: int,
    event_key: str,
    payload_xml: str,
    payload_json: dict[str, Any],
):
    db = get_db()
    row = db.execute(
        """
        INSERT INTO wecom_external_contact_event_logs (
            corp_id, event_type, change_type, external_userid, user_id, event_time,
            event_key, payload_xml, payload_json, process_status, retry_count, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, '')
        RETURNING id, process_status, retry_count
        """,
        (
            corp_id,
            event_type,
            change_type,
            external_userid,
            user_id,
            event_time,
            event_key,
            payload_xml,
            json.dumps(payload_json, ensure_ascii=False),
        ),
    ).fetchone()
    db.commit()
    return row


def mark_external_contact_event_processing(event_log_id: int):
    db = get_db()
    db.execute(
        """
        UPDATE wecom_external_contact_event_logs
        SET process_status = 'processing',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(event_log_id),),
    )
    db.commit()
    return get_external_contact_event_log(event_log_id)


def get_external_contact_event_log(event_log_id: int):
    return get_db().execute(
        """
        SELECT *
        FROM wecom_external_contact_event_logs
        WHERE id = ?
        """,
        (int(event_log_id),),
    ).fetchone()


def finish_external_contact_event_log(
    event_log_id: int,
    *,
    status: str,
    error_message: str = "",
    increment_retry: bool = False,
) -> None:
    db = get_db()
    retry_expr = "retry_count + 1" if increment_retry else "retry_count"
    db.execute(
        f"""
        UPDATE wecom_external_contact_event_logs
        SET process_status = ?,
            error_message = ?,
            retry_count = {retry_expr},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, error_message, int(event_log_id)),
    )
    db.commit()


def get_recent_external_contact_event_logs(limit: int = 20):
    safe_limit = max(1, min(int(limit), 200))
    return get_db().execute(
        """
        SELECT id, corp_id, event_type, change_type, external_userid, user_id, event_time,
               event_key, process_status, retry_count, error_message, created_at, updated_at
        FROM wecom_external_contact_event_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (safe_limit,),
    ).fetchall()


def count_pending_events() -> dict[str, Any]:
    db = get_db()
    row = db.execute(
        """
        SELECT
            COUNT(*) AS pending_count,
            MIN(created_at) AS oldest_created_at
        FROM wecom_external_contact_event_logs
        WHERE process_status IN ('pending', 'processing')
        """,
    ).fetchone()
    return dict(row) if row else {"pending_count": 0, "oldest_created_at": None}


def count_failed_events_since(since_timestamp: str) -> int:
    row = get_db().execute(
        """
        SELECT COUNT(*) AS cnt
        FROM wecom_external_contact_event_logs
        WHERE process_status = 'failed'
          AND updated_at >= ?
        """,
        (since_timestamp,),
    ).fetchone()
    return int(row["cnt"]) if row else 0


def list_stale_pending_events(*, age_seconds: int = 120, limit: int = 50) -> list[dict[str, Any]]:
    db = get_db()
    rows = db.execute(
        """
        SELECT id, corp_id, event_type, change_type, external_userid, user_id,
               process_status, retry_count, created_at, updated_at
        FROM wecom_external_contact_event_logs
        WHERE process_status IN ('pending', 'processing')
          AND created_at <= NOW() - (? || ' seconds')::interval
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(age_seconds), int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_event_dead_letter(event_log_id: int, *, error_message: str = "") -> None:
    db = get_db()
    db.execute(
        """
        UPDATE wecom_external_contact_event_logs
        SET process_status = 'dead_letter',
            error_message = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (error_message, int(event_log_id)),
    )
    db.commit()
