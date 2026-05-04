from __future__ import annotations

from typing import Any

from ..db import get_db

# Per-source upper bound when no caller-provided limit is given. Picked so the
# combined-page can still produce a correct top-N ordering after global sort
# without pulling unbounded rows for hot customers.
_DEFAULT_FETCH_LIMIT = 200


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _normalize_limit(limit: int | None) -> int:
    if limit is None or limit <= 0:
        return _DEFAULT_FETCH_LIMIT
    return int(limit)


def has_customer_timeline_scope(external_userid: str, *, customer_pulse_tenant_key: str = "") -> bool:
    for table in [
        "contacts",
        "archived_messages",
        "class_user_status_history",
        "customer_marketing_state_history",
        "customer_value_segment_history",
        "conversion_dispatch_log",
        "questionnaire_submissions",
        "wecom_external_contact_event_logs",
    ]:
        row = get_db().execute(
            f"SELECT 1 AS found FROM {table} WHERE external_userid = ? LIMIT 1",
            (external_userid,),
        ).fetchone()
        if row:
            return True
    if str(customer_pulse_tenant_key or "").strip():
        row = get_db().execute(
            """
            SELECT 1 AS found
            FROM customer_pulse_activity_logs
            WHERE tenant_key = ?
              AND external_userid = ?
            LIMIT 1
            """,
            (str(customer_pulse_tenant_key).strip(), external_userid),
        ).fetchone()
        if row:
            return True
    return False


def fetch_archived_messages(external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
               msgtype, content, send_time, raw_payload, created_at
        FROM archived_messages
        WHERE external_userid = ?
        ORDER BY send_time DESC, id DESC
        LIMIT ?
        """,
        (external_userid, _normalize_limit(limit)),
    )


def fetch_status_changes(external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, external_userid, old_signup_status, new_signup_status, old_label_name, new_label_name,
               customer_name_snapshot, owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at,
               wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json, created_at
        FROM class_user_status_history
        WHERE external_userid = ?
        ORDER BY set_at DESC, id DESC
        LIMIT ?
        """,
        (external_userid, _normalize_limit(limit)),
    )


def fetch_questionnaire_submissions(external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            qs.id,
            qs.questionnaire_id,
            qs.respondent_key,
            qs.openid,
            qs.unionid,
            qs.external_userid,
            qs.follow_user_userid,
            qs.matched_by,
            qs.source_channel,
            qs.campaign_id,
            qs.staff_id,
            qs.total_score,
            qs.final_tags,
            qs.redirect_url_snapshot,
            qs.submitted_at,
            COALESCE(q.name, '') AS questionnaire_name,
            COALESCE(q.title, '') AS questionnaire_title
        FROM questionnaire_submissions qs
        LEFT JOIN questionnaires q ON q.id = qs.questionnaire_id
        WHERE qs.external_userid = ?
        ORDER BY qs.submitted_at DESC, qs.id DESC
        LIMIT ?
        """,
        (external_userid, _normalize_limit(limit)),
    )


def fetch_wecom_events(external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
               payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
        FROM wecom_external_contact_event_logs
        WHERE external_userid = ?
        ORDER BY event_time DESC, id DESC
        LIMIT ?
        """,
        (external_userid, _normalize_limit(limit)),
    )


def fetch_marketing_state_changes(external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            id,
            person_id,
            external_userid,
            automation_key,
            main_stage,
            sub_stage,
            activated,
            converted,
            eligible_for_conversion,
            batch_id,
            lifecycle_status,
            exit_reason,
            last_activation_at,
            last_conversion_marked_at,
            last_message_at,
            change_reason,
            state_payload_json,
            recorded_at,
            created_at
        FROM customer_marketing_state_history
        WHERE external_userid = ?
        ORDER BY recorded_at DESC, id DESC
        LIMIT ?
        """,
        (external_userid, _normalize_limit(limit)),
    )


def fetch_value_segment_changes(external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            id,
            external_userid,
            segment,
            segment_rank,
            score,
            scoring_version,
            change_reason,
            submission_id,
            matched_question_ids_json,
            source_payload_json,
            evaluated_at,
            recorded_at,
            created_at
        FROM customer_value_segment_history
        WHERE external_userid = ?
        ORDER BY recorded_at DESC, id DESC
        LIMIT ?
        """,
        (external_userid, _normalize_limit(limit)),
    )


def fetch_conversion_dispatch_logs(external_userid: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            id,
            automation_key,
            batch_id,
            external_userid,
            dispatch_status,
            dispatch_channel,
            dispatch_payload_json,
            dispatch_note,
            dispatched_at,
            acked_at,
            created_at,
            updated_at
        FROM conversion_dispatch_log
        WHERE external_userid = ?
        ORDER BY COALESCE(dispatched_at, acked_at, updated_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (external_userid, _normalize_limit(limit)),
    )


def fetch_customer_pulse_activity_logs(
    external_userid: str,
    *,
    tenant_key: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            id,
            card_id,
            external_userid,
            owner_userid,
            activity_type,
            activity_status,
            activity_source,
            tenant_key,
            execution_key,
            idempotency_key,
            title,
            summary,
            due_at,
            operator,
            payload_json,
            undone_at,
            created_at,
            updated_at
        FROM customer_pulse_activity_logs
        WHERE tenant_key = ?
          AND external_userid = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (tenant_key, external_userid, _normalize_limit(limit)),
    )
