"""SOP-related data-access for automation_conversion (阶段 4.4).

Extracted from repo.py. Covers automation_sop_* tables (pool_config / batch /
template / pool_state / etc) and the cross-table SOP pool lock acquisition.
External callers keep using ``automation_conversion.repo.X``.
"""

from __future__ import annotations

from typing import Any

from ...db import cast_text, get_db, get_db_backend, is_postgres
from ._repo_helpers import (
    _AUTOMATION_SOP_POOL_LOCK_NAMESPACE,
    _db_bool,
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _json_loads,
    _normalized_text,
    _row_bool,
    _sop_pool_lookup_keys,
)


def list_sop_pool_configs() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_pool_config
        ORDER BY pool_key ASC, id ASC
        """
    )


def get_sop_pool_config(pool_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_pool_config
        WHERE pool_key = ?
        LIMIT 1
        """,
        (_normalized_text(pool_key),),
    )


def save_sop_pool_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_pool_config(_normalized_text(payload.get("pool_key")))
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_pool_config
            SET enabled = ?,
                max_day_count = ?,
                send_time = ?,
                timezone = ?,
                effective_start_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                int(payload.get("max_day_count") or 0),
                _normalized_text(payload.get("send_time")),
                _normalized_text(payload.get("timezone")),
                _normalized_text(payload.get("effective_start_at")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_pool_config (
            pool_key,
            enabled,
            max_day_count,
            send_time,
            timezone,
            effective_start_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("max_day_count") or 0),
            _normalized_text(payload.get("send_time")),
            _normalized_text(payload.get("timezone")),
            _normalized_text(payload.get("effective_start_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_sop_templates(*, pool_key: str = "") -> list[dict[str, Any]]:
    normalized_pool_key = _normalized_text(pool_key)
    if normalized_pool_key:
        return _fetchall_dicts(
            """
            SELECT *
            FROM automation_sop_template
            WHERE pool_key = ?
            ORDER BY day_index ASC, id ASC
            """,
            (normalized_pool_key,),
        )
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_template
        ORDER BY pool_key ASC, day_index ASC, id ASC
        """
    )


def get_sop_template(*, pool_key: str, day_index: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_template
        WHERE pool_key = ?
          AND day_index = ?
        LIMIT 1
        """,
        (_normalized_text(pool_key), int(day_index)),
    )


def save_sop_template(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_template(
        pool_key=_normalized_text(payload.get("pool_key")),
        day_index=int(payload.get("day_index") or 0),
    )
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_template
            SET content = ?,
                images_json = ?,
                miniprograms_json = ?,
                enabled = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _normalized_text(payload.get("content")),
                _json_dumps(payload.get("images_json") or []),
                _json_dumps(payload.get("miniprograms_json") or []),
                _db_bool(bool(payload.get("enabled"))),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_template (
            pool_key,
            day_index,
            content,
            images_json,
            miniprograms_json,
            enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            _normalized_text(payload.get("content")),
            _json_dumps(payload.get("images_json") or []),
            _json_dumps(payload.get("miniprograms_json") or []),
            _db_bool(bool(payload.get("enabled"))),
        ),
    ).fetchone()
    return dict(row) if row else {}


def delete_sop_template_day(*, pool_key: str, day_index: int) -> None:
    normalized_pool_key = _normalized_text(pool_key)
    normalized_day_index = int(day_index)
    db = get_db()
    db.execute(
        """
        DELETE FROM automation_sop_template
        WHERE pool_key = ?
          AND day_index = ?
        """,
        (normalized_pool_key, normalized_day_index),
    )
    db.execute(
        """
        UPDATE automation_sop_template
        SET day_index = day_index + 1000,
            updated_at = CURRENT_TIMESTAMP
        WHERE pool_key = ?
          AND day_index > ?
        """,
        (normalized_pool_key, normalized_day_index),
    )
    db.execute(
        """
        UPDATE automation_sop_template
        SET day_index = day_index - 1001,
            updated_at = CURRENT_TIMESTAMP
        WHERE pool_key = ?
          AND day_index > ?
        """,
        (normalized_pool_key, normalized_day_index + 1000),
    )


def get_sop_progress(*, member_id: int, pool_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_progress
        WHERE member_id = ?
          AND pool_key = ?
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key)),
    )


def list_sop_progress_for_members(*, member_ids: list[int] | None = None, pool_key: str = "") -> list[dict[str, Any]]:
    normalized_member_ids = [int(item) for item in (member_ids or []) if str(item).strip()]
    normalized_pool_key = _normalized_text(pool_key)
    params: list[Any] = []
    sql = """
    SELECT *
    FROM automation_sop_progress
    WHERE 1 = 1
    """
    if normalized_member_ids:
        placeholders = ",".join("?" for _ in normalized_member_ids)
        sql += f" AND member_id IN ({placeholders})"
        params.extend(normalized_member_ids)
    if normalized_pool_key:
        sql += " AND pool_key = ?"
        params.append(normalized_pool_key)
    sql += " ORDER BY pool_key ASC, member_id ASC, id ASC"
    return _fetchall_dicts(sql, tuple(params))


