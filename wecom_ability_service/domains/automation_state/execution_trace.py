"""Per-decision trace writer for automation workflow execution.

The Sprint 1 migration created ``automation_execution_trace``; this module is
the canonical writer. Workflow runtime code can call ``record_execution_trace``
at any decision point (matched, skipped, errored, dispatched, etc.) so that
operators and engineers can later reconstruct *why* a specific customer was
or wasn't processed by a workflow run.

The schema intentionally captures both correlation ids (``request_id``,
``job_id``, ``parent_request_id``) and the small JSON ``payload`` so we don't
need a join table to surface why a node fired. Keep payloads small (think
"current_pool=operating, last_msg_at=..."), not full state dumps — those
belong in dedicated history tables.

Reads are exposed for tests and for an upcoming admin "trace viewer" that
will hang off the workflow detail page.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ...db import get_db
from ...observability import get_job_id, get_parent_request_id, get_request_id

trace_logger = logging.getLogger("automation_trace")


def record_execution_trace(
    *,
    workflow_id: str,
    decision_point: str,
    decision_outcome: str,
    workflow_node_id: str = "",
    external_userid: str = "",
    member_id: int | None = None,
    reason: str = "",
    payload: dict[str, Any] | None = None,
) -> int:
    """Insert one row into ``automation_execution_trace``.

    ``decision_point``: short string naming the gate (e.g. ``"evaluate"``,
    ``"enqueue_dispatch"``, ``"skip_dnd"``). ``decision_outcome``: one of
    ``"matched"``, ``"skipped"``, ``"errored"``, ``"dispatched"`` — keep this
    enum short so reports group cleanly. Returns the row id (or 0 if the
    insert returned no lastrowid, which only happens on Postgres without
    RETURNING).

    Correlation ids (request_id/job_id/parent_request_id) are pulled from
    the observability ContextVars automatically — call from a request handler
    or an ``enqueue_task``-wrapped background runner and you'll get the
    correct linkage for free.
    """
    db = get_db()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    cursor = db.execute(
        """
        INSERT INTO automation_execution_trace
            (workflow_id, workflow_node_id, external_userid, member_id,
             decision_point, decision_outcome, reason, request_id, job_id,
             parent_request_id, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(workflow_id or "").strip(),
            str(workflow_node_id or "").strip(),
            str(external_userid or "").strip(),
            int(member_id) if member_id is not None else None,
            str(decision_point or "").strip(),
            str(decision_outcome or "").strip(),
            str(reason or "")[:1000],
            get_request_id(),
            get_job_id(),
            get_parent_request_id(),
            payload_json,
        ),
    )
    last_id = getattr(cursor, "lastrowid", None) or 0
    trace_logger.info(
        "automation_trace workflow=%s node=%s point=%s outcome=%s external=%s reason=%s",
        workflow_id,
        workflow_node_id,
        decision_point,
        decision_outcome,
        external_userid,
        reason,
    )
    return int(last_id)


def list_execution_trace_for_external(
    external_userid: str, *, limit: int = 100
) -> list[dict[str, Any]]:
    """Read trace rows for a single customer, newest first. Capped by ``limit``."""
    rows = (
        get_db()
        .execute(
            """
            SELECT id, workflow_id, workflow_node_id, external_userid, member_id,
                   decision_point, decision_outcome, reason, request_id, job_id,
                   parent_request_id, payload_json, created_at
            FROM automation_execution_trace
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(external_userid or "").strip(), int(max(1, limit))),
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


def list_execution_trace_for_workflow(
    workflow_id: str, *, limit: int = 100
) -> list[dict[str, Any]]:
    """Read trace rows for a single workflow, newest first."""
    rows = (
        get_db()
        .execute(
            """
            SELECT id, workflow_id, workflow_node_id, external_userid, member_id,
                   decision_point, decision_outcome, reason, request_id, job_id,
                   parent_request_id, payload_json, created_at
            FROM automation_execution_trace
            WHERE workflow_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(workflow_id or "").strip(), int(max(1, limit))),
        )
        .fetchall()
    )
    return [dict(row) for row in rows]
