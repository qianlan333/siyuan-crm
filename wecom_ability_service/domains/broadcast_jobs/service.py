from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import repo


def _ensure_target_users(target_external_userids: list[str], *, allow_empty_targets: bool = False) -> list[str]:
    cleaned: list[str] = []
    for uid in target_external_userids or []:
        text = str(uid or "").strip()
        if text:
            cleaned.append(text)
    if not cleaned and not bool(allow_empty_targets):
        raise ValueError("target_external_userids is empty")
    return cleaned


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
    trace_id: str = "",
    created_by: str = "",
    allow_empty_targets: bool = False,
) -> int:
    targets = _ensure_target_users(target_external_userids, allow_empty_targets=allow_empty_targets)
    status = "waiting_approval" if requires_approval else "queued"
    return repo.insert_job(
        source_type=source_type,
        source_id=str(source_id or ""),
        source_table=str(source_table or ""),
        scheduled_for=scheduled_for,
        priority=int(priority),
        batch_key=str(batch_key or ""),
        status=status,
        requires_approval=bool(requires_approval),
        target_external_userids=targets,
        target_summary=str(target_summary or "")[:500],
        content_type=str(content_type or "text"),
        content_payload=content_payload or {},
        content_summary=str(content_summary or "")[:500],
        trace_id=str(trace_id or ""),
        created_by=str(created_by or ""),
    )


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


def claim_due_jobs(*, limit: int = 50, now: Any = None) -> list[dict[str, Any]]:
    cutoff = now if now is not None else datetime.now(timezone.utc)
    return repo.claim_due_jobs(now=cutoff, limit=int(limit))


def mark_sent(
    job_id: int,
    *,
    outbound_task_id: int | None,
    sent_count: int,
    failed_count: int = 0,
) -> None:
    repo.mark_sent(
        int(job_id),
        outbound_task_id=outbound_task_id,
        sent_count=int(sent_count),
        failed_count=int(failed_count),
    )


def mark_failed(job_id: int, *, error: str) -> None:
    repo.mark_failed(int(job_id), error=str(error or ""))


def cancel_job(job_id: int, *, cancelled_by: str, reason: str = "") -> bool:
    return repo.cancel_job(
        int(job_id), cancelled_by=str(cancelled_by or ""), reason=str(reason or "")
    ) > 0


def approve_job(job_id: int, *, approved_by: str) -> bool:
    return repo.approve_job(
        int(job_id), approved_by=str(approved_by or "")
    ) > 0


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