def save_sop_progress(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_progress(
        member_id=int(payload.get("member_id") or 0),
        pool_key=_normalized_text(payload.get("pool_key")),
    )
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_progress
            SET first_entered_at = ?,
                last_entered_at = ?,
                sop_anchor_date = ?,
                first_effective_in_pool_at = ?,
                last_in_pool_at = ?,
                last_sent_day = ?,
                last_sent_at = ?,
                completed_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _normalized_text(payload.get("first_entered_at")),
                _normalized_text(payload.get("last_entered_at")),
                _normalized_text(payload.get("sop_anchor_date")),
                _normalized_text(payload.get("first_effective_in_pool_at")),
                _normalized_text(payload.get("last_in_pool_at")),
                int(payload.get("last_sent_day") or 0),
                _normalized_text(payload.get("last_sent_at")),
                _normalized_text(payload.get("completed_at")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_progress (
            member_id,
            pool_key,
            first_entered_at,
            last_entered_at,
            sop_anchor_date,
            first_effective_in_pool_at,
            last_in_pool_at,
            last_sent_day,
            last_sent_at,
            completed_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("member_id") or 0),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("first_entered_at")),
            _normalized_text(payload.get("last_entered_at")),
            _normalized_text(payload.get("sop_anchor_date")),
            _normalized_text(payload.get("first_effective_in_pool_at")),
            _normalized_text(payload.get("last_in_pool_at")),
            int(payload.get("last_sent_day") or 0),
            _normalized_text(payload.get("last_sent_at")),
            _normalized_text(payload.get("completed_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_sop_batch(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_sop_batch (
            pool_key,
            day_index,
            template_id,
            scheduled_for,
            status,
            total_count,
            success_count,
            skipped_count,
            failed_count,
            summary_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            payload.get("template_id"),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_dumps(payload.get("summary_json") or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_sop_batch(batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_sop_batch
        SET pool_key = ?,
            day_index = ?,
            template_id = ?,
            scheduled_for = ?,
            status = ?,
            total_count = ?,
            success_count = ?,
            skipped_count = ?,
            failed_count = ?,
            summary_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            payload.get("template_id"),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_dumps(payload.get("summary_json") or {}),
            int(batch_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_sop_batch(batch_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch
        WHERE id = ?
        LIMIT 1
        """,
        (int(batch_id),),
    )


def list_sop_batches(*, pool_key: str = "", limit: int = 50) -> list[dict[str, Any]]:
    normalized_pool_key = _normalized_text(pool_key)
    params: list[Any] = []
    sql = """
    SELECT *
    FROM automation_sop_batch
    WHERE 1 = 1
    """
    if normalized_pool_key:
        lookup_keys = _sop_pool_lookup_keys(normalized_pool_key)
        sql += f" AND pool_key IN ({', '.join('?' for _ in lookup_keys)})"
        params.extend(lookup_keys)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    return _fetchall_dicts(sql, tuple(params))


def try_acquire_sop_pool_run_lock(*, pool_key: str) -> bool:
    normalized_pool_key = _normalized_text(pool_key)
    if not normalized_pool_key or get_db_backend() != "postgres":
        return True
    row = get_db().execute(
        """
        SELECT pg_try_advisory_xact_lock(?, hashtext(?)) AS locked
        """,
        (_AUTOMATION_SOP_POOL_LOCK_NAMESPACE, normalized_pool_key),
    ).fetchone()
    return _row_bool((row or {}).get("locked"))


def get_successful_sop_batch_item(*, member_id: int, pool_key: str, day_index: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE member_id = ?
          AND pool_key = ?
          AND day_index = ?
          AND status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key), int(day_index)),
    )


def get_sop_batch_item_for_member_day(*, member_id: int, pool_key: str, day_index_snapshot: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE member_id = ?
          AND pool_key = ?
          AND day_index_snapshot = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key), int(day_index_snapshot)),
    )


def insert_sop_batch_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_sop_batch_item (
            batch_id,
            member_id,
            pool_key,
            day_index,
            day_index_snapshot,
            external_userid,
            status,
            error_message,
            content_snapshot,
            images_snapshot,
            sent_record_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            int(payload.get("day_index_snapshot") or payload.get("day_index") or 0),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("content_snapshot")),
            _json_dumps(payload.get("images_snapshot") or []),
            payload.get("sent_record_id"),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_sop_batch_item(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_sop_batch_item
        SET batch_id = ?,
            member_id = ?,
            pool_key = ?,
            day_index = ?,
            day_index_snapshot = ?,
            external_userid = ?,
            status = ?,
            error_message = ?,
            content_snapshot = ?,
            images_snapshot = ?,
            sent_record_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            int(payload.get("day_index_snapshot") or payload.get("day_index") or 0),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("content_snapshot")),
            _json_dumps(payload.get("images_snapshot") or []),
            payload.get("sent_record_id"),
            int(item_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_sop_batch_items(*, batch_id: int, limit: int = 200) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE batch_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(batch_id), max(1, int(limit))),
    )


def deserialize_sop_template_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "images_json": _json_loads(row.get("images_json"), default=[]),
        "miniprograms_json": _json_loads(row.get("miniprograms_json"), default=[]),
        "enabled": _row_bool(row.get("enabled")),
    }


def deserialize_sop_progress_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row or {})


def deserialize_sop_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "summary_json": _json_loads(row.get("summary_json"), default={}),
    }


def deserialize_sop_batch_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "images_snapshot": _json_loads((row or {}).get("images_snapshot"), default=[]),
    }



__all__ = [
    "delete_sop_template_day",
    "deserialize_sop_batch_item_row",
    "deserialize_sop_batch_row",
    "deserialize_sop_progress_row",
    "deserialize_sop_template_row",
    "get_sop_batch",
    "get_sop_batch_item_for_member_day",
    "get_sop_pool_config",
    "get_sop_progress",
    "get_sop_template",
    "get_successful_sop_batch_item",
    "insert_sop_batch",
    "insert_sop_batch_item",
    "list_sop_batch_items",
    "list_sop_batches",
    "list_sop_pool_configs",
    "list_sop_progress_for_members",
    "list_sop_templates",
    "save_sop_pool_config",
    "save_sop_progress",
    "save_sop_template",
    "try_acquire_sop_pool_run_lock",
    "update_sop_batch",
    "update_sop_batch_item",
]
