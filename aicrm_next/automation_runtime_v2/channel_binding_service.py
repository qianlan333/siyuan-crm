from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from aicrm_next.shared.postgres_connection import db_session, get_db

from . import process_event_payload
from .domain import AutomationEventInput, EVENT_CHANNEL_ENTERED, as_int, text


DEFAULT_INITIAL_STAGE = "pending_questionnaire"
ACTIVE_STAGES = {"pending_questionnaire", "operating", "converted"}


def _json_text(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = text(value).lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _as_int_list(values: list[Any]) -> list[int]:
    result: list[int] = []
    for item in values:
        value = as_int(item)
        if value > 0 and value not in result:
            result.append(value)
    return result


def _program_exists(program_id: int) -> bool:
    row = get_db().execute("SELECT id FROM automation_program WHERE id = ? LIMIT 1", (int(program_id),)).fetchone()
    return bool(row)


def _channel_exists(channel_id: int) -> bool:
    row = get_db().execute("SELECT id FROM automation_channel WHERE id = ? LIMIT 1", (int(channel_id),)).fetchone()
    return bool(row)


def _active_conflict(program_id: int, channel_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT id, program_id, channel_id
        FROM automation_program_channel_binding
        WHERE channel_id = ?
          AND program_id <> ?
          AND binding_status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(channel_id), int(program_id)),
    ).fetchone()
    return dict(row) if row else None


def _contact_count(channel_ids: list[int]) -> int:
    if not channel_ids:
        return 0
    rows = get_db().execute(
        """
        SELECT COUNT(*) AS count
        FROM automation_channel_contact
        WHERE channel_id = ANY(CAST(? AS bigint[]))
        """,
        ([int(item) for item in channel_ids],),
    ).fetchone()
    return as_int((rows or {}).get("count"))


