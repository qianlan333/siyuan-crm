from __future__ import annotations

import json
from typing import Any

from ...db import get_db


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def save_outbound_task_record(
    task_type: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    *,
    status: str = "created",
) -> int:
    task_id = (
        response_payload.get("msgid")
        or response_payload.get("jobid")
        or response_payload.get("task_id")
        or response_payload.get("moment_id")
    )
    db = get_db()
    row = db.execute(
        """
        INSERT INTO outbound_tasks (task_type, request_payload, response_payload, wecom_task_id, status)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            task_type,
            json.dumps(request_payload, ensure_ascii=False),
            json.dumps(response_payload, ensure_ascii=False),
            task_id,
            str(status or "").strip() or "created",
        ),
    )
    result = row.fetchone()
    db.commit()
    return int(result["id"])


def save_outbound_task(task_type: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> int:
    return save_outbound_task_record(task_type, request_payload, response_payload, status="created")


def get_outbound_task(task_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT id, task_type, request_payload, response_payload, wecom_task_id, status, created_at
        FROM outbound_tasks
        WHERE id = ?
        LIMIT 1
        """,
        (int(task_id),),
    )


def update_outbound_task_status(
    task_id: int,
    *,
    status: str,
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db = get_db()
    if response_payload is None:
        db.execute(
            """
            UPDATE outbound_tasks
            SET status = ?
            WHERE id = ?
            """,
            (str(status or "").strip() or "created", int(task_id)),
        )
    else:
        db.execute(
            """
            UPDATE outbound_tasks
            SET status = ?,
                response_payload = ?
            WHERE id = ?
            """,
            (
                str(status or "").strip() or "created",
                json.dumps(response_payload, ensure_ascii=False),
                int(task_id),
            ),
        )
    db.commit()
    return get_outbound_task(int(task_id)) or {}


def record_conversion_feedback(
    *,
    feedback_type: str,
    external_userid: str = "",
    chat_id: str = "",
    actor: str = "",
    feedback_payload: dict[str, Any] | None = None,
) -> int:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO conversion_feedback (external_userid, chat_id, feedback_type, feedback_payload, actor)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            external_userid or "",
            chat_id or "",
            feedback_type,
            json.dumps(feedback_payload or {}, ensure_ascii=False),
            actor or "",
        ),
    ).fetchone()
    db.commit()
    return int(row["id"])
