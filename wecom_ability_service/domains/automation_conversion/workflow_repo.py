from __future__ import annotations

import json
from typing import Any

from ...db import get_db
from ._repo_helpers import (  # noqa: F401  shared helpers
    _fetchall_dicts,
    _fetchone_dict,
    _json_loads,
    _normalized_text,
    _row_bool,
)
from ._workflow_repo_serializers import (  # noqa: F401  Row deserialization helpers for workflow_repo (阶段 6.1)
    _serialize_automation_member_row,
    _serialize_customer_marketing_state_row,
    _serialize_member_audience_entry_row,
    _serialize_node_content_row,
    _serialize_node_content_variant_row,
    _serialize_profile_segment_category_row,
    _serialize_profile_segment_option_mapping_row,
    _serialize_profile_segment_template_row,
    _serialize_workflow_agent_binding_row,
    _serialize_workflow_audience_row,
    _serialize_workflow_execution_item_row,
    _serialize_workflow_execution_row,
    _serialize_workflow_node_row,
    _serialize_workflow_row,
)
from ._workflow_repo_profile_segment import (  # noqa: F401  Profile segment template + category + option mapping (阶段 6.1)
    delete_profile_segment_category_rows,
    delete_profile_segment_option_mapping_rows,
    get_profile_segment_template_row,
    get_profile_segment_template_row_by_code,
    insert_profile_segment_category_row,
    insert_profile_segment_option_mapping_row,
    insert_profile_segment_template_row,
    list_profile_segment_category_rows,
    list_profile_segment_option_mapping_rows,
    list_profile_segment_template_rows,
    update_profile_segment_template_row,
)
from ._workflow_repo_questionnaire import (  # noqa: F401  Questionnaire-related read paths used by workflow runtime (阶段 6.1)
    get_latest_any_questionnaire_submission_row,
    get_latest_questionnaire_submission_row,
    get_questionnaire_question_row,
    get_questionnaire_row,
    list_questionnaire_option_rows,
    list_questionnaire_question_rows,
    list_questionnaire_rows,
    list_questionnaire_submission_answer_rows,
)
from ._workflow_repo_externals import (  # noqa: F401  Cross-table reads (agent_config / archived_messages / automation_member) used by workflow flows (阶段 6.1)
    count_archived_customer_messages,
    get_archived_customer_message_counts,
    get_automation_member_row,
    list_agent_config_codes,
    list_agent_config_summary_rows,
    list_automation_member_rows,
)