def _upsert_binding(
    *,
    program_id: int,
    channel_id: int,
    binding_status: str,
    auto_enter_pool: bool,
    initial_audience_code: str,
    entry_rule_json: dict[str, Any],
    priority: int,
    operator_id: str,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_program_channel_binding (
            program_id, channel_id, binding_status, auto_enter_pool, initial_audience_code,
            entry_rule_json, priority, bound_by, bound_at, unbound_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?, CURRENT_TIMESTAMP, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (program_id, channel_id) DO UPDATE
        SET binding_status = EXCLUDED.binding_status,
            auto_enter_pool = EXCLUDED.auto_enter_pool,
            initial_audience_code = EXCLUDED.initial_audience_code,
            entry_rule_json = EXCLUDED.entry_rule_json,
            priority = EXCLUDED.priority,
            bound_by = EXCLUDED.bound_by,
            bound_at = CASE
                WHEN automation_program_channel_binding.binding_status <> 'active'
                  OR EXCLUDED.binding_status = 'active'
                THEN CURRENT_TIMESTAMP
                ELSE automation_program_channel_binding.bound_at
            END,
            unbound_at = CASE WHEN EXCLUDED.binding_status = 'active' THEN NULL ELSE automation_program_channel_binding.unbound_at END,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        (
            int(program_id),
            int(channel_id),
            text(binding_status) or "active",
            bool(auto_enter_pool),
            text(initial_audience_code) or DEFAULT_INITIAL_STAGE,
            _json_text(entry_rule_json or {}),
            int(priority),
            text(operator_id) or "next_admin",
        ),
    ).fetchone()
    return dict(row or {})


def _contacts(channel_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT id, channel_id, external_contact_id, first_channel_entered_at, last_channel_entered_at, source_payload_json
        FROM automation_channel_contact
        WHERE channel_id = ?
          AND COALESCE(external_contact_id, '') <> ''
        ORDER BY id ASC
        """,
        (int(channel_id),),
    ).fetchall()
    return [dict(row) for row in rows or []]


def _event_exists(source_type: str, source_id: str) -> bool:
    row = get_db().execute(
        "SELECT id FROM automation_event_v2 WHERE source_type = ? AND source_id = ? LIMIT 1",
        (text(source_type), text(source_id)),
    ).fetchone()
    return bool(row)


def _import_contacts_for_binding(
    *,
    program_id: int,
    binding: dict[str, Any],
    channel_id: int,
    operator_id: str,
    batch_size: int,
) -> dict[str, Any]:
    imported = 0
    skipped = 0
    failed = 0
    generated_events = 0
    generated_memberships = 0
    generated_stage_entries = 0
    generated_task_plans = 0
    generated_broadcast_jobs = 0
    processed: list[dict[str, Any]] = []
    bound_at = binding.get("bound_at") or datetime.now(timezone.utc)
    binding_id = as_int(binding.get("id"))
    for contact in _contacts(channel_id):
        contact_id = as_int(contact.get("id"))
        external = text(contact.get("external_contact_id"))
        if not contact_id or not external:
            continue
        source_id = f"{int(program_id)}:{binding_id}:{contact_id}"
        idempotency_key = f"binding_import:{int(program_id)}:{binding_id}:{contact_id}"
        if _event_exists("binding_import", source_id):
            skipped += 1
            continue
        try:
            before_membership = get_db().execute(
                """
                SELECT id FROM automation_membership_v2
                WHERE program_id = ? AND external_userid = ?
                LIMIT 1
                """,
                (int(program_id), external),
            ).fetchone()
            result = process_event_payload(
                AutomationEventInput(
                    event_type=EVENT_CHANNEL_ENTERED,
                    source_type="binding_import",
                    source_id=source_id,
                    idempotency_key=idempotency_key,
                    program_id=int(program_id),
                    channel_id=int(channel_id),
                    binding_id=binding_id,
                    external_userid=external,
                    occurred_at=bound_at,
                    raw_occurred_at=contact.get("first_channel_entered_at"),
                    payload_json={
                        "source": "channel_binding_import",
                        "operator_id": text(operator_id),
                        "channel_contact_id": contact_id,
                    },
                )
            )
            imported += 1
            generated_events += 1
            if not before_membership and result.get("membership"):
                generated_memberships += 1
            if result.get("stage_entry"):
                generated_stage_entries += 1
            counts = result.get("counts") or {}
            generated_task_plans += as_int(counts.get("planned"))
            generated_broadcast_jobs += as_int(counts.get("enqueued"))
            processed.append({"contact_id": contact_id, "event_id": result.get("event_id")})
            if int(batch_size or 0) > 0 and imported % int(batch_size) == 0:
                get_db().commit()
        except Exception as exc:
            failed += 1
            processed.append({"contact_id": contact_id, "error": str(exc)})
            try:
                get_db().rollback()
            except Exception:
                pass
    return {
        "imported_contact_count": imported,
        "skipped_existing_count": skipped,
        "failed_count": failed,
        "generated_event_count": generated_events,
        "generated_membership_count": generated_memberships,
        "generated_stage_entry_count": generated_stage_entries,
        "generated_task_plan_count": generated_task_plans,
        "generated_broadcast_job_count": generated_broadcast_jobs,
        "runtime_v2_summary": {
            "binding_id": binding_id,
            "channel_id": int(channel_id),
            "processed_count": imported + skipped + failed,
            "processed_samples": processed[:10],
        },
    }


def bind_channels_to_program(
    program_id: int,
    channel_ids: list[int],
    payload: dict[str, Any] | None = None,
    *,
    operator_id: str = "next_admin",
) -> dict[str, Any]:
    payload = dict(payload or {})
    normalized_ids = _as_int_list(channel_ids)
    if not normalized_ids:
        raise ValueError("channel_ids_required")
    binding_status = text(payload.get("binding_status")) or "active"
    auto_enter_pool = _bool(payload.get("auto_enter_pool"), default=True)
    initial_audience_code = text(payload.get("initial_audience_code")) or DEFAULT_INITIAL_STAGE
    if initial_audience_code not in ACTIVE_STAGES:
        raise ValueError("invalid_initial_audience_code")
    priority = as_int(payload.get("priority"))
    batch_size = max(1, as_int(payload.get("batch_size"), 100))
    max_import_count = as_int(payload.get("max_import_count"), 1000)
    confirm_large_import = _bool(payload.get("confirm_large_import"), default=False)
    entry_rule_json = payload.get("entry_rule_json") if isinstance(payload.get("entry_rule_json"), dict) else {}
    with db_session():
        if not _program_exists(int(program_id)):
            raise LookupError("program_not_found")
        for channel_id in normalized_ids:
            if not _channel_exists(channel_id):
                raise LookupError("channel_not_found")
            conflict = _active_conflict(int(program_id), channel_id)
            if conflict and binding_status == "active":
                raise ValueError("channel_already_bound")
        total_contacts = _contact_count(normalized_ids)
        if binding_status == "active" and auto_enter_pool and max_import_count > 0 and total_contacts > max_import_count and not confirm_large_import:
            return {
                "bindings": [],
                "reason": "requires_batch_import",
                "history_imported": False,
                "history_import_reason": "contact_count_exceeds_max_import_count",
                "requires_batch_import": True,
                "total_contact_count": total_contacts,
                "max_import_count": max_import_count,
                "import_continue_token": f"channel_binding:{int(program_id)}:{','.join(str(item) for item in normalized_ids)}:{total_contacts}",
                "imported_contact_count": 0,
                "skipped_existing_count": 0,
                "failed_count": 0,
                "generated_event_count": 0,
                "generated_membership_count": 0,
                "generated_stage_entry_count": 0,
                "generated_task_plan_count": 0,
                "generated_broadcast_job_count": 0,
                "runtime_v2_summary": {"blocked": True, "total_contact_count": total_contacts},
            }
        bindings: list[dict[str, Any]] = []
        aggregate = {
            "imported_contact_count": 0,
            "skipped_existing_count": 0,
            "failed_count": 0,
            "generated_event_count": 0,
            "generated_membership_count": 0,
            "generated_stage_entry_count": 0,
            "generated_task_plan_count": 0,
            "generated_broadcast_job_count": 0,
        }
        summaries: list[dict[str, Any]] = []
        for channel_id in normalized_ids:
            binding = _upsert_binding(
                program_id=int(program_id),
                channel_id=channel_id,
                binding_status=binding_status,
                auto_enter_pool=auto_enter_pool,
                initial_audience_code=initial_audience_code,
                entry_rule_json=entry_rule_json,
                priority=priority,
                operator_id=operator_id,
            )
            bindings.append(binding)
            if binding_status == "active" and auto_enter_pool:
                imported = _import_contacts_for_binding(
                    program_id=int(program_id),
                    binding=binding,
                    channel_id=channel_id,
                    operator_id=operator_id,
                    batch_size=batch_size,
                )
                for key in aggregate:
                    aggregate[key] += as_int(imported.get(key))
                summaries.append(dict(imported.get("runtime_v2_summary") or {}))
        get_db().commit()
        return {
            "bindings": bindings,
            "reason": "program_channels_bound",
            "history_imported": binding_status == "active" and auto_enter_pool,
            "history_import_reason": "binding_import_completed" if binding_status == "active" and auto_enter_pool else "auto_enter_pool_disabled",
            "requires_batch_import": False,
            "total_contact_count": total_contacts,
            "max_import_count": max_import_count,
            "import_continue_token": "",
            **aggregate,
            "runtime_v2_summary": {
                "program_id": int(program_id),
                "binding_count": len(bindings),
                "bindings": summaries,
            },
        }
