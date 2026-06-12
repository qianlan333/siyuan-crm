from __future__ import annotations

import json
from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import STAGE_PENDING_QUESTIONNAIRE, as_int, text


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if value is not None else {}


def _row(row: Any) -> dict[str, Any]:
    return dict(row or {})


def find_program_for_event(event: dict[str, Any]) -> dict[str, Any]:
    program_id = as_int(event.get("program_id"))
    external_userid = text(event.get("external_userid"))
    channel_id = as_int(event.get("channel_id"))
    if program_id > 0:
        return {"program_id": program_id, "channel_id": channel_id or None, "binding_id": as_int(event.get("binding_id")) or None}
    if external_userid:
        row = get_db().execute(
            """
            SELECT program_id, source_channel_id AS channel_id, source_binding_id AS binding_id
            FROM automation_membership_v2
            WHERE external_userid = ? AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()
        if row:
            return dict(row)
    if channel_id > 0:
        row = get_db().execute(
            """
            SELECT id AS binding_id, program_id, channel_id
            FROM automation_program_channel_binding
            WHERE channel_id = ? AND binding_status = 'active' AND auto_enter_pool = TRUE
            ORDER BY priority DESC, bound_at DESC, id DESC
            LIMIT 1
            """,
            (channel_id,),
        ).fetchone()
        if row:
            return dict(row)
    if external_userid:
        row = get_db().execute(
            """
            SELECT b.id AS binding_id, b.program_id, cc.channel_id
            FROM automation_channel_contact cc
            INNER JOIN automation_program_channel_binding b ON b.channel_id = cc.channel_id
            WHERE cc.external_contact_id = ?
              AND b.binding_status = 'active'
              AND b.auto_enter_pool = TRUE
            ORDER BY b.priority DESC, b.bound_at DESC, b.id DESC
            LIMIT 1
            """,
            (external_userid,),
        ).fetchone()
        if row:
            return dict(row)
    return {"program_id": 0, "channel_id": channel_id or None, "binding_id": as_int(event.get("binding_id")) or None}


def get_membership(membership_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM automation_membership_v2 WHERE id = ? LIMIT 1", (int(membership_id),)).fetchone()
    return _row(row) if row else None


def get_membership_by_program_external(program_id: int, external_userid: str) -> dict[str, Any] | None:
    row = get_db().execute(
        "SELECT * FROM automation_membership_v2 WHERE program_id = ? AND external_userid = ? LIMIT 1",
        (int(program_id), text(external_userid)),
    ).fetchone()
    return _row(row) if row else None


def ensure_membership_for_event(event: dict[str, Any]) -> dict[str, Any] | None:
    resolved = find_program_for_event(event)
    program_id = as_int(resolved.get("program_id"))
    external_userid = text(event.get("external_userid"))
    if program_id <= 0 or not external_userid:
        return None
    row = get_db().execute(
        """
        INSERT INTO automation_membership_v2 (
            program_id, external_userid, phone, person_id, source_channel_id, source_binding_id,
            status, current_stage, joined_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (program_id, external_userid) DO UPDATE
        SET phone = COALESCE(NULLIF(EXCLUDED.phone, ''), automation_membership_v2.phone),
            person_id = COALESCE(EXCLUDED.person_id, automation_membership_v2.person_id),
            source_channel_id = COALESCE(EXCLUDED.source_channel_id, automation_membership_v2.source_channel_id),
            source_binding_id = COALESCE(EXCLUDED.source_binding_id, automation_membership_v2.source_binding_id),
            status = 'active',
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            program_id,
            external_userid,
            text(event.get("phone")),
            as_int(event.get("person_id")) or None,
            as_int(event.get("channel_id")) or as_int(resolved.get("channel_id")) or None,
            as_int(event.get("binding_id")) or as_int(resolved.get("binding_id")) or None,
            STAGE_PENDING_QUESTIONNAIRE,
            event.get("occurred_at"),
        ),
    ).fetchone()
    return _row(row)


def create_stage_entry(
    *,
    membership: dict[str, Any],
    event: dict[str, Any],
    stage_code: str,
    entry_reason: str,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if text(membership.get("current_stage")) == text(stage_code) and as_int(membership.get("current_stage_entry_id")) > 0:
        return None
    row = get_db().execute(
        """
        INSERT INTO automation_stage_entry_v2 (
            membership_id, program_id, stage_code, entered_at, source_event_id, entry_reason, snapshot_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP)
        ON CONFLICT (membership_id, stage_code, source_event_id) DO NOTHING
        RETURNING *
        """,
        (
            int(membership["id"]),
            int(membership["program_id"]),
            text(stage_code),
            event.get("occurred_at"),
            int(event["id"]),
            text(entry_reason),
            json.dumps(snapshot or {}, ensure_ascii=False),
        ),
    ).fetchone()
    if not row:
        return None
    entry = dict(row)
    get_db().execute(
        """
        UPDATE automation_membership_v2
        SET current_stage = ?, current_stage_entry_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (text(stage_code), int(entry["id"]), int(membership["id"])),
    )
    updated = get_membership(int(membership["id"])) or membership
    entry["membership"] = updated
    return entry


def list_active_memberships(program_id: int, stage_code: str = "") -> list[dict[str, Any]]:
    params: list[Any] = [int(program_id)]
    where = "WHERE program_id = ? AND status = 'active'"
    if text(stage_code):
        where += " AND current_stage = ?"
        params.append(text(stage_code))
    rows = get_db().execute(f"SELECT * FROM automation_membership_v2 {where} ORDER BY id ASC", tuple(params)).fetchall()
    return [dict(row) for row in rows]


def get_stage_entry(stage_entry_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM automation_stage_entry_v2 WHERE id = ? LIMIT 1", (int(stage_entry_id),)).fetchone()
    item = dict(row or {}) if row else None
    if item:
        item["snapshot_json"] = _json(item.get("snapshot_json"))
    return item
