"""Data-access layer for the automation_conversion agents subdomain.

Extracted from automation_conversion/repo.py (阶段 4.2 拆分蓝图).

Covers 48 functions across these tables:
- automation_agent_prompt
- automation_agent_llm_call_log
- automation_agent_router_config
- automation_agent_config
- automation_agent_skill
- automation_agent_run
- automation_agent_output
- automation_agent_output_export_job
- automation_agent_skill_call_audit

External callers (services / orchestration / workflow) keep importing through
``automation_conversion.repo`` — repo.py re-exports everything via
``from .agents.repo import *``. This file is purely for code organisation;
zero behaviour change.
"""

from __future__ import annotations

from typing import Any

from ....db import cast_text, get_db, is_postgres
from .._repo_helpers import (
    _db_bool,
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _json_loads,
    _normalized_text,
    _row_bool,
)


def get_agent_prompt_row(agent_code: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_prompt_registry
        WHERE agent_code = ?
        LIMIT 1
        """,
        (_normalized_text(agent_code),),
    )


def list_agent_prompt_rows() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_prompt_registry
        ORDER BY updated_at DESC, id DESC
        """
    )


def insert_agent_prompt_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_prompt_registry (
            agent_code,
            display_name,
            prompt_text,
            enabled,
            version,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("display_name")),
            _normalized_text(payload.get("prompt_text")),
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("version") or 1),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_prompt_row(agent_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_prompt_registry
        SET display_name = ?,
            prompt_text = ?,
            enabled = ?,
            version = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE agent_code = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("display_name")),
            _normalized_text(payload.get("prompt_text")),
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("version") or 1),
            _normalized_text(agent_code),
        ),
    ).fetchone()
    return dict(row) if row else {}


def delete_agent_prompt_row(agent_code: str) -> None:
    get_db().execute(
        """
        DELETE FROM automation_agent_prompt_registry
        WHERE agent_code = ?
        """,
        (_normalized_text(agent_code),),
    )


