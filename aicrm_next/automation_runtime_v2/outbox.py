from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import TRIGGER_ON_ENTER_STAGE, TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH, as_int, text
from .membership_service import get_membership
from .task_adapter import get_task
from .task_planner import get_plan, update_plan_status


def _source_id(plan: dict[str, Any]) -> str:
    trigger = text(plan.get("trigger_type"))
    task_id = as_int(plan.get("task_id"))
    membership_id = as_int(plan.get("membership_id"))
    if trigger == TRIGGER_ON_ENTER_STAGE:
        return f"v2:stage:{as_int(plan.get('stage_entry_id'))}:task:{task_id}:member:{membership_id}"
    if trigger == TRIGGER_SCHEDULED:
        return f"v2:scheduled:{text(plan.get('schedule_key'))}:task:{task_id}:member:{membership_id}"
    if trigger == TRIGGER_WEBHOOK_PUSH:
        return f"v2:webhook:{as_int(plan.get('event_id'))}:task:{task_id}:member:{membership_id}"
    return f"v2:event:{as_int(plan.get('event_id'))}:task:{task_id}:member:{membership_id}"


def enqueue(task_plan_id: int, *, operator_id: str = "automation_runtime_v2") -> dict[str, Any]:
    plan = get_plan(int(task_plan_id))
    if not plan:
        raise LookupError("task_plan_not_found")
    if as_int(plan.get("broadcast_job_id")) > 0:
        return {"status": "duplicate", "broadcast_job_id": as_int(plan.get("broadcast_job_id"))}
    rendered = dict(plan.get("rendered_content_json") or {})
    if text(plan.get("status")) != "rendered" or not rendered:
        return {"status": "skipped", "reason": "plan_not_rendered"}
    membership = get_membership(as_int(plan.get("membership_id"))) or {}
    external = text(membership.get("external_userid"))
    if not external:
        updated = update_plan_status(int(task_plan_id), "failed", skip_reason="external_userid_missing")
        return {"status": "failed", "reason": "external_userid_missing", "plan": updated}
    task = get_task(as_int(plan.get("task_id"))) or {}
    sender_resolution = _resolve_sender_userid(task=task, membership=membership, operator_id=operator_id)
    sender_userid = text(sender_resolution.get("sender_userid"))
    if not sender_userid:
        updated = update_plan_status(int(task_plan_id), "failed", skip_reason="sender_userid_missing", diagnostics={"sender_resolution": sender_resolution})
        return {"status": "failed", "reason": "sender_userid_missing", "plan": updated}
    source_id = _source_id(plan)
    payload = {
        "runtime_version": "v2",
        "channel": "wecom_private",
        "task_plan_id": int(task_plan_id),
        "task_id": as_int(plan.get("task_id")),
        "membership_id": as_int(plan.get("membership_id")),
        "event_id": as_int(plan.get("event_id")) or None,
        "stage_entry_id": as_int(plan.get("stage_entry_id")) or None,
        "sender_userid": sender_userid,
        "owner_userid": sender_userid,
        "target_external_userids": [external],
        "rendered_content": rendered,
        "operator_id": text(operator_id),
    }
    job_id = _insert_broadcast_job(
        source_id=source_id,
        target_external_userids=[external],
        content_type=text(rendered.get("type")) or "text",
        content_payload=payload,
        content_summary=text(rendered.get("content_text"))[:500],
        batch_key=f"automation_runtime_v2:{as_int(plan.get('program_id'))}",
        trace_id=source_id,
        created_by=text(operator_id) or "automation_runtime_v2",
        metadata_json={"sender_resolution": sender_resolution},
    )
    updated = update_plan_status(int(task_plan_id), "enqueued", broadcast_job_id=job_id, diagnostics={"broadcast_job_id": job_id, "sender_resolution": sender_resolution})
    return {"status": "enqueued" if job_id else "duplicate", "broadcast_job_id": job_id, "plan": updated}