def list_workflow_rows(*, include_archived: bool = False, status: str = "", program_id: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_workflow
        WHERE 1 = 1
    """
    params: list[Any] = []
    if program_id is not None:
        sql += " AND program_id = ?"
        params.append(int(program_id))
    if not include_archived:
        sql += " AND status <> ?"
        params.append("archived")
    if _normalized_text(status):
        sql += " AND status = ?"
        params.append(_normalized_text(status))
    sql += " ORDER BY updated_at DESC, id DESC"
    return [_serialize_workflow_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def list_workflow_execution_summary_rows(*, include_archived: bool = False, program_id: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT
            w.id AS workflow_id,
            w.workflow_code,
            w.workflow_name,
            w.status AS workflow_status,
            COUNT(e.id) AS execution_count,
            MAX(
                CASE
                    WHEN COALESCE(CAST(e.scheduled_for AS TEXT), '') <> '' THEN CAST(e.scheduled_for AS TEXT)
                    WHEN e.updated_at IS NOT NULL THEN CAST(e.updated_at AS TEXT)
                    ELSE COALESCE(CAST(e.created_at AS TEXT), '')
                END
            ) AS latest_execution_at,
            w.updated_at AS workflow_updated_at
        FROM automation_workflow w
        LEFT JOIN automation_workflow_execution e ON e.workflow_id = w.id
        WHERE 1 = 1
    """
    params: list[Any] = []
    if program_id is not None:
        sql += " AND w.program_id = ?"
        params.append(int(program_id))
    if not include_archived:
        sql += " AND w.status <> ?"
        params.append("archived")
    sql += """
        GROUP BY w.id, w.workflow_code, w.workflow_name, w.status, w.updated_at
        ORDER BY
            CASE WHEN w.status = 'active' THEN 0 ELSE 1 END,
            execution_count DESC,
            latest_execution_at DESC,
            w.updated_at DESC,
            w.id DESC
    """
    return _fetchall_dicts(sql, tuple(params))


def count_workflow_rows(*, include_archived: bool = False, status: str = "", program_id: int | None = None) -> int:
    sql = """
        SELECT COUNT(*) AS total
        FROM automation_workflow
        WHERE 1 = 1
    """
    params: list[Any] = []
    if program_id is not None:
        sql += " AND program_id = ?"
        params.append(int(program_id))
    if not include_archived:
        sql += " AND status <> ?"
        params.append("archived")
    if _normalized_text(status):
        sql += " AND status = ?"
        params.append(_normalized_text(status))
    row = _fetchone_dict(sql, tuple(params)) or {}
    return int(row.get("total") or 0)


def get_workflow_row(workflow_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_workflow
        WHERE id = ?
        LIMIT 1
        """,
        (int(workflow_id),),
    )
    return _serialize_workflow_row(row) if row else None


def get_workflow_row_by_code(workflow_code: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_workflow
        WHERE workflow_code = ?
        LIMIT 1
        """,
        (_normalized_text(workflow_code),),
    )
    return _serialize_workflow_row(row) if row else None


def _serialize_operation_template_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": int(row.get("id") or 0),
        "template_code": _normalized_text(row.get("template_code")),
        "template_name": _normalized_text(row.get("template_name")),
        "template_source": _normalized_text(row.get("template_source")) or "crm_local",
        "category": _normalized_text(row.get("category")),
        "description": _normalized_text(row.get("description")),
        "status": _normalized_text(row.get("status")) or "active",
        "default_config": _json_loads(row.get("default_config_json"), default={}),
        "ui_schema": _json_loads(row.get("ui_schema_json"), default={}),
        "workflow_blueprint": _json_loads(row.get("workflow_blueprint_json"), default={}),
        "node_blueprints": _json_loads(row.get("node_blueprints_json"), default=[]),
        "created_by": _normalized_text(row.get("created_by")),
        "updated_by": _normalized_text(row.get("updated_by")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
        "archived_at": _normalized_text(row.get("archived_at")),
    }


def list_operation_template_rows(
    *,
    template_source: str = "",
    category: str = "",
    keyword: str = "",
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_operation_templates
        WHERE 1 = 1
    """
    params: list[Any] = []
    if not include_archived:
        sql += " AND status <> ?"
        params.append("archived")
    if _normalized_text(template_source):
        sql += " AND template_source = ?"
        params.append(_normalized_text(template_source))
    if _normalized_text(category):
        sql += " AND category = ?"
        params.append(_normalized_text(category))
    normalized_keyword = _normalized_text(keyword)
    if normalized_keyword:
        sql += " AND (template_name ILIKE ? OR description ILIKE ? OR category ILIKE ?)"
        like_keyword = f"%{normalized_keyword}%"
        params.extend([like_keyword, like_keyword, like_keyword])
    sql += " ORDER BY updated_at DESC, id DESC"
    return [_serialize_operation_template_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def get_operation_template_row(template_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_operation_templates
        WHERE id = ?
        LIMIT 1
        """,
        (int(template_id),),
    )
    return _serialize_operation_template_row(row) if row else None


def get_operation_template_row_by_code(template_code: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_operation_templates
        WHERE template_code = ?
        LIMIT 1
        """,
        (_normalized_text(template_code),),
    )
    return _serialize_operation_template_row(row) if row else None


def insert_operation_template_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_operation_templates (
            template_code,
            template_name,
            template_source,
            category,
            description,
            status,
            default_config_json,
            ui_schema_json,
            workflow_blueprint_json,
            node_blueprints_json,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("template_code")),
            _normalized_text(payload.get("template_name")),
            _normalized_text(payload.get("template_source")) or "crm_local",
            _normalized_text(payload.get("category")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "active",
            json.dumps(payload.get("default_config_json") or payload.get("default_config") or {}, ensure_ascii=False),
            json.dumps(payload.get("ui_schema_json") or payload.get("ui_schema") or {}, ensure_ascii=False),
            json.dumps(payload.get("workflow_blueprint_json") or payload.get("workflow_blueprint") or {}, ensure_ascii=False),
            json.dumps(payload.get("node_blueprints_json") or payload.get("node_blueprints") or [], ensure_ascii=False),
            _normalized_text(payload.get("created_by")),
            _normalized_text(payload.get("updated_by")),
        ),
    ).fetchone()
    return _serialize_operation_template_row(dict(row) if row else {})


def update_operation_template_row(template_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_operation_templates
        SET template_code = ?,
            template_name = ?,
            template_source = ?,
            category = ?,
            description = ?,
            status = ?,
            default_config_json = ?,
            ui_schema_json = ?,
            workflow_blueprint_json = ?,
            node_blueprints_json = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP,
            archived_at = CASE WHEN ? = 'archived' AND archived_at IS NULL THEN CURRENT_TIMESTAMP ELSE archived_at END
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("template_code")),
            _normalized_text(payload.get("template_name")),
            _normalized_text(payload.get("template_source")) or "crm_local",
            _normalized_text(payload.get("category")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "active",
            json.dumps(payload.get("default_config_json") or payload.get("default_config") or {}, ensure_ascii=False),
            json.dumps(payload.get("ui_schema_json") or payload.get("ui_schema") or {}, ensure_ascii=False),
            json.dumps(payload.get("workflow_blueprint_json") or payload.get("workflow_blueprint") or {}, ensure_ascii=False),
            json.dumps(payload.get("node_blueprints_json") or payload.get("node_blueprints") or [], ensure_ascii=False),
            _normalized_text(payload.get("updated_by")),
            _normalized_text(payload.get("status")) or "active",
            int(template_id),
        ),
    ).fetchone()
    return _serialize_operation_template_row(dict(row) if row else {})


def insert_workflow_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow (
            program_id,
            workflow_code,
            workflow_name,
            description,
            status,
            segmentation_basis,
            generation_mode,
            profile_segment_template_id,
            behavior_tier_scheme,
            fallback_to_standard_content,
            enabled,
            created_by,
            updated_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("program_id") or 0) or None,
            _normalized_text(payload.get("workflow_code")),
            _normalized_text(payload.get("workflow_name")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "draft",
            _normalized_text(payload.get("segmentation_basis")) or "none",
            _normalized_text(payload.get("generation_mode")) or "manual_layered",
            payload.get("profile_segment_template_id"),
            _normalized_text(payload.get("behavior_tier_scheme")) or "fixed_v1",
            bool(payload.get("fallback_to_standard_content", True)),
            bool(payload.get("enabled", False)),
            _normalized_text(payload.get("created_by")),
            _normalized_text(payload.get("updated_by")),
        ),
    ).fetchone()
    return _serialize_workflow_row(dict(row) if row else {})


def update_workflow_row(workflow_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_workflow
        SET program_id = ?,
            workflow_code = ?,
            workflow_name = ?,
            description = ?,
            status = ?,
            segmentation_basis = ?,
            generation_mode = ?,
            profile_segment_template_id = ?,
            behavior_tier_scheme = ?,
            fallback_to_standard_content = ?,
            enabled = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            int(payload.get("program_id") or 0) or None,
            _normalized_text(payload.get("workflow_code")),
            _normalized_text(payload.get("workflow_name")),
            _normalized_text(payload.get("description")),
            _normalized_text(payload.get("status")) or "draft",
            _normalized_text(payload.get("segmentation_basis")) or "none",
            _normalized_text(payload.get("generation_mode")) or "manual_layered",
            payload.get("profile_segment_template_id"),
            _normalized_text(payload.get("behavior_tier_scheme")) or "fixed_v1",
            bool(payload.get("fallback_to_standard_content", True)),
            bool(payload.get("enabled", False)),
            _normalized_text(payload.get("updated_by")),
            int(workflow_id),
        ),
    ).fetchone()
    return _serialize_workflow_row(dict(row) if row else {})


def delete_workflow_row(workflow_id: int) -> None:
    get_db().execute("DELETE FROM automation_workflow WHERE id = ?", (int(workflow_id),))


def list_workflow_audience_rows(workflow_id: int) -> list[dict[str, Any]]:
    return [
        _serialize_workflow_audience_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_workflow_audience
            WHERE workflow_id = ?
            ORDER BY audience_code ASC, id ASC
            """,
            (int(workflow_id),),
        )
    ]


