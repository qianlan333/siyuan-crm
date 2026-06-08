from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from . import repo

logger = logging.getLogger(__name__)

BROADCAST_BUSINESS_DOMAINS = {"automation_ops", "ai_assistant", "group_ops", "manual", "unknown"}
BROADCAST_CHANNELS = {"wecom_private", "wecom_customer_group", "wechat", "manual", "unknown"}
BROADCAST_TARGET_KINDS = {"external_userid", "chat_id", "mixed", "dynamic", "unknown"}
BROADCAST_FAILURE_TYPES = set(repo.VALID_FAILURE_TYPES)
AUTOMATION_SOURCE_TYPES = {"campaign", "sop", "workflow", "operation_task", "focus_send", "deferred"}
GROUP_OPS_SOURCE_TABLE = "automation_group_ops_plans"


def _ensure_target_users(target_external_userids: list[str], *, allow_empty_targets: bool = False) -> list[str]:
    cleaned: list[str] = []
    for uid in target_external_userids or []:
        text = str(uid or "").strip()
        if text:
            cleaned.append(text)
    if not cleaned and not bool(allow_empty_targets):
        raise ValueError("target_external_userids is empty")
    return cleaned


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_error_summary(value: Any) -> str:
    text = _clean_text(value).replace("\n", " ")
    for marker in ("secret", "token", "webhook", "external_userid", "content_payload"):
        text = text.replace(marker, "[redacted]")
    text = re.sub(r"\bwm_[A-Za-z0-9_-]+\b", "[external_userid]", text)
    return text[:200]


def _stable_scheduled_text(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")
    return _clean_text(value)


def resolve_broadcast_business_domain(
    *,
    source_type: str | None = None,
    source_table: str | None = None,
    content_payload: dict[str, Any] | None = None,
) -> str:
    payload = _json_object(content_payload)
    if _clean_text(source_table) == GROUP_OPS_SOURCE_TABLE:
        return "group_ops"
    if _clean_text(payload.get("channel")) == "wecom_customer_group":
        return "group_ops"
    source = _clean_text(source_type)
    if source == "cloud_plan":
        return "ai_assistant"
    if source in AUTOMATION_SOURCE_TYPES:
        return "automation_ops"
    if source == "manual":
        return "manual"
    return "unknown"


def resolve_broadcast_channel(
    *,
    source_type: str | None = None,
    source_table: str | None = None,
    content_payload: dict[str, Any] | None = None,
    target_user_id: str | None = None,
    target_external_userid: str | None = None,
    target_chat_id: str | None = None,
) -> str:
    payload = _json_object(content_payload)
    if _clean_text(payload.get("channel")) == "wecom_customer_group":
        return "wecom_customer_group"
    if _clean_text(target_chat_id) or _clean_text(payload.get("target_chat_id")):
        return "wecom_customer_group"
    if _clean_text(target_external_userid) or _clean_text(target_user_id):
        return "wecom_private"
    if _clean_text(source_table) == GROUP_OPS_SOURCE_TABLE:
        return "wecom_customer_group"
    if _clean_text(source_type) == "manual":
        return "manual"
    return "unknown"


def resolve_broadcast_target_kind(
    *,
    target_user_id: str | None = None,
    target_external_userid: str | None = None,
    target_chat_id: str | None = None,
    content_payload: dict[str, Any] | None = None,
) -> str:
    payload = _json_object(content_payload)
    if _clean_text(target_chat_id) or _clean_text(payload.get("target_chat_id")):
        return "chat_id"
    if _clean_text(target_external_userid) or _clean_text(target_user_id):
        return "external_userid"
    sendable_targets = payload.get("sendable_targets")
    if isinstance(sendable_targets, list):
        has_external = any(isinstance(item, dict) and _clean_text(item.get("external_userid")) for item in sendable_targets)
        has_chat = any(isinstance(item, dict) and _clean_text(item.get("chat_id")) for item in sendable_targets)
        if has_external and has_chat:
            return "mixed"
        if has_chat:
            return "chat_id"
        if has_external:
            return "external_userid"
    if _clean_text(payload.get("channel")) == "wecom_customer_group":
        if payload.get("chat_ids"):
            return "chat_id"
        return "dynamic"
    if payload.get("dynamic_targeting") or payload.get("pre_scheduled") or payload.get("audience_filter"):
        return "dynamic"
    return "unknown"


def build_broadcast_job_idempotency_key(input_data: dict[str, Any]) -> str | None:
    explicit = _clean_text(input_data.get("idempotencyKey") or input_data.get("idempotency_key"))
    if explicit:
        return explicit
    source_type = _clean_text(input_data.get("sourceType") or input_data.get("source_type"))
    source_id = _clean_text(input_data.get("sourceId") or input_data.get("source_id"))
    source_table = _clean_text(input_data.get("sourceTable") or input_data.get("source_table"))
    scheduled = _stable_scheduled_text(input_data.get("scheduledFor") or input_data.get("scheduled_for"))
    payload = _json_object(input_data.get("contentPayload") or input_data.get("content_payload"))
    if source_type == "cloud_plan" and source_id:
        return f"cloud_plan:{source_id}"
    if source_table == GROUP_OPS_SOURCE_TABLE and source_id and scheduled:
        node_key = _clean_text(payload.get("node_id") or payload.get("step_id") or payload.get("event_id") or payload.get("webhook_event_id"))
        return f"group_ops:{source_id}:{scheduled}:{node_key}" if node_key else f"group_ops:{source_id}:{scheduled}"
    if source_type == "focus_send" and source_id:
        return f"focus_send:{source_id}"
    if source_type == "sop" and source_id and scheduled:
        return f"sop:{source_id}:{scheduled}"
    if source_type == "workflow" and source_id and scheduled:
        node_key = _clean_text(payload.get("node_id"))
        return f"workflow:{source_id}:{scheduled}:{node_key}" if node_key else f"workflow:{source_id}:{scheduled}"
    if source_type == "operation_task" and source_id and scheduled:
        trigger_key = _clean_text(payload.get("trigger_key") or payload.get("execution_id"))
        return f"operation_task:{source_id}:{scheduled}:{trigger_key}" if trigger_key else f"operation_task:{source_id}:{scheduled}"
    if source_type == "campaign" and source_id and scheduled:
        targets = input_data.get("target_external_userids") or input_data.get("targetExternalUserIds") or []
        target_hash = ""
        if isinstance(targets, list) and targets:
            joined = "|".join(sorted(_clean_text(item) for item in targets if _clean_text(item)))
            target_hash = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12] if joined else ""
        return f"campaign:{source_id}:{scheduled}:{target_hash}" if target_hash else f"campaign:{source_id}:{scheduled}"
    return None


