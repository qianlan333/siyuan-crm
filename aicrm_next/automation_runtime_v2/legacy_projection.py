from __future__ import annotations

import json
from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import STAGE_CONVERTED, STAGE_OPERATING, STAGE_PENDING_QUESTIONNAIRE, as_int, text


def _audience(stage: str) -> str:
    normalized = text(stage)
    if normalized == STAGE_CONVERTED:
        return STAGE_CONVERTED
    if normalized == STAGE_OPERATING:
        return STAGE_OPERATING
    return STAGE_PENDING_QUESTIONNAIRE


def project_membership(*, event: dict[str, Any], membership: dict[str, Any], stage_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    external = text(membership.get("external_userid"))
    if not external:
        return {"ok": False, "reason": "external_userid_missing"}
    stage = _audience(text(membership.get("current_stage")))
    event_type = text(event.get("event_type"))
    questionnaire_status = "submitted" if event_type == "questionnaire_submitted" or stage in {STAGE_OPERATING, STAGE_CONVERTED} else "pending"
    entered_at = (stage_entry or {}).get("entered_at") or event.get("occurred_at")
    row = get_db().execute(
        """
        INSERT INTO automation_member (
            external_contact_id, phone, master_customer_id, in_pool, current_pool, questionnaire_status,
            decision_source, source_type, source_channel_id, current_audience_code,
            current_audience_entered_at, joined_at, created_at, updated_at
        )
        VALUES (?, ?, ?, TRUE, ?, ?, 'automation_runtime_v2', 'automation_runtime_v2', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (external_contact_id) WHERE external_contact_id <> '' DO UPDATE
        SET phone = COALESCE(NULLIF(EXCLUDED.phone, ''), automation_member.phone),
            in_pool = TRUE,
            current_pool = EXCLUDED.current_pool,
            questionnaire_status = EXCLUDED.questionnaire_status,
            source_channel_id = COALESCE(EXCLUDED.source_channel_id, automation_member.source_channel_id),
            current_audience_code = EXCLUDED.current_audience_code,
            current_audience_entered_at = EXCLUDED.current_audience_entered_at,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            external,
            text(membership.get("phone")),
            as_int(membership.get("person_id")) or None,
            stage,
            questionnaire_status,
            as_int(membership.get("source_channel_id")) or None,
            stage,
            text(entered_at),
            text(membership.get("joined_at") or event.get("occurred_at")),
        ),
    ).fetchone()
    legacy_member = dict(row or {})
    program_member = get_db().execute(
        """
        INSERT INTO automation_program_member (
            program_id, external_contact_id, master_customer_id, source_channel_id, source_binding_id,
            first_source_channel_id, latest_source_channel_id, in_program, current_stage_code,
            current_audience_code, current_stage_entered_at, pool_entered_at, state_payload_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, ?, ?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (program_id, external_contact_id) WHERE external_contact_id <> '' DO UPDATE
        SET source_channel_id = COALESCE(EXCLUDED.source_channel_id, automation_program_member.source_channel_id),
            source_binding_id = COALESCE(EXCLUDED.source_binding_id, automation_program_member.source_binding_id),
            latest_source_channel_id = COALESCE(EXCLUDED.latest_source_channel_id, automation_program_member.latest_source_channel_id),
            in_program = TRUE,
            current_stage_code = EXCLUDED.current_stage_code,
            current_audience_code = EXCLUDED.current_audience_code,
            current_stage_entered_at = EXCLUDED.current_stage_entered_at,
            state_payload_json = EXCLUDED.state_payload_json,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            as_int(membership.get("program_id")),
            external,
            as_int(membership.get("person_id")) or None,
            as_int(membership.get("source_channel_id")) or None,
            as_int(membership.get("source_binding_id")) or None,
            as_int(membership.get("source_channel_id")) or None,
            as_int(membership.get("source_channel_id")) or None,
            stage,
            stage,
            entered_at,
            membership.get("joined_at") or event.get("occurred_at"),
            json.dumps({"runtime_version": "v2", "membership_id": as_int(membership.get("id"))}, ensure_ascii=False),
        ),
    ).fetchone()
    audience_entry_id = 0
    if stage_entry:
        get_db().execute(
            """
            UPDATE automation_member_audience_entry
            SET is_current = FALSE, exited_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE member_id = ? AND is_current = TRUE
            """,
            (text(stage_entry.get("entered_at")), as_int(legacy_member.get("id"))),
        )
        entry = get_db().execute(
            """
            INSERT INTO automation_member_audience_entry (
                member_id, audience_code, entered_at, is_current, entry_source, entry_reason,
                source_snapshot_json, created_at, updated_at
            )
            VALUES (?, ?, ?, TRUE, 'automation_runtime_v2', ?, CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                as_int(legacy_member.get("id")),
                stage,
                text(stage_entry.get("entered_at")),
                "audience_entry_rule_passed" if text(stage_entry.get("entry_reason")) == "questionnaire_submitted" else text(stage_entry.get("entry_reason")),
                json.dumps({"runtime_version": "v2", "stage_entry_id": as_int(stage_entry.get("id"))}, ensure_ascii=False),
            ),
        ).fetchone()
        audience_entry_id = as_int((entry or {}).get("id"))
    return {"ok": True, "legacy_member_id": as_int(legacy_member.get("id")), "program_member_id": as_int((program_member or {}).get("id")), "audience_entry_id": audience_entry_id}
