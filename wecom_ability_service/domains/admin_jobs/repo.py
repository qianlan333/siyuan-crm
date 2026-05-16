from __future__ import annotations

from typing import Any

from ...db import get_db
from ...db.helpers import fetchall_dicts, fetchone_dict
from ...infra.json_utils import safe_json_loads as _json_loads


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return fetchall_dicts(get_db(), sql, params)


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    return fetchone_dict(get_db(), sql, params)


def list_sync_runs(*, status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    normalized_status = str(status or "").strip()
    sql = """
        SELECT id, status, start_time, end_time, owner_userid, cursor, fetched_count, inserted_count,
               error_message, created_at, finished_at
        FROM sync_runs
    """
    params: list[Any] = []
    if normalized_status:
        sql += " WHERE status = ?"
        params.append(normalized_status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit or 20), 100)))
    return _fetchall_dict(sql, tuple(params))


def get_sync_run_counts() -> dict[str, int]:
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0) AS success_count,
            COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
        FROM sync_runs
        """
    ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0) if row else 0,
        "success_count": int(row["success_count"] or 0) if row else 0,
        "failed_count": int(row["failed_count"] or 0) if row else 0,
    }


def list_callback_logs(*, process_status: str = "", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    normalized_status = str(process_status or "").strip()
    normalized_query = str(query or "").strip().lower()
    sql = """
        SELECT id, corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
               process_status, retry_count, error_message, created_at, updated_at
        FROM wecom_external_contact_event_logs
    """
    clauses: list[str] = []
    params: list[Any] = []
    if normalized_status:
        clauses.append("process_status = ?")
        params.append(normalized_status)
    if normalized_query:
        like_value = f"%{normalized_query}%"
        clauses.append(
            "("
            "LOWER(event_type) LIKE ? OR LOWER(change_type) LIKE ? OR LOWER(external_userid) LIKE ? "
            "OR LOWER(user_id) LIKE ? OR LOWER(error_message) LIKE ? OR LOWER(event_key) LIKE ?"
            ")"
        )
        params.extend([like_value] * 6)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit or 20), 100)))
    return _fetchall_dict(sql, tuple(params))


def get_callback_counts() -> dict[str, int]:
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN process_status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
            COALESCE(SUM(CASE WHEN process_status = 'processing' THEN 1 ELSE 0 END), 0) AS processing_count,
            COALESCE(SUM(CASE WHEN process_status = 'success' THEN 1 ELSE 0 END), 0) AS success_count,
            COALESCE(SUM(CASE WHEN process_status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
        FROM wecom_external_contact_event_logs
        """
    ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0) if row else 0,
        "pending_count": int(row["pending_count"] or 0) if row else 0,
        "processing_count": int(row["processing_count"] or 0) if row else 0,
        "success_count": int(row["success_count"] or 0) if row else 0,
        "failed_count": int(row["failed_count"] or 0) if row else 0,
    }


def list_message_batches(*, status: str = "", limit: int = 20) -> list[dict[str, Any]]:
    normalized_status = str(status or "").strip()
    sql = """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
    """
    params: list[Any] = []
    if normalized_status:
        sql += " WHERE status = ?"
        params.append(normalized_status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit or 20), 100)))
    return _fetchall_dict(sql, tuple(params))


def get_message_batch_counts() -> dict[str, int]:
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
            COALESCE(SUM(CASE WHEN status = 'acked' THEN 1 ELSE 0 END), 0) AS acked_count
        FROM message_batches
        """
    ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0) if row else 0,
        "pending_count": int(row["pending_count"] or 0) if row else 0,
        "acked_count": int(row["acked_count"] or 0) if row else 0,
    }


def list_deferred_jobs(
    *,
    status: str = "",
    owner_userid: str = "",
    external_userid: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    normalized_status = str(status or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    normalized_external_userid = str(external_userid or "").strip()
    sql = """
        SELECT id, job_type, external_userid, owner_userid, run_after, status,
               attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
    """
    clauses: list[str] = []
    params: list[Any] = []
    if normalized_status:
        clauses.append("status = ?")
        params.append(normalized_status)
    if normalized_owner_userid:
        clauses.append("owner_userid = ?")
        params.append(normalized_owner_userid)
    if normalized_external_userid:
        clauses.append("external_userid = ?")
        params.append(normalized_external_userid)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY run_after ASC, id ASC LIMIT ?"
    params.append(max(1, min(int(limit or 20), 100)))
    rows = _fetchall_dict(sql, tuple(params))
    for row in rows:
        row["payload_json"] = _json_loads(row.get("payload_json"), default={})
        row["result_json"] = _json_loads(row.get("result_json"), default={})
    return rows


def get_selected_message_batch(batch_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    )
