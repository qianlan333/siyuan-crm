from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ...db import get_db


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, *, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_text(value: Any, *, default: Any) -> str:
    return json.dumps(value if value is not None else default, ensure_ascii=False)


def _group_row(row: Any) -> dict[str, Any]:
    item = dict(row or {})
    return {
        **item,
        "id": int(item.get("id") or 0),
        "program_id": int(item.get("program_id") or 0),
        "sort_order": int(item.get("sort_order") or 0),
    }


def _task_row(row: Any) -> dict[str, Any]:
    item = dict(row or {})
    return {
        **item,
        "id": int(item.get("id") or 0),
        "program_id": int(item.get("program_id") or 0),
        "group_id": int(item.get("group_id") or 0) or None,
        "trigger_type": _text(item.get("trigger_type")) or "scheduled_daily",
        "audience_day_offset": int(item.get("audience_day_offset") or 1),
        "profile_segment_template_id": int(item.get("profile_segment_template_id") or 0) or None,
        "unified_content_json": _json(item.get("unified_content_json"), default={}),
        "segment_contents_json": _json(item.get("segment_contents_json"), default=[]),
        "agent_config_json": _json(item.get("agent_config_json"), default={}),
    }


def _execution_row(row: Any) -> dict[str, Any]:
    item = dict(row or {})
    return {
        **item,
        "id": int(item.get("id") or 0),
        "program_id": int(item.get("program_id") or 0),
        "task_id": int(item.get("task_id") or 0),
        "target_count": int(item.get("target_count") or 0),
        "enqueued_count": int(item.get("enqueued_count") or 0),
        "sent_count": int(item.get("sent_count") or 0),
        "failed_count": int(item.get("failed_count") or 0),
        "summary_json": _json(item.get("summary_json"), default={}),
    }


def _execution_item_row(row: Any) -> dict[str, Any]:
    item = dict(row or {})
    return {
        **item,
        "id": int(item.get("id") or 0),
        "task_id": int(item.get("task_id") or 0),
        "member_id": int(item.get("member_id") or 0),
        "audience_entry_id": int(item.get("audience_entry_id") or 0) or None,
        "content_snapshot_json": _json(item.get("content_snapshot_json"), default={}),
    }


def list_groups(program_id: int, *, include_archived: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_operation_task_group
        WHERE program_id = ?
    """
    params: list[Any] = [int(program_id)]
    if not include_archived:
        sql += " AND COALESCE(archived_at, '') = ''"
    sql += " ORDER BY sort_order ASC, id ASC"
    return [_group_row(row) for row in get_db().execute(sql, tuple(params)).fetchall()]


def get_group(group_id: int) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM automation_operation_task_group WHERE id = ? LIMIT 1", (int(group_id),)).fetchone()
    return _group_row(row) if row else None


def insert_group(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_operation_task_group (
            program_id, group_name, sort_order, created_by, updated_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("program_id") or 0),
            _text(payload.get("group_name")),
            int(payload.get("sort_order") or 0),
            _text(payload.get("created_by")),
            _text(payload.get("updated_by")),
        ),
    ).fetchone()
    return _group_row(row)


def update_group(group_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_operation_task_group
        SET group_name = ?, sort_order = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (_text(payload.get("group_name")), int(payload.get("sort_order") or 0), _text(payload.get("updated_by")), int(group_id)),
    ).fetchone()
    return _group_row(row) if row else {}


def archive_group(group_id: int, *, operator_id: str) -> None:
    get_db().execute(
        """
        UPDATE automation_operation_task
        SET group_id = NULL,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE group_id = ?
        """,
        (_text(operator_id), int(group_id)),
    )
    get_db().execute(
        """
        UPDATE automation_operation_task_group
        SET archived_at = CURRENT_TIMESTAMP, updated_by = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_text(operator_id), int(group_id)),
    )


