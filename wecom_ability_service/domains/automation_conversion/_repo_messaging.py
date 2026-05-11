"""Messaging-related data-access for automation_conversion.

Extracted from repo.py (阶段 4.3 拆分蓝图).

Covers 10 functions across:
- automation_message_activity_sync_run / _sync_item
- archived_messages (read-side cursor + by-ids lookup)
- corresponding deserialize_*_row helpers

External callers keep importing through ``automation_conversion.repo`` —
repo.py re-exports everything via ``from ._repo_messaging import *``. Zero
behaviour change.
"""

from __future__ import annotations

from typing import Any

from ...db import cast_text, get_db, is_postgres
from ._repo_helpers import (
    _db_bool,
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _json_loads,
    _normalized_text,
    _row_bool,
)


def insert_message_activity_sync_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_message_activity_sync_run (
            trigger_source,
            operator_type,
            operator_id,
            status,
            candidate_count,
            matched_count,
            updated_count,
            skipped_ambiguous_count,
            skipped_unmatched_count,
            skipped_missing_phone_count,
            focus_count,
            normal_count,
            error_message,
            summary_json,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("trigger_source")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("candidate_count") or 0),
            int(payload.get("matched_count") or 0),
            int(payload.get("updated_count") or 0),
            int(payload.get("skipped_ambiguous_count") or 0),
            int(payload.get("skipped_unmatched_count") or 0),
            int(payload.get("skipped_missing_phone_count") or 0),
            int(payload.get("focus_count") or 0),
            int(payload.get("normal_count") or 0),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("summary_json") or {}),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_message_activity_sync_run(run_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_message_activity_sync_run
        SET trigger_source = ?,
            operator_type = ?,
            operator_id = ?,
            status = ?,
            candidate_count = ?,
            matched_count = ?,
            updated_count = ?,
            skipped_ambiguous_count = ?,
            skipped_unmatched_count = ?,
            skipped_missing_phone_count = ?,
            focus_count = ?,
            normal_count = ?,
            error_message = ?,
            summary_json = ?,
            started_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("trigger_source")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("candidate_count") or 0),
            int(payload.get("matched_count") or 0),
            int(payload.get("updated_count") or 0),
            int(payload.get("skipped_ambiguous_count") or 0),
            int(payload.get("skipped_unmatched_count") or 0),
            int(payload.get("skipped_missing_phone_count") or 0),
            int(payload.get("focus_count") or 0),
            int(payload.get("normal_count") or 0),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("summary_json") or {}),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
            int(run_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_latest_message_activity_sync_run() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_message_activity_sync_run
        ORDER BY finished_at DESC, id DESC
        LIMIT 1
        """
    )


def list_message_activity_sync_items(*, run_id: int, limit: int = 100) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_message_activity_sync_item
        WHERE run_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(run_id), int(limit)),
    )


def insert_message_activity_sync_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_message_activity_sync_item (
            run_id,
            member_id,
            external_contact_id,
            phone,
            phone_prefix3,
            phone_last4,
            phone_match_key,
            message_count,
            status,
            detail,
            before_snapshot,
            after_snapshot,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(payload.get("run_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            _normalized_text(payload.get("phone_prefix3")),
            _normalized_text(payload.get("phone_last4")),
            _normalized_text(payload.get("phone_match_key")),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("before_snapshot") or {}),
            _json_dumps(payload.get("after_snapshot") or {}),
            _normalized_text(payload.get("created_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_latest_archived_message_storage_id() -> int:
    row = _fetchone_dict(
        """
        SELECT COALESCE(MAX(id), 0) AS latest_id
        FROM archived_messages
        """
    ) or {}
    return int(row.get("latest_id") or 0)


def list_archived_messages_after_storage_cursor(*, after_id: int, limit: int = 500) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(after_id), int(limit)),
    )


def list_archived_messages_by_ids(message_ids: list[int]) -> list[dict[str, Any]]:
    normalized_ids = [int(item) for item in message_ids if str(item).strip()]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        tuple(normalized_ids),
    )


def deserialize_message_activity_sync_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "summary_json": _json_loads(row.get("summary_json"), default={}),
    }


def deserialize_message_activity_sync_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "before_snapshot": _json_loads(row.get("before_snapshot"), default={}),
        "after_snapshot": _json_loads(row.get("after_snapshot"), default={}),
    }




__all__ = [
    "deserialize_message_activity_sync_item_row",
    "deserialize_message_activity_sync_run_row",
    "get_latest_archived_message_storage_id",
    "get_latest_message_activity_sync_run",
    "insert_message_activity_sync_item",
    "insert_message_activity_sync_run",
    "list_archived_messages_after_storage_cursor",
    "list_archived_messages_by_ids",
    "list_message_activity_sync_items",
    "update_message_activity_sync_run",
]