def _first_text(*values: Any) -> str:
    for value in values:
        candidate = text(value)
        if candidate:
            return candidate
    return ""


def _resolve_sender_userid(*, task: dict[str, Any], membership: dict[str, Any], operator_id: str) -> dict[str, Any]:
    runtime_v2 = task.get("runtime_v2") if isinstance(task.get("runtime_v2"), dict) else {}
    unified = task.get("unified_content_json") if isinstance(task.get("unified_content_json"), dict) else {}
    agent = task.get("agent_config_json") if isinstance(task.get("agent_config_json"), dict) else {}
    direct = _first_text(
        task.get("sender_userid"),
        task.get("owner_staff_id"),
        task.get("send_as_userid"),
        runtime_v2.get("sender_userid"),
        runtime_v2.get("owner_staff_id"),
        runtime_v2.get("send_as_userid"),
        agent.get("sender_userid"),
        agent.get("owner_staff_id"),
        agent.get("send_as_userid"),
        unified.get("sender_userid"),
        unified.get("owner_staff_id"),
        unified.get("send_as_userid"),
    )
    if direct:
        return {"sender_userid": direct, "source": "task_config", "fallback_used": False}
    channel_id = as_int(membership.get("source_channel_id"))
    external = text(membership.get("external_userid"))
    if channel_id > 0:
        row = get_db().execute(
            """
            SELECT COALESCE(NULLIF(cc.owner_staff_id, ''), NULLIF(ch.owner_staff_id, '')) AS sender_userid
            FROM automation_channel ch
            LEFT JOIN automation_channel_contact cc
              ON cc.channel_id = ch.id
             AND cc.external_contact_id = ?
            WHERE ch.id = ?
            LIMIT 1
            """,
            (external, channel_id),
        ).fetchone()
        sender = text((row or {}).get("sender_userid") if row else "")
        if sender:
            return {"sender_userid": sender, "source": "channel", "fallback_used": False}
    operator = text(operator_id)
    if operator:
        return {"sender_userid": operator, "source": "operator", "fallback_used": True}
    return {"sender_userid": "", "source": "unresolved", "fallback_used": True}


def _insert_broadcast_job(
    *,
    source_id: str,
    target_external_userids: list[str],
    content_type: str,
    content_payload: dict[str, Any],
    content_summary: str,
    batch_key: str,
    trace_id: str,
    created_by: str,
    metadata_json: dict[str, Any] | None = None,
) -> int:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO broadcast_jobs (
            source_type, source_id, source_table, scheduled_for, priority, batch_key,
            business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
            status, requires_approval,
            target_external_userids, target_count, target_summary,
            content_type, content_payload, content_summary,
            trace_id, created_by
        )
        VALUES (
            'automation_runtime_v2', ?, 'automation_task_plan_v2', ?, 100, ?,
            'automation_ops', ?, 'wecom_private', 'external_userid', '{}'::jsonb, CAST(? AS jsonb),
            'queued', FALSE,
            CAST(? AS jsonb), ?, ?,
            ?, CAST(? AS jsonb), ?,
            ?, ?
        )
        ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> '' DO NOTHING
        RETURNING id
        """,
        (
            source_id,
            datetime.now(timezone.utc),
            batch_key,
            source_id,
            json.dumps(metadata_json or {}, ensure_ascii=False, default=str),
            json.dumps(list(target_external_userids or []), ensure_ascii=False),
            len(list(target_external_userids or [])),
            f"runtime_v2 member {', '.join(target_external_userids)}",
            content_type,
            json.dumps(content_payload or {}, ensure_ascii=False, default=str),
            content_summary,
            trace_id,
            created_by,
        ),
    ).fetchone()
    if row:
        return int(row["id"])
    existing = db.execute(
        "SELECT id FROM broadcast_jobs WHERE idempotency_key = ? ORDER BY id DESC LIMIT 1",
        (source_id,),
    ).fetchone()
    return int((existing or {}).get("id") or 0)
