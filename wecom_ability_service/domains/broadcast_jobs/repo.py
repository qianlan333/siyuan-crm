from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ...db import get_db


VALID_STATUSES = (
    "waiting_approval",
    "queued",
    "claimed",
    "sent",
    "failed",
    "cancelled",
)
VALID_SOURCE_TYPES = (
    "campaign",
    "sop",
    "workflow",
    "operation_task",
    "cloud_plan",
    "focus_send",
    "deferred",
    "manual",
)

_BASE_COLUMNS = (
    "id, source_type, source_id, source_table, scheduled_for, priority, batch_key, "
    "status, requires_approval, approved_by, approved_at, "
    "cancelled_by, cancelled_at, cancel_reason, "
    "target_external_userids, target_count, target_summary, "
    "content_type, content_payload, content_summary, "
    "attempt_count, last_error, outbound_task_id, sent_count, failed_count, "
    "trace_id, created_by, created_at, updated_at, claimed_at, sent_at"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")


def _normalize_dt(value: Any) -> str:
    """将各种时间值标准化为 PG TIMESTAMPTZ 可正确解析的带时区字符串。

    naive datetime 视为本地时间（服务器 Asia/Shanghai），而非 UTC。
    """
    if value is None:
        return _now_iso()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # naive datetime 来自 datetime.now() — 本地时间，标记为 +08:00
            return value.strftime("%Y-%m-%d %H:%M:%S+08:00")
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
    return str(value).strip() or _now_iso()


def _bool_to_db(value: bool) -> Any:
    return bool(value)


def _to_jsonb_text(payload: Any, *, default: str = "{}") -> str:
    if payload is None:
        return default
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, str):
        return payload or default
    return json.dumps(payload, ensure_ascii=False)


def _decode_jsonb(value: Any, *, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _row_to_dict(row: Any) -> dict[str, Any]:
    record = dict(row)
    record["target_external_userids"] = _decode_jsonb(
        record.get("target_external_userids"), default=[]
    )
    record["content_payload"] = _decode_jsonb(
        record.get("content_payload"), default={}
    )
    record["requires_approval"] = bool(record.get("requires_approval") or False)
    return record


def insert_job(
    *,
    source_type: str,
    source_id: str,
    source_table: str,
    scheduled_for: Any,
    priority: int,
    batch_key: str,
    status: str,
    requires_approval: bool,
    target_external_userids: list[str],
    target_summary: str,
    content_type: str,
    content_payload: dict[str, Any],
    content_summary: str,
    trace_id: str,
    created_by: str,
) -> int:
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"invalid source_type: {source_type!r}")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    target_list = list(target_external_userids or [])
    target_count = len(target_list)
    db = get_db()
    row = db.execute(
        """
        INSERT INTO broadcast_jobs (
            source_type, source_id, source_table, scheduled_for, priority, batch_key,
            status, requires_approval,
            target_external_userids, target_count, target_summary,
            content_type, content_payload, content_summary,
            trace_id, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            source_type,
            str(source_id or ""),
            str(source_table or ""),
            _normalize_dt(scheduled_for),
            int(priority),
            str(batch_key or ""),
            status,
            _bool_to_db(requires_approval),
            _to_jsonb_text(target_list, default="[]"),
            target_count,
            str(target_summary or ""),
            str(content_type or "text"),
            _to_jsonb_text(content_payload, default="{}"),
            str(content_summary or ""),
            str(trace_id or ""),
            str(created_by or ""),
        ),
    )
    result = row.fetchone()
    db.commit()
    return int(result["id"])


def fetch_job_by_id(job_id: int) -> dict[str, Any] | None:
    db = get_db()
    row = db.execute(
        f"SELECT {_BASE_COLUMNS} FROM broadcast_jobs WHERE id = ? LIMIT 1",
        (int(job_id),),
    ).fetchone()
    return _row_to_dict(row) if row else None


def fetch_jobs_filtered(
    *,
    statuses: list[str] | None = None,
    source_types: list[str] | None = None,
    since: Any = None,
    until: Any = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if statuses:
        placeholders = ", ".join("?" * len(statuses))
        where.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if source_types:
        placeholders = ", ".join("?" * len(source_types))
        where.append(f"source_type IN ({placeholders})")
        params.extend(source_types)
    if since is not None:
        where.append("scheduled_for >= ?")
        params.append(_normalize_dt(since))
    if until is not None:
        where.append("scheduled_for <= ?")
        params.append(_normalize_dt(until))
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    params.append(int(limit))
    params.append(int(offset))
    sql = (
        f"SELECT {_BASE_COLUMNS} FROM broadcast_jobs"
        f"{where_sql} ORDER BY scheduled_for DESC, id DESC LIMIT ? OFFSET ?"
    )
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(r) for r in rows]


def fetch_job_by_source(
    *,
    source_type: str,
    source_id: str,
    source_table: str = "",
    statuses: list[str] | None = None,
) -> dict[str, Any] | None:
    where = ["source_type = ?", "source_id = ?"]
    params: list[Any] = [str(source_type or ""), str(source_id or "")]
    if source_table:
        where.append("source_table = ?")
        params.append(str(source_table or ""))
    if statuses:
        placeholders = ", ".join("?" * len(statuses))
        where.append(f"status IN ({placeholders})")
        params.extend(statuses)
    sql = (
        f"SELECT {_BASE_COLUMNS} FROM broadcast_jobs "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY id DESC LIMIT 1"
    )
    row = get_db().execute(sql, tuple(params)).fetchone()
    return _row_to_dict(row) if row else None


def claim_due_jobs(*, now: Any, limit: int) -> list[dict[str, Any]]:
    """原子地把到期的 queued 任务标 claimed 并返回。

    用 UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING
    保证多 worker 并发安全。
    """
    db = get_db()
    cutoff = _normalize_dt(now)
    rows = db.execute(
        f"""
        UPDATE broadcast_jobs
        SET status = 'claimed',
            claimed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            attempt_count = attempt_count + 1
        WHERE id IN (
            SELECT id FROM broadcast_jobs
            WHERE status = 'queued' AND scheduled_for <= ?
            ORDER BY scheduled_for ASC, priority ASC, id ASC
            LIMIT ?
            FOR UPDATE SKIP LOCKED
        )
        RETURNING {_BASE_COLUMNS}
        """,
        (cutoff, int(limit)),
    ).fetchall()
    db.commit()
    return [_row_to_dict(r) for r in rows]


def mark_sent(
    job_id: int,
    *,
    outbound_task_id: int | None,
    sent_count: int,
    failed_count: int,
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE broadcast_jobs
        SET status = 'sent',
            sent_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            outbound_task_id = ?,
            sent_count = ?,
            failed_count = ?,
            last_error = ''
        WHERE id = ? AND status = 'claimed'
        """,
        (
            int(outbound_task_id) if outbound_task_id else None,
            int(sent_count),
            int(failed_count),
            int(job_id),
        ),
    )
    db.commit()