def list_tasks(
    program_id: int,
    *,
    group_id: int | None = None,
    status: str = "",
    keyword: str = "",
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    sql = """
        SELECT t.*, g.group_name
        FROM automation_operation_task t
        LEFT JOIN automation_operation_task_group g ON g.id = t.group_id
        WHERE t.program_id = ?
    """
    params: list[Any] = [int(program_id)]
    if group_id is not None:
        sql += " AND t.group_id = ?"
        params.append(int(group_id))
    if _text(status):
        sql += " AND t.status = ?"
        params.append(_text(status))
    if _text(keyword):
        sql += " AND LOWER(t.task_name) LIKE LOWER(?)"
        params.append(f"%{_text(keyword)}%")
    if not include_archived:
        sql += " AND t.status <> 'archived'"
    sql += " ORDER BY COALESCE(g.sort_order, 999999) ASC, t.updated_at DESC, t.id DESC"
    return [_task_row(row) for row in get_db().execute(sql, tuple(params)).fetchall()]


def get_task(task_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT t.*, g.group_name
        FROM automation_operation_task t
        LEFT JOIN automation_operation_task_group g ON g.id = t.group_id
        WHERE t.id = ?
        LIMIT 1
        """,
        (int(task_id),),
    ).fetchone()
    return _task_row(row) if row else None


def insert_task(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_operation_task (
            program_id, group_id, task_name, description, status, trigger_type, send_time, timezone,
            target_audience_code, audience_day_offset, behavior_filter, content_mode,
            profile_segment_template_id, unified_content_json, segment_contents_json,
            agent_config_json, created_by, updated_by, created_at, updated_at, published_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        RETURNING *
        """,
        _task_params(payload),
    ).fetchone()
    return _task_row(row)


def update_task(task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    params = _task_params(payload)
    row = get_db().execute(
        """
        UPDATE automation_operation_task
        SET program_id = ?, group_id = ?, task_name = ?, description = ?, status = ?,
            trigger_type = ?, send_time = ?, timezone = ?, target_audience_code = ?, audience_day_offset = ?,
            behavior_filter = ?, content_mode = ?, profile_segment_template_id = ?,
            unified_content_json = ?, segment_contents_json = ?, agent_config_json = ?,
            updated_by = ?, updated_at = CURRENT_TIMESTAMP,
            published_at = CASE WHEN ? = 'active' THEN COALESCE(published_at, CURRENT_TIMESTAMP) ELSE published_at END
        WHERE id = ?
        RETURNING *
        """,
        (*params[:16], params[17], _text(payload.get("status")), int(task_id)),
    ).fetchone()
    return _task_row(row) if row else {}


def _task_params(payload: dict[str, Any]) -> tuple[Any, ...]:
    status = _text(payload.get("status")) or "draft"
    return (
        int(payload.get("program_id") or 0),
        int(payload.get("group_id") or 0) or None,
        _text(payload.get("task_name")),
        _text(payload.get("description")),
        status,
        _text(payload.get("trigger_type")) or "scheduled_daily",
        _text(payload.get("send_time")) or "10:00",
        _text(payload.get("timezone")) or "Asia/Shanghai",
        _text(payload.get("target_audience_code")) or "operating",
        int(payload.get("audience_day_offset") or 1),
        _text(payload.get("behavior_filter")) or "none",
        _text(payload.get("content_mode")) or "unified",
        int(payload.get("profile_segment_template_id") or 0) or None,
        _json_text(payload.get("unified_content_json") or {}, default={}),
        _json_text(payload.get("segment_contents_json") or [], default=[]),
        _json_text(payload.get("agent_config_json") or {}, default={}),
        _text(payload.get("created_by") or payload.get("updated_by")),
        _text(payload.get("updated_by") or payload.get("created_by")),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == "active" else None,
    )


def archive_task(task_id: int, *, operator_id: str) -> None:
    get_db().execute(
        """
        UPDATE automation_operation_task
        SET status = 'archived', updated_by = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_text(operator_id), int(task_id)),
    )


def list_current_audience_entries(audience_code: str) -> list[dict[str, Any]]:
    from . import workflow_repo

    return workflow_repo.list_current_member_audience_rows(_text(audience_code))


def insert_execution(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_db().execute(
        "SELECT * FROM automation_operation_task_execution WHERE execution_id = ? LIMIT 1",
        (_text(payload.get("execution_id")),),
    ).fetchone()
    if existing:
        return _execution_row(existing)
    row = get_db().execute(
        """
        INSERT INTO automation_operation_task_execution (
            execution_id, program_id, task_id, scheduled_for, status, target_count,
            enqueued_count, sent_count, failed_count, summary_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _text(payload.get("execution_id")),
            int(payload.get("program_id") or 0),
            int(payload.get("task_id") or 0),
            payload.get("scheduled_for"),
            _text(payload.get("status")) or "running",
            int(payload.get("target_count") or 0),
            int(payload.get("enqueued_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_text(payload.get("summary_json") or {}, default={}),
        ),
    ).fetchone()
    return _execution_row(row)


def get_execution(execution_id: str) -> dict[str, Any] | None:
    row = get_db().execute(
        "SELECT * FROM automation_operation_task_execution WHERE execution_id = ? LIMIT 1",
        (_text(execution_id),),
    ).fetchone()
    return _execution_row(row) if row else None


def update_execution(execution_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_operation_task_execution
        SET status = ?, target_count = ?, enqueued_count = ?, sent_count = ?, failed_count = ?,
            summary_json = ?, finished_at = CASE WHEN ? IN ('finished', 'failed', 'partial_failed') THEN CURRENT_TIMESTAMP ELSE finished_at END
        WHERE execution_id = ?
        RETURNING *
        """,
        (
            _text(payload.get("status")) or "running",
            int(payload.get("target_count") or 0),
            int(payload.get("enqueued_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_text(payload.get("summary_json") or {}, default={}),
            _text(payload.get("status")),
            _text(execution_id),
        ),
    ).fetchone()
    return _execution_row(row) if row else {}


def insert_execution_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    task_id = int(payload.get("task_id") or 0)
    member_id = int(payload.get("member_id") or 0)
    audience_entry_id = int(payload.get("audience_entry_id") or 0) or None
    if audience_entry_id:
        existing = get_db().execute(
            """
            SELECT * FROM automation_operation_task_execution_item
            WHERE task_id = ? AND audience_entry_id = ?
            LIMIT 1
            """,
            (task_id, audience_entry_id),
        ).fetchone()
        if existing:
            return None
    row = get_db().execute(
        """
        INSERT INTO automation_operation_task_execution_item (
            execution_id, task_id, member_id, audience_entry_id, external_contact_id,
            segment_key, rendered_content_text, content_snapshot_json, send_record_id,
            status, error_message, sent_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        RETURNING *
        """,
        (
            _text(payload.get("execution_id")),
            task_id,
            member_id,
            audience_entry_id,
            _text(payload.get("external_contact_id")),
            _text(payload.get("segment_key")),
            _text(payload.get("rendered_content_text")),
            _json_text(payload.get("content_snapshot_json") or {}, default={}),
            payload.get("send_record_id"),
            _text(payload.get("status")) or "pending",
            _text(payload.get("error_message")),
            _text(payload.get("sent_at")) or None,
        ),
    ).fetchone()
    return _execution_item_row(row) if row else None


def list_execution_items(execution_id: str, *, statuses: list[str] | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_operation_task_execution_item
        WHERE execution_id = ?
    """
    params: list[Any] = [_text(execution_id)]
    normalized_statuses = [_text(item) for item in list(statuses or []) if _text(item)]
    if normalized_statuses:
        sql += f" AND status IN ({','.join(['?'] * len(normalized_statuses))})"
        params.extend(normalized_statuses)
    sql += " ORDER BY id ASC"
    return [_execution_item_row(row) for row in get_db().execute(sql, tuple(params)).fetchall()]


def update_execution_item(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_operation_task_execution_item
        SET rendered_content_text = ?, content_snapshot_json = ?, send_record_id = ?,
            status = ?, error_message = ?, sent_at = CASE WHEN ? = 'sent' THEN CURRENT_TIMESTAMP ELSE sent_at END
        WHERE id = ?
        RETURNING *
        """,
        (
            _text(payload.get("rendered_content_text")),
            _json_text(payload.get("content_snapshot_json") or {}, default={}),
            payload.get("send_record_id"),
            _text(payload.get("status")) or "queued",
            _text(payload.get("error_message")),
            _text(payload.get("status")),
            int(item_id),
        ),
    ).fetchone()
    return _execution_item_row(row) if row else {}
