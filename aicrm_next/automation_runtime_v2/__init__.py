from __future__ import annotations

from typing import Any

from aicrm_next.shared.postgres_connection import db_session, get_db

from .content_renderer import render
from .domain import AutomationEventInput, as_int, text
from .event_store import get_event, insert_event, mark_ignored, update_event_status
from .legacy_projection import project_membership
from .membership_service import ensure_membership_for_event, create_stage_entry
from .outbox import enqueue
from .runtime_check import check_task_runtime
from .stage_machine import resolve_next_stage
from .task_planner import plan_for_event, run_due_scheduled_tasks
from .replay_service import replay_channel_binding, replay_event, replay_membership


def _counts(plans: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "planned": len(plans),
        "rendered": sum(1 for p in plans if text(p.get("status")) in {"rendered", "enqueued"}),
        "enqueued": sum(1 for p in plans if as_int(p.get("broadcast_job_id")) > 0 or text(p.get("status")) == "enqueued"),
        "skipped": sum(1 for p in plans if text(p.get("status")) == "skipped"),
        "failed": sum(1 for p in plans if text(p.get("status")) == "failed"),
    }


def process_event(event_id: int) -> dict[str, Any]:
    event = get_event(int(event_id))
    if not event:
        raise LookupError("event_not_found")
    plans_out: list[dict[str, Any]] = []
    try:
        membership = ensure_membership_for_event(event)
        if not membership:
            mark_ignored(int(event_id), "no_active_binding" if text(event.get("event_type")) == "channel_entered" else "membership_unresolved")
            get_db().commit()
            return {"event_id": int(event_id), "membership": None, "stage_entry": None, "plans": [], "counts": _counts([]), "status": "ignored", "reason": "membership_unresolved"}
        if as_int(event.get("program_id")) <= 0:
            get_db().execute("UPDATE automation_event_v2 SET program_id = ?, channel_id = COALESCE(channel_id, ?), binding_id = COALESCE(binding_id, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?", (as_int(membership.get("program_id")), as_int(membership.get("source_channel_id")) or None, as_int(membership.get("source_binding_id")) or None, int(event_id)))
            event = get_event(int(event_id)) or event
        transition = resolve_next_stage(event, membership, {})
        stage_entry = create_stage_entry(
            membership=membership,
            event=event,
            stage_code=transition.target_stage,
            entry_reason=transition.entry_reason,
            snapshot={"transition": transition.diagnostics},
        ) if transition.changed else None
        if stage_entry:
            membership = dict(stage_entry.get("membership") or membership)
        plans = plan_for_event(event, membership, stage_entry)
        for plan in plans:
            rendered = render(int(plan["id"]), event=event)
            if text(rendered.get("status")) == "rendered":
                enqueued = enqueue(int(plan["id"]))
                final_plan = dict((enqueued.get("plan") or rendered))
            else:
                final_plan = dict(rendered)
            plans_out.append(
                {
                    "task_id": as_int(final_plan.get("task_id")),
                    "plan_id": as_int(final_plan.get("id")),
                    "status": text(final_plan.get("status")),
                    "broadcast_job_id": as_int(final_plan.get("broadcast_job_id")) or None,
                    "diagnostics": final_plan.get("diagnostics_json") or {},
                }
            )
        projection = project_membership(event=event, membership=membership, stage_entry=stage_entry)
        update_event_status(int(event_id), "processed")
        get_db().commit()
        return {
            "event_id": int(event_id),
            "membership": membership,
            "stage_entry": stage_entry,
            "plans": plans_out,
            "counts": _counts(plans_out),
            "legacy_projection": projection,
        }
    except Exception as exc:
        try:
            update_event_status(int(event_id), "failed", str(exc))
            get_db().commit()
        except Exception:
            try:
                get_db().rollback()
            except Exception:
                pass
        raise


def process_event_payload(payload: AutomationEventInput | dict[str, Any]) -> dict[str, Any]:
    with db_session():
        event = insert_event(payload)
        return process_event(int(event["id"]))


__all__ = [
    "AutomationEventInput",
    "check_task_runtime",
    "process_event",
    "process_event_payload",
    "replay_channel_binding",
    "replay_event",
    "replay_membership",
    "run_due_scheduled_tasks",
]