def delete_workflow_audience_rows(workflow_id: int) -> None:
    get_db().execute("DELETE FROM automation_workflow_audience WHERE workflow_id = ?", (int(workflow_id),))


def insert_workflow_audience_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow_audience (
            workflow_id,
            audience_code,
            created_at
        )
        VALUES (?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("workflow_id") or 0),
            _normalized_text(payload.get("audience_code")),
        ),
    ).fetchone()
    return _serialize_workflow_audience_row(dict(row) if row else {})


def list_workflow_agent_binding_rows(workflow_id: int) -> list[dict[str, Any]]:
    return [
        _serialize_workflow_agent_binding_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_workflow_agent_binding
            WHERE workflow_id = ?
            ORDER BY COALESCE(node_id, 0) ASC, binding_scope ASC, segment_key ASC, id ASC
            """,
            (int(workflow_id),),
        )
    ]


def list_workflow_agent_binding_reference_rows(agent_code: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT
            b.workflow_id,
            b.node_id,
            b.binding_scope,
            b.segment_key,
            w.workflow_name,
            w.workflow_code,
            w.status AS workflow_status,
            n.node_name,
            n.node_code
        FROM automation_workflow_agent_binding AS b
        JOIN automation_workflow AS w
          ON w.id = b.workflow_id
        LEFT JOIN automation_workflow_node AS n
          ON n.id = b.node_id
        WHERE b.agent_code = ?
        ORDER BY w.updated_at DESC, w.id DESC, COALESCE(n.position_index, 0) ASC, b.id ASC
        """,
        (_normalized_text(agent_code),),
    )