def record_job_event(
    job_id: int,
    *,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    event_payload: dict[str, Any] | None = None,
    actor_type: str = "",
    actor_id: str = "",
) -> None:
    safe_payload = dict(event_payload or {})
    safe_payload.pop("content_payload", None)
    safe_payload.pop("target_external_userids", None)
    try:
        repo.insert_broadcast_job_event(
            job_id=int(job_id),
            event_type=_clean_text(event_type),
            from_status=from_status,
            to_status=to_status,
            event_payload=safe_payload,
            actor_type=actor_type,
            actor_id=actor_id,
        )
    except Exception:
        try:
            repo.get_db().rollback()
        except Exception:
            pass
        logger.warning("broadcast_job_event_write_failed job_id=%s event_type=%s", int(job_id), _clean_text(event_type))


def _enqueued_event_payload(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": _clean_text(job.get("source_type")),
        "business_domain": _clean_text(job.get("business_domain")),
        "channel": _clean_text(job.get("channel")),
        "target_kind": _clean_text(job.get("target_kind")),
        "scheduled_for": _clean_text(job.get("scheduled_for")),
        "has_idempotency_key": bool(_clean_text(job.get("idempotency_key"))),
    }


def enqueue_broadcast_job(input_data: dict[str, Any]) -> dict[str, Any]:
    payload = _json_object(input_data.get("contentPayload") or input_data.get("content_payload"))
    source_type = _clean_text(input_data.get("sourceType") or input_data.get("source_type"))
    source_table = _clean_text(input_data.get("sourceTable") or input_data.get("source_table"))
    target_external_userids = list(input_data.get("targetExternalUserIds") or input_data.get("target_external_userids") or [])
    primary_external_userid = _clean_text(input_data.get("targetExternalUserId") or input_data.get("target_external_userid"))
    if not primary_external_userid and target_external_userids:
        primary_external_userid = _clean_text(target_external_userids[0])
    status = "waiting_approval" if bool(input_data.get("requiresApproval") or input_data.get("requires_approval")) else "queued"
    idempotency_key = build_broadcast_job_idempotency_key(input_data) or ""
    existing = repo.fetch_job_by_idempotency_key(idempotency_key) if idempotency_key else None
    if existing:
        return {"status": "duplicate", "job": existing}

    business_domain = _clean_text(input_data.get("businessDomain") or input_data.get("business_domain"))
    if business_domain not in BROADCAST_BUSINESS_DOMAINS:
        business_domain = resolve_broadcast_business_domain(source_type=source_type, source_table=source_table, content_payload=payload)
    channel = _clean_text(input_data.get("channel"))
    if channel not in BROADCAST_CHANNELS:
        channel = resolve_broadcast_channel(
            source_type=source_type,
            source_table=source_table,
            content_payload=payload,
            target_user_id=input_data.get("targetUserId") or input_data.get("target_user_id"),
            target_external_userid=primary_external_userid,
            target_chat_id=input_data.get("targetChatId") or input_data.get("target_chat_id"),
        )
    target_kind = _clean_text(input_data.get("targetKind") or input_data.get("target_kind"))
    if target_kind not in BROADCAST_TARGET_KINDS:
        target_kind = resolve_broadcast_target_kind(
            target_user_id=input_data.get("targetUserId") or input_data.get("target_user_id"),
            target_external_userid=primary_external_userid,
            target_chat_id=input_data.get("targetChatId") or input_data.get("target_chat_id"),
            content_payload=payload,
        )

    targets = _ensure_target_users(target_external_userids, allow_empty_targets=bool(input_data.get("allow_empty_targets") or input_data.get("allowEmptyTargets")))
    job_id = repo.insert_job(
        source_type=source_type,
        source_id=_clean_text(input_data.get("sourceId") or input_data.get("source_id")),
        source_table=source_table,
        scheduled_for=input_data.get("scheduledFor") or input_data.get("scheduled_for"),
        priority=int(input_data.get("priority") or 100),
        batch_key=_clean_text(input_data.get("batchKey") or input_data.get("batch_key")),
        business_domain=business_domain,
        idempotency_key=idempotency_key,
        channel=channel,
        target_kind=target_kind,
        retry_policy_json=_json_object(input_data.get("retryPolicy") or input_data.get("retry_policy")),
        metadata_json=_json_object(input_data.get("metadata")),
        status=status,
        requires_approval=status == "waiting_approval",
        target_external_userids=targets,
        target_summary=_clean_text(input_data.get("targetSummary") or input_data.get("target_summary"))[:500],
        content_type=_clean_text(input_data.get("contentType") or input_data.get("content_type")) or "text",
        content_payload=payload,
        content_summary=_clean_text(input_data.get("contentSummary") or input_data.get("content_summary"))[:500],
        trace_id=_clean_text(input_data.get("traceId") or input_data.get("trace_id")),
        created_by=_clean_text(input_data.get("createdBy") or input_data.get("created_by")),
    )
    if not job_id and idempotency_key:
        existing = repo.fetch_job_by_idempotency_key(idempotency_key)
        return {"status": "duplicate", "job": existing}
    job = repo.fetch_job_by_id(int(job_id)) if job_id else None
    if job:
        record_job_event(
            int(job["id"]),
            event_type="enqueued",
            from_status=None,
            to_status=_clean_text(job.get("status")),
            event_payload=_enqueued_event_payload(job),
            actor_type="system",
            actor_id=_clean_text(job.get("created_by")),
        )
    return {"status": "created", "job": job}


