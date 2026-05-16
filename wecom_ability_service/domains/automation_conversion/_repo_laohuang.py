"""Laohuang-chat data-access (阶段 4.4).

Extracted from repo.py. Covers automation_laohuang_chat_job table used by
the laohuang-chat side-channel.
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _json_loads,
    _normalized_text,
)


def get_laohuang_chat_job(job_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE id = ?
        LIMIT 1
        """,
        (int(job_id),),
    )


def get_laohuang_chat_job_by_external_message_id(external_message_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE external_message_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (_normalized_text(external_message_id),),
    )


def get_laohuang_chat_job_by_task_id(task_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE laohuang_task_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (_normalized_text(task_id),),
    )


def list_laohuang_chat_jobs_for_review(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE reply_text <> ''
          AND status IN ('callback_success', 'send_success', 'send_failed')
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (max(1, min(50, int(limit or 20))),),
    )


def insert_laohuang_chat_job(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_laohuang_chat_job (
            queue_id,
            member_id,
            external_contact_id,
            phone,
            external_message_id,
            external_session_id,
            laohuang_task_id,
            request_payload_json,
            accepted_payload_json,
            callback_payload_json,
            status,
            reply_text,
            error_code,
            error_message,
            send_channel,
            send_record_id,
            send_result_json,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        RETURNING *
        """,
        (
            payload.get("queue_id"),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            _normalized_text(payload.get("external_message_id")),
            _normalized_text(payload.get("external_session_id")),
            _normalized_text(payload.get("laohuang_task_id")),
            _json_dumps(payload.get("request_payload_json") or payload.get("request_payload") or {}),
            _json_dumps(payload.get("accepted_payload_json") or payload.get("accepted_payload") or {}),
            _json_dumps(payload.get("callback_payload_json") or payload.get("callback_payload") or {}),
            _normalized_text(payload.get("status")) or "created",
            _normalized_text(payload.get("reply_text")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("send_channel")),
            payload.get("send_record_id"),
            _json_dumps(payload.get("send_result_json") or payload.get("send_result") or {}),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_laohuang_chat_job(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    column_serializers = {
        "queue_id": lambda value: value,
        "member_id": lambda value: value,
        "external_contact_id": _normalized_text,
        "phone": _normalized_text,
        "external_message_id": _normalized_text,
        "external_session_id": _normalized_text,
        "laohuang_task_id": _normalized_text,
        "request_payload_json": lambda value: _json_dumps(value or {}),
        "accepted_payload_json": lambda value: _json_dumps(value or {}),
        "callback_payload_json": lambda value: _json_dumps(value or {}),
        "status": _normalized_text,
        "reply_text": _normalized_text,
        "error_code": _normalized_text,
        "error_message": _normalized_text,
        "send_channel": _normalized_text,
        "send_record_id": lambda value: value,
        "send_result_json": lambda value: _json_dumps(value or {}),
        "finished_at": _normalized_text,
    }
    updates: list[str] = []
    values: list[Any] = []
    for key, value in payload.items():
        if key not in column_serializers:
            continue
        updates.append(f"{key} = ?")
        values.append(column_serializers[key](value))
    if not updates:
        return get_laohuang_chat_job(int(job_id)) or {}
    values.append(int(job_id))
    row = get_db().execute(
        f"""
        UPDATE automation_laohuang_chat_job
        SET {", ".join(updates)},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        tuple(values),
    ).fetchone()
    return dict(row) if row else {}


def deserialize_laohuang_chat_job_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "request_payload_json": _json_loads(row.get("request_payload_json"), default={}),
        "accepted_payload_json": _json_loads(row.get("accepted_payload_json"), default={}),
        "callback_payload_json": _json_loads(row.get("callback_payload_json"), default={}),
        "send_result_json": _json_loads(row.get("send_result_json"), default={}),
    }




__all__ = [
    "deserialize_laohuang_chat_job_row",
    "get_laohuang_chat_job",
    "get_laohuang_chat_job_by_external_message_id",
    "get_laohuang_chat_job_by_task_id",
    "insert_laohuang_chat_job",
    "list_laohuang_chat_jobs_for_review",
    "update_laohuang_chat_job",
]
