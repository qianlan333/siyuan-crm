from __future__ import annotations

from datetime import datetime
from typing import Any

from ...db import get_db
from ..broadcast_jobs import repo as broadcast_queue_repo
from ..broadcast_jobs import service as broadcast_queue
from . import operation_task_repo as task_repo
from . import repo as member_repo
from . import workflow_repo
from .operation_task_service import (
    _entry_for_task,
    _entry_matches_event_task,
    _event_execution_id_for_task,
    _event_task_diagnostic_result,
    _execution_without_items,
    _materialize_operation_task_execution,
    _render_result_summary_for_entry,
    _text,
)


EMPTY_EXECUTION_REASONS = {
    "content_missing",
    "agent_runtime_content_missing",
    "behavior_segment_content_missing",
    "external_contact_id_missing",
    "task_unpublishable",
}


def _int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _member_from_scope(*, external_userid: str, member_id: int) -> dict[str, Any] | None:
    if _int(member_id):
        return member_repo.get_member_by_id(_int(member_id))
    if _text(external_userid):
        return member_repo.get_member_by_external_contact_id(_text(external_userid))
    return None


def _entry_from_scope(*, member: dict[str, Any], audience_entry_id: int) -> dict[str, Any] | None:
    rows = workflow_repo.list_member_audience_entry_rows(_int(member.get("id")), current_only=False)
    for row in rows:
        if _int(audience_entry_id) and _int(row.get("id")) == _int(audience_entry_id):
            row = dict(row)
            row["member"] = dict(member)
            return row
    for row in rows:
        if bool(row.get("is_current")):
            row = dict(row)
            row["member"] = dict(member)
            return row
    return None


def _existing_state(task_id: int, audience_entry_id: int) -> dict[str, Any]:
    execution_id = _event_execution_id_for_task(int(task_id), int(audience_entry_id))
    source_id = f"{int(task_id)}:audience_entered:{int(audience_entry_id)}"
    execution = task_repo.get_execution(execution_id) or {}
    items = task_repo.list_execution_items(execution_id) if execution else []
    job = broadcast_queue_repo.fetch_job_by_source(
        source_type="operation_task",
        source_id=source_id,
        source_table="automation_operation_task_execution",
    )
    return {
        "execution_id": execution_id,
        "source_id": source_id,
        "execution": execution,
        "items": items,
        "job": job or {},
    }


