from __future__ import annotations

import json
from typing import Any

from ...db import get_db, get_db_backend


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return parsed


def list_recent_customer_messages(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
               msgtype, content, send_time, raw_payload, created_at
        FROM archived_messages
        WHERE external_userid = ?
        ORDER BY send_time DESC, id DESC
        LIMIT ?
        """,
        (str(external_userid or "").strip(), max(1, min(int(limit or 20), 100))),
    )


def list_customer_questionnaire_history(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            qs.id,
            qs.questionnaire_id,
            qs.external_userid,
            qs.follow_user_userid,
            qs.total_score,
            qs.final_tags,
            qs.redirect_url_snapshot,
            qs.submitted_at,
            COALESCE(q.name, '') AS questionnaire_name,
            COALESCE(q.title, '') AS questionnaire_title,
            COALESCE(apply_logs.status, '') AS scrm_apply_status,
            COALESCE(apply_logs.error_message, '') AS scrm_apply_error,
            COALESCE(apply_logs.created_at, '') AS scrm_apply_at
        FROM questionnaire_submissions qs
        LEFT JOIN questionnaires q
          ON q.id = qs.questionnaire_id
        LEFT JOIN questionnaire_scrm_apply_logs apply_logs
          ON apply_logs.id = (
                SELECT inner_logs.id
                FROM questionnaire_scrm_apply_logs inner_logs
                WHERE inner_logs.submission_id = qs.id
                ORDER BY inner_logs.id DESC
                LIMIT 1
             )
        WHERE qs.external_userid = ?
        ORDER BY qs.submitted_at DESC, qs.id DESC
        LIMIT ?
        """,
        (str(external_userid or "").strip(), max(1, min(int(limit or 20), 100))),
    )


