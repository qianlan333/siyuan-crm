"""Focus-send batch / item data-access (阶段 4.4).

Extracted from repo.py. Covers automation_focus_send_batch / _item tables
used by the focus-send pipeline. External callers keep using
``automation_conversion.repo.X``.
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
    _stage_route_lookup_keys,
)


def insert_focus_send_batch(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_focus_send_batch (
            stage_key,
            pool_key,
            operator_type,
            operator_id,
            status,
            total_count,
            sent_count,
            failed_count,
            skipped_count,
            cancelled_count,
            next_run_at,
            last_run_at,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("stage_key")),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("cancelled_count") or 0),
            _normalized_text(payload.get("next_run_at")),
            _normalized_text(payload.get("last_run_at")),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_focus_send_batch(batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch
        SET stage_key = ?,
            pool_key = ?,
            operator_type = ?,
            operator_id = ?,
            status = ?,
            total_count = ?,
            sent_count = ?,
            failed_count = ?,
            skipped_count = ?,
            cancelled_count = ?,
            next_run_at = ?,
            last_run_at = ?,
            updated_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("stage_key")),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("cancelled_count") or 0),
            _normalized_text(payload.get("next_run_at")),
            _normalized_text(payload.get("last_run_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("finished_at")),
            int(batch_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_focus_send_batch(batch_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_focus_send_batch
        WHERE id = ?
        LIMIT 1
        """,
        (int(batch_id),),
    )


def find_active_focus_send_batch_by_stage(stage_key: str) -> dict[str, Any] | None:
    stage_keys = _stage_route_lookup_keys(stage_key)
    if not stage_keys:
        return None
    placeholders = ",".join("?" for _ in stage_keys)
    return _fetchone_dict(
        f"""
        SELECT *
        FROM automation_focus_send_batch
        WHERE stage_key IN ({placeholders})
          AND status IN ('pending', 'running')
        ORDER BY id DESC
        LIMIT 1
        """,
        tuple(stage_keys),
    )


def list_due_focus_send_batches(*, due_at: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_focus_send_batch
        WHERE status IN ('pending', 'running')
          AND (next_run_at = '' OR next_run_at <= ?)
        ORDER BY id ASC
        LIMIT ?
        """,
        (_normalized_text(due_at), int(limit)),
    )


def list_recent_focus_send_batches(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_focus_send_batch
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def insert_focus_send_batch_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_focus_send_batch_item (
            batch_id,
            member_id,
            external_contact_id,
            phone,
            position_index,
            status,
            detail,
            result_payload,
            created_at,
            updated_at,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            int(payload.get("position_index") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("result_payload") or {}),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_focus_send_batch_item(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch_item
        SET member_id = ?,
            external_contact_id = ?,
            phone = ?,
            position_index = ?,
            status = ?,
            detail = ?,
            result_payload = ?,
            updated_at = ?,
            started_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            int(payload.get("position_index") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("result_payload") or {}),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
            int(item_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_focus_send_batch_items(*, batch_id: int, limit: int = 100, descending: bool = False) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_focus_send_batch_item
        WHERE batch_id = ?
        ORDER BY position_index {'DESC' if descending else 'ASC'}, id {'DESC' if descending else 'ASC'}
        LIMIT ?
        """,
        (int(batch_id), int(limit)),
    )


def claim_next_focus_send_batch_item(*, batch_id: int, started_at: str) -> dict[str, Any] | None:
    candidate = _fetchone_dict(
        """
        SELECT *
        FROM automation_focus_send_batch_item
        WHERE batch_id = ?
          AND status = 'pending'
        ORDER BY position_index ASC, id ASC
        LIMIT 1
        """,
        (int(batch_id),),
    )
    if not candidate:
        return None
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch_item
        SET status = 'running',
            updated_at = ?,
            started_at = ?
        WHERE id = ?
          AND status = 'pending'
        RETURNING *
        """,
        (
            _normalized_text(started_at),
            _normalized_text(started_at),
            int(candidate["id"]),
        ),
    ).fetchone()
    return dict(row) if row else None


def has_historical_focus_send_delivery(*, rule_key: str, external_contact_id: str) -> bool:
    rule_keys = _stage_route_lookup_keys(rule_key)
    if not rule_keys:
        return False
    placeholders = ",".join("?" for _ in rule_keys)
    row = _fetchone_dict(
        f"""
        SELECT item.id
        FROM automation_focus_send_batch_item item
        JOIN automation_focus_send_batch batch ON batch.id = item.batch_id
        WHERE batch.stage_key IN ({placeholders})
          AND item.external_contact_id = ?
          AND item.status = 'sent'
        ORDER BY item.id DESC
        LIMIT 1
        """,
        (*rule_keys, _normalized_text(external_contact_id)),
    )
    return bool(row)


def deserialize_focus_send_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row or {})


def deserialize_focus_send_batch_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "result_payload": _json_loads(row.get("result_payload"), default={}),
    }




__all__ = [
    "claim_next_focus_send_batch_item",
    "deserialize_focus_send_batch_item_row",
    "deserialize_focus_send_batch_row",
    "find_active_focus_send_batch_by_stage",
    "get_focus_send_batch",
    "has_historical_focus_send_delivery",
    "insert_focus_send_batch",
    "insert_focus_send_batch_item",
    "list_due_focus_send_batches",
    "list_focus_send_batch_items",
    "list_recent_focus_send_batches",
    "update_focus_send_batch",
    "update_focus_send_batch_item",
]