def mark_failed(job_id: int, *, error: str) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE broadcast_jobs
        SET status = 'failed',
            updated_at = CURRENT_TIMESTAMP,
            last_error = ?
        WHERE id = ? AND status IN ('claimed', 'queued')
        """,
        (str(error or "")[:4000], int(job_id)),
    )
    db.commit()


def cancel_job(job_id: int, *, cancelled_by: str, reason: str) -> int:
    db = get_db()
    cur = db.execute(
        """
        UPDATE broadcast_jobs
        SET status = 'cancelled',
            cancelled_by = ?,
            cancelled_at = CURRENT_TIMESTAMP,
            cancel_reason = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status IN ('queued', 'waiting_approval')
        """,
        (str(cancelled_by or ""), str(reason or "")[:1000], int(job_id)),
    )
    db.commit()
    return int(getattr(cur, "rowcount", 0) or 0)


def approve_job(job_id: int, *, approved_by: str) -> int:
    db = get_db()
    cur = db.execute(
        """
        UPDATE broadcast_jobs
        SET status = 'queued',
            approved_by = ?,
            approved_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status = 'waiting_approval'
        """,
        (str(approved_by or ""), int(job_id)),
    )
    db.commit()
    return int(getattr(cur, "rowcount", 0) or 0)


def approve_job_by_source(
    *, source_table: str, source_id: str, approved_by: str
) -> int:
    db = get_db()
    cur = db.execute(
        """
        UPDATE broadcast_jobs
        SET status = 'queued',
            approved_by = ?,
            approved_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE source_table = ? AND source_id = ? AND status = 'waiting_approval'
        """,
        (str(approved_by or ""), str(source_table), str(source_id)),
    )
    db.commit()
    return int(getattr(cur, "rowcount", 0) or 0)


def count_jobs_by_status() -> dict[str, int]:
    rows = get_db().execute(
        "SELECT status, COUNT(*) AS cnt FROM broadcast_jobs GROUP BY status"
    ).fetchall()
    return {str(r["status"]): int(r["cnt"]) for r in rows}
