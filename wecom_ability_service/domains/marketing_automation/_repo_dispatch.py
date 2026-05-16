"""conversion_dispatch_log (阶段 5.4).

Extracted from repo.py. External callers keep using
``marketing_automation.repo.X``.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (  # noqa: F401
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _normalized_text,
)


def get_conversion_dispatch_log(batch_id: int, external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM conversion_dispatch_log
        WHERE batch_id = ? AND external_userid = ?
        """,
        (int(batch_id), _normalized_text(external_userid)),
    )


def upsert_conversion_dispatch_log(
    *,
    automation_key: str,
    batch_id: int,
    external_userid: str,
    dispatch_status: str,
    dispatch_channel: str,
    dispatch_payload: dict[str, Any] | None,
    dispatch_note: str,
    dispatched_at: str = "",
    acked_at: str = "",
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(automation_key),
        int(batch_id),
        _normalized_text(external_userid),
        _normalized_text(dispatch_status),
        _normalized_text(dispatch_channel),
        _json_dumps(dispatch_payload),
        _normalized_text(dispatch_note),
        _normalized_text(dispatched_at),
        _normalized_text(acked_at),
    )
    row = db.execute(
        """
        INSERT INTO conversion_dispatch_log (
            automation_key,
            batch_id,
            external_userid,
            dispatch_status,
            dispatch_channel,
            dispatch_payload_json,
            dispatch_note,
            dispatched_at,
            acked_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?::jsonb, ?, NULLIF(?, '')::timestamptz, NULLIF(?, '')::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (batch_id, external_userid) DO UPDATE SET
            automation_key = EXCLUDED.automation_key,
            dispatch_status = EXCLUDED.dispatch_status,
            dispatch_channel = EXCLUDED.dispatch_channel,
            dispatch_payload_json = EXCLUDED.dispatch_payload_json,
            dispatch_note = EXCLUDED.dispatch_note,
            dispatched_at = CASE
                WHEN EXCLUDED.dispatched_at IS NOT NULL THEN EXCLUDED.dispatched_at
                ELSE conversion_dispatch_log.dispatched_at
            END,
            acked_at = CASE
                WHEN EXCLUDED.acked_at IS NOT NULL THEN EXCLUDED.acked_at
                ELSE conversion_dispatch_log.acked_at
            END,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def list_conversion_dispatch_logs(
    *,
    external_userid: str = "",
    batch_id: int | None = None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    normalized_external_userid = _normalized_text(external_userid)
    if batch_id is not None:
        filters.append("batch_id = ?")
        params.append(int(batch_id))
    if normalized_external_userid:
        filters.append("external_userid = ?")
        params.append(normalized_external_userid)
    if not filters:
        return []
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM conversion_dispatch_log
        WHERE {' AND '.join(filters)}
        ORDER BY updated_at DESC, id DESC
        """,
        tuple(params),
    )




__all__ = [
    "get_conversion_dispatch_log",
    "list_conversion_dispatch_logs",
    "upsert_conversion_dispatch_log",
]