def delete_workflow_agent_binding_rows(workflow_id: int) -> None:
    get_db().execute("DELETE FROM automation_workflow_agent_binding WHERE workflow_id = ?", (int(workflow_id),))


def delete_workflow_agent_binding_rows_for_node(workflow_id: int, node_id: int) -> None:
    get_db().execute(
        "DELETE FROM automation_workflow_agent_binding WHERE workflow_id = ? AND node_id = ?",
        (int(workflow_id), int(node_id)),
    )


def insert_workflow_agent_binding_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow_agent_binding (
            workflow_id,
            node_id,
            binding_scope,
            segment_key,
            agent_code,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("workflow_id") or 0),
            int(payload.get("node_id") or 0) or None,
            _normalized_text(payload.get("binding_scope")) or "default",
            _normalized_text(payload.get("segment_key")),
            _normalized_text(payload.get("agent_code")),
        ),
    ).fetchone()
    return _serialize_workflow_agent_binding_row(dict(row) if row else {})


def list_workflow_node_rows(workflow_id: int) -> list[dict[str, Any]]:
    return [
        _serialize_workflow_node_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_workflow_node
            WHERE workflow_id = ?
            ORDER BY position_index ASC, id ASC
            """,
            (int(workflow_id),),
        )
    ]


def get_workflow_node_row(node_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_workflow_node
        WHERE id = ?
        LIMIT 1
        """,
        (int(node_id),),
    )
    return _serialize_workflow_node_row(row) if row else None


def insert_workflow_node_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow_node (
            workflow_id,
            node_code,
            node_name,
            target_audience_code,
            trigger_mode,
            day_offset,
            send_time,
            timezone,
            position_index,
            enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("workflow_id") or 0),
            _normalized_text(payload.get("node_code")),
            _normalized_text(payload.get("node_name")),
            _normalized_text(payload.get("target_audience_code")),
            _normalized_text(payload.get("trigger_mode")) or "scheduled",
            int(payload.get("day_offset") or 1),
            _normalized_text(payload.get("send_time")) or "09:00",
            _normalized_text(payload.get("timezone")) or "Asia/Shanghai",
            int(payload.get("position_index") or 0),
            bool(payload.get("enabled", True)),
        ),
    ).fetchone()
    return _serialize_workflow_node_row(dict(row) if row else {})


def update_workflow_node_row(node_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_workflow_node
        SET node_code = ?,
            node_name = ?,
            target_audience_code = ?,
            trigger_mode = ?,
            day_offset = ?,
            send_time = ?,
            timezone = ?,
            position_index = ?,
            enabled = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("node_code")),
            _normalized_text(payload.get("node_name")),
            _normalized_text(payload.get("target_audience_code")),
            _normalized_text(payload.get("trigger_mode")) or "scheduled",
            int(payload.get("day_offset") or 1),
            _normalized_text(payload.get("send_time")) or "09:00",
            _normalized_text(payload.get("timezone")) or "Asia/Shanghai",
            int(payload.get("position_index") or 0),
            bool(payload.get("enabled", True)),
            int(node_id),
        ),
    ).fetchone()
    return _serialize_workflow_node_row(dict(row) if row else {})


def delete_workflow_node_row(node_id: int) -> None:
    get_db().execute("DELETE FROM automation_workflow_node WHERE id = ?", (int(node_id),))


def get_workflow_node_content_row(node_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_workflow_node_content
        WHERE node_id = ?
        LIMIT 1
        """,
        (int(node_id),),
    )
    return _serialize_node_content_row(row) if row else None


def insert_workflow_node_content_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow_node_content (
            node_id,
            standard_content_text,
            standard_content_payload_json,
            fallback_to_standard_content,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("node_id") or 0),
            _normalized_text(payload.get("standard_content_text")),
            json.dumps(payload.get("standard_content_payload_json") or {}, ensure_ascii=False),
            bool(payload.get("fallback_to_standard_content", True)),
        ),
    ).fetchone()
    return _serialize_node_content_row(dict(row) if row else {})


def update_workflow_node_content_row(node_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_workflow_node_content
        SET standard_content_text = ?,
            standard_content_payload_json = ?,
            fallback_to_standard_content = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE node_id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("standard_content_text")),
            json.dumps(payload.get("standard_content_payload_json") or {}, ensure_ascii=False),
            bool(payload.get("fallback_to_standard_content", True)),
            int(node_id),
        ),
    ).fetchone()
    return _serialize_node_content_row(dict(row) if row else {})


def list_workflow_node_content_variant_rows(node_content_id: int) -> list[dict[str, Any]]:
    return [
        _serialize_node_content_variant_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_workflow_node_content_variant
            WHERE node_content_id = ?
            ORDER BY variant_scope ASC, segment_key ASC, id ASC
            """,
            (int(node_content_id),),
        )
    ]


