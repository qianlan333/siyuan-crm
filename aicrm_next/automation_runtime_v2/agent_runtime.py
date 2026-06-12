from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from aicrm_next.shared.postgres_connection import get_db

from .domain import as_int, text


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _columns(table: str) -> set[str]:
    rows = get_db().execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ?
        """,
        (table,),
    ).fetchall()
    return {text(row.get("column_name")) for row in rows}


def _insert_available(table: str, values: dict[str, Any]) -> dict[str, Any]:
    columns = [key for key in values if key in _columns(table)]
    if not columns:
        return {}
    placeholders = ", ".join(["?"] * len(columns))
    col_sql = ", ".join(columns)
    row = get_db().execute(
        f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}) RETURNING *",
        tuple(values[key] for key in columns),
    ).fetchone()
    return dict(row or {})


def _update_available(table: str, row_id: int, values: dict[str, Any]) -> dict[str, Any]:
    columns = [key for key in values if key in _columns(table)]
    if not columns or int(row_id or 0) <= 0:
        return {}
    assignments = ", ".join(f"{key} = ?" for key in columns)
    row = get_db().execute(
        f"UPDATE {table} SET {assignments} WHERE id = ? RETURNING *",
        tuple(values[key] for key in columns) + (int(row_id),),
    ).fetchone()
    return dict(row or {})


def _hash_text(value: str) -> str:
    return hashlib.sha256(text(value).encode("utf-8")).hexdigest()[:24]


def create_agent_run(
    *,
    agent_code: str,
    task: dict[str, Any],
    plan: dict[str, Any],
    membership: dict[str, Any],
    event: dict[str, Any] | None,
    stage_entry: dict[str, Any] | None,
    variables: dict[str, Any],
) -> dict[str, Any]:
    run_id = f"runtime_v2_agent_run_{uuid4().hex}"
    request_id = f"runtime_v2_agent_request_{uuid4().hex}"
    trace_id = f"v2:agent:{as_int(plan.get('id'))}:task:{as_int(task.get('id'))}:member:{as_int(membership.get('id'))}"
    runtime_metadata = {
        "runtime_version": "v2",
        "task_plan_id": as_int(plan.get("id")),
        "program_id": as_int(plan.get("program_id")),
        "task_id": as_int(task.get("id")),
        "membership_id": as_int(membership.get("id")),
        "event_id": as_int((event or {}).get("id")) or None,
        "stage_entry_id": as_int((stage_entry or {}).get("id")) or None,
    }
    return _insert_available(
        "automation_agent_run",
        {
            "run_id": run_id,
            "request_id": request_id,
            "batch_id": "",
            "userid": "",
            "external_contact_id": text(membership.get("external_userid")),
            "agent_code": text(agent_code),
            "agent_type": "runtime_v2",
            "provider": "",
            "input_snapshot_json": _json({"runtime_metadata": runtime_metadata, "event": event or {}, "stage": stage_entry or {}, "membership": membership}),
            "variables_snapshot_json": _json(variables),
            "final_prompt_preview": "",
            "role_prompt_version": as_int((task.get("agent_prompt") or {}).get("published_version")),
            "task_prompt_version": as_int((task.get("agent_prompt") or {}).get("published_version")),
            "status": "running",
            "error_code": "",
            "error_message": "",
            "latency_ms": 0,
            "source": "automation_runtime_v2",
            "parent_run_id": "",
            "replay_of_run_id": "",
            "trace_id": trace_id,
        },
    )


def complete_agent_run(run: dict[str, Any], *, status: str, provider: str = "", latency_ms: int = 0, final_prompt_preview: str = "", error_code: str = "", error_message: str = "") -> dict[str, Any]:
    return _update_available(
        "automation_agent_run",
        as_int(run.get("id")),
        {
            "status": text(status),
            "provider": text(provider),
            "latency_ms": int(latency_ms or 0),
            "final_prompt_preview": text(final_prompt_preview)[:500],
            "error_code": text(error_code),
            "error_message": text(error_message)[:1000],
        },
    )


def log_llm_call(
    *,
    run: dict[str, Any],
    agent_code: str,
    provider: str,
    model: str,
    status: str,
    latency_ms: int = 0,
    error_code: str = "",
    error_message: str = "",
    request_summary: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None,
    prompt_text: str = "",
) -> dict[str, Any]:
    summary = {
        "provider": text(provider),
        "prompt_hash": _hash_text(prompt_text),
        "request_summary": request_summary or {},
        "response_summary": response_summary or {},
        "error_code": text(error_code),
    }
    return _insert_available(
        "automation_agent_llm_call_log",
        {
            "run_id": text(run.get("run_id")),
            "agent_code": text(agent_code),
            "provider": text(provider),
            "model": text(model),
            "model_name": text(model),
            "request_id": text(run.get("request_id")),
            "prompt_hash": _hash_text(prompt_text),
            "request_summary": _json(request_summary or {}),
            "response_summary": _json(response_summary or {}),
            "status": text(status),
            "latency_ms": int(latency_ms or 0),
            "error_code": text(error_code),
            "error_message": (text(error_message) or json.dumps(summary, ensure_ascii=False))[:1000],
        },
    )


def record_agent_output(
    *,
    run: dict[str, Any],
    agent_code: str,
    external_userid: str,
    final_text: str,
    applied_status: str = "generated",
    error_code: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    output_id = f"runtime_v2_agent_output_{uuid4().hex}"
    normalized = {"runtime_version": "v2", "run_id": text(run.get("run_id")), "content_chars": len(text(final_text))}
    return _insert_available(
        "automation_agent_output",
        {
            "output_id": output_id,
            "run_id": text(run.get("run_id")),
            "request_id": text(run.get("request_id")),
            "userid": "",
            "external_contact_id": text(external_userid),
            "agent_code": text(agent_code),
            "output_type": "reply_draft",
            "raw_output_text": text(final_text),
            "normalized_output_json": _json(normalized),
            "rendered_output_text": text(final_text),
            "target_agent_code": text(agent_code),
            "target_pool": "automation_runtime_v2",
            "confidence": 1,
            "reason": "",
            "need_human_review": False,
            "applied_status": text(applied_status),
            "adopted_by": "",
            "adopted_action": "",
            "outcome_status": "",
            "outcome_value": "",
            "revision_of_output_id": "",
            "error_code": text(error_code),
            "error_message": text(error_message)[:1000],
        },
    )