def enqueue_job(
    *,
    source_type: str,
    source_id: str,
    source_table: str,
    scheduled_for: Any,
    target_external_userids: list[str],
    target_summary: str,
    content_type: str,
    content_payload: dict[str, Any],
    content_summary: str,
    batch_key: str = "",
    priority: int = 100,
    requires_approval: bool = False,
    idempotency_key: str = "",
    business_domain: str = "",
    channel: str = "",
    target_kind: str = "",
    retry_policy_json: dict[str, Any] | None = None,
    metadata_json: dict[str, Any] | None = None,
    trace_id: str = "",
    created_by: str = "",
    allow_empty_targets: bool = False,
) -> int:
    result = enqueue_broadcast_job(
        {
            "source_type": source_type,
            "source_id": source_id,
            "source_table": source_table,
            "scheduled_for": scheduled_for,
            "target_external_userids": target_external_userids,
            "target_summary": target_summary,
            "content_type": content_type,
            "content_payload": content_payload or {},
            "content_summary": content_summary,
            "batch_key": batch_key,
            "priority": priority,
            "requires_approval": requires_approval,
            "idempotency_key": idempotency_key,
            "business_domain": business_domain,
            "channel": channel,
            "target_kind": target_kind,
            "retry_policy": retry_policy_json or {},
            "metadata": metadata_json or {},
            "trace_id": trace_id,
            "created_by": created_by,
            "allow_empty_targets": allow_empty_targets,
        }
    )
    job = result.get("job") or {}
    return int(job.get("id") or 0)


def get_job(job_id: int) -> dict[str, Any] | None:
    return repo.fetch_job_by_id(int(job_id))