def delete_workflow_node_content_variant_rows(node_content_id: int) -> None:
    get_db().execute("DELETE FROM automation_workflow_node_content_variant WHERE node_content_id = ?", (int(node_content_id),))


def insert_workflow_node_content_variant_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow_node_content_variant (
            node_content_id,
            variant_scope,
            segment_key,
            content_text,
            content_payload_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("node_content_id") or 0),
            _normalized_text(payload.get("variant_scope")),
            _normalized_text(payload.get("segment_key")),
            _normalized_text(payload.get("content_text")),
            json.dumps(payload.get("content_payload_json") or {}, ensure_ascii=False),
            ),
    ).fetchone()
    return _serialize_node_content_variant_row(dict(row) if row else {})


def list_member_audience_entry_rows(member_id: int, *, current_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_member_audience_entry
        WHERE member_id = ?
    """
    params: list[Any] = [int(member_id)]
    if current_only:
        sql += " AND is_current = ?"
        params.append(True)
    sql += " ORDER BY entered_at DESC, id DESC"
    return [_serialize_member_audience_entry_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def get_current_member_audience_entry_row(member_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_member_audience_entry
        WHERE member_id = ?
          AND is_current = ?
        ORDER BY entered_at DESC, id DESC
        LIMIT 1
        """,
        (int(member_id), True),
    )
    return _serialize_member_audience_entry_row(row) if row else None


def _program_member_filter_sql(
    *,
    member_alias: str = "m",
    program_id: int | None = None,
    include_unscoped: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    if program_id is None:
        return "", ()
    alias = _normalized_text(member_alias) or "m"
    source_expr = f"{alias}.source_channel_id"
    program_channel_sql = """
        SELECT id FROM automation_channel WHERE program_id = ?
        UNION
        SELECT channel_id FROM automation_program_channel_binding WHERE program_id = ?
    """
    if include_unscoped:
        return (
            f"""
            AND (
                {source_expr} IS NULL
                OR {source_expr} IN (
                    {program_channel_sql}
                )
            )
            """,
            (int(program_id), int(program_id)),
        )
    return (
        f"""
        AND {source_expr} IN (
            {program_channel_sql}
        )
        """,
        (int(program_id), int(program_id)),
    )


def get_current_member_audience_counts(
    *, program_id: int | None = None, include_unscoped: bool = False
) -> dict[str, int]:
    counts: dict[str, int] = {}
    program_filter_sql, program_filter_params = _program_member_filter_sql(
        member_alias="automation_member",
        program_id=program_id,
        include_unscoped=include_unscoped,
    )
    for row in _fetchall_dicts(
        f"""
        SELECT current_audience_code, COUNT(*) AS total
        FROM automation_member
        WHERE 1 = 1
        {program_filter_sql}
        GROUP BY current_audience_code
        """,
        program_filter_params,
    ):
        counts[_normalized_text(row.get("current_audience_code"))] = int(row.get("total") or 0)
    return counts


def get_current_audience_member_counts(
    *, program_id: int | None = None, include_unscoped: bool = False
) -> dict[str, int]:
    return get_current_member_audience_counts(
        program_id=program_id,
        include_unscoped=include_unscoped,
    )


def list_current_member_audience_rows(
    audience_code: str,
    *,
    program_id: int | None = None,
    include_unscoped: bool = False,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    program_filter_sql, program_filter_params = _program_member_filter_sql(
        member_alias="m",
        program_id=program_id,
        include_unscoped=include_unscoped,
    )
    for row in _fetchall_dicts(
        f"""
        SELECT
            e.*,
            m.id AS member_row_id,
            m.external_contact_id AS member_external_contact_id,
            m.phone AS member_phone,
            m.master_customer_id AS member_master_customer_id,
            m.owner_staff_id AS member_owner_staff_id,
            m.in_pool AS member_in_pool,
            m.current_pool AS member_current_pool,
            m.follow_type AS member_follow_type,
            m.questionnaire_status AS member_questionnaire_status,
            m.decision_source AS member_decision_source,
            m.source_type AS member_source_type,
            m.source_channel_id AS member_source_channel_id,
            m.last_active_pool AS member_last_active_pool,
            m.joined_at AS member_joined_at,
            m.last_ai_push_at AS member_last_ai_push_at,
            m.ai_cooldown_until AS member_ai_cooldown_until,
            m.current_audience_code AS member_current_audience_code,
            m.current_audience_entered_at AS member_current_audience_entered_at,
            m.profile_segment_key AS member_profile_segment_key,
            m.behavior_tier_key AS member_behavior_tier_key,
            m.segment_refreshed_at AS member_segment_refreshed_at,
            m.created_at AS member_created_at,
            m.updated_at AS member_updated_at,
            c.customer_name AS member_customer_name
        FROM automation_member_audience_entry e
        INNER JOIN automation_member m ON m.id = e.member_id
        LEFT JOIN contacts c ON c.external_userid = m.external_contact_id AND m.external_contact_id <> ''
        WHERE e.audience_code = ?
          AND e.is_current = ?
          {program_filter_sql}
        ORDER BY e.entered_at ASC, e.id ASC
        """,
        (_normalized_text(audience_code), True, *program_filter_params),
    ):
        items.append(
            {
                **_serialize_member_audience_entry_row(row),
                "member": _serialize_automation_member_row(
                    {
                        "id": row.get("member_row_id"),
                        "external_contact_id": row.get("member_external_contact_id"),
                        "phone": row.get("member_phone"),
                        "master_customer_id": row.get("member_master_customer_id"),
                        "owner_staff_id": row.get("member_owner_staff_id"),
                        "in_pool": row.get("member_in_pool"),
                        "current_pool": row.get("member_current_pool"),
                        "follow_type": row.get("member_follow_type"),
                        "questionnaire_status": row.get("member_questionnaire_status"),
                        "decision_source": row.get("member_decision_source"),
                        "source_type": row.get("member_source_type"),
                        "source_channel_id": row.get("member_source_channel_id"),
                        "last_active_pool": row.get("member_last_active_pool"),
                        "joined_at": row.get("member_joined_at"),
                        "last_ai_push_at": row.get("member_last_ai_push_at"),
                        "ai_cooldown_until": row.get("member_ai_cooldown_until"),
                        "current_audience_code": row.get("member_current_audience_code"),
                        "current_audience_entered_at": row.get("member_current_audience_entered_at"),
                        "profile_segment_key": row.get("member_profile_segment_key"),
                        "behavior_tier_key": row.get("member_behavior_tier_key"),
                        "segment_refreshed_at": row.get("member_segment_refreshed_at"),
                        "created_at": row.get("member_created_at"),
                        "updated_at": row.get("member_updated_at"),
                        "customer_name": row.get("member_customer_name"),
                    }
                ),
            }
        )
    return items


def insert_member_audience_entry_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_member_audience_entry (
            member_id,
            audience_code,
            entered_at,
            exited_at,
            is_current,
            entry_source,
            entry_reason,
            source_snapshot_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("member_id") or 0),
            _normalized_text(payload.get("audience_code")),
            _normalized_text(payload.get("entered_at")),
            _normalized_text(payload.get("exited_at")),
            bool(payload.get("is_current", True)),
            _normalized_text(payload.get("entry_source")) or "system",
            _normalized_text(payload.get("entry_reason")),
            json.dumps(payload.get("source_snapshot_json") or {}, ensure_ascii=False),
        ),
    ).fetchone()
    return _serialize_member_audience_entry_row(dict(row) if row else {})