def insert_agent_llm_call_log(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_llm_call_log (
            agent_code,
            model_name,
            request_id,
            status,
            latency_ms,
            error_message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("model_name")),
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("latency_ms") or 0),
            _normalized_text(payload.get("error_message")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_recent_agent_llm_call_logs(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_llm_call_log
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def get_agent_router_config() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_router_config
        WHERE config_key = 'default'
        LIMIT 1
        """
    )


def insert_agent_router_config(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_router_config (
            config_key,
            enabled,
            webhook_url,
            signature_token,
            signature_secret,
            signature_header,
            timeout_seconds,
            retry_count,
            fallback_strategy_json,
            request_sample_json,
            response_sample_json,
            last_status,
            last_error,
            last_called_at,
            updated_by,
            updated_source,
            created_at,
            updated_at
        )
        VALUES (
            'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING *
        """,
        (
            _db_bool(bool(payload.get("enabled"))),
            _normalized_text(payload.get("webhook_url")),
            _normalized_text(payload.get("signature_token")),
            _normalized_text(payload.get("signature_secret")),
            _normalized_text(payload.get("signature_header")) or "X-Lobster-Signature",
            int(payload.get("timeout_seconds") or 8),
            int(payload.get("retry_count") or 1),
            _json_dumps(payload.get("fallback_strategy_json") or {}),
            _json_dumps(payload.get("request_sample_json") or {}),
            _json_dumps(payload.get("response_sample_json") or {}),
            _normalized_text(payload.get("last_status")),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("last_called_at")),
            _normalized_text(payload.get("updated_by")),
            _normalized_text(payload.get("updated_source")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def save_agent_router_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_agent_router_config()
    if existing:
        row = get_db().execute(
            """
            UPDATE automation_agent_router_config
            SET enabled = ?,
                webhook_url = ?,
                signature_token = ?,
                signature_secret = ?,
                signature_header = ?,
                timeout_seconds = ?,
                retry_count = ?,
                fallback_strategy_json = ?,
                request_sample_json = ?,
                response_sample_json = ?,
                last_status = ?,
                last_error = ?,
                last_called_at = ?,
                updated_by = ?,
                updated_source = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                _normalized_text(payload.get("webhook_url")),
                _normalized_text(payload.get("signature_token")),
                _normalized_text(payload.get("signature_secret")),
                _normalized_text(payload.get("signature_header")) or "X-Lobster-Signature",
                int(payload.get("timeout_seconds") or 8),
                int(payload.get("retry_count") or 1),
                _json_dumps(payload.get("fallback_strategy_json") or {}),
                _json_dumps(payload.get("request_sample_json") or {}),
                _json_dumps(payload.get("response_sample_json") or {}),
                _normalized_text(payload.get("last_status")),
                _normalized_text(payload.get("last_error")),
                _normalized_text(payload.get("last_called_at")),
                _normalized_text(payload.get("updated_by")),
                _normalized_text(payload.get("updated_source")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    return insert_agent_router_config(payload)


def get_agent_config_row(agent_code: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_config
        WHERE agent_code = ?
        LIMIT 1
        """,
        (_normalized_text(agent_code),),
    )


def list_agent_config_rows() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_config
        ORDER BY updated_at DESC, id DESC
        """
    )


def insert_agent_config_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_config (
            agent_code,
            display_name,
            pool_keys_json,
            enabled,
            draft_role_prompt,
            draft_task_prompt,
            draft_variables_json,
            draft_output_schema_json,
            published_role_prompt,
            published_task_prompt,
            published_variables_json,
            published_output_schema_json,
            draft_version,
            published_version,
            published_at,
            published_by,
            last_modified_at,
            last_modified_by,
            last_modified_source,
            last_change_summary,
            submitted_for_publish,
            submitted_at,
            submitted_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("display_name")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _db_bool(bool(payload.get("enabled"))),
            _normalized_text(payload.get("draft_role_prompt")),
            _normalized_text(payload.get("draft_task_prompt")),
            _json_dumps(payload.get("draft_variables_json") or payload.get("draft_variables") or []),
            _json_dumps(payload.get("draft_output_schema_json") or payload.get("draft_output_schema") or []),
            _normalized_text(payload.get("published_role_prompt")),
            _normalized_text(payload.get("published_task_prompt")),
            _json_dumps(payload.get("published_variables_json") or payload.get("published_variables") or []),
            _json_dumps(payload.get("published_output_schema_json") or payload.get("published_output_schema") or []),
            int(payload.get("draft_version") or 1),
            int(payload.get("published_version") or 0),
            _normalized_text(payload.get("published_at")),
            _normalized_text(payload.get("published_by")),
            _normalized_text(payload.get("last_modified_at")),
            _normalized_text(payload.get("last_modified_by")),
            _normalized_text(payload.get("last_modified_source")),
            _normalized_text(payload.get("last_change_summary")),
            _db_bool(bool(payload.get("submitted_for_publish"))),
            _normalized_text(payload.get("submitted_at")),
            _normalized_text(payload.get("submitted_by")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_config_row(agent_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_config
        SET display_name = ?,
            pool_keys_json = ?,
            enabled = ?,
            draft_role_prompt = ?,
            draft_task_prompt = ?,
            draft_variables_json = ?,
            draft_output_schema_json = ?,
            published_role_prompt = ?,
            published_task_prompt = ?,
            published_variables_json = ?,
            published_output_schema_json = ?,
            draft_version = ?,
            published_version = ?,
            published_at = ?,
            published_by = ?,
            last_modified_at = ?,
            last_modified_by = ?,
            last_modified_source = ?,
            last_change_summary = ?,
            submitted_for_publish = ?,
            submitted_at = ?,
            submitted_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE agent_code = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("display_name")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _db_bool(bool(payload.get("enabled"))),
            _normalized_text(payload.get("draft_role_prompt")),
            _normalized_text(payload.get("draft_task_prompt")),
            _json_dumps(payload.get("draft_variables_json") or payload.get("draft_variables") or []),
            _json_dumps(payload.get("draft_output_schema_json") or payload.get("draft_output_schema") or []),
            _normalized_text(payload.get("published_role_prompt")),
            _normalized_text(payload.get("published_task_prompt")),
            _json_dumps(payload.get("published_variables_json") or payload.get("published_variables") or []),
            _json_dumps(payload.get("published_output_schema_json") or payload.get("published_output_schema") or []),
            int(payload.get("draft_version") or 1),
            int(payload.get("published_version") or 0),
            _normalized_text(payload.get("published_at")),
            _normalized_text(payload.get("published_by")),
            _normalized_text(payload.get("last_modified_at")),
            _normalized_text(payload.get("last_modified_by")),
            _normalized_text(payload.get("last_modified_source")),
            _normalized_text(payload.get("last_change_summary")),
            _db_bool(bool(payload.get("submitted_for_publish"))),
            _normalized_text(payload.get("submitted_at")),
            _normalized_text(payload.get("submitted_by")),
            _normalized_text(agent_code),
        ),
    ).fetchone()
    return dict(row) if row else {}


def delete_agent_config_row(agent_code: str) -> None:
    get_db().execute(
        """
        DELETE FROM automation_agent_config
        WHERE agent_code = ?
        """,
        (_normalized_text(agent_code),),
    )


def get_agent_skill_row(skill_code: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_skill_registry
        WHERE skill_code = ?
        LIMIT 1
        """,
        (_normalized_text(skill_code),),
    )


def list_agent_skill_rows() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_skill_registry
        ORDER BY updated_at DESC, id DESC
        """
    )


def list_agent_skill_rows_for_agent(agent_code: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_skill_registry
        WHERE agent_code = ?
        ORDER BY skill_code ASC, id ASC
        """,
        (_normalized_text(agent_code),),
    )


def insert_agent_skill_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_skill_registry (
            skill_code,
            agent_code,
            pool_keys_json,
            read_capabilities_json,
            write_capabilities_json,
            enabled,
            input_schema_json,
            output_schema_json,
            permission_notes,
            idempotency_notes,
            audit_notes,
            example_request_json,
            example_response_json,
            last_call_status,
            last_error,
            last_called_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("skill_code")),
            _normalized_text(payload.get("agent_code")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _json_dumps(payload.get("read_capabilities_json") or payload.get("read_capabilities") or []),
            _json_dumps(payload.get("write_capabilities_json") or payload.get("write_capabilities") or []),
            _db_bool(bool(payload.get("enabled"))),
            _json_dumps(payload.get("input_schema_json") or payload.get("input_schema") or {}),
            _json_dumps(payload.get("output_schema_json") or payload.get("output_schema") or {}),
            _normalized_text(payload.get("permission_notes")),
            _normalized_text(payload.get("idempotency_notes")),
            _normalized_text(payload.get("audit_notes")),
            _json_dumps(payload.get("example_request_json") or payload.get("example_request") or {}),
            _json_dumps(payload.get("example_response_json") or payload.get("example_response") or {}),
            _normalized_text(payload.get("last_call_status")),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("last_called_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_skill_row(skill_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_skill_registry
        SET agent_code = ?,
            pool_keys_json = ?,
            read_capabilities_json = ?,
            write_capabilities_json = ?,
            enabled = ?,
            input_schema_json = ?,
            output_schema_json = ?,
            permission_notes = ?,
            idempotency_notes = ?,
            audit_notes = ?,
            example_request_json = ?,
            example_response_json = ?,
            last_call_status = ?,
            last_error = ?,
            last_called_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE skill_code = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _json_dumps(payload.get("read_capabilities_json") or payload.get("read_capabilities") or []),
            _json_dumps(payload.get("write_capabilities_json") or payload.get("write_capabilities") or []),
            _db_bool(bool(payload.get("enabled"))),
            _json_dumps(payload.get("input_schema_json") or payload.get("input_schema") or {}),
            _json_dumps(payload.get("output_schema_json") or payload.get("output_schema") or {}),
            _normalized_text(payload.get("permission_notes")),
            _normalized_text(payload.get("idempotency_notes")),
            _normalized_text(payload.get("audit_notes")),
            _json_dumps(payload.get("example_request_json") or payload.get("example_request") or {}),
            _json_dumps(payload.get("example_response_json") or payload.get("example_response") or {}),
            _normalized_text(payload.get("last_call_status")),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("last_called_at")),
            _normalized_text(skill_code),
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_agent_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_run (
            run_id,
            request_id,
            batch_id,
            userid,
            external_contact_id,
            agent_code,
            agent_type,
            provider,
            input_snapshot_json,
            variables_snapshot_json,
            final_prompt_preview,
            role_prompt_version,
            task_prompt_version,
            status,
            error_code,
            error_message,
            latency_ms,
            source,
            parent_run_id,
            replay_of_run_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("run_id")),
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("batch_id")),
            _normalized_text(payload.get("userid")),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("agent_type")),
            _normalized_text(payload.get("provider")),
            _json_dumps(payload.get("input_snapshot_json") or payload.get("input_snapshot") or {}),
            _json_dumps(payload.get("variables_snapshot_json") or payload.get("variables_snapshot") or {}),
            _normalized_text(payload.get("final_prompt_preview")),
            _normalized_text(payload.get("role_prompt_version")),
            _normalized_text(payload.get("task_prompt_version")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            int(payload.get("latency_ms") or 0),
            _normalized_text(payload.get("source")),
            _normalized_text(payload.get("parent_run_id")),
            _normalized_text(payload.get("replay_of_run_id")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_run(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_run
        SET request_id = ?,
            batch_id = ?,
            userid = ?,
            external_contact_id = ?,
            agent_code = ?,
            agent_type = ?,
            provider = ?,
            input_snapshot_json = ?,
            variables_snapshot_json = ?,
            final_prompt_preview = ?,
            role_prompt_version = ?,
            task_prompt_version = ?,
            status = ?,
            error_code = ?,
            error_message = ?,
            latency_ms = ?,
            source = ?,
            parent_run_id = ?,
            replay_of_run_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE run_id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("batch_id")),
            _normalized_text(payload.get("userid")),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("agent_type")),
            _normalized_text(payload.get("provider")),
            _json_dumps(payload.get("input_snapshot_json") or payload.get("input_snapshot") or {}),
            _json_dumps(payload.get("variables_snapshot_json") or payload.get("variables_snapshot") or {}),
            _normalized_text(payload.get("final_prompt_preview")),
            _normalized_text(payload.get("role_prompt_version")),
            _normalized_text(payload.get("task_prompt_version")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            int(payload.get("latency_ms") or 0),
            _normalized_text(payload.get("source")),
            _normalized_text(payload.get("parent_run_id")),
            _normalized_text(payload.get("replay_of_run_id")),
            _normalized_text(run_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_agent_run_row(run_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_run
        WHERE run_id = ?
        LIMIT 1
        """,
        (_normalized_text(run_id),),
    )


def get_agent_run_row_by_request_id(request_id: str) -> dict[str, Any] | None:
    normalized_request_id = _normalized_text(request_id)
    if not normalized_request_id:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_run
        WHERE request_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_request_id,),
    )


def _agent_run_where_sql(filters: dict[str, Any] | None = None) -> tuple[str, list[Any]]:
    filters = dict(filters or {})
    clauses: list[str] = []
    params: list[Any] = []
    if _normalized_text(filters.get("request_id")):
        clauses.append("request_id = ?")
        params.append(_normalized_text(filters.get("request_id")))
    if _normalized_text(filters.get("batch_id")):
        clauses.append("batch_id = ?")
        params.append(_normalized_text(filters.get("batch_id")))
    if _normalized_text(filters.get("agent_code")):
        clauses.append("agent_code = ?")
        params.append(_normalized_text(filters.get("agent_code")))
    if _normalized_text(filters.get("userid")):
        clauses.append("userid = ?")
        params.append(_normalized_text(filters.get("userid")))
    if _normalized_text(filters.get("external_contact_id")):
        clauses.append("external_contact_id = ?")
        params.append(_normalized_text(filters.get("external_contact_id")))
    if _normalized_text(filters.get("date_from")):
        clauses.append("created_at >= ?")
        params.append(_normalized_text(filters.get("date_from")))
    if _normalized_text(filters.get("date_to")):
        clauses.append("created_at <= ?")
        params.append(_normalized_text(filters.get("date_to")))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def count_agent_run_rows(filters: dict[str, Any] | None = None) -> int:
    where_sql, params = _agent_run_where_sql(filters)
    row = _fetchone_dict(f"SELECT COUNT(*) AS total FROM automation_agent_run {where_sql}", tuple(params)) or {}
    return int(row.get("total") or 0)


def list_agent_run_rows(*, filters: dict[str, Any] | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    where_sql, params = _agent_run_where_sql(filters)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_agent_run
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        tuple([*params, int(limit), int(offset)]),
    )


def _agent_output_where_sql(filters: dict[str, Any] | None = None) -> tuple[str, list[Any]]:
    filters = dict(filters or {})
    clauses: list[str] = []
    params: list[Any] = []
    if _normalized_text(filters.get("request_id")):
        clauses.append("request_id = ?")
        params.append(_normalized_text(filters.get("request_id")))
    if _normalized_text(filters.get("batch_id")):
        clauses.append("request_id IN (SELECT request_id FROM automation_agent_run WHERE batch_id = ?)")
        params.append(_normalized_text(filters.get("batch_id")))
    if _normalized_text(filters.get("agent_code")):
        clauses.append("agent_code = ?")
        params.append(_normalized_text(filters.get("agent_code")))
    if _normalized_text(filters.get("output_type")):
        clauses.append("output_type = ?")
        params.append(_normalized_text(filters.get("output_type")))
    elif bool(filters.get("scripts_only")):
        clauses.append("output_type IN ('agent_reply_draft', 'agent_reply_final')")
    if _normalized_text(filters.get("userid")):
        clauses.append("userid = ?")
        params.append(_normalized_text(filters.get("userid")))
    if _normalized_text(filters.get("external_contact_id")):
        clauses.append("external_contact_id = ?")
        params.append(_normalized_text(filters.get("external_contact_id")))
    if _normalized_text(filters.get("target_pool")):
        clauses.append("target_pool = ?")
        params.append(_normalized_text(filters.get("target_pool")))
    if _normalized_text(filters.get("applied_status")):
        clauses.append("applied_status = ?")
        params.append(_normalized_text(filters.get("applied_status")))
    if filters.get("min_confidence") not in (None, ""):
        clauses.append("confidence >= ?")
        params.append(float(filters.get("min_confidence") or 0))
    if filters.get("max_confidence") not in (None, ""):
        clauses.append("confidence <= ?")
        params.append(float(filters.get("max_confidence") or 0))
    if _normalized_text(filters.get("date_from")):
        clauses.append("created_at >= ?")
        params.append(_normalized_text(filters.get("date_from")))
    if _normalized_text(filters.get("date_to")):
        clauses.append("created_at <= ?")
        params.append(_normalized_text(filters.get("date_to")))
    if _normalized_text(filters.get("has_error")):
        wanted = _normalized_text(filters.get("has_error")).lower() in {"1", "true", "yes", "on"}
        clauses.append("(error_code <> '' OR error_message <> '')" if wanted else "(error_code = '' AND error_message = '')")
    if _normalized_text(filters.get("current_pool")):
        clauses.append(
            "external_contact_id IN (SELECT external_contact_id FROM automation_member WHERE current_pool = ?)"
        )
        params.append(_normalized_text(filters.get("current_pool")))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def count_agent_output_rows(filters: dict[str, Any] | None = None) -> int:
    where_sql, params = _agent_output_where_sql(filters)
    row = _fetchone_dict(f"SELECT COUNT(*) AS total FROM automation_agent_output {where_sql}", tuple(params)) or {}
    return int(row.get("total") or 0)


def list_agent_output_rows(*, filters: dict[str, Any] | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    where_sql, params = _agent_output_where_sql(filters)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_agent_output
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        tuple([*params, int(limit), int(offset)]),
    )


def insert_agent_output(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_output (
            output_id,
            run_id,
            request_id,
            userid,
            external_contact_id,
            agent_code,
            output_type,
            raw_output_text,
            normalized_output_json,
            rendered_output_text,
            target_agent_code,
            target_pool,
            confidence,
            reason,
            need_human_review,
            applied_status,
            applied_at,
            adopted_by,
            adopted_action,
            adopted_at,
            outcome_status,
            outcome_value,
            revision_of_output_id,
            error_code,
            error_message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("output_id")),
            _normalized_text(payload.get("run_id")),
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("userid")),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("output_type")),
            _normalized_text(payload.get("raw_output_text")),
            _json_dumps(payload.get("normalized_output_json") or payload.get("normalized_output") or {}),
            _normalized_text(payload.get("rendered_output_text")),
            _normalized_text(payload.get("target_agent_code")),
            _normalized_text(payload.get("target_pool")),
            float(payload.get("confidence") or 0),
            _normalized_text(payload.get("reason")),
            _db_bool(bool(payload.get("need_human_review"))),
            _normalized_text(payload.get("applied_status")),
            _normalized_text(payload.get("applied_at")),
            _normalized_text(payload.get("adopted_by")),
            _normalized_text(payload.get("adopted_action")),
            _normalized_text(payload.get("adopted_at")),
            _normalized_text(payload.get("outcome_status")),
            _normalized_text(payload.get("outcome_value")),
            _normalized_text(payload.get("revision_of_output_id")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_output(output_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = deserialize_agent_output_row(get_agent_output_row(output_id) or {})
    if not existing:
        return {}
    row = get_db().execute(
        """
        UPDATE automation_agent_output
        SET run_id = ?,
            request_id = ?,
            userid = ?,
            external_contact_id = ?,
            agent_code = ?,
            output_type = ?,
            raw_output_text = ?,
            normalized_output_json = ?,
            rendered_output_text = ?,
            target_agent_code = ?,
            target_pool = ?,
            confidence = ?,
            reason = ?,
            need_human_review = ?,
            applied_status = ?,
            applied_at = ?,
            adopted_by = ?,
            adopted_action = ?,
            adopted_at = ?,
            outcome_status = ?,
            outcome_value = ?,
            revision_of_output_id = ?,
            error_code = ?,
            error_message = ?
        WHERE output_id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("run_id", existing.get("run_id"))),
            _normalized_text(payload.get("request_id", existing.get("request_id"))),
            _normalized_text(payload.get("userid", existing.get("userid"))),
            _normalized_text(payload.get("external_contact_id", existing.get("external_contact_id"))),
            _normalized_text(payload.get("agent_code", existing.get("agent_code"))),
            _normalized_text(payload.get("output_type", existing.get("output_type"))),
            _normalized_text(payload.get("raw_output_text", existing.get("raw_output_text"))),
            _json_dumps(payload.get("normalized_output_json") or payload.get("normalized_output") or existing.get("normalized_output_json") or {}),
            _normalized_text(payload.get("rendered_output_text", existing.get("rendered_output_text"))),
            _normalized_text(payload.get("target_agent_code", existing.get("target_agent_code"))),
            _normalized_text(payload.get("target_pool", existing.get("target_pool"))),
            float(payload.get("confidence", existing.get("confidence") or 0) or 0),
            _normalized_text(payload.get("reason", existing.get("reason"))),
            _db_bool(bool(payload.get("need_human_review", existing.get("need_human_review")))),
            _normalized_text(payload.get("applied_status", existing.get("applied_status"))),
            _normalized_text(payload.get("applied_at", existing.get("applied_at"))),
            _normalized_text(payload.get("adopted_by", existing.get("adopted_by"))),
            _normalized_text(payload.get("adopted_action", existing.get("adopted_action"))),
            _normalized_text(payload.get("adopted_at", existing.get("adopted_at"))),
            _normalized_text(payload.get("outcome_status", existing.get("outcome_status"))),
            _normalized_text(payload.get("outcome_value", existing.get("outcome_value"))),
            _normalized_text(payload.get("revision_of_output_id", existing.get("revision_of_output_id"))),
            _normalized_text(payload.get("error_code", existing.get("error_code"))),
            _normalized_text(payload.get("error_message", existing.get("error_message"))),
            _normalized_text(output_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_agent_output_row(output_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_output
        WHERE output_id = ?
        LIMIT 1
        """,
        (_normalized_text(output_id),),
    )


def get_latest_agent_output_row_by_request_id(request_id: str, *, output_types: list[str] | None = None) -> dict[str, Any] | None:
    normalized_request_id = _normalized_text(request_id)
    if not normalized_request_id:
        return None
    clauses = ["request_id = ?"]
    params: list[Any] = [normalized_request_id]
    normalized_types = [_normalized_text(item) for item in list(output_types or []) if _normalized_text(item)]
    if normalized_types:
        placeholders = ",".join("?" for _ in normalized_types)
        clauses.append(f"output_type IN ({placeholders})")
        params.extend(normalized_types)
    where_sql = " AND ".join(clauses)
    return _fetchone_dict(
        f"""
        SELECT *
        FROM automation_agent_output
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )


def list_agent_outputs_by_run_id(run_id: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_output
        WHERE run_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (_normalized_text(run_id),),
    )


def insert_agent_output_export_job(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_output_export_job (
            job_id,
            requested_by,
            filters_json,
            status,
            total_count,
            exported_count,
            file_name,
            file_content_base64,
            error_message,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("job_id")),
            _normalized_text(payload.get("requested_by")),
            _json_dumps(payload.get("filters_json") or payload.get("filters") or {}),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("exported_count") or 0),
            _normalized_text(payload.get("file_name")),
            _normalized_text(payload.get("file_content_base64")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_output_export_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_output_export_job
        SET requested_by = ?,
            filters_json = ?,
            status = ?,
            total_count = ?,
            exported_count = ?,
            file_name = ?,
            file_content_base64 = ?,
            error_message = ?,
            finished_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("requested_by")),
            _json_dumps(payload.get("filters_json") or payload.get("filters") or {}),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("exported_count") or 0),
            _normalized_text(payload.get("file_name")),
            _normalized_text(payload.get("file_content_base64")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("finished_at")),
            _normalized_text(job_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_agent_output_export_job(job_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_output_export_job
        WHERE job_id = ?
        LIMIT 1
        """,
        (_normalized_text(job_id),),
    )


def count_recent_agent_output_export_jobs(requested_by: str, *, since_text: str) -> int:
    row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM automation_agent_output_export_job
        WHERE requested_by = ?
          AND created_at >= ?
        """,
        (_normalized_text(requested_by), _normalized_text(since_text)),
    ) or {}
    return int(row.get("total") or 0)


def insert_agent_skill_call_audit(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_skill_call_audit (
            call_id,
            skill_code,
            source,
            permissions_scope,
            idempotency_key,
            request_payload_json,
            response_payload_json,
            status,
            error_code,
            error_message,
            latency_ms,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("call_id")),
            _normalized_text(payload.get("skill_code")),
            _normalized_text(payload.get("source")),
            _normalized_text(payload.get("permissions_scope")),
            _normalized_text(payload.get("idempotency_key")),
            _json_dumps(payload.get("request_payload_json") or payload.get("request_payload") or {}),
            _json_dumps(payload.get("response_payload_json") or payload.get("response_payload") or {}),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            int(payload.get("latency_ms") or 0),
        ),
    ).fetchone()
    return dict(row) if row else {}


def deserialize_agent_prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "enabled": _row_bool(row.get("enabled")),
    }


def deserialize_agent_router_config_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "enabled": _row_bool((row or {}).get("enabled")),
        "fallback_strategy_json": _json_loads((row or {}).get("fallback_strategy_json"), default={}),
        "request_sample_json": _json_loads((row or {}).get("request_sample_json"), default={}),
        "response_sample_json": _json_loads((row or {}).get("response_sample_json"), default={}),
    }


def deserialize_agent_config_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "enabled": _row_bool((row or {}).get("enabled")),
        "submitted_for_publish": _row_bool((row or {}).get("submitted_for_publish")),
        "pool_keys_json": _json_loads((row or {}).get("pool_keys_json"), default=[]),
        "draft_variables_json": _json_loads((row or {}).get("draft_variables_json"), default=[]),
        "draft_output_schema_json": _json_loads((row or {}).get("draft_output_schema_json"), default=[]),
        "published_variables_json": _json_loads((row or {}).get("published_variables_json"), default=[]),
        "published_output_schema_json": _json_loads((row or {}).get("published_output_schema_json"), default=[]),
    }