def _empty_execution_retry_allowed(execution: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    if not _execution_without_items(execution, items):
        return False
    summary = dict(execution.get("summary_json") or {})
    reason = _text(summary.get("reason"))
    if reason in EMPTY_EXECUTION_REASONS:
        return True
    return bool(summary.get("no_execution_items")) or int(summary.get("created_item_count") or 0) == 0


def _retry_execution_id(task_id: int, audience_entry_id: int, now: datetime) -> str:
    return f"actask-event-{int(task_id)}-{int(audience_entry_id)}-retry-{now.strftime('%Y%m%d%H%M%S')}"


def replay_audience_entered_operation_task(
    *,
    program_id: int,
    external_userid: str = "",
    member_id: int = 0,
    audience_entry_id: int = 0,
    task_ids: list[int] | None = None,
    dry_run: bool = True,
    allow_failed_empty_execution_retry: bool = False,
    operator_id: str = "operation_task_replay",
    now: datetime | None = None,
) -> dict[str, Any]:
    if _int(program_id) <= 0:
        raise ValueError("program_id is required")
    if not (_text(external_userid) or _int(member_id) or _int(audience_entry_id)):
        raise ValueError("external_userid, member_id, or audience_entry_id is required")
    normalized_task_ids = sorted(dict.fromkeys(_int(item) for item in list(task_ids or []) if _int(item)))
    if not normalized_task_ids:
        raise ValueError("task_ids is required")

    current_time = now or datetime.now()
    member = _member_from_scope(external_userid=external_userid, member_id=_int(member_id))
    if not member:
        return {
            "ok": True,
            "dry_run": bool(dry_run),
            "program_id": int(program_id),
            "external_userid": _text(external_userid),
            "member_found": False,
            "results": [],
            "reason": "member_not_found",
        }
    entry = _entry_from_scope(member=member, audience_entry_id=_int(audience_entry_id))
    if not entry:
        return {
            "ok": True,
            "dry_run": bool(dry_run),
            "program_id": int(program_id),
            "external_userid": _text(external_userid) or _text(member.get("external_contact_id")),
            "member_id": _int(member.get("id")),
            "member_found": True,
            "audience_entry_found": False,
            "results": [],
            "reason": "audience_entry_not_found",
        }

    results: list[dict[str, Any]] = []
    for task_id in normalized_task_ids:
        task = task_repo.get_task(task_id)
        if not task or _int(task.get("program_id")) != _int(program_id):
            results.append({"task_id": int(task_id), "can_replay": False, "reason": "task_not_found"})
            continue
        scoped_entry = _entry_for_task(task, entry)
        if not _entry_matches_event_task(task, scoped_entry):
            results.append(
                {
                    "task_id": int(task_id),
                    "task_name": _text(task.get("task_name")),
                    "audience_entry_id": _int(scoped_entry.get("id")),
                    "can_replay": False,
                    "reason": "task_not_matched",
                    "render_result_summary": _render_result_summary_for_entry(task, scoped_entry),
                }
            )
            continue

        state = _existing_state(int(task_id), _int(scoped_entry.get("id")))
        execution = dict(state["execution"] or {})
        items = list(state["items"] or [])
        job = dict(state["job"] or {})
        blocked_by_existing_execution = bool(execution)
        blocked_by_existing_job = bool(job)
        retry_of_execution_id = ""
        use_retry = False
        can_replay = True
        reason = "ready"
        if job:
            can_replay = False
            reason = "existing_broadcast_job"
        elif execution and items:
            can_replay = False
            reason = "existing_execution_with_items"
        elif execution:
            if _empty_execution_retry_allowed(execution, items):
                retry_of_execution_id = _text(execution.get("execution_id"))
                use_retry = True
                can_replay = bool(allow_failed_empty_execution_retry)
                reason = "existing_execution_without_items" if can_replay else "failed_empty_content_execution_blocks_replay"
            else:
                can_replay = False
                reason = "existing_execution_without_items"

        execution_id = _retry_execution_id(int(task_id), _int(scoped_entry.get("id")), current_time) if use_retry else state["execution_id"]
        source_id = (
            f"{int(task_id)}:audience_entered:{_int(scoped_entry.get('id'))}:retry:{current_time.strftime('%Y%m%d%H%M%S')}"
            if use_retry
            else state["source_id"]
        )
        diagnostic = _event_task_diagnostic_result(
            task=task,
            execution_id=execution_id,
            audience_entry_id=_int(scoped_entry.get("id")),
            enqueued_count=0,
            status=_text(execution.get("status")),
            reason=reason,
            render_result_summary=_render_result_summary_for_entry(task, scoped_entry),
            blocked_by_existing_execution=blocked_by_existing_execution,
            blocked_by_existing_job=blocked_by_existing_job,
        )
        diagnostic.update(
            {
                "can_replay": bool(can_replay),
                "dry_run": bool(dry_run),
                "source_id": source_id,
                "retry_of_execution_id": retry_of_execution_id,
                "existing_execution": execution,
                "existing_item_count": len(items),
                "existing_job": job,
            }
        )
        if not can_replay or dry_run:
            results.append(diagnostic)
            continue

        execution_row, created_items = _materialize_operation_task_execution(
            task=task,
            scheduled_for=current_time,
            operator_id=_text(operator_id) or "operation_task_replay",
            entries=[scoped_entry],
            execution_id=execution_id,
            summary_extra={
                "trigger_type": "audience_entered",
                "audience_entry_id": _int(scoped_entry.get("id")),
                "replay": True,
                "retry_of_execution_id": retry_of_execution_id,
            },
        )
        if not created_items:
            summary = dict(execution_row.get("summary_json") or {})
            diagnostic.update(
                {
                    "status": _text(execution_row.get("status")),
                    "reason": _text(summary.get("reason")) or "content_missing",
                    "can_replay": False,
                    "created_execution_id": _text(execution_row.get("execution_id")),
                    "created_item_count": 0,
                }
            )
            results.append(diagnostic)
            continue
        job_id = broadcast_queue.enqueue_job(
            source_type="operation_task",
            source_id=source_id,
            source_table="automation_operation_task_execution",
            scheduled_for=current_time,
            target_external_userids=[],
            target_summary=f"{task.get('task_name')} 受控 replay",
            content_type="private_message",
            content_payload={
                "trigger_type": "audience_entered",
                "scheduled_for": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "execution_id": execution_id,
                "task_id": int(task_id),
                "operator_id": _text(operator_id) or "operation_task_replay",
                "replay": True,
                "retry_of_execution_id": retry_of_execution_id,
            },
            content_summary=_text(task.get("task_name"))[:100],
            trace_id=execution_id,
            created_by=_text(operator_id) or "operation_task_replay",
            allow_empty_targets=True,
        )
        diagnostic.update(
            {
                "status": "queued",
                "reason": "ok",
                "enqueued_count": 1,
                "job_id": int(job_id or 0),
                "created_execution_id": execution_id,
                "created_item_count": len(created_items),
            }
        )
        results.append(diagnostic)

    if not dry_run:
        get_db().commit()
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "program_id": int(program_id),
        "external_userid": _text(external_userid) or _text(member.get("external_contact_id")),
        "member_id": _int(member.get("id")),
        "member_found": True,
        "audience_entry_found": True,
        "audience_entry": {
            "id": _int(entry.get("id")),
            "audience_code": _text(entry.get("audience_code")),
            "entry_reason": _text(entry.get("entry_reason")),
            "is_current": bool(entry.get("is_current")),
            "entered_at": _text(entry.get("entered_at")),
        },
        "results": results,
    }