def list_customer_outbound_tasks(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return []
    rows = _fetchall_dict(
        """
        SELECT id, task_type, request_payload, response_payload, wecom_task_id, status, created_at
        FROM outbound_tasks
        WHERE request_payload LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (f"%{normalized_external_userid}%", max(1, min(int(limit or 20), 200))),
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        request_payload = _json_loads(row.get("request_payload"), default={})
        response_payload = _json_loads(row.get("response_payload"), default={})
        external_userids: list[str] = []
        raw_external_userids = request_payload.get("external_userid") or request_payload.get("external_userids") or []
        if isinstance(raw_external_userids, list):
            external_userids = [str(item or "").strip() for item in raw_external_userids if str(item or "").strip()]
        elif raw_external_userids:
            external_userids = [str(raw_external_userids).strip()]
        if normalized_external_userid not in external_userids:
            continue
        results.append(
            {
                **row,
                "request_payload": request_payload,
                "response_payload": response_payload,
                "external_userids": external_userids,
            }
        )
    return results[: max(1, min(int(limit or 20), 100))]


def list_questionnaire_submissions(questionnaire_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            id,
            questionnaire_id,
            respondent_key,
            openid,
            unionid,
            external_userid,
            follow_user_userid,
            matched_by,
            mobile_snapshot,
            source_channel,
            campaign_id,
            staff_id,
            total_score,
            final_tags,
            redirect_url_snapshot,
            submitted_at
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        ORDER BY submitted_at DESC, id DESC
        LIMIT ?
        """,
        (int(questionnaire_id), max(1, min(int(limit or 50), 200))),
    )


def list_questionnaire_apply_logs(questionnaire_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            logs.id,
            logs.submission_id,
            logs.external_userid,
            logs.follow_user_userid,
            logs.final_tags,
            logs.status,
            logs.error_message,
            logs.created_at,
            qs.submitted_at
        FROM questionnaire_scrm_apply_logs logs
        INNER JOIN questionnaire_submissions qs
          ON qs.id = logs.submission_id
        WHERE qs.questionnaire_id = ?
        ORDER BY logs.created_at DESC, logs.id DESC
        LIMIT ?
        """,
        (int(questionnaire_id), max(1, min(int(limit or 50), 200))),
    )


def list_questionnaire_external_push_logs(
    questionnaire_id: int,
    *,
    status: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    normalized_status = str(status or "").strip()
    sql = """
        SELECT
            id,
            questionnaire_id,
            questionnaire_title_snapshot,
            submission_record_id,
            retry_from_log_id,
            retry_attempt,
            user_id,
            target_url,
            request_payload,
            response_status_code,
            response_body,
            status,
            failure_reason,
            created_at,
            updated_at
        FROM questionnaire_external_push_logs
        WHERE questionnaire_id = ?
    """
    params: list[Any] = [int(questionnaire_id)]
    if normalized_status:
        sql += " AND status = ?"
        params.append(normalized_status)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit or 50), 200)))
    rows = _fetchall_dict(sql, tuple(params))
    for row in rows:
        row["request_payload"] = _json_loads(row.get("request_payload"), default={})
    return rows


def get_questionnaire_external_push_log(log_id: int) -> dict[str, Any] | None:
    row = _fetchone_dict(
        """
        SELECT
            id,
            questionnaire_id,
            questionnaire_title_snapshot,
            submission_record_id,
            retry_from_log_id,
            retry_attempt,
            user_id,
            target_url,
            request_payload,
            response_status_code,
            response_body,
            status,
            failure_reason,
            created_at,
            updated_at
        FROM questionnaire_external_push_logs
        WHERE id = ?
        """,
        (int(log_id),),
    )
    if not row:
        return None
    row["request_payload"] = _json_loads(row.get("request_payload"), default={})
    return row


def list_questionnaire_external_push_log_threads(
    questionnaire_id: int | None,
    *,
    questionnaire_title: str = "",
    user_id: str = "",
    target_url: str = "",
    status: str = "",
    limit: int | None = 50,
) -> list[dict[str, Any]]:
    normalized_status = str(status or "").strip()
    normalized_questionnaire_title = str(questionnaire_title or "").strip()
    normalized_user_id = str(user_id or "").strip()
    normalized_target_url = str(target_url or "").strip()
    sql = """
        SELECT
            id,
            questionnaire_id,
            questionnaire_title_snapshot,
            submission_record_id,
            retry_from_log_id,
            retry_attempt,
            user_id,
            target_url,
            request_payload,
            response_status_code,
            response_body,
            status,
            failure_reason,
            created_at,
            updated_at
        FROM questionnaire_external_push_logs
        WHERE retry_from_log_id IS NULL
    """
    params: list[Any] = []
    if questionnaire_id is not None:
        sql += " AND questionnaire_id = ?"
        params.append(int(questionnaire_id))
    if normalized_questionnaire_title:
        sql += " AND questionnaire_title_snapshot LIKE ?"
        params.append(f"%{normalized_questionnaire_title}%")
    if normalized_user_id:
        sql += " AND user_id LIKE ?"
        params.append(f"%{normalized_user_id}%")
    if normalized_target_url:
        sql += " AND target_url LIKE ?"
        params.append(f"%{normalized_target_url}%")
    sql += " ORDER BY created_at DESC, id DESC"
    root_rows = _fetchall_dict(sql, tuple(params))
    for row in root_rows:
        row["request_payload"] = _json_loads(row.get("request_payload"), default={})
    root_ids = [int(row["id"]) for row in root_rows]
    retries_by_root: dict[int, list[dict[str, Any]]] = {root_id: [] for root_id in root_ids}
    if root_ids:
        placeholder = ", ".join("?" for _ in root_ids)
        retry_rows = _fetchall_dict(
            f"""
            SELECT
                id,
                questionnaire_id,
                questionnaire_title_snapshot,
                submission_record_id,
                retry_from_log_id,
                retry_attempt,
                user_id,
                target_url,
                request_payload,
                response_status_code,
                response_body,
                status,
                failure_reason,
                created_at,
                updated_at
            FROM questionnaire_external_push_logs
            WHERE retry_from_log_id IN ({placeholder})
            ORDER BY created_at DESC, id DESC
            """,
            tuple(root_ids),
        )
        for row in retry_rows:
            row["request_payload"] = _json_loads(row.get("request_payload"), default={})
            retry_from_log_id = int(row.get("retry_from_log_id") or 0)
            retries_by_root.setdefault(retry_from_log_id, []).append(row)

    threads: list[dict[str, Any]] = []
    for root in root_rows:
        retries = retries_by_root.get(int(root["id"]), [])
        latest = retries[0] if retries else root
        effective_status = str(latest.get("status") or "").strip()
        if normalized_status and effective_status != normalized_status:
            continue
        threads.append(
            {
                **root,
                "is_retry": False,
                "retry_count": len(retries),
                "retries": retries,
                "latest_log": latest,
                "latest_status": effective_status,
                "latest_response_status_code": latest.get("response_status_code"),
                "latest_response_body": latest.get("response_body"),
                "latest_failure_reason": latest.get("failure_reason"),
                "latest_updated_at": latest.get("updated_at") or latest.get("created_at"),
                "has_retry": bool(retries),
                "can_retry": effective_status == "failed",
            }
        )
    threads.sort(key=lambda item: (str(item.get("latest_updated_at") or ""), int(item.get("latest_log", {}).get("id") or 0)), reverse=True)
    if limit is None:
        return threads
    return threads[: max(1, min(int(limit or 50), 200))]


def count_questionnaire_external_push_logs(
    *,
    questionnaire_id: int | None = None,
    questionnaire_title: str = "",
    user_id: str = "",
    target_url: str = "",
    status: str = "",
    created_at_gte: str = "",
) -> int:
    sql = "SELECT COUNT(*) AS total FROM questionnaire_external_push_logs WHERE 1 = 1"
    params: list[Any] = []
    if questionnaire_id is not None:
        sql += " AND questionnaire_id = ?"
        params.append(int(questionnaire_id))
    if str(questionnaire_title or "").strip():
        sql += " AND questionnaire_title_snapshot LIKE ?"
        params.append(f"%{str(questionnaire_title).strip()}%")
    if str(user_id or "").strip():
        sql += " AND user_id LIKE ?"
        params.append(f"%{str(user_id).strip()}%")
    if str(target_url or "").strip():
        sql += " AND target_url LIKE ?"
        params.append(f"%{str(target_url).strip()}%")
    if str(status or "").strip():
        sql += " AND status = ?"
        params.append(str(status).strip())
    if str(created_at_gte or "").strip():
        sql += " AND created_at >= ?"
        params.append(str(created_at_gte).strip())
    row = _fetchone_dict(sql, tuple(params)) or {}
    return int(row.get("total") or 0)


def summarize_questionnaire_external_push_logs(questionnaire_id: int) -> dict[str, Any]:
    row = _fetchone_dict(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
            MAX(created_at) AS last_created_at
        FROM questionnaire_external_push_logs
        WHERE questionnaire_id = ?
        """,
        (int(questionnaire_id),),
    ) or {}
    return {
        "total_count": int(row.get("total_count") or 0),
        "success_count": int(row.get("success_count") or 0),
        "failed_count": int(row.get("failed_count") or 0),
        "last_created_at": str(row.get("last_created_at") or "").strip(),
    }


def list_recent_user_ops_import_batches(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, import_type, file_name, total_rows, success_rows, failed_rows,
               error_summary, created_by, created_at
        FROM user_ops_import_batches
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 20), 100)),),
    )