def deserialize_agent_skill_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "enabled": _row_bool((row or {}).get("enabled")),
        "pool_keys_json": _json_loads((row or {}).get("pool_keys_json"), default=[]),
        "read_capabilities_json": _json_loads((row or {}).get("read_capabilities_json"), default=[]),
        "write_capabilities_json": _json_loads((row or {}).get("write_capabilities_json"), default=[]),
        "input_schema_json": _json_loads((row or {}).get("input_schema_json"), default={}),
        "output_schema_json": _json_loads((row or {}).get("output_schema_json"), default={}),
        "example_request_json": _json_loads((row or {}).get("example_request_json"), default={}),
        "example_response_json": _json_loads((row or {}).get("example_response_json"), default={}),
    }


def deserialize_agent_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "input_snapshot_json": _json_loads((row or {}).get("input_snapshot_json"), default={}),
        "variables_snapshot_json": _json_loads((row or {}).get("variables_snapshot_json"), default={}),
    }


def deserialize_agent_output_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "normalized_output_json": _json_loads((row or {}).get("normalized_output_json"), default={}),
        "need_human_review": _row_bool((row or {}).get("need_human_review")),
    }


def deserialize_agent_output_export_job_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "filters_json": _json_loads((row or {}).get("filters_json"), default={}),
    }