def list_jobs(
    *,
    statuses: list[str] | None = None,
    source_types: list[str] | None = None,
    since: Any = None,
    until: Any = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return repo.fetch_jobs_filtered(
        statuses=statuses,
        source_types=source_types,
        since=since,
        until=until,
        limit=int(limit),
        offset=int(offset),
    )


def claim_due_jobs(
    *,
    limit: int = 50,
    now: Any = None,
    claim_token: str = "",
    lease_seconds: int = 900,
) -> list[dict[str, Any]]:
    cutoff = now if now is not None else datetime.now(timezone.utc)
    claimed = repo.claim_due_jobs(
        now=cutoff,
        limit=int(limit),
        claim_token=str(claim_token or ""),
        lease_seconds=max(1, int(lease_seconds)),
    )
    for job in claimed:
        record_job_event(
            int(job["id"]),
            event_type="claimed",
            from_status="queued",
            to_status="claimed",
            event_payload={
                "lease_expires_at": _clean_text(job.get("lease_expires_at")),
                "attempt_count": int(job.get("attempt_count") or 0),
            },
        )
    return claimed


def recover_stale_claimed_jobs(
    *,
    older_than_seconds: int = 900,
    limit: int = 50,
    now: Any = None,
) -> dict[str, list[dict[str, Any]]]:
    cutoff = now if now is not None else datetime.now(timezone.utc)
    recovered = repo.recover_stale_claimed_jobs(
        now=cutoff,
        older_than_seconds=max(1, int(older_than_seconds)),
        limit=max(1, int(limit)),
    )
    for key, jobs in recovered.items():
        to_status = "failed" if key == "failed_unknown_outbound" else "queued"
        for job in jobs:
            record_job_event(
                int(job["id"]),
                event_type="recovered",
                from_status="claimed",
                to_status=to_status,
                event_payload={"reason": key},
            )
    return recovered


def mark_dispatch_started(job_id: int, *, outbound_task_id: int) -> None:
    repo.mark_dispatch_started(int(job_id), outbound_task_id=int(outbound_task_id))


def mark_sent(
    job_id: int,
    *,
    outbound_task_id: int | None,
    sent_count: int,
    failed_count: int = 0,
) -> None:
    before = get_job(job_id) or {}
    repo.mark_sent(
        int(job_id),
        outbound_task_id=outbound_task_id,
        sent_count=int(sent_count),
        failed_count=int(failed_count),
    )
    after = get_job(job_id) or {}
    if after.get("status") == "sent":
        record_job_event(
            int(job_id),
            event_type="sent",
            from_status=_clean_text(before.get("status")) or "claimed",
            to_status="sent",
            event_payload={"sent_count": int(sent_count), "failed_count": int(failed_count)},
        )


def mark_failed(job_id: int, *, error: str, failure_type: str = "unknown") -> None:
    before = get_job(job_id) or {}
    clean_failure_type = _clean_text(failure_type) or "unknown"
    if clean_failure_type not in BROADCAST_FAILURE_TYPES:
        clean_failure_type = "unknown"
    repo.mark_failed(int(job_id), error=str(error or ""), failure_type=clean_failure_type)
    after = get_job(job_id) or {}
    if after.get("status") == "failed":
        record_job_event(
            int(job_id),
            event_type="failed",
            from_status=_clean_text(before.get("status")) or "unknown",
            to_status="failed",
            event_payload={"failure_type": clean_failure_type, "error_summary": _safe_error_summary(error)},
        )


def cancel_job(job_id: int, *, cancelled_by: str, reason: str = "") -> bool:
    before = get_job(job_id) or {}
    count = repo.cancel_job(
        int(job_id), cancelled_by=str(cancelled_by or ""), reason=str(reason or "")
    )
    if count > 0:
        record_job_event(
            int(job_id),
            event_type="cancelled",
            from_status=_clean_text(before.get("status")) or "unknown",
            to_status="cancelled",
            event_payload={"reason": _safe_error_summary(reason)},
            actor_type="admin",
            actor_id=_clean_text(cancelled_by),
        )
    return count > 0


def approve_job(job_id: int, *, approved_by: str) -> bool:
    count = repo.approve_job(
        int(job_id), approved_by=str(approved_by or "")
    )
    if count > 0:
        record_job_event(
            int(job_id),
            event_type="approved",
            from_status="waiting_approval",
            to_status="queued",
            actor_type="admin",
            actor_id=_clean_text(approved_by),
        )
    return count > 0


def approve_job_by_source(
    *, source_table: str, source_id: str, approved_by: str
) -> bool:
    return repo.approve_job_by_source(
        source_table=str(source_table or ""),
        source_id=str(source_id or ""),
        approved_by=str(approved_by or ""),
    ) > 0


def count_by_status() -> dict[str, int]:
    return repo.count_jobs_by_status()