def list_deferred_jobs(*, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    normalized_status = str(status or "").strip()
    sql = """
        SELECT id, job_type, external_userid, owner_userid, run_after, status,
               attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
    """
    params: list[Any] = []
    if normalized_status:
        sql += " WHERE status = ?"
        params.append(normalized_status)
    sql += " ORDER BY run_after ASC, id ASC LIMIT ?"
    params.append(max(1, min(int(limit or 50), 200)))
    rows = _fetchall_dict(sql, tuple(params))
    for row in rows:
        row["payload_json"] = _json_loads(row.get("payload_json"), default={})
        row["result_json"] = _json_loads(row.get("result_json"), default={})
    return rows


def list_recent_admin_operation_logs(*, target_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
    normalized_target_type = str(target_type or "").strip()
    sql = """
        SELECT id, operator, action_type, target_type, target_id, before_json, after_json, created_at
        FROM admin_operation_logs
    """
    params: list[Any] = []
    if normalized_target_type:
        sql += " WHERE target_type = ?"
        params.append(normalized_target_type)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(int(limit or 20), 100)))
    rows = _fetchall_dict(sql, tuple(params))
    for row in rows:
        row["before_json"] = _json_loads(row.get("before_json"), default={})
        row["after_json"] = _json_loads(row.get("after_json"), default={})
    return rows


def get_latest_questionnaire_apply_log(submission_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT id, submission_id, external_userid, follow_user_userid, final_tags,
               status, error_message, created_at
        FROM questionnaire_scrm_apply_logs
        WHERE submission_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(submission_id),),
    )


def ping_database() -> bool:
    row = get_db().execute("SELECT 1 AS ok").fetchone()
    return bool(row and int(row["ok"] or 0) == 1)


def get_mcp_dependency_snapshot() -> dict[str, Any]:
    counts: dict[str, Any] = {
        "database_backend": get_db_backend(),
        "database_ok": ping_database(),
        "contacts_total": 0,
        "archived_messages_total": 0,
        "message_batches_total": 0,
        "message_batches_pending": 0,
    }

    contacts_row = get_db().execute("SELECT COUNT(*) AS total, MAX(updated_at) AS latest_updated_at FROM contacts").fetchone()
    if contacts_row:
        counts["contacts_total"] = int(contacts_row["total"] or 0)
        counts["contacts_latest_updated_at"] = str(contacts_row["latest_updated_at"] or "").strip()

    archived_row = get_db().execute("SELECT COUNT(*) AS total, MAX(send_time) AS latest_send_time FROM archived_messages").fetchone()
    if archived_row:
        counts["archived_messages_total"] = int(archived_row["total"] or 0)
        counts["archived_messages_latest_send_time"] = str(archived_row["latest_send_time"] or "").strip()

    message_batch_row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_total
        FROM message_batches
        """
    ).fetchone()
    if message_batch_row:
        counts["message_batches_total"] = int(message_batch_row["total"] or 0)
        counts["message_batches_pending"] = int(message_batch_row["pending_total"] or 0)

    return counts
