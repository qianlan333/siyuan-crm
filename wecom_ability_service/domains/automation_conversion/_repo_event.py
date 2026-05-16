"""Event / AI push log / touch delivery data-access (阶段 4.5).

Extracted from repo.py. Covers automation_event, automation_ai_push_log,
automation_touch_delivery_log tables. Imports get_member_by_* from
_repo_member to resolve member by phone/external_contact_id when claiming
touch delivery.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _json_loads,
    _normalized_text,
    _stage_route_lookup_keys,
)
from ._repo_member import (
    get_member_by_external_contact_id,
    get_member_by_phone,
)


def insert_event(
    *,
    member_id: int,
    action: str,
    operator_type: str,
    operator_id: str,
    before_snapshot: dict[str, Any] | None,
    after_snapshot: dict[str, Any] | None,
    remark: str = "",
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_event (
            member_id,
            action,
            operator_type,
            operator_id,
            before_snapshot,
            after_snapshot,
            remark,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(member_id),
            _normalized_text(action),
            _normalized_text(operator_type),
            _normalized_text(operator_id),
            _json_dumps(before_snapshot or {}),
            _json_dumps(after_snapshot or {}),
            _normalized_text(remark),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_recent_events(member_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_event
        WHERE member_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(member_id), int(limit)),
    )


def get_latest_manual_event(member_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_event
        WHERE member_id = ?
          AND operator_type = 'user'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (int(member_id),),
    )


def insert_ai_push_log(
    *,
    member_id: int,
    scene: str,
    request_payload: dict[str, Any],
    status: str,
    request_id: str = "",
    error_message: str = "",
    pushed_at: str = "",
    cooldown_until: str = "",
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_ai_push_log (
            member_id,
            scene,
            request_payload,
            status,
            request_id,
            error_message,
            pushed_at,
            cooldown_until
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(member_id),
            _normalized_text(scene),
            _json_dumps(request_payload),
            _normalized_text(status),
            _normalized_text(request_id),
            _normalized_text(error_message),
            _normalized_text(pushed_at),
            _normalized_text(cooldown_until),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_active_touch_delivery(
    *,
    program_code: str,
    touch_surface: str,
    rule_key: str,
    external_contact_id: str,
) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_touch_delivery_log
        WHERE program_code = ?
          AND touch_surface = ?
          AND rule_key = ?
          AND external_contact_id = ?
          AND status IN ('claimed', 'sent')
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            _normalized_text(program_code),
            _normalized_text(touch_surface),
            _normalized_text(rule_key),
            _normalized_text(external_contact_id),
        ),
    )


def has_historical_stage_manual_send_delivery(*, rule_key: str, external_contact_id: str) -> bool:
    normalized_rule_key = _normalized_text(rule_key)
    normalized_external_contact_id = _normalized_text(external_contact_id)
    if not normalized_rule_key or not normalized_external_contact_id:
        return False
    rule_keys = set(_stage_route_lookup_keys(normalized_rule_key))
    like_clauses = " OR ".join("CAST(filter_snapshot_json AS TEXT) LIKE ?" for _ in rule_keys)
    rows = _fetchall_dicts(
        f"""
        SELECT task_results_json, filter_snapshot_json, status
        FROM user_ops_send_records
        WHERE status IN ('sent', 'partial_failed', 'created')
          AND ({like_clauses})
        ORDER BY id DESC
        LIMIT 500
        """,
        tuple(f"%{rule_key}%" for rule_key in rule_keys),
    )
    for row in rows:
        filter_snapshot = _json_loads(row.get("filter_snapshot_json"), default={})
        if _normalized_text(filter_snapshot.get("selection_mode")) != "automation_conversion_stage":
            continue
        if _normalized_text(filter_snapshot.get("stage_key")) not in rule_keys:
            continue
        task_results = _json_loads(row.get("task_results_json"), default=[])
        if not isinstance(task_results, list):
            continue
        for item in task_results:
            if not isinstance(item, dict) or _normalized_text(item.get("status")) == "failed":
                continue
            external_userids = item.get("external_userids")
            if not isinstance(external_userids, list):
                continue
            if normalized_external_contact_id in {_normalized_text(value) for value in external_userids}:
                return True
    return False


def claim_touch_delivery_once(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_external_contact_id = _normalized_text(payload.get("external_contact_id"))
    if not normalized_external_contact_id:
        return {"_did_claim": False}
    row = get_db().execute(
        """
        INSERT INTO automation_touch_delivery_log (
            program_code,
            touch_surface,
            rule_key,
            member_id,
            external_contact_id,
            source_batch_id,
            source_item_id,
            send_record_id,
            status,
            detail,
            metadata_json,
            claimed_at,
            sent_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, '', ?, ?)
        ON CONFLICT DO NOTHING
        RETURNING *
        """,
        (
            _normalized_text(payload.get("program_code")) or "signup_conversion_v1",
            _normalized_text(payload.get("touch_surface")),
            _normalized_text(payload.get("rule_key")),
            payload.get("member_id"),
            normalized_external_contact_id,
            payload.get("source_batch_id"),
            payload.get("source_item_id"),
            payload.get("send_record_id"),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("metadata") or {}),
            _normalized_text(payload.get("claimed_at")),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
        ),
    ).fetchone()
    if row:
        return {**dict(row), "_did_claim": True}
    existing = get_active_touch_delivery(
        program_code=_normalized_text(payload.get("program_code")) or "signup_conversion_v1",
        touch_surface=_normalized_text(payload.get("touch_surface")),
        rule_key=_normalized_text(payload.get("rule_key")),
        external_contact_id=normalized_external_contact_id,
    )
    return {**dict(existing or {}), "_did_claim": False}


def update_touch_delivery_log_status(
    delivery_id: int,
    *,
    status: str,
    send_record_id: int | None = None,
    source_batch_id: int | None = None,
    source_item_id: int | None = None,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    sent_at: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        UPDATE automation_touch_delivery_log
        SET status = ?,
            send_record_id = COALESCE(?, send_record_id),
            source_batch_id = COALESCE(?, source_batch_id),
            source_item_id = COALESCE(?, source_item_id),
            detail = ?,
            metadata_json = ?,
            sent_at = ?,
            updated_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(status),
            send_record_id,
            source_batch_id,
            source_item_id,
            _normalized_text(detail),
            _json_dumps(metadata or {}),
            _normalized_text(sent_at),
            _normalized_text(updated_at),
            int(delivery_id),
        ),
    ).fetchone()
    return dict(row) if row else None


def update_touch_delivery_log_status_by_source(
    *,
    touch_surface: str,
    source_batch_id: int,
    source_item_id: int,
    external_contact_id: str,
    status: str,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    sent_at: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        UPDATE automation_touch_delivery_log
        SET status = ?,
            detail = ?,
            metadata_json = ?,
            sent_at = ?,
            updated_at = ?
        WHERE id = (
            SELECT id
            FROM automation_touch_delivery_log
            WHERE touch_surface = ?
              AND source_batch_id = ?
              AND source_item_id = ?
              AND external_contact_id = ?
            ORDER BY id DESC
            LIMIT 1
        )
        RETURNING *
        """,
        (
            _normalized_text(status),
            _normalized_text(detail),
            _json_dumps(metadata or {}),
            _normalized_text(sent_at),
            _normalized_text(updated_at),
            _normalized_text(touch_surface),
            int(source_batch_id),
            int(source_item_id),
            _normalized_text(external_contact_id),
        ),
    ).fetchone()
    return dict(row) if row else None


def list_recent_debug_events(*, external_contact_id: str = "", phone: str = "", limit: int = 10) -> list[dict[str, Any]]:
    member = get_member_by_external_contact_id(external_contact_id) or get_member_by_phone(phone)
    if not member:
        return []
    return list_recent_events(int(member["id"]), limit=int(limit))


def deserialize_event_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "before_snapshot": _json_loads(row.get("before_snapshot"), default={}),
        "after_snapshot": _json_loads(row.get("after_snapshot"), default={}),
    }


def deserialize_ai_push_log_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "request_payload": _json_loads(row.get("request_payload"), default={}),
    }




__all__ = [
    "claim_touch_delivery_once",
    "deserialize_ai_push_log_row",
    "deserialize_event_row",
    "get_active_touch_delivery",
    "get_latest_manual_event",
    "has_historical_stage_manual_send_delivery",
    "insert_ai_push_log",
    "insert_event",
    "list_recent_debug_events",
    "list_recent_events",
    "update_touch_delivery_log_status",
    "update_touch_delivery_log_status_by_source",
]
