from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any

from aicrm_next.shared.postgres_connection import db_session, get_db

from .domain import EVENT_WEBHOOK_RECEIVED, TRIGGER_ON_ENTER_STAGE, TRIGGER_ON_EVENT, TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH, as_int, text
from .membership_service import get_stage_entry, list_active_memberships
from .task_adapter import list_active_tasks


def _row(row: Any) -> dict[str, Any]:
    item = dict(row or {})
    for key in ("diagnostics_json", "rendered_content_json"):
        value = item.get(key)
        if isinstance(value, str):
            try:
                item[key] = json.loads(value)
            except (TypeError, ValueError):
                item[key] = {}
        elif value is None:
            item[key] = {}
    return item


def _insert_plan(
    *,
    task: dict[str, Any],
    membership_id: int,
    event_id: int | None,
    stage_entry_id: int | None,
    schedule_key: str = "",
    trigger_type: str,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        INSERT INTO automation_task_plan_v2 (
            program_id, task_id, membership_id, event_id, stage_entry_id, schedule_key,
            trigger_type, status, diagnostics_json, rendered_content_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', CAST(? AS jsonb), '{}'::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
        RETURNING *
        """,
        (
            int(task["program_id"]),
            int(task["id"]),
            int(membership_id),
            event_id,
            stage_entry_id,
            text(schedule_key),
            text(trigger_type),
            json.dumps(diagnostics or {}, ensure_ascii=False),
        ),
    ).fetchone()
    return _row(row) if row else None


def get_plan(plan_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM automation_task_plan_v2 WHERE id = ? LIMIT 1", (int(plan_id),)).fetchone()
    return _row(row) if row else None


def update_plan_status(plan_id: int, status: str, *, skip_reason: str = "", diagnostics: dict[str, Any] | None = None, rendered: dict[str, Any] | None = None, broadcast_job_id: int | None = None) -> dict[str, Any]:
    current = get_plan(int(plan_id)) or {}
    merged_diag = dict(current.get("diagnostics_json") or {})
    merged_diag.update(diagnostics or {})
    rendered_payload = rendered if rendered is not None else current.get("rendered_content_json") or {}
    row = get_db().execute(
        """
        UPDATE automation_task_plan_v2
        SET status = ?, skip_reason = ?, diagnostics_json = CAST(? AS jsonb),
            rendered_content_json = CAST(? AS jsonb),
            broadcast_job_id = COALESCE(?, broadcast_job_id),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            text(status),
            text(skip_reason),
            json.dumps(merged_diag, ensure_ascii=False, default=str),
            json.dumps(rendered_payload or {}, ensure_ascii=False, default=str),
            broadcast_job_id,
            int(plan_id),
        ),
    ).fetchone()
    return _row(row) if row else {}