def close_current_member_audience_entries(
    member_id: int,
    *,
    exited_at: str,
    entry_reason: str = "",
    source_snapshot_json: dict[str, Any] | None = None,
) -> None:
    get_db().execute(
        """
        UPDATE automation_member_audience_entry
        SET is_current = ?,
            exited_at = ?,
            entry_reason = CASE
                WHEN TRIM(COALESCE(?, '')) <> '' THEN ?
                ELSE entry_reason
            END,
            source_snapshot_json = CASE
                WHEN TRIM(COALESCE(?, '')) <> '' THEN ?
                ELSE source_snapshot_json
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE member_id = ?
          AND is_current = ?
        """,
        (
            False,
            _normalized_text(exited_at),
            _normalized_text(entry_reason),
            _normalized_text(entry_reason),
            json.dumps(source_snapshot_json or {}, ensure_ascii=False),
            json.dumps(source_snapshot_json or {}, ensure_ascii=False),
            int(member_id),
            True,
        ),
    )


def update_member_current_audience_row(member_id: int, *, audience_code: str, entered_at: str) -> None:
    get_db().execute(
        """
        UPDATE automation_member
        SET current_audience_code = ?,
            current_audience_entered_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            _normalized_text(audience_code),
            _normalized_text(entered_at),
            int(member_id),
        ),
    )


def update_member_segment_keys(
    member_id: int,
    *,
    profile_segment_key: str,
    behavior_tier_key: str,
    refreshed_at: str,
) -> None:
    """Materialize profile/behavior segmentation onto automation_member."""
    if not int(member_id or 0):
        return
    get_db().execute(
        """
        UPDATE automation_member
        SET profile_segment_key = ?,
            behavior_tier_key = ?,
            segment_refreshed_at = ?
        WHERE id = ?
        """,
        (
            _normalized_text(profile_segment_key),
            _normalized_text(behavior_tier_key),
            _normalized_text(refreshed_at),
            int(member_id),
        ),
    )


def get_customer_marketing_state_current_row(*, external_userid: str = "", person_id: int | None = None) -> dict[str, Any] | None:
    normalized_external_userid = _normalized_text(external_userid)
    conditions: list[str] = []
    params: list[Any] = []
    if normalized_external_userid:
        conditions.append("external_userid = ?")
        params.append(normalized_external_userid)
    if person_id is not None:
        conditions.append("person_id = ?")
        params.append(int(person_id))
    if not conditions:
        return None
    row = _fetchone_dict(
        f"""
        SELECT *
        FROM customer_marketing_state_current
        WHERE {' OR '.join(conditions)}
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return _serialize_customer_marketing_state_row(row) if row else None


def list_workflow_execution_rows(
    *,
    workflow_id: int | None = None,
    node_id: int | None = None,
    program_id: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_workflow_execution
        WHERE 1 = 1
    """
    params: list[Any] = []
    if program_id is not None:
        sql += " AND program_id = ?"
        params.append(int(program_id))
    if workflow_id is not None:
        sql += " AND workflow_id = ?"
        params.append(int(workflow_id))
    if node_id is not None:
        sql += " AND node_id = ?"
        params.append(int(node_id))
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    return [_serialize_workflow_execution_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def get_workflow_execution_row(execution_row_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_workflow_execution
        WHERE id = ?
        LIMIT 1
        """,
        (int(execution_row_id),),
    )
    return _serialize_workflow_execution_row(row) if row else None


def get_workflow_execution_item_row(execution_item_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_workflow_execution_item
        WHERE id = ?
        LIMIT 1
        """,
        (int(execution_item_id),),
    )
    return _serialize_workflow_execution_item_row(row) if row else None


def get_workflow_execution_row_by_execution_id(execution_id: str) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT *
        FROM automation_workflow_execution
        WHERE execution_id = ?
        LIMIT 1
        """,
        (_normalized_text(execution_id),),
    )
    return _serialize_workflow_execution_row(row) if row else None


def insert_workflow_execution_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow_execution (
            execution_id,
            program_id,
            workflow_id,
            node_id,
            trigger_type,
            audience_code,
            scheduled_for,
            status,
            total_count,
            success_count,
            skipped_count,
            failed_count,
            summary_json,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        ON CONFLICT(execution_id) DO NOTHING
        RETURNING *
        """,
        (
            _normalized_text(payload.get("execution_id")),
            int(payload.get("program_id") or 0) or None,
            int(payload.get("workflow_id") or 0) or None,
            int(payload.get("node_id") or 0) or None,
            _normalized_text(payload.get("trigger_type")) or "scheduled_poll",
            _normalized_text(payload.get("audience_code")),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")) or "pending",
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            json.dumps(payload.get("summary_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return _serialize_workflow_execution_row(dict(row) if row else {}) if row else None


def update_workflow_execution_row(execution_row_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_workflow_execution
        SET program_id = ?,
            workflow_id = ?,
            node_id = ?,
            trigger_type = ?,
            audience_code = ?,
            scheduled_for = ?,
            status = ?,
            total_count = ?,
            success_count = ?,
            skipped_count = ?,
            failed_count = ?,
            summary_json = ?,
            updated_at = CURRENT_TIMESTAMP,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            int(payload.get("program_id") or 0) or None,
            int(payload.get("workflow_id") or 0) or None,
            int(payload.get("node_id") or 0) or None,
            _normalized_text(payload.get("trigger_type")) or "scheduled_poll",
            _normalized_text(payload.get("audience_code")),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")) or "pending",
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            json.dumps(payload.get("summary_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("finished_at")),
            int(execution_row_id),
        ),
    ).fetchone()
    return _serialize_workflow_execution_row(dict(row) if row else {})


def list_workflow_execution_item_rows(execution_row_id: int) -> list[dict[str, Any]]:
    return [
        _serialize_workflow_execution_item_row(row)
        for row in _fetchall_dicts(
            """
            SELECT *
            FROM automation_workflow_execution_item
            WHERE execution_id = ?
            ORDER BY id ASC
            """,
            (int(execution_row_id),),
        )
    ]


def get_workflow_execution_item_count_map(execution_row_ids: list[int]) -> dict[int, dict[str, int]]:
    normalized_ids = [int(item) for item in execution_row_ids if int(item or 0) > 0]
    if not normalized_ids:
        return {}
    placeholders = ",".join("?" for _ in normalized_ids)
    rows = _fetchall_dicts(
        f"""
        SELECT
            execution_id,
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END), 0) AS success_count,
            COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count,
            COALESCE(SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped_count
        FROM automation_workflow_execution_item
        WHERE execution_id IN ({placeholders})
        GROUP BY execution_id
        """,
        tuple(normalized_ids),
    )
    return {
        int(row.get("execution_id") or 0): {
            "total_count": int(row.get("total_count") or 0),
            "success_count": int(row.get("success_count") or 0),
            "failed_count": int(row.get("failed_count") or 0),
            "skipped_count": int(row.get("skipped_count") or 0),
        }
        for row in rows
    }


def list_workflow_sent_timed_execution_history_rows(
    *,
    workflow_id: int,
    audience_entry_ids: list[int],
    trigger_modes: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_entry_ids = [int(item) for item in audience_entry_ids if int(item or 0) > 0]
    if not normalized_entry_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_entry_ids)
    normalized_trigger_modes = [_normalized_text(item) for item in (trigger_modes or []) if _normalized_text(item)]
    if not normalized_trigger_modes:
        normalized_trigger_modes = ["scheduled"]
    trigger_mode_placeholders = ",".join("?" for _ in normalized_trigger_modes)
    return _fetchall_dicts(
        f"""
        SELECT
            ei.execution_id,
            ei.workflow_id,
            ei.node_id,
            ei.member_id,
            ei.audience_entry_id,
            ei.status,
            ei.error_message,
            ei.sent_at,
            e.scheduled_for,
            e.trigger_type
        FROM automation_workflow_execution_item AS ei
        INNER JOIN automation_workflow_execution AS e
          ON e.id = ei.execution_id
        INNER JOIN automation_workflow_node AS n
          ON n.id = ei.node_id
        WHERE ei.workflow_id = ?
          AND ei.audience_entry_id IN ({placeholders})
          AND COALESCE(n.trigger_mode, '') IN ({trigger_mode_placeholders})
          AND ei.status = 'sent'
        ORDER BY e.scheduled_for ASC, ei.id ASC
        """,
        (int(workflow_id), *normalized_entry_ids, *normalized_trigger_modes),
    )


def list_recent_workflow_execution_item_rows(*, limit: int = 50, status: str = "") -> list[dict[str, Any]]:
    sql = """
        SELECT *
        FROM automation_workflow_execution_item
        WHERE 1 = 1
    """
    params: list[Any] = []
    if _normalized_text(status):
        sql += " AND status = ?"
        params.append(_normalized_text(status))
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    return [_serialize_workflow_execution_item_row(row) for row in _fetchall_dicts(sql, tuple(params))]


def insert_workflow_execution_item_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        INSERT INTO automation_workflow_execution_item (
            execution_id,
            workflow_id,
            node_id,
            member_id,
            audience_entry_id,
            external_contact_id,
            rendered_content_text,
            content_snapshot_json,
            agent_code,
            agent_run_id,
            agent_output_id,
            status,
            error_message,
            send_record_id,
            sent_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(execution_id, member_id) DO NOTHING
        RETURNING *
        """,
        (
            int(payload.get("execution_id") or 0),
            int(payload.get("workflow_id") or 0) or None,
            int(payload.get("node_id") or 0) or None,
            int(payload.get("member_id") or 0) or None,
            int(payload.get("audience_entry_id") or 0) or None,
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("rendered_content_text")),
            json.dumps(payload.get("content_snapshot_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("agent_run_id")),
            _normalized_text(payload.get("agent_output_id")),
            _normalized_text(payload.get("status")) or "pending",
            _normalized_text(payload.get("error_message")),
            int(payload.get("send_record_id") or 0) or None,
            _normalized_text(payload.get("sent_at")),
        ),
    ).fetchone()
    return _serialize_workflow_execution_item_row(dict(row) if row else {}) if row else None


def update_workflow_execution_item_row(execution_item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_workflow_execution_item
        SET workflow_id = ?,
            node_id = ?,
            member_id = ?,
            audience_entry_id = ?,
            external_contact_id = ?,
            rendered_content_text = ?,
            content_snapshot_json = ?,
            agent_code = ?,
            agent_run_id = ?,
            agent_output_id = ?,
            status = ?,
            error_message = ?,
            send_record_id = ?,
            sent_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            int(payload.get("workflow_id") or 0) or None,
            int(payload.get("node_id") or 0) or None,
            int(payload.get("member_id") or 0) or None,
            int(payload.get("audience_entry_id") or 0) or None,
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("rendered_content_text")),
            json.dumps(payload.get("content_snapshot_json") or {}, ensure_ascii=False),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("agent_run_id")),
            _normalized_text(payload.get("agent_output_id")),
            _normalized_text(payload.get("status")) or "pending",
            _normalized_text(payload.get("error_message")),
            int(payload.get("send_record_id") or 0) or None,
            _normalized_text(payload.get("sent_at")),
            int(execution_item_id),
        ),
    ).fetchone()
    return _serialize_workflow_execution_item_row(dict(row) if row else {})
