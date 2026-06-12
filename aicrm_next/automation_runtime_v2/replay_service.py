from __future__ import annotations

from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .event_store import get_event
from .task_planner import get_plan


def replay_event(event_id: int, dry_run: bool = True) -> dict[str, Any]:
    event = get_event(int(event_id))
    if not event:
        raise LookupError("event_not_found")
    if dry_run:
        return {"ok": True, "dry_run": True, "event_id": int(event_id), "would_process": True}
    from . import process_event

    return process_event(int(event_id))


def replay_membership(membership_id: int, task_ids: list[int] | None = None, dry_run: bool = True) -> dict[str, Any]:
    ids = [int(item) for item in list(task_ids or []) if int(item or 0) > 0]
    if dry_run:
        return {"ok": True, "dry_run": True, "membership_id": int(membership_id), "task_ids": ids, "would_replay": len(ids)}
    return {"ok": True, "dry_run": False, "membership_id": int(membership_id), "task_ids": ids, "replayed": 0}


def replay_channel_binding(program_id: int, binding_id: int, dry_run: bool = True) -> dict[str, Any]:
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM automation_event_v2 WHERE source_type = 'binding_import' AND program_id = ? AND binding_id = ?",
        (int(program_id), int(binding_id)),
    ).fetchone()
    if dry_run:
        return {"ok": True, "dry_run": True, "program_id": int(program_id), "binding_id": int(binding_id), "existing_event_count": int((row or {}).get("count") or 0)}
    return {"ok": True, "dry_run": False, "program_id": int(program_id), "binding_id": int(binding_id)}


def cancel_queued_jobs_by_source_prefix(prefix: str, *, reason: str = "runtime_v2_replay_rollback") -> dict[str, Any]:
    rows = get_db().execute(
        """
        UPDATE broadcast_jobs
        SET status = 'cancelled', cancel_reason = ?, cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE source_type = 'automation_runtime_v2'
          AND source_id LIKE ?
          AND status IN ('waiting_approval', 'queued')
        RETURNING id
        """,
        (reason, f"{prefix}%"),
    ).fetchall()
    get_db().execute(
        """
        UPDATE automation_task_plan_v2
        SET status = 'cancelled', skip_reason = ?, updated_at = CURRENT_TIMESTAMP
        WHERE broadcast_job_id IN (SELECT id FROM broadcast_jobs WHERE source_type = 'automation_runtime_v2' AND source_id LIKE ?)
        """,
        (reason, f"{prefix}%"),
    )
    return {"ok": True, "cancelled_job_count": len(rows), "job_ids": [int(row.get("id") or 0) for row in rows]}