def plan_for_event(event: dict[str, Any], membership: dict[str, Any], stage_entry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    program_id = as_int(event.get("program_id")) or as_int(membership.get("program_id"))
    plans: list[dict[str, Any]] = []
    if program_id <= 0:
        return plans
    event_type = text(event.get("event_type"))
    payload = event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {}
    for task in list_active_tasks(program_id):
        rv2 = task.get("runtime_v2") or {}
        trigger = text(rv2.get("trigger_type"))
        if trigger == TRIGGER_ON_EVENT and text(rv2.get("trigger_event_type") or event_type) == event_type:
            plan = _insert_plan(task=task, membership_id=int(membership["id"]), event_id=int(event["id"]), stage_entry_id=None, trigger_type=TRIGGER_ON_EVENT)
            if plan:
                plan["task"] = task
                plans.append(plan)
        if trigger == TRIGGER_ON_ENTER_STAGE and stage_entry and text(rv2.get("target_stage")) == text(stage_entry.get("stage_code")):
            plan = _insert_plan(task=task, membership_id=int(membership["id"]), event_id=None, stage_entry_id=int(stage_entry["id"]), trigger_type=TRIGGER_ON_ENTER_STAGE)
            if plan:
                plan["task"] = task
                plans.append(plan)
        if event_type == EVENT_WEBHOOK_RECEIVED and trigger == TRIGGER_WEBHOOK_PUSH:
            webhook_key = text(rv2.get("webhook_key"))
            event_key = text(payload.get("webhook_key"))
            if not webhook_key or webhook_key == event_key:
                plan = _insert_plan(task=task, membership_id=int(membership["id"]), event_id=int(event["id"]), stage_entry_id=None, trigger_type=TRIGGER_WEBHOOK_PUSH)
                if plan:
                    plan["task"] = task
                    plans.append(plan)
    return plans


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _daily_time_due(send_time: str, now: datetime) -> bool:
    raw = text(send_time) or "10:00"
    try:
        hour, minute = raw.split(":", 1)
        due = time(hour=int(hour), minute=int(minute[:2]))
    except (TypeError, ValueError):
        due = time(hour=10, minute=0)
    return now.time() >= due


def _stage_day_offset_due(membership: dict[str, Any], day_offset: int, now: datetime) -> bool:
    entry_id = as_int(membership.get("current_stage_entry_id"))
    if entry_id <= 0:
        return False
    entry = get_stage_entry(entry_id) or {}
    entered_at = _as_datetime(entry.get("entered_at"))
    if not entered_at:
        return False
    due_days = max(0, int(day_offset) - 1)
    return (now.date() - entered_at.date()).days >= due_days


def run_due_scheduled_tasks(program_id: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    with db_session():
        return _run_due_scheduled_tasks(program_id=program_id, now=now)


def _run_due_scheduled_tasks(program_id: int | None = None, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now()
    try:
        program_ids: list[int]
        if int(program_id or 0) > 0:
            program_ids = [int(program_id or 0)]
        else:
            rows = get_db().execute("SELECT DISTINCT program_id FROM automation_operation_task WHERE status = 'active'").fetchall()
            program_ids = [int(row.get("program_id") or 0) for row in rows]
        created: list[dict[str, Any]] = []
        rendered_count = 0
        enqueued_count = 0
        failed_count = 0
        for pid in program_ids:
            for task in list_active_tasks(pid):
                rv2 = task.get("runtime_v2") or {}
                if text(rv2.get("trigger_type")) != TRIGGER_SCHEDULED:
                    continue
                schedule_type = text(rv2.get("schedule_type")) or "daily_time"
                target_stage = text(rv2.get("target_stage")) or "operating"
                if schedule_type == "daily_time" and not _daily_time_due(text(rv2.get("send_time")), current):
                    continue
                for membership in list_active_memberships(pid, target_stage):
                    if schedule_type == "stage_day_offset":
                        day_offset = max(1, as_int(rv2.get("day_offset"), 1))
                        if not _stage_day_offset_due(membership, day_offset, current):
                            continue
                        entry_id = as_int(membership.get("current_stage_entry_id"))
                        schedule_key = f"stage_day_offset:{current.date().isoformat()}:d{day_offset}:entry:{entry_id}"
                    else:
                        schedule_key = f"daily_time:{current.date().isoformat()}:{text(rv2.get('send_time')) or '10:00'}"
                    plan = _insert_plan(task=task, membership_id=int(membership["id"]), event_id=None, stage_entry_id=as_int(membership.get("current_stage_entry_id")) or None, schedule_key=schedule_key, trigger_type=TRIGGER_SCHEDULED)
                    if plan:
                        plan["task"] = task
                        plan["membership"] = membership
                        from .content_renderer import render
                        from .outbox import enqueue

                        rendered = render(int(plan["id"]))
                        if text(rendered.get("status")) == "rendered":
                            rendered_count += 1
                            enqueued = enqueue(int(plan["id"]))
                            final_plan = dict(enqueued.get("plan") or rendered)
                            if text(final_plan.get("status")) == "enqueued":
                                enqueued_count += 1
                        else:
                            final_plan = dict(rendered)
                            failed_count += 1
                        plan.update(final_plan)
                        created.append(plan)
        result = {"ok": True, "plans": created, "counts": {"planned": len(created), "rendered": rendered_count, "enqueued": enqueued_count, "failed": failed_count}}
        get_db().commit()
        return result
    except Exception:
        get_db().rollback()
        raise
