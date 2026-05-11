"""Profile segment template + category + option mapping (阶段 6.1).

Extracted from workflow_repo.py. External callers keep using
``automation_conversion.workflow_repo.X``.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (  # noqa: F401
    _fetchall_dicts,
    _fetchone_dict,
    _normalized_text,
)
from ._workflow_repo_serializers import (
    _serialize_profile_segment_category_row,
    _serialize_profile_segment_option_mapping_row,
    _serialize_profile_segment_template_row,
)


def list_profile_segment_template_rows(*, enabled_only: bool = False, program_id: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_profile_segment_template
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    if program_id is not None:
        where_clauses.append("program_id = ?")
        params.append(int(program_id))
    if enabled_only:
        where_clauses.append("enabled = ?")
        params.append(True)
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY updated_at DESC, id DESC"
    return [_serialize_profile_segment_template_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def get_profile_segment_template_row(template_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_profile_segment_template
        WHERE id = ?
        LIMIT 1
        """,
        (int(template_id),),
    )
    return _serialize_profile_segment_template_row(row) if row else None


def get_profile_segment_template_row_by_code(template_code: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_profile_segment_template
        WHERE template_code = ?
        LIMIT 1
        """,
        (_normalized_text(template_code),),
    )
    return _serialize_profile_segment_template_row(row) if row else None


def insert_profile_segment_template_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_profile_segment_template (
            program_id,
            template_code,
            template_name,
            questionnaire_id,
            segmentation_question_id,
            description,
            enabled,
            version,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("program_id") or 0) or None,
            _normalized_text(payload.get("template_code")),
            _normalized_text(payload.get("template_name")),
            payload.get("questionnaire_id"),
            payload.get("segmentation_question_id"),
            _normalized_text(payload.get("description")),
            bool(payload.get("enabled", True)),
            int(payload.get("version") or 1),
            _normalized_text(payload.get("created_by")),
            _normalized_text(payload.get("updated_by")),
        ),
    ).fetchone()
    return _serialize_profile_segment_template_row(dict(row) if row else {})


def update_profile_segment_template_row(template_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_profile_segment_template
        SET program_id = ?,
            template_code = ?,
            template_name = ?,
            questionnaire_id = ?,
            segmentation_question_id = ?,
            description = ?,
            enabled = ?,
            version = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            int(payload.get("program_id") or 0) or None,
            _normalized_text(payload.get("template_code")),
            _normalized_text(payload.get("template_name")),
            payload.get("questionnaire_id"),
            payload.get("segmentation_question_id"),
            _normalized_text(payload.get("description")),
            bool(payload.get("enabled", True)),
            int(payload.get("version") or 1),
            _normalized_text(payload.get("updated_by")),
            int(template_id),
        ),
    ).fetchone()
    return _serialize_profile_segment_template_row(dict(row) if row else {})


def list_profile_segment_category_rows(template_id: int) -> list[dict[str, Any]]:
    return [
        _serialize_profile_segment_category_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_profile_segment_category
            WHERE template_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (int(template_id),),
        )
    ]


def delete_profile_segment_category_rows(template_id: int) -> None:
    get_db().execute("DELETE FROM automation_profile_segment_category WHERE template_id = ?", (int(template_id),))


def insert_profile_segment_category_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_profile_segment_category (
            template_id,
            category_key,
            category_name,
            description,
            sort_order,
            enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("template_id") or 0),
            _normalized_text(payload.get("category_key")),
            _normalized_text(payload.get("category_name")),
            _normalized_text(payload.get("description")),
            int(payload.get("sort_order") or 0),
            bool(payload.get("enabled", True)),
        ),
    ).fetchone()
    return _serialize_profile_segment_category_row(dict(row) if row else {})


def list_profile_segment_option_mapping_rows(template_id: int) -> list[dict[str, Any]]:
    return [
        _serialize_profile_segment_option_mapping_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_profile_segment_option_mapping
            WHERE template_id = ?
            ORDER BY category_id ASC, question_id ASC, option_id ASC, id ASC
            """,
            (int(template_id),),
        )
    ]


def delete_profile_segment_option_mapping_rows(template_id: int) -> None:
    get_db().execute("DELETE FROM automation_profile_segment_option_mapping WHERE template_id = ?", (int(template_id),))


def insert_profile_segment_option_mapping_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_profile_segment_option_mapping (
            template_id,
            category_id,
            question_id,
            option_id,
            created_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("template_id") or 0),
            int(payload.get("category_id") or 0),
            int(payload.get("question_id") or 0),
            int(payload.get("option_id") or 0),
        ),
    ).fetchone()
    return _serialize_profile_segment_option_mapping_row(dict(row) if row else {})




__all__ = [
    "delete_profile_segment_category_rows",
    "delete_profile_segment_option_mapping_rows",
    "get_profile_segment_template_row",
    "get_profile_segment_template_row_by_code",
    "insert_profile_segment_category_row",
    "insert_profile_segment_option_mapping_row",
    "insert_profile_segment_template_row",
    "list_profile_segment_category_rows",
    "list_profile_segment_option_mapping_rows",
    "list_profile_segment_template_rows",
    "update_profile_segment_template_row",
]