def deserialize_agent_skill_call_audit_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "request_payload_json": _json_loads((row or {}).get("request_payload_json"), default={}),
        "response_payload_json": _json_loads((row or {}).get("response_payload_json"), default={}),
    }




__all__ = [
    "_agent_output_where_sql",
    "_agent_run_where_sql",
    "count_agent_output_rows",
    "count_agent_run_rows",
    "count_recent_agent_output_export_jobs",
    "delete_agent_config_row",
    "delete_agent_prompt_row",
    "deserialize_agent_config_row",
    "deserialize_agent_output_export_job_row",
    "deserialize_agent_output_row",
    "deserialize_agent_prompt_row",
    "deserialize_agent_router_config_row",
    "deserialize_agent_run_row",
    "deserialize_agent_skill_call_audit_row",
    "deserialize_agent_skill_row",
    "get_agent_config_row",
    "get_agent_output_export_job",
    "get_agent_output_row",
    "get_agent_prompt_row",
    "get_agent_router_config",
    "get_agent_run_row",
    "get_agent_run_row_by_request_id",
    "get_agent_skill_row",
    "get_latest_agent_output_row_by_request_id",
    "insert_agent_config_row",
    "insert_agent_llm_call_log",
    "insert_agent_output",
    "insert_agent_output_export_job",
    "insert_agent_prompt_row",
    "insert_agent_router_config",
    "insert_agent_run",
    "insert_agent_skill_call_audit",
    "insert_agent_skill_row",
    "list_agent_config_rows",
    "list_agent_output_rows",
    "list_agent_outputs_by_run_id",
    "list_agent_prompt_rows",
    "list_agent_run_rows",
    "list_agent_skill_rows",
    "list_agent_skill_rows_for_agent",
    "list_recent_agent_llm_call_logs",
    "save_agent_router_config",
    "update_agent_config_row",
    "update_agent_output",
    "update_agent_output_export_job",
    "update_agent_prompt_row",
    "update_agent_run",
    "update_agent_skill_row",
]
