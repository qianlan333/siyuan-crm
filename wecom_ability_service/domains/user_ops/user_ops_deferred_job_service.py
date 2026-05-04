from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from ...db import get_db
from ...infra.constants import (
    USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
)
from . import repo


@dataclass(frozen=True)
class DeferredJobRuntime:
    """Internal-only dependency bag for user-ops deferred-job execution."""

    current_operator_resolver: Callable[[], str]
    stringify_db_timestamp: Callable[[Any], str]
    build_user_ops_backfill_preview: Callable[[str], list[dict[str, Any]]]
    list_class_term_matches_for_external_contact: Callable[[str, str], dict[str, Any]]
    sync_user_ops_class_term_tag_definitions: Callable[[], dict[str, Any]]
    refresh_user_ops_contact_tags_for_external_userid: Callable[..., dict[str, Any]]
    resolve_person_identity: Callable[..., dict[str, Any]]
    upsert_user_ops_lead_pool_member: Callable[..., dict[str, Any]]


def get_user_ops_deferred_job_counts() -> dict[str, int]:
    return repo.get_deferred_job_counts()


def schedule_user_ops_auto_assign_class_term_job(
    *,
    external_userid: str,
    owner_userid: str,
    delay_seconds: int = 10,
    operator: str = "",
    runtime: DeferredJobRuntime,
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {"ok": True, "scheduled": False, "reason": "missing_external_userid"}

    delay_seconds = max(int(delay_seconds or 0), 0)
    now_dt = datetime.now()
    run_after_dt = now_dt + timedelta(seconds=delay_seconds)
    run_after = run_after_dt.strftime("%Y-%m-%d %H:%M:%S")
    actor = str(operator or runtime.current_operator_resolver()).strip() or "system_auto_assign"
    payload = {
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "delay_seconds": delay_seconds,
        "scheduled_by": actor,
    }
    row = get_db().execute(
        """
        INSERT INTO user_ops_deferred_jobs (
            job_type, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'pending', 0, ?, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id, job_type, external_userid, owner_userid, run_after, status, attempt_count, created_at, updated_at
        """,
        (
            USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
            normalized_external_userid,
            normalized_owner_userid,
            run_after,
            json.dumps(payload, ensure_ascii=False),
        ),
    ).fetchone()
    get_db().commit()
    return {
        "ok": True,
        "scheduled": True,
        "job": {
            "id": int(row["id"]),
            "job_type": str(row.get("job_type") or "").strip(),
            "external_userid": str(row.get("external_userid") or "").strip(),
            "owner_userid": str(row.get("owner_userid") or "").strip(),
            "run_after": runtime.stringify_db_timestamp(row.get("run_after")),
            "status": str(row.get("status") or "").strip(),
            "attempt_count": int(row.get("attempt_count") or 0),
            "created_at": runtime.stringify_db_timestamp(row.get("created_at")),
            "updated_at": runtime.stringify_db_timestamp(row.get("updated_at")),
        },
    }


def _list_due_user_ops_deferred_jobs(limit: int, now_at: str) -> list[dict[str, Any]]:
    """Internal only: load pending deferred jobs due for execution."""

    rows = get_db().execute(
        """
        SELECT
            id, job_type, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
        WHERE job_type = ?
          AND status = 'pending'
          AND run_after <= ?
        ORDER BY run_after ASC, id ASC
        LIMIT ?
        """,
        (
            USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
            now_at,
            max(int(limit or 0), 1),
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def _get_user_ops_deferred_job(job_id: int) -> dict[str, Any] | None:
    """Internal only: fetch a single deferred job row."""

    row = get_db().execute(
        """
        SELECT
            id, job_type, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
        WHERE id = ?
        LIMIT 1
        """,
        (int(job_id),),
    ).fetchone()
    return dict(row) if row else None


def _mark_user_ops_deferred_job_running(job_id: int) -> dict[str, Any] | None:
    """Internal only: claim a pending job for execution."""

    job = _get_user_ops_deferred_job(job_id)
    if not job or str(job.get("status") or "").strip() != "pending":
        return None
    get_db().execute(
        """
        UPDATE user_ops_deferred_jobs
        SET status = 'running',
            attempt_count = COALESCE(attempt_count, 0) + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(job_id),),
    )
    get_db().commit()
    return _get_user_ops_deferred_job(job_id)


def _finish_user_ops_deferred_job(job_id: int, *, status: str, result_payload: dict[str, Any]) -> None:
    """Internal only: persist deferred job completion payload."""

    get_db().execute(
        """
        UPDATE user_ops_deferred_jobs
        SET status = ?,
            result_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            str(status or "").strip(),
            json.dumps(result_payload, ensure_ascii=False),
            int(job_id),
        ),
    )
    get_db().commit()


def _insert_user_ops_history_record(
    *,
    pool_id: int | None,
    mobile: str,
    external_userid: str,
    action_type: str,
    old_payload: dict[str, Any],
    new_payload: dict[str, Any],
    operator: str,
    source_type: str,
    created_at: str,
) -> None:
    """Internal only: retained here because deferred job flows still share history-write semantics."""

    get_db().execute(
        """
        INSERT INTO user_ops_pool_history (
            pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pool_id,
            str(mobile or "").strip(),
            str(external_userid or "").strip(),
            str(action_type or "").strip(),
            json.dumps(old_payload, ensure_ascii=False),
            json.dumps(new_payload, ensure_ascii=False),
            str(operator or "").strip(),
            str(source_type or "").strip(),
            str(created_at or "").strip(),
        ),
    )


def _find_user_ops_backfill_preview_item(
    owner_userid: str,
    external_userid: str,
    *,
    runtime: DeferredJobRuntime,
) -> dict[str, Any] | None:
    """Internal only: align a deferred job with owner-backfill preview payload."""

    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    for item in runtime.build_user_ops_backfill_preview(owner_userid):
        if str(item.get("external_userid") or "").strip() == normalized_external_userid:
            return item
    return None


def _upsert_lead_pool_from_verified_class_term_tag(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source_type: str = USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
    runtime: DeferredJobRuntime,
) -> dict[str, Any]:
    """Internal only: execute the verified class-term auto-assign write path."""

    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    actor = str(operator or runtime.current_operator_resolver()).strip() or "system_auto_assign"
    tag_definition_sync = runtime.sync_user_ops_class_term_tag_definitions()
    tag_refresh = runtime.refresh_user_ops_contact_tags_for_external_userid(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
    )
    match_payload = runtime.list_class_term_matches_for_external_contact(
        normalized_external_userid,
        normalized_owner_userid,
    )
    matched_terms = list(match_payload["matched_terms"])
    if len(matched_terms) > 1:
        return {
            "status": "conflict",
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
            "matched_terms": matched_terms,
            "tag_definition_sync": tag_definition_sync,
            "tag_refresh": tag_refresh,
        }
    if not matched_terms:
        return {
            "status": "skipped",
            "reason": "no_match",
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
            "matched_terms": [],
            "tag_definition_sync": tag_definition_sync,
            "tag_refresh": tag_refresh,
        }

    identity = runtime.resolve_person_identity(external_userid=normalized_external_userid)
    matched = matched_terms[0]
    result = runtime.upsert_user_ops_lead_pool_member(
        mobile=str(identity.get("mobile") or "").strip(),
        external_userid=str(identity.get("external_userid") or normalized_external_userid).strip(),
        customer_name=str(identity.get("customer_name") or "").strip(),
        owner_userid=str(identity.get("owner_userid") or normalized_owner_userid).strip(),
        is_wecom_added=bool(str(identity.get("external_userid") or normalized_external_userid).strip()),
        is_mobile_bound=bool(identity.get("is_bound")),
        class_term_no=matched.get("class_term_no"),
        class_term_label=str(matched.get("class_term_label") or "").strip(),
        entry_source=source_type,
        operator=actor,
        remark=f"verified class term tag external_userid={normalized_external_userid}",
    )
    return {
        "status": "success",
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "matched_terms": matched_terms,
        "tag_definition_sync": tag_definition_sync,
        "tag_refresh": tag_refresh,
        "member": result.get("member"),
        "action_type": result.get("action_type"),
    }


def _execute_auto_assign_class_term_job(
    job: dict[str, Any],
    *,
    operator: str,
    runtime: DeferredJobRuntime,
) -> dict[str, Any]:
    """Internal only: run a single auto-assign deferred job."""

    normalized_owner_userid = str(job.get("owner_userid") or "").strip()
    normalized_external_userid = str(job.get("external_userid") or "").strip()
    actor = str(operator or "").strip() or "system_auto_assign"
    return _upsert_lead_pool_from_verified_class_term_tag(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        operator=actor,
        source_type=USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
        runtime=runtime,
    )


def run_due_user_ops_deferred_jobs(
    limit: int = 20,
    *,
    runtime: DeferredJobRuntime,
) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 20), 200))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    due_jobs = _list_due_user_ops_deferred_jobs(normalized_limit, now)
    summary = {
        "ok": True,
        "limit": normalized_limit,
        "scanned_count": len(due_jobs),
        "success_count": 0,
        "conflict_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "items": [],
    }
    if not due_jobs:
        return summary

    actor = "system_auto_assign"
    logger = logging.getLogger("user_ops")
    for job in due_jobs:
        running_job = _mark_user_ops_deferred_job_running(int(job["id"]))
        if not running_job:
            continue
        try:
            result = _execute_auto_assign_class_term_job(running_job, operator=actor, runtime=runtime)
            status = str(result.get("status") or "").strip() or "failed"
        except Exception as exc:
            logger.exception("user ops deferred job failed id=%s", job["id"])
            status = "failed"
            result = {
                "status": "failed",
                "external_userid": str(job.get("external_userid") or "").strip(),
                "owner_userid": str(job.get("owner_userid") or "").strip(),
                "error": str(exc),
            }
        _finish_user_ops_deferred_job(int(job["id"]), status=status, result_payload=result)
        if status == "success":
            summary["success_count"] += 1
        elif status == "conflict":
            summary["conflict_count"] += 1
        elif status == "skipped":
            summary["skipped_count"] += 1
        else:
            summary["failed_count"] += 1
        summary["items"].append(
            {
                "job_id": int(job["id"]),
                "status": status,
                **result,
            }
        )
    return summary


__all__ = [
    "DeferredJobRuntime",
    "get_user_ops_deferred_job_counts",
    "run_due_user_ops_deferred_jobs",
    "schedule_user_ops_auto_assign_class_term_job",
]
