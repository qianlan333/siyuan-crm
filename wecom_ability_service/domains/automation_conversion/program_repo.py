from __future__ import annotations

import json
from typing import Any

from ...db import get_db


DEFAULT_AUTOMATION_PROGRAM_CODE = "signup_conversion_v1"
DEFAULT_AUTOMATION_PROGRAM_NAME = "默认自动化转化方案"


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def serialize_program_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": int(row.get("id") or 0),
        "config_json": _json_loads(row.get("config_json"), default={}),
    }


def get_program_row(program_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_program
        WHERE id = ?
        LIMIT 1
        """,
        (int(program_id),),
    )
    return serialize_program_row(row) if row else None


def get_program_row_by_code(program_code: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_program
        WHERE program_code = ?
        LIMIT 1
        """,
        (_normalized_text(program_code),),
    )
    return serialize_program_row(row) if row else None


def list_program_rows(*, include_archived: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_program
        WHERE 1 = 1
    """
    params: list[Any] = []
    if not include_archived:
        sql += " AND status <> ?"
        params.append("archived")
    sql += """
        ORDER BY
            CASE status
                WHEN 'active' THEN 0
                WHEN 'draft' THEN 1
                WHEN 'paused' THEN 2
                ELSE 3
            END,
            updated_at DESC,
            id DESC
    """
    return [serialize_program_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def get_default_program_row() -> dict[str, Any] | None:
    return get_program_row_by_code(DEFAULT_AUTOMATION_PROGRAM_CODE)


def insert_program_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_program (
            program_code,
            program_name,
            description,
            status,
            config_json,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("program_code")),
            _normalized_text(payload.get("program_name")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "draft",
            json.dumps(payload.get("config_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("created_by")),
            _normalized_text(payload.get("updated_by")),
        ),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def update_program_row(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_program
        SET program_code = ?,
            program_name = ?,
            description = ?,
            status = ?,
            config_json = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("program_code")),
            _normalized_text(payload.get("program_name")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "draft",
            json.dumps(payload.get("config_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("updated_by")),
            int(program_id),
        ),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def update_program_basic_info_row(program_id: int, *, program_name: str, description: str, operator_id: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_program
        SET program_name = ?,
            description = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(program_name),
            _normalized_text(description),
            _normalized_text(operator_id),
            int(program_id),
        ),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def update_program_status_row(program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_program
        SET status = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (_normalized_text(status), _normalized_text(operator_id), int(program_id)),
    ).fetchone()
    return serialize_program_row(dict(row) if row else {})


def get_program_summary(program_id: int) -> dict[str, Any]:
    workflow_count_row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM automation_workflow
        WHERE program_id = ?
          AND status <> 'archived'
        """,
        (int(program_id),),
    ) or {}
    execution_row = _fetchone_dict(
        """
        SELECT MAX(
            CASE
                WHEN COALESCE(CAST(scheduled_for AS TEXT), '') <> '' THEN CAST(scheduled_for AS TEXT)
                WHEN updated_at IS NOT NULL THEN CAST(updated_at AS TEXT)
                ELSE COALESCE(CAST(created_at AS TEXT), '')
            END
        ) AS latest_execution_at
        FROM automation_workflow_execution
        WHERE program_id = ?
        """,
        (int(program_id),),
    ) or {}
    return {
        "workflow_count": int(workflow_count_row.get("total") or 0),
        "latest_execution_at": _normalized_text(execution_row.get("latest_execution_at")),
    }
