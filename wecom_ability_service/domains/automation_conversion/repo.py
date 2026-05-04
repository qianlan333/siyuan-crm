from __future__ import annotations

import json
from typing import Any

from ...db import cast_text, get_db, get_db_backend, is_postgres

_AUTOMATION_SOP_POOL_LOCK_NAMESPACE = 41017


def _db_bool(value: bool) -> bool | int:
    return value if get_db_backend() == "postgres" else (1 if value else 0)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps({} if value is None else value, ensure_ascii=False)


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _row_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _sop_pool_lookup_keys(pool_key: str) -> tuple[str, ...]:
    normalized_pool_key = _normalized_text(pool_key)
    if not normalized_pool_key:
        return ()
    alias_groups = {
        "pending_questionnaire": ("pending_questionnaire", "new_user"),
        "operating": (
            "operating",
            "inactive_normal",
            "inactive_focus",
            "active_normal",
            "active_focus",
            "silent",
        ),
        "converted": ("converted", "won"),
    }
    return alias_groups.get(normalized_pool_key, (normalized_pool_key,))


def _stage_route_lookup_keys(route_key: str) -> tuple[str, ...]:
    normalized_route_key = _normalized_text(route_key)
    if not normalized_route_key:
        return ()
    alias_groups = {
        "pending-questionnaire": ("pending-questionnaire", "new-user"),
        "new-user": ("pending-questionnaire", "new-user"),
        "operating": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "inactive-normal": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "inactive-focus": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "active-normal": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "active-focus": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "silent": (
            "operating",
            "inactive-normal",
            "inactive-focus",
            "active-normal",
            "active-focus",
            "silent",
        ),
        "converted": ("converted", "won"),
        "won": ("converted", "won"),
    }
    return alias_groups.get(normalized_route_key, (normalized_route_key,))


def lookup_person_id_by_external_contact_id(external_contact_id: str) -> int | None:
    row = _fetchone_dict(
        """
        SELECT person_id
        FROM external_contact_bindings
        WHERE external_userid = ?
        LIMIT 1
        """,
        (_normalized_text(external_contact_id),),
    )
    person_id = row.get("person_id") if row else None
    return int(person_id) if person_id not in (None, "") else None


def lookup_person_id_by_phone(phone: str) -> int | None:
    row = _fetchone_dict(
        """
        SELECT id
        FROM people
        WHERE mobile = ?
        LIMIT 1
        """,
        (_normalized_text(phone),),
    )
    person_id = row.get("id") if row else None
    return int(person_id) if person_id not in (None, "") else None


def list_external_contact_ids_by_person_id(person_id: int | None) -> list[str]:
    if person_id in (None, ""):
        return []
    rows = _fetchall_dicts(
        """
        SELECT external_userid
        FROM external_contact_bindings
        WHERE person_id = ?
        ORDER BY updated_at DESC, external_userid ASC
        """,
        (int(person_id),),
    )
    return [_normalized_text(row.get("external_userid")) for row in rows if _normalized_text(row.get("external_userid"))]


def find_latest_external_contact_id_by_phone(phone: str) -> str:
    normalized_phone = _normalized_text(phone)
    if not normalized_phone:
        return ""
    binding_ordering = f"COALESCE({cast_text('b.updated_at')}, {cast_text('b.created_at')}, '')"
    class_status_ordering = f"COALESCE({cast_text('updated_at')}, {cast_text('created_at')}, '')"
    submission_ordering = f"COALESCE({cast_text('submitted_at')}, '')"
    sql = f"""
    SELECT external_userid
    FROM (
        SELECT b.external_userid, {binding_ordering} AS ordering_value
        FROM external_contact_bindings b
        INNER JOIN people p ON p.id = b.person_id
        WHERE p.mobile = ?

        UNION ALL

        SELECT external_userid, {class_status_ordering} AS ordering_value
        FROM class_user_status_current
        WHERE mobile_snapshot = ?

        UNION ALL

        SELECT external_userid, {submission_ordering} AS ordering_value
        FROM questionnaire_submissions
        WHERE mobile_snapshot = ? AND external_userid IS NOT NULL AND external_userid <> ''
    ) candidates
    WHERE external_userid IS NOT NULL AND external_userid <> ''
    ORDER BY ordering_value DESC, external_userid ASC
    LIMIT 1
    """
    row = _fetchone_dict(sql, (normalized_phone, normalized_phone, normalized_phone))
    return _normalized_text((row or {}).get("external_userid"))


def get_member_by_id(member_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE id = ?
        LIMIT 1
        """,
        (int(member_id),),
    )


def get_member_by_external_contact_id(external_contact_id: str) -> dict[str, Any] | None:
    normalized = _normalized_text(external_contact_id)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE external_contact_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def get_member_by_phone(phone: str) -> dict[str, Any] | None:
    normalized = _normalized_text(phone)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE phone = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def list_members_by_ids(member_ids: list[int]) -> list[dict[str, Any]]:
    normalized_ids = [int(item) for item in member_ids if str(item).strip()]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        tuple(normalized_ids),
    )


def insert_member(payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(payload.get("external_contact_id")),
        _normalized_text(payload.get("phone")),
        payload.get("master_customer_id"),
        _normalized_text(payload.get("owner_staff_id")),
        _db_bool(bool(payload.get("in_pool"))),
        _normalized_text(payload.get("current_pool")),
        _normalized_text(payload.get("follow_type")),
        _normalized_text(payload.get("questionnaire_status")),
        _normalized_text(payload.get("decision_source")),
        _normalized_text(payload.get("source_type")),
        payload.get("source_channel_id"),
        _normalized_text(payload.get("last_active_pool")),
        _normalized_text(payload.get("joined_at")),
        _normalized_text(payload.get("last_ai_push_at")),
        _normalized_text(payload.get("ai_cooldown_until")),
    )
    row = db.execute(
        """
        INSERT INTO automation_member (
            external_contact_id,
            phone,
            master_customer_id,
            owner_staff_id,
            in_pool,
            current_pool,
            follow_type,
            questionnaire_status,
            decision_source,
            source_type,
            source_channel_id,
            last_active_pool,
            joined_at,
            last_ai_push_at,
            ai_cooldown_until,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def update_member(member_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(payload.get("external_contact_id")),
        _normalized_text(payload.get("phone")),
        payload.get("master_customer_id"),
        _normalized_text(payload.get("owner_staff_id")),
        _db_bool(bool(payload.get("in_pool"))),
        _normalized_text(payload.get("current_pool")),
        _normalized_text(payload.get("follow_type")),
        _normalized_text(payload.get("questionnaire_status")),
        _normalized_text(payload.get("decision_source")),
        _normalized_text(payload.get("source_type")),
        payload.get("source_channel_id"),
        _normalized_text(payload.get("last_active_pool")),
        _normalized_text(payload.get("joined_at")),
        _normalized_text(payload.get("last_ai_push_at")),
        _normalized_text(payload.get("ai_cooldown_until")),
        int(member_id),
    )
    row = db.execute(
        """
        UPDATE automation_member
        SET external_contact_id = ?,
            phone = ?,
            master_customer_id = ?,
            owner_staff_id = ?,
            in_pool = ?,
            current_pool = ?,
            follow_type = ?,
            questionnaire_status = ?,
            decision_source = ?,
            source_type = ?,
            source_channel_id = ?,
            last_active_pool = ?,
            joined_at = ?,
            last_ai_push_at = ?,
            ai_cooldown_until = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def insert_event(
    *,
    member_id: int,
    action: str,
    operator_type: str,
    operator_id: str,
    before_snapshot: dict[str, Any] | None,
    after_snapshot: dict[str, Any] | None,
    remark: str = "",
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_event (
            member_id,
            action,
            operator_type,
            operator_id,
            before_snapshot,
            after_snapshot,
            remark,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(member_id),
            _normalized_text(action),
            _normalized_text(operator_type),
            _normalized_text(operator_id),
            _json_dumps(before_snapshot or {}),
            _json_dumps(after_snapshot or {}),
            _normalized_text(remark),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_recent_events(member_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_event
        WHERE member_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(member_id), int(limit)),
    )


def get_latest_manual_event(member_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_event
        WHERE member_id = ?
          AND operator_type = 'user'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (int(member_id),),
    )


def insert_ai_push_log(
    *,
    member_id: int,
    scene: str,
    request_payload: dict[str, Any],
    status: str,
    request_id: str = "",
    error_message: str = "",
    pushed_at: str = "",
    cooldown_until: str = "",
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_ai_push_log (
            member_id,
            scene,
            request_payload,
            status,
            request_id,
            error_message,
            pushed_at,
            cooldown_until
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(member_id),
            _normalized_text(scene),
            _json_dumps(request_payload),
            _normalized_text(status),
            _normalized_text(request_id),
            _normalized_text(error_message),
            _normalized_text(pushed_at),
            _normalized_text(cooldown_until),
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_message_activity_sync_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_message_activity_sync_run (
            trigger_source,
            operator_type,
            operator_id,
            status,
            candidate_count,
            matched_count,
            updated_count,
            skipped_ambiguous_count,
            skipped_unmatched_count,
            skipped_missing_phone_count,
            focus_count,
            normal_count,
            error_message,
            summary_json,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("trigger_source")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("candidate_count") or 0),
            int(payload.get("matched_count") or 0),
            int(payload.get("updated_count") or 0),
            int(payload.get("skipped_ambiguous_count") or 0),
            int(payload.get("skipped_unmatched_count") or 0),
            int(payload.get("skipped_missing_phone_count") or 0),
            int(payload.get("focus_count") or 0),
            int(payload.get("normal_count") or 0),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("summary_json") or {}),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_message_activity_sync_run(run_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_message_activity_sync_run
        SET trigger_source = ?,
            operator_type = ?,
            operator_id = ?,
            status = ?,
            candidate_count = ?,
            matched_count = ?,
            updated_count = ?,
            skipped_ambiguous_count = ?,
            skipped_unmatched_count = ?,
            skipped_missing_phone_count = ?,
            focus_count = ?,
            normal_count = ?,
            error_message = ?,
            summary_json = ?,
            started_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("trigger_source")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("candidate_count") or 0),
            int(payload.get("matched_count") or 0),
            int(payload.get("updated_count") or 0),
            int(payload.get("skipped_ambiguous_count") or 0),
            int(payload.get("skipped_unmatched_count") or 0),
            int(payload.get("skipped_missing_phone_count") or 0),
            int(payload.get("focus_count") or 0),
            int(payload.get("normal_count") or 0),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("summary_json") or {}),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
            int(run_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_latest_message_activity_sync_run() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_message_activity_sync_run
        ORDER BY finished_at DESC, id DESC
        LIMIT 1
        """
    )


def list_message_activity_sync_items(*, run_id: int, limit: int = 100) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_message_activity_sync_item
        WHERE run_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(run_id), int(limit)),
    )


def insert_message_activity_sync_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_message_activity_sync_item (
            run_id,
            member_id,
            external_contact_id,
            phone,
            phone_prefix3,
            phone_last4,
            phone_match_key,
            message_count,
            status,
            detail,
            before_snapshot,
            after_snapshot,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(payload.get("run_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            _normalized_text(payload.get("phone_prefix3")),
            _normalized_text(payload.get("phone_last4")),
            _normalized_text(payload.get("phone_match_key")),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("before_snapshot") or {}),
            _json_dumps(payload.get("after_snapshot") or {}),
            _normalized_text(payload.get("created_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_latest_archived_message_storage_id() -> int:
    row = _fetchone_dict(
        """
        SELECT COALESCE(MAX(id), 0) AS latest_id
        FROM archived_messages
        """
    ) or {}
    return int(row.get("latest_id") or 0)


def list_archived_messages_after_storage_cursor(*, after_id: int, limit: int = 500) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(after_id), int(limit)),
    )


def list_archived_messages_by_ids(message_ids: list[int]) -> list[dict[str, Any]]:
    normalized_ids = [int(item) for item in message_ids if str(item).strip()]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        tuple(normalized_ids),
    )


def list_active_automation_external_contact_ids(external_contact_ids: list[str]) -> list[str]:
    normalized_ids = [_normalized_text(item) for item in external_contact_ids if _normalized_text(item)]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    rows = _fetchall_dicts(
        f"""
        SELECT external_contact_id
        FROM automation_member
        WHERE in_pool = ?
          AND external_contact_id IN ({placeholders})
        ORDER BY external_contact_id ASC
        """,
        (_db_bool(True), *normalized_ids),
    )
    return [_normalized_text(row.get("external_contact_id")) for row in rows if _normalized_text(row.get("external_contact_id"))]


def list_active_automation_members_by_external_contact_ids(external_contact_ids: list[str]) -> list[dict[str, Any]]:
    normalized_ids = [_normalized_text(item) for item in external_contact_ids if _normalized_text(item)]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE in_pool = ?
          AND external_contact_id IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        """,
        (_db_bool(True), *normalized_ids),
    )


def list_app_setting_rows(keys: list[str]) -> list[dict[str, Any]]:
    normalized_keys = [_normalized_text(item) for item in keys if _normalized_text(item)]
    if not normalized_keys:
        return []
    placeholders = ",".join("?" for _ in normalized_keys)
    return _fetchall_dicts(
        f"""
        SELECT key, value, updated_at
        FROM app_settings
        WHERE key IN ({placeholders})
        ORDER BY updated_at DESC, key ASC
        """,
        tuple(normalized_keys),
    )


def get_agent_prompt_row(agent_code: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_prompt_registry
        WHERE agent_code = ?
        LIMIT 1
        """,
        (_normalized_text(agent_code),),
    )


def list_agent_prompt_rows() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_prompt_registry
        ORDER BY updated_at DESC, id DESC
        """
    )


def insert_agent_prompt_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_prompt_registry (
            agent_code,
            display_name,
            prompt_text,
            enabled,
            version,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("display_name")),
            _normalized_text(payload.get("prompt_text")),
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("version") or 1),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_prompt_row(agent_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_prompt_registry
        SET display_name = ?,
            prompt_text = ?,
            enabled = ?,
            version = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE agent_code = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("display_name")),
            _normalized_text(payload.get("prompt_text")),
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("version") or 1),
            _normalized_text(agent_code),
        ),
    ).fetchone()
    return dict(row) if row else {}


def delete_agent_prompt_row(agent_code: str) -> None:
    get_db().execute(
        """
        DELETE FROM automation_agent_prompt_registry
        WHERE agent_code = ?
        """,
        (_normalized_text(agent_code),),
    )


def insert_agent_llm_call_log(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_llm_call_log (
            agent_code,
            model_name,
            request_id,
            status,
            latency_ms,
            error_message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("model_name")),
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("latency_ms") or 0),
            _normalized_text(payload.get("error_message")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_recent_agent_llm_call_logs(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_llm_call_log
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def get_agent_router_config() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_router_config
        WHERE config_key = 'default'
        LIMIT 1
        """
    )


def insert_agent_router_config(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_router_config (
            config_key,
            enabled,
            webhook_url,
            signature_token,
            signature_secret,
            signature_header,
            timeout_seconds,
            retry_count,
            fallback_strategy_json,
            request_sample_json,
            response_sample_json,
            last_status,
            last_error,
            last_called_at,
            updated_by,
            updated_source,
            created_at,
            updated_at
        )
        VALUES (
            'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING *
        """,
        (
            _db_bool(bool(payload.get("enabled"))),
            _normalized_text(payload.get("webhook_url")),
            _normalized_text(payload.get("signature_token")),
            _normalized_text(payload.get("signature_secret")),
            _normalized_text(payload.get("signature_header")) or "X-Lobster-Signature",
            int(payload.get("timeout_seconds") or 8),
            int(payload.get("retry_count") or 1),
            _json_dumps(payload.get("fallback_strategy_json") or {}),
            _json_dumps(payload.get("request_sample_json") or {}),
            _json_dumps(payload.get("response_sample_json") or {}),
            _normalized_text(payload.get("last_status")),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("last_called_at")),
            _normalized_text(payload.get("updated_by")),
            _normalized_text(payload.get("updated_source")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def save_agent_router_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_agent_router_config()
    if existing:
        row = get_db().execute(
            """
            UPDATE automation_agent_router_config
            SET enabled = ?,
                webhook_url = ?,
                signature_token = ?,
                signature_secret = ?,
                signature_header = ?,
                timeout_seconds = ?,
                retry_count = ?,
                fallback_strategy_json = ?,
                request_sample_json = ?,
                response_sample_json = ?,
                last_status = ?,
                last_error = ?,
                last_called_at = ?,
                updated_by = ?,
                updated_source = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                _normalized_text(payload.get("webhook_url")),
                _normalized_text(payload.get("signature_token")),
                _normalized_text(payload.get("signature_secret")),
                _normalized_text(payload.get("signature_header")) or "X-Lobster-Signature",
                int(payload.get("timeout_seconds") or 8),
                int(payload.get("retry_count") or 1),
                _json_dumps(payload.get("fallback_strategy_json") or {}),
                _json_dumps(payload.get("request_sample_json") or {}),
                _json_dumps(payload.get("response_sample_json") or {}),
                _normalized_text(payload.get("last_status")),
                _normalized_text(payload.get("last_error")),
                _normalized_text(payload.get("last_called_at")),
                _normalized_text(payload.get("updated_by")),
                _normalized_text(payload.get("updated_source")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    return insert_agent_router_config(payload)


def get_agent_config_row(agent_code: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_config
        WHERE agent_code = ?
        LIMIT 1
        """,
        (_normalized_text(agent_code),),
    )


def list_agent_config_rows() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_config
        ORDER BY updated_at DESC, id DESC
        """
    )


def insert_agent_config_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_config (
            agent_code,
            display_name,
            pool_keys_json,
            enabled,
            draft_role_prompt,
            draft_task_prompt,
            draft_variables_json,
            draft_output_schema_json,
            published_role_prompt,
            published_task_prompt,
            published_variables_json,
            published_output_schema_json,
            draft_version,
            published_version,
            published_at,
            published_by,
            last_modified_at,
            last_modified_by,
            last_modified_source,
            last_change_summary,
            submitted_for_publish,
            submitted_at,
            submitted_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("display_name")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _db_bool(bool(payload.get("enabled"))),
            _normalized_text(payload.get("draft_role_prompt")),
            _normalized_text(payload.get("draft_task_prompt")),
            _json_dumps(payload.get("draft_variables_json") or payload.get("draft_variables") or []),
            _json_dumps(payload.get("draft_output_schema_json") or payload.get("draft_output_schema") or []),
            _normalized_text(payload.get("published_role_prompt")),
            _normalized_text(payload.get("published_task_prompt")),
            _json_dumps(payload.get("published_variables_json") or payload.get("published_variables") or []),
            _json_dumps(payload.get("published_output_schema_json") or payload.get("published_output_schema") or []),
            int(payload.get("draft_version") or 1),
            int(payload.get("published_version") or 0),
            _normalized_text(payload.get("published_at")),
            _normalized_text(payload.get("published_by")),
            _normalized_text(payload.get("last_modified_at")),
            _normalized_text(payload.get("last_modified_by")),
            _normalized_text(payload.get("last_modified_source")),
            _normalized_text(payload.get("last_change_summary")),
            _db_bool(bool(payload.get("submitted_for_publish"))),
            _normalized_text(payload.get("submitted_at")),
            _normalized_text(payload.get("submitted_by")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_config_row(agent_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_config
        SET display_name = ?,
            pool_keys_json = ?,
            enabled = ?,
            draft_role_prompt = ?,
            draft_task_prompt = ?,
            draft_variables_json = ?,
            draft_output_schema_json = ?,
            published_role_prompt = ?,
            published_task_prompt = ?,
            published_variables_json = ?,
            published_output_schema_json = ?,
            draft_version = ?,
            published_version = ?,
            published_at = ?,
            published_by = ?,
            last_modified_at = ?,
            last_modified_by = ?,
            last_modified_source = ?,
            last_change_summary = ?,
            submitted_for_publish = ?,
            submitted_at = ?,
            submitted_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE agent_code = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("display_name")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _db_bool(bool(payload.get("enabled"))),
            _normalized_text(payload.get("draft_role_prompt")),
            _normalized_text(payload.get("draft_task_prompt")),
            _json_dumps(payload.get("draft_variables_json") or payload.get("draft_variables") or []),
            _json_dumps(payload.get("draft_output_schema_json") or payload.get("draft_output_schema") or []),
            _normalized_text(payload.get("published_role_prompt")),
            _normalized_text(payload.get("published_task_prompt")),
            _json_dumps(payload.get("published_variables_json") or payload.get("published_variables") or []),
            _json_dumps(payload.get("published_output_schema_json") or payload.get("published_output_schema") or []),
            int(payload.get("draft_version") or 1),
            int(payload.get("published_version") or 0),
            _normalized_text(payload.get("published_at")),
            _normalized_text(payload.get("published_by")),
            _normalized_text(payload.get("last_modified_at")),
            _normalized_text(payload.get("last_modified_by")),
            _normalized_text(payload.get("last_modified_source")),
            _normalized_text(payload.get("last_change_summary")),
            _db_bool(bool(payload.get("submitted_for_publish"))),
            _normalized_text(payload.get("submitted_at")),
            _normalized_text(payload.get("submitted_by")),
            _normalized_text(agent_code),
        ),
    ).fetchone()
    return dict(row) if row else {}


def delete_agent_config_row(agent_code: str) -> None:
    get_db().execute(
        """
        DELETE FROM automation_agent_config
        WHERE agent_code = ?
        """,
        (_normalized_text(agent_code),),
    )


def get_agent_skill_row(skill_code: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_skill_registry
        WHERE skill_code = ?
        LIMIT 1
        """,
        (_normalized_text(skill_code),),
    )


def list_agent_skill_rows() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_skill_registry
        ORDER BY updated_at DESC, id DESC
        """
    )


def list_agent_skill_rows_for_agent(agent_code: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_skill_registry
        WHERE agent_code = ?
        ORDER BY skill_code ASC, id ASC
        """,
        (_normalized_text(agent_code),),
    )


def insert_agent_skill_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_skill_registry (
            skill_code,
            agent_code,
            pool_keys_json,
            read_capabilities_json,
            write_capabilities_json,
            enabled,
            input_schema_json,
            output_schema_json,
            permission_notes,
            idempotency_notes,
            audit_notes,
            example_request_json,
            example_response_json,
            last_call_status,
            last_error,
            last_called_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("skill_code")),
            _normalized_text(payload.get("agent_code")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _json_dumps(payload.get("read_capabilities_json") or payload.get("read_capabilities") or []),
            _json_dumps(payload.get("write_capabilities_json") or payload.get("write_capabilities") or []),
            _db_bool(bool(payload.get("enabled"))),
            _json_dumps(payload.get("input_schema_json") or payload.get("input_schema") or {}),
            _json_dumps(payload.get("output_schema_json") or payload.get("output_schema") or {}),
            _normalized_text(payload.get("permission_notes")),
            _normalized_text(payload.get("idempotency_notes")),
            _normalized_text(payload.get("audit_notes")),
            _json_dumps(payload.get("example_request_json") or payload.get("example_request") or {}),
            _json_dumps(payload.get("example_response_json") or payload.get("example_response") or {}),
            _normalized_text(payload.get("last_call_status")),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("last_called_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_skill_row(skill_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_skill_registry
        SET agent_code = ?,
            pool_keys_json = ?,
            read_capabilities_json = ?,
            write_capabilities_json = ?,
            enabled = ?,
            input_schema_json = ?,
            output_schema_json = ?,
            permission_notes = ?,
            idempotency_notes = ?,
            audit_notes = ?,
            example_request_json = ?,
            example_response_json = ?,
            last_call_status = ?,
            last_error = ?,
            last_called_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE skill_code = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("agent_code")),
            _json_dumps(payload.get("pool_keys_json") or payload.get("pool_keys") or []),
            _json_dumps(payload.get("read_capabilities_json") or payload.get("read_capabilities") or []),
            _json_dumps(payload.get("write_capabilities_json") or payload.get("write_capabilities") or []),
            _db_bool(bool(payload.get("enabled"))),
            _json_dumps(payload.get("input_schema_json") or payload.get("input_schema") or {}),
            _json_dumps(payload.get("output_schema_json") or payload.get("output_schema") or {}),
            _normalized_text(payload.get("permission_notes")),
            _normalized_text(payload.get("idempotency_notes")),
            _normalized_text(payload.get("audit_notes")),
            _json_dumps(payload.get("example_request_json") or payload.get("example_request") or {}),
            _json_dumps(payload.get("example_response_json") or payload.get("example_response") or {}),
            _normalized_text(payload.get("last_call_status")),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("last_called_at")),
            _normalized_text(skill_code),
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_agent_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_run (
            run_id,
            request_id,
            batch_id,
            userid,
            external_contact_id,
            agent_code,
            agent_type,
            provider,
            input_snapshot_json,
            variables_snapshot_json,
            final_prompt_preview,
            role_prompt_version,
            task_prompt_version,
            status,
            error_code,
            error_message,
            latency_ms,
            source,
            parent_run_id,
            replay_of_run_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("run_id")),
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("batch_id")),
            _normalized_text(payload.get("userid")),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("agent_type")),
            _normalized_text(payload.get("provider")),
            _json_dumps(payload.get("input_snapshot_json") or payload.get("input_snapshot") or {}),
            _json_dumps(payload.get("variables_snapshot_json") or payload.get("variables_snapshot") or {}),
            _normalized_text(payload.get("final_prompt_preview")),
            _normalized_text(payload.get("role_prompt_version")),
            _normalized_text(payload.get("task_prompt_version")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            int(payload.get("latency_ms") or 0),
            _normalized_text(payload.get("source")),
            _normalized_text(payload.get("parent_run_id")),
            _normalized_text(payload.get("replay_of_run_id")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_run(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_run
        SET request_id = ?,
            batch_id = ?,
            userid = ?,
            external_contact_id = ?,
            agent_code = ?,
            agent_type = ?,
            provider = ?,
            input_snapshot_json = ?,
            variables_snapshot_json = ?,
            final_prompt_preview = ?,
            role_prompt_version = ?,
            task_prompt_version = ?,
            status = ?,
            error_code = ?,
            error_message = ?,
            latency_ms = ?,
            source = ?,
            parent_run_id = ?,
            replay_of_run_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE run_id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("batch_id")),
            _normalized_text(payload.get("userid")),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("agent_type")),
            _normalized_text(payload.get("provider")),
            _json_dumps(payload.get("input_snapshot_json") or payload.get("input_snapshot") or {}),
            _json_dumps(payload.get("variables_snapshot_json") or payload.get("variables_snapshot") or {}),
            _normalized_text(payload.get("final_prompt_preview")),
            _normalized_text(payload.get("role_prompt_version")),
            _normalized_text(payload.get("task_prompt_version")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            int(payload.get("latency_ms") or 0),
            _normalized_text(payload.get("source")),
            _normalized_text(payload.get("parent_run_id")),
            _normalized_text(payload.get("replay_of_run_id")),
            _normalized_text(run_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_agent_run_row(run_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_run
        WHERE run_id = ?
        LIMIT 1
        """,
        (_normalized_text(run_id),),
    )


def get_agent_run_row_by_request_id(request_id: str) -> dict[str, Any] | None:
    normalized_request_id = _normalized_text(request_id)
    if not normalized_request_id:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_run
        WHERE request_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_request_id,),
    )


def _agent_run_where_sql(filters: dict[str, Any] | None = None) -> tuple[str, list[Any]]:
    filters = dict(filters or {})
    clauses: list[str] = []
    params: list[Any] = []
    if _normalized_text(filters.get("request_id")):
        clauses.append("request_id = ?")
        params.append(_normalized_text(filters.get("request_id")))
    if _normalized_text(filters.get("batch_id")):
        clauses.append("batch_id = ?")
        params.append(_normalized_text(filters.get("batch_id")))
    if _normalized_text(filters.get("agent_code")):
        clauses.append("agent_code = ?")
        params.append(_normalized_text(filters.get("agent_code")))
    if _normalized_text(filters.get("userid")):
        clauses.append("userid = ?")
        params.append(_normalized_text(filters.get("userid")))
    if _normalized_text(filters.get("external_contact_id")):
        clauses.append("external_contact_id = ?")
        params.append(_normalized_text(filters.get("external_contact_id")))
    if _normalized_text(filters.get("date_from")):
        clauses.append("created_at >= ?")
        params.append(_normalized_text(filters.get("date_from")))
    if _normalized_text(filters.get("date_to")):
        clauses.append("created_at <= ?")
        params.append(_normalized_text(filters.get("date_to")))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def count_agent_run_rows(filters: dict[str, Any] | None = None) -> int:
    where_sql, params = _agent_run_where_sql(filters)
    row = _fetchone_dict(f"SELECT COUNT(*) AS total FROM automation_agent_run {where_sql}", tuple(params)) or {}
    return int(row.get("total") or 0)


def list_agent_run_rows(*, filters: dict[str, Any] | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    where_sql, params = _agent_run_where_sql(filters)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_agent_run
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        tuple([*params, int(limit), int(offset)]),
    )


def _agent_output_where_sql(filters: dict[str, Any] | None = None) -> tuple[str, list[Any]]:
    filters = dict(filters or {})
    clauses: list[str] = []
    params: list[Any] = []
    if _normalized_text(filters.get("request_id")):
        clauses.append("request_id = ?")
        params.append(_normalized_text(filters.get("request_id")))
    if _normalized_text(filters.get("batch_id")):
        clauses.append("request_id IN (SELECT request_id FROM automation_agent_run WHERE batch_id = ?)")
        params.append(_normalized_text(filters.get("batch_id")))
    if _normalized_text(filters.get("agent_code")):
        clauses.append("agent_code = ?")
        params.append(_normalized_text(filters.get("agent_code")))
    if _normalized_text(filters.get("output_type")):
        clauses.append("output_type = ?")
        params.append(_normalized_text(filters.get("output_type")))
    elif bool(filters.get("scripts_only")):
        clauses.append("output_type IN ('agent_reply_draft', 'agent_reply_final')")
    if _normalized_text(filters.get("userid")):
        clauses.append("userid = ?")
        params.append(_normalized_text(filters.get("userid")))
    if _normalized_text(filters.get("external_contact_id")):
        clauses.append("external_contact_id = ?")
        params.append(_normalized_text(filters.get("external_contact_id")))
    if _normalized_text(filters.get("target_pool")):
        clauses.append("target_pool = ?")
        params.append(_normalized_text(filters.get("target_pool")))
    if _normalized_text(filters.get("applied_status")):
        clauses.append("applied_status = ?")
        params.append(_normalized_text(filters.get("applied_status")))
    if filters.get("min_confidence") not in (None, ""):
        clauses.append("confidence >= ?")
        params.append(float(filters.get("min_confidence") or 0))
    if filters.get("max_confidence") not in (None, ""):
        clauses.append("confidence <= ?")
        params.append(float(filters.get("max_confidence") or 0))
    if _normalized_text(filters.get("date_from")):
        clauses.append("created_at >= ?")
        params.append(_normalized_text(filters.get("date_from")))
    if _normalized_text(filters.get("date_to")):
        clauses.append("created_at <= ?")
        params.append(_normalized_text(filters.get("date_to")))
    if _normalized_text(filters.get("has_error")):
        wanted = _normalized_text(filters.get("has_error")).lower() in {"1", "true", "yes", "on"}
        clauses.append("(error_code <> '' OR error_message <> '')" if wanted else "(error_code = '' AND error_message = '')")
    if _normalized_text(filters.get("current_pool")):
        clauses.append(
            "external_contact_id IN (SELECT external_contact_id FROM automation_member WHERE current_pool = ?)"
        )
        params.append(_normalized_text(filters.get("current_pool")))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def count_agent_output_rows(filters: dict[str, Any] | None = None) -> int:
    where_sql, params = _agent_output_where_sql(filters)
    row = _fetchone_dict(f"SELECT COUNT(*) AS total FROM automation_agent_output {where_sql}", tuple(params)) or {}
    return int(row.get("total") or 0)


def list_agent_output_rows(*, filters: dict[str, Any] | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    where_sql, params = _agent_output_where_sql(filters)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_agent_output
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        tuple([*params, int(limit), int(offset)]),
    )


def insert_agent_output(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_output (
            output_id,
            run_id,
            request_id,
            userid,
            external_contact_id,
            agent_code,
            output_type,
            raw_output_text,
            normalized_output_json,
            rendered_output_text,
            target_agent_code,
            target_pool,
            confidence,
            reason,
            need_human_review,
            applied_status,
            applied_at,
            adopted_by,
            adopted_action,
            adopted_at,
            outcome_status,
            outcome_value,
            revision_of_output_id,
            error_code,
            error_message,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("output_id")),
            _normalized_text(payload.get("run_id")),
            _normalized_text(payload.get("request_id")),
            _normalized_text(payload.get("userid")),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("agent_code")),
            _normalized_text(payload.get("output_type")),
            _normalized_text(payload.get("raw_output_text")),
            _json_dumps(payload.get("normalized_output_json") or payload.get("normalized_output") or {}),
            _normalized_text(payload.get("rendered_output_text")),
            _normalized_text(payload.get("target_agent_code")),
            _normalized_text(payload.get("target_pool")),
            float(payload.get("confidence") or 0),
            _normalized_text(payload.get("reason")),
            _db_bool(bool(payload.get("need_human_review"))),
            _normalized_text(payload.get("applied_status")),
            _normalized_text(payload.get("applied_at")),
            _normalized_text(payload.get("adopted_by")),
            _normalized_text(payload.get("adopted_action")),
            _normalized_text(payload.get("adopted_at")),
            _normalized_text(payload.get("outcome_status")),
            _normalized_text(payload.get("outcome_value")),
            _normalized_text(payload.get("revision_of_output_id")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_output(output_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = deserialize_agent_output_row(get_agent_output_row(output_id) or {})
    if not existing:
        return {}
    row = get_db().execute(
        """
        UPDATE automation_agent_output
        SET run_id = ?,
            request_id = ?,
            userid = ?,
            external_contact_id = ?,
            agent_code = ?,
            output_type = ?,
            raw_output_text = ?,
            normalized_output_json = ?,
            rendered_output_text = ?,
            target_agent_code = ?,
            target_pool = ?,
            confidence = ?,
            reason = ?,
            need_human_review = ?,
            applied_status = ?,
            applied_at = ?,
            adopted_by = ?,
            adopted_action = ?,
            adopted_at = ?,
            outcome_status = ?,
            outcome_value = ?,
            revision_of_output_id = ?,
            error_code = ?,
            error_message = ?
        WHERE output_id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("run_id", existing.get("run_id"))),
            _normalized_text(payload.get("request_id", existing.get("request_id"))),
            _normalized_text(payload.get("userid", existing.get("userid"))),
            _normalized_text(payload.get("external_contact_id", existing.get("external_contact_id"))),
            _normalized_text(payload.get("agent_code", existing.get("agent_code"))),
            _normalized_text(payload.get("output_type", existing.get("output_type"))),
            _normalized_text(payload.get("raw_output_text", existing.get("raw_output_text"))),
            _json_dumps(payload.get("normalized_output_json") or payload.get("normalized_output") or existing.get("normalized_output_json") or {}),
            _normalized_text(payload.get("rendered_output_text", existing.get("rendered_output_text"))),
            _normalized_text(payload.get("target_agent_code", existing.get("target_agent_code"))),
            _normalized_text(payload.get("target_pool", existing.get("target_pool"))),
            float(payload.get("confidence", existing.get("confidence") or 0) or 0),
            _normalized_text(payload.get("reason", existing.get("reason"))),
            _db_bool(bool(payload.get("need_human_review", existing.get("need_human_review")))),
            _normalized_text(payload.get("applied_status", existing.get("applied_status"))),
            _normalized_text(payload.get("applied_at", existing.get("applied_at"))),
            _normalized_text(payload.get("adopted_by", existing.get("adopted_by"))),
            _normalized_text(payload.get("adopted_action", existing.get("adopted_action"))),
            _normalized_text(payload.get("adopted_at", existing.get("adopted_at"))),
            _normalized_text(payload.get("outcome_status", existing.get("outcome_status"))),
            _normalized_text(payload.get("outcome_value", existing.get("outcome_value"))),
            _normalized_text(payload.get("revision_of_output_id", existing.get("revision_of_output_id"))),
            _normalized_text(payload.get("error_code", existing.get("error_code"))),
            _normalized_text(payload.get("error_message", existing.get("error_message"))),
            _normalized_text(output_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_agent_output_row(output_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_output
        WHERE output_id = ?
        LIMIT 1
        """,
        (_normalized_text(output_id),),
    )


def get_latest_agent_output_row_by_request_id(request_id: str, *, output_types: list[str] | None = None) -> dict[str, Any] | None:
    normalized_request_id = _normalized_text(request_id)
    if not normalized_request_id:
        return None
    clauses = ["request_id = ?"]
    params: list[Any] = [normalized_request_id]
    normalized_types = [_normalized_text(item) for item in list(output_types or []) if _normalized_text(item)]
    if normalized_types:
        placeholders = ",".join("?" for _ in normalized_types)
        clauses.append(f"output_type IN ({placeholders})")
        params.extend(normalized_types)
    where_sql = " AND ".join(clauses)
    return _fetchone_dict(
        f"""
        SELECT *
        FROM automation_agent_output
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )


def list_agent_outputs_by_run_id(run_id: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_agent_output
        WHERE run_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (_normalized_text(run_id),),
    )


def insert_agent_output_export_job(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_output_export_job (
            job_id,
            requested_by,
            filters_json,
            status,
            total_count,
            exported_count,
            file_name,
            file_content_base64,
            error_message,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("job_id")),
            _normalized_text(payload.get("requested_by")),
            _json_dumps(payload.get("filters_json") or payload.get("filters") or {}),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("exported_count") or 0),
            _normalized_text(payload.get("file_name")),
            _normalized_text(payload.get("file_content_base64")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_agent_output_export_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_agent_output_export_job
        SET requested_by = ?,
            filters_json = ?,
            status = ?,
            total_count = ?,
            exported_count = ?,
            file_name = ?,
            file_content_base64 = ?,
            error_message = ?,
            finished_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("requested_by")),
            _json_dumps(payload.get("filters_json") or payload.get("filters") or {}),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("exported_count") or 0),
            _normalized_text(payload.get("file_name")),
            _normalized_text(payload.get("file_content_base64")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("finished_at")),
            _normalized_text(job_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_agent_output_export_job(job_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_output_export_job
        WHERE job_id = ?
        LIMIT 1
        """,
        (_normalized_text(job_id),),
    )


def count_recent_agent_output_export_jobs(requested_by: str, *, since_text: str) -> int:
    row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM automation_agent_output_export_job
        WHERE requested_by = ?
          AND created_at >= ?
        """,
        (_normalized_text(requested_by), _normalized_text(since_text)),
    ) or {}
    return int(row.get("total") or 0)


def insert_agent_skill_call_audit(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_agent_skill_call_audit (
            call_id,
            skill_code,
            source,
            permissions_scope,
            idempotency_key,
            request_payload_json,
            response_payload_json,
            status,
            error_code,
            error_message,
            latency_ms,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("call_id")),
            _normalized_text(payload.get("skill_code")),
            _normalized_text(payload.get("source")),
            _normalized_text(payload.get("permissions_scope")),
            _normalized_text(payload.get("idempotency_key")),
            _json_dumps(payload.get("request_payload_json") or payload.get("request_payload") or {}),
            _json_dumps(payload.get("response_payload_json") or payload.get("response_payload") or {}),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            int(payload.get("latency_ms") or 0),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_reply_monitor_config() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_config
        WHERE config_key = 'default'
        LIMIT 1
        """
    )


def save_reply_monitor_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_reply_monitor_config()
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_reply_monitor_config
            SET enabled = ?,
                last_capture_cursor = ?,
                last_capture_at = ?,
                last_capture_status = ?,
                last_capture_summary_json = ?,
                last_dispatch_at = ?,
                last_dispatch_status = ?,
                last_dispatch_summary_json = ?,
                last_error = ?,
                quiet_hours_start = ?,
                quiet_hours_end = ?,
                dispatch_interval_seconds = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                int(payload.get("last_capture_cursor") or 0),
                _normalized_text(payload.get("last_capture_at")),
                _normalized_text(payload.get("last_capture_status")),
                _json_dumps(payload.get("last_capture_summary_json") or {}),
                _normalized_text(payload.get("last_dispatch_at")),
                _normalized_text(payload.get("last_dispatch_status")),
                _json_dumps(payload.get("last_dispatch_summary_json") or {}),
                _normalized_text(payload.get("last_error")),
                _normalized_text(payload.get("quiet_hours_start")),
                _normalized_text(payload.get("quiet_hours_end")),
                int(payload.get("dispatch_interval_seconds") or 0),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_reply_monitor_config (
            config_key,
            enabled,
            last_capture_cursor,
            last_capture_at,
            last_capture_status,
            last_capture_summary_json,
            last_dispatch_at,
            last_dispatch_status,
            last_dispatch_summary_json,
            last_error,
            quiet_hours_start,
            quiet_hours_end,
            dispatch_interval_seconds,
            created_at,
            updated_at
        )
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("last_capture_cursor") or 0),
            _normalized_text(payload.get("last_capture_at")),
            _normalized_text(payload.get("last_capture_status")),
            _json_dumps(payload.get("last_capture_summary_json") or {}),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("last_dispatch_status")),
            _json_dumps(payload.get("last_dispatch_summary_json") or {}),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("quiet_hours_start")),
            _normalized_text(payload.get("quiet_hours_end")),
            int(payload.get("dispatch_interval_seconds") or 0),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_reply_monitor_queue_item(queue_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE id = ?
        LIMIT 1
        """,
        (int(queue_id),),
    )


def get_active_reply_monitor_queue_item(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE external_userid = ?
          AND status IN ('pending', 'deferred_quiet_hours', 'paused')
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def insert_reply_monitor_queue_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_reply_monitor_queue (
            member_id,
            external_userid,
            owner_userid,
            status,
            message_ids_json,
            message_count,
            first_inbound_at,
            last_inbound_at,
            not_before,
            last_dispatch_at,
            error_message,
            payload_snapshot_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("owner_userid")),
            _normalized_text(payload.get("status")),
            _json_dumps(payload.get("message_ids_json") or []),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("first_inbound_at")),
            _normalized_text(payload.get("last_inbound_at")),
            _normalized_text(payload.get("not_before")),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("payload_snapshot_json") or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_reply_monitor_queue_item(queue_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_reply_monitor_queue
        SET member_id = ?,
            external_userid = ?,
            owner_userid = ?,
            status = ?,
            message_ids_json = ?,
            message_count = ?,
            first_inbound_at = ?,
            last_inbound_at = ?,
            not_before = ?,
            last_dispatch_at = ?,
            error_message = ?,
            payload_snapshot_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("owner_userid")),
            _normalized_text(payload.get("status")),
            _json_dumps(payload.get("message_ids_json") or []),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("first_inbound_at")),
            _normalized_text(payload.get("last_inbound_at")),
            _normalized_text(payload.get("not_before")),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("payload_snapshot_json") or {}),
            int(queue_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_laohuang_chat_job(job_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE id = ?
        LIMIT 1
        """,
        (int(job_id),),
    )


def get_laohuang_chat_job_by_external_message_id(external_message_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE external_message_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (_normalized_text(external_message_id),),
    )


def get_laohuang_chat_job_by_task_id(task_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE laohuang_task_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (_normalized_text(task_id),),
    )


def list_laohuang_chat_jobs_for_review(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_laohuang_chat_job
        WHERE reply_text <> ''
          AND status IN ('callback_success', 'send_success', 'send_failed')
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (max(1, min(50, int(limit or 20))),),
    )


def insert_laohuang_chat_job(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_laohuang_chat_job (
            queue_id,
            member_id,
            external_contact_id,
            phone,
            external_message_id,
            external_session_id,
            laohuang_task_id,
            request_payload_json,
            accepted_payload_json,
            callback_payload_json,
            status,
            reply_text,
            error_code,
            error_message,
            send_channel,
            send_record_id,
            send_result_json,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        RETURNING *
        """,
        (
            payload.get("queue_id"),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            _normalized_text(payload.get("external_message_id")),
            _normalized_text(payload.get("external_session_id")),
            _normalized_text(payload.get("laohuang_task_id")),
            _json_dumps(payload.get("request_payload_json") or payload.get("request_payload") or {}),
            _json_dumps(payload.get("accepted_payload_json") or payload.get("accepted_payload") or {}),
            _json_dumps(payload.get("callback_payload_json") or payload.get("callback_payload") or {}),
            _normalized_text(payload.get("status")) or "created",
            _normalized_text(payload.get("reply_text")),
            _normalized_text(payload.get("error_code")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("send_channel")),
            payload.get("send_record_id"),
            _json_dumps(payload.get("send_result_json") or payload.get("send_result") or {}),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_laohuang_chat_job(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    column_serializers = {
        "queue_id": lambda value: value,
        "member_id": lambda value: value,
        "external_contact_id": _normalized_text,
        "phone": _normalized_text,
        "external_message_id": _normalized_text,
        "external_session_id": _normalized_text,
        "laohuang_task_id": _normalized_text,
        "request_payload_json": lambda value: _json_dumps(value or {}),
        "accepted_payload_json": lambda value: _json_dumps(value or {}),
        "callback_payload_json": lambda value: _json_dumps(value or {}),
        "status": _normalized_text,
        "reply_text": _normalized_text,
        "error_code": _normalized_text,
        "error_message": _normalized_text,
        "send_channel": _normalized_text,
        "send_record_id": lambda value: value,
        "send_result_json": lambda value: _json_dumps(value or {}),
        "finished_at": _normalized_text,
    }
    updates: list[str] = []
    values: list[Any] = []
    for key, value in payload.items():
        if key not in column_serializers:
            continue
        updates.append(f"{key} = ?")
        values.append(column_serializers[key](value))
    if not updates:
        return get_laohuang_chat_job(int(job_id)) or {}
    values.append(int(job_id))
    row = get_db().execute(
        f"""
        UPDATE automation_laohuang_chat_job
        SET {", ".join(updates)},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        tuple(values),
    ).fetchone()
    return dict(row) if row else {}


def list_due_reply_monitor_queue_items(*, now_text: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE status IN ('pending', 'deferred_quiet_hours')
          AND not_before <> ''
          AND not_before <= ?
        ORDER BY not_before ASC, id ASC
        LIMIT ?
        """,
        (_normalized_text(now_text), int(limit)),
    )


def list_recent_reply_monitor_queue_items(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def get_reply_monitor_queue_counts() -> dict[str, int]:
    rows = _fetchall_dicts(
        """
        SELECT status, COUNT(*) AS total
        FROM automation_reply_monitor_queue
        GROUP BY status
        """
    )
    counts = {
        "pending": 0,
        "deferred_quiet_hours": 0,
        "dispatched": 0,
        "failed": 0,
        "paused": 0,
    }
    for row in rows:
        status = _normalized_text(row.get("status"))
        if status in counts:
            counts[status] = int(row.get("total") or 0)
    counts["active_total"] = counts["pending"] + counts["deferred_quiet_hours"] + counts["paused"]
    return counts


def get_latest_reply_monitor_not_before() -> str:
    row = _fetchone_dict(
        """
        SELECT not_before
        FROM automation_reply_monitor_queue
        WHERE status IN ('pending', 'deferred_quiet_hours', 'paused')
        ORDER BY not_before DESC, id DESC
        LIMIT 1
        """
    ) or {}
    return _normalized_text(row.get("not_before"))


def insert_focus_send_batch(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_focus_send_batch (
            stage_key,
            pool_key,
            operator_type,
            operator_id,
            status,
            total_count,
            sent_count,
            failed_count,
            skipped_count,
            cancelled_count,
            next_run_at,
            last_run_at,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("stage_key")),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("cancelled_count") or 0),
            _normalized_text(payload.get("next_run_at")),
            _normalized_text(payload.get("last_run_at")),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_focus_send_batch(batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch
        SET stage_key = ?,
            pool_key = ?,
            operator_type = ?,
            operator_id = ?,
            status = ?,
            total_count = ?,
            sent_count = ?,
            failed_count = ?,
            skipped_count = ?,
            cancelled_count = ?,
            next_run_at = ?,
            last_run_at = ?,
            updated_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("stage_key")),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("cancelled_count") or 0),
            _normalized_text(payload.get("next_run_at")),
            _normalized_text(payload.get("last_run_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("finished_at")),
            int(batch_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_focus_send_batch(batch_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_focus_send_batch
        WHERE id = ?
        LIMIT 1
        """,
        (int(batch_id),),
    )


def find_active_focus_send_batch_by_stage(stage_key: str) -> dict[str, Any] | None:
    stage_keys = _stage_route_lookup_keys(stage_key)
    if not stage_keys:
        return None
    placeholders = ",".join("?" for _ in stage_keys)
    return _fetchone_dict(
        f"""
        SELECT *
        FROM automation_focus_send_batch
        WHERE stage_key IN ({placeholders})
          AND status IN ('pending', 'running')
        ORDER BY id DESC
        LIMIT 1
        """,
        tuple(stage_keys),
    )


def list_due_focus_send_batches(*, due_at: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_focus_send_batch
        WHERE status IN ('pending', 'running')
          AND (next_run_at = '' OR next_run_at <= ?)
        ORDER BY id ASC
        LIMIT ?
        """,
        (_normalized_text(due_at), int(limit)),
    )


def list_recent_focus_send_batches(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_focus_send_batch
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def insert_focus_send_batch_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_focus_send_batch_item (
            batch_id,
            member_id,
            external_contact_id,
            phone,
            position_index,
            status,
            detail,
            result_payload,
            created_at,
            updated_at,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            int(payload.get("position_index") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("result_payload") or {}),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_focus_send_batch_item(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch_item
        SET member_id = ?,
            external_contact_id = ?,
            phone = ?,
            position_index = ?,
            status = ?,
            detail = ?,
            result_payload = ?,
            updated_at = ?,
            started_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            int(payload.get("position_index") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("result_payload") or {}),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
            int(item_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_focus_send_batch_items(*, batch_id: int, limit: int = 100, descending: bool = False) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_focus_send_batch_item
        WHERE batch_id = ?
        ORDER BY position_index {'DESC' if descending else 'ASC'}, id {'DESC' if descending else 'ASC'}
        LIMIT ?
        """,
        (int(batch_id), int(limit)),
    )


def claim_next_focus_send_batch_item(*, batch_id: int, started_at: str) -> dict[str, Any] | None:
    candidate = _fetchone_dict(
        """
        SELECT *
        FROM automation_focus_send_batch_item
        WHERE batch_id = ?
          AND status = 'pending'
        ORDER BY position_index ASC, id ASC
        LIMIT 1
        """,
        (int(batch_id),),
    )
    if not candidate:
        return None
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch_item
        SET status = 'running',
            updated_at = ?,
            started_at = ?
        WHERE id = ?
          AND status = 'pending'
        RETURNING *
        """,
        (
            _normalized_text(started_at),
            _normalized_text(started_at),
            int(candidate["id"]),
        ),
    ).fetchone()
    return dict(row) if row else None


def get_active_touch_delivery(
    *,
    program_code: str,
    touch_surface: str,
    rule_key: str,
    external_contact_id: str,
) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_touch_delivery_log
        WHERE program_code = ?
          AND touch_surface = ?
          AND rule_key = ?
          AND external_contact_id = ?
          AND status IN ('claimed', 'sent')
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            _normalized_text(program_code),
            _normalized_text(touch_surface),
            _normalized_text(rule_key),
            _normalized_text(external_contact_id),
        ),
    )


def has_historical_focus_send_delivery(*, rule_key: str, external_contact_id: str) -> bool:
    rule_keys = _stage_route_lookup_keys(rule_key)
    if not rule_keys:
        return False
    placeholders = ",".join("?" for _ in rule_keys)
    row = _fetchone_dict(
        f"""
        SELECT item.id
        FROM automation_focus_send_batch_item item
        JOIN automation_focus_send_batch batch ON batch.id = item.batch_id
        WHERE batch.stage_key IN ({placeholders})
          AND item.external_contact_id = ?
          AND item.status = 'sent'
        ORDER BY item.id DESC
        LIMIT 1
        """,
        (*rule_keys, _normalized_text(external_contact_id)),
    )
    return bool(row)


def has_historical_stage_manual_send_delivery(*, rule_key: str, external_contact_id: str) -> bool:
    normalized_rule_key = _normalized_text(rule_key)
    normalized_external_contact_id = _normalized_text(external_contact_id)
    if not normalized_rule_key or not normalized_external_contact_id:
        return False
    rule_keys = set(_stage_route_lookup_keys(normalized_rule_key))
    like_clauses = " OR ".join("CAST(filter_snapshot_json AS TEXT) LIKE ?" for _ in rule_keys)
    rows = _fetchall_dicts(
        f"""
        SELECT task_results_json, filter_snapshot_json, status
        FROM user_ops_send_records
        WHERE status IN ('sent', 'partial_failed', 'created')
          AND ({like_clauses})
        ORDER BY id DESC
        LIMIT 500
        """,
        tuple(f"%{rule_key}%" for rule_key in rule_keys),
    )
    for row in rows:
        filter_snapshot = _json_loads(row.get("filter_snapshot_json"), default={})
        if _normalized_text(filter_snapshot.get("selection_mode")) != "automation_conversion_stage":
            continue
        if _normalized_text(filter_snapshot.get("stage_key")) not in rule_keys:
            continue
        task_results = _json_loads(row.get("task_results_json"), default=[])
        if not isinstance(task_results, list):
            continue
        for item in task_results:
            if not isinstance(item, dict) or _normalized_text(item.get("status")) == "failed":
                continue
            external_userids = item.get("external_userids")
            if not isinstance(external_userids, list):
                continue
            if normalized_external_contact_id in {_normalized_text(value) for value in external_userids}:
                return True
    return False


def claim_touch_delivery_once(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_external_contact_id = _normalized_text(payload.get("external_contact_id"))
    if not normalized_external_contact_id:
        return {"_did_claim": False}
    row = get_db().execute(
        """
        INSERT INTO automation_touch_delivery_log (
            program_code,
            touch_surface,
            rule_key,
            member_id,
            external_contact_id,
            source_batch_id,
            source_item_id,
            send_record_id,
            status,
            detail,
            metadata_json,
            claimed_at,
            sent_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'claimed', ?, ?, ?, '', ?, ?)
        ON CONFLICT DO NOTHING
        RETURNING *
        """,
        (
            _normalized_text(payload.get("program_code")) or "signup_conversion_v1",
            _normalized_text(payload.get("touch_surface")),
            _normalized_text(payload.get("rule_key")),
            payload.get("member_id"),
            normalized_external_contact_id,
            payload.get("source_batch_id"),
            payload.get("source_item_id"),
            payload.get("send_record_id"),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("metadata") or {}),
            _normalized_text(payload.get("claimed_at")),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
        ),
    ).fetchone()
    if row:
        return {**dict(row), "_did_claim": True}
    existing = get_active_touch_delivery(
        program_code=_normalized_text(payload.get("program_code")) or "signup_conversion_v1",
        touch_surface=_normalized_text(payload.get("touch_surface")),
        rule_key=_normalized_text(payload.get("rule_key")),
        external_contact_id=normalized_external_contact_id,
    )
    return {**dict(existing or {}), "_did_claim": False}


def update_touch_delivery_log_status(
    delivery_id: int,
    *,
    status: str,
    send_record_id: int | None = None,
    source_batch_id: int | None = None,
    source_item_id: int | None = None,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    sent_at: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        UPDATE automation_touch_delivery_log
        SET status = ?,
            send_record_id = COALESCE(?, send_record_id),
            source_batch_id = COALESCE(?, source_batch_id),
            source_item_id = COALESCE(?, source_item_id),
            detail = ?,
            metadata_json = ?,
            sent_at = ?,
            updated_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(status),
            send_record_id,
            source_batch_id,
            source_item_id,
            _normalized_text(detail),
            _json_dumps(metadata or {}),
            _normalized_text(sent_at),
            _normalized_text(updated_at),
            int(delivery_id),
        ),
    ).fetchone()
    return dict(row) if row else None


def update_touch_delivery_log_status_by_source(
    *,
    touch_surface: str,
    source_batch_id: int,
    source_item_id: int,
    external_contact_id: str,
    status: str,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    sent_at: str = "",
    updated_at: str = "",
) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        UPDATE automation_touch_delivery_log
        SET status = ?,
            detail = ?,
            metadata_json = ?,
            sent_at = ?,
            updated_at = ?
        WHERE id = (
            SELECT id
            FROM automation_touch_delivery_log
            WHERE touch_surface = ?
              AND source_batch_id = ?
              AND source_item_id = ?
              AND external_contact_id = ?
            ORDER BY id DESC
            LIMIT 1
        )
        RETURNING *
        """,
        (
            _normalized_text(status),
            _normalized_text(detail),
            _json_dumps(metadata or {}),
            _normalized_text(sent_at),
            _normalized_text(updated_at),
            _normalized_text(touch_surface),
            int(source_batch_id),
            int(source_item_id),
            _normalized_text(external_contact_id),
        ),
    ).fetchone()
    return dict(row) if row else None


def list_sop_pool_configs() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_pool_config
        ORDER BY pool_key ASC, id ASC
        """
    )


def get_sop_pool_config(pool_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_pool_config
        WHERE pool_key = ?
        LIMIT 1
        """,
        (_normalized_text(pool_key),),
    )


def save_sop_pool_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_pool_config(_normalized_text(payload.get("pool_key")))
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_pool_config
            SET enabled = ?,
                max_day_count = ?,
                send_time = ?,
                timezone = ?,
                effective_start_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                int(payload.get("max_day_count") or 0),
                _normalized_text(payload.get("send_time")),
                _normalized_text(payload.get("timezone")),
                _normalized_text(payload.get("effective_start_at")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_pool_config (
            pool_key,
            enabled,
            max_day_count,
            send_time,
            timezone,
            effective_start_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("max_day_count") or 0),
            _normalized_text(payload.get("send_time")),
            _normalized_text(payload.get("timezone")),
            _normalized_text(payload.get("effective_start_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_sop_templates(*, pool_key: str = "") -> list[dict[str, Any]]:
    normalized_pool_key = _normalized_text(pool_key)
    if normalized_pool_key:
        return _fetchall_dicts(
            """
            SELECT *
            FROM automation_sop_template
            WHERE pool_key = ?
            ORDER BY day_index ASC, id ASC
            """,
            (normalized_pool_key,),
        )
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_template
        ORDER BY pool_key ASC, day_index ASC, id ASC
        """
    )


def get_sop_template(*, pool_key: str, day_index: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_template
        WHERE pool_key = ?
          AND day_index = ?
        LIMIT 1
        """,
        (_normalized_text(pool_key), int(day_index)),
    )


def save_sop_template(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_template(
        pool_key=_normalized_text(payload.get("pool_key")),
        day_index=int(payload.get("day_index") or 0),
    )
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_template
            SET content = ?,
                images_json = ?,
                enabled = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _normalized_text(payload.get("content")),
                _json_dumps(payload.get("images_json") or []),
                _db_bool(bool(payload.get("enabled"))),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_template (
            pool_key,
            day_index,
            content,
            images_json,
            enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            _normalized_text(payload.get("content")),
            _json_dumps(payload.get("images_json") or []),
            _db_bool(bool(payload.get("enabled"))),
        ),
    ).fetchone()
    return dict(row) if row else {}


def delete_sop_template_day(*, pool_key: str, day_index: int) -> None:
    normalized_pool_key = _normalized_text(pool_key)
    normalized_day_index = int(day_index)
    db = get_db()
    db.execute(
        """
        DELETE FROM automation_sop_template
        WHERE pool_key = ?
          AND day_index = ?
        """,
        (normalized_pool_key, normalized_day_index),
    )
    db.execute(
        """
        UPDATE automation_sop_template
        SET day_index = day_index + 1000,
            updated_at = CURRENT_TIMESTAMP
        WHERE pool_key = ?
          AND day_index > ?
        """,
        (normalized_pool_key, normalized_day_index),
    )
    db.execute(
        """
        UPDATE automation_sop_template
        SET day_index = day_index - 1001,
            updated_at = CURRENT_TIMESTAMP
        WHERE pool_key = ?
          AND day_index > ?
        """,
        (normalized_pool_key, normalized_day_index + 1000),
    )


def get_sop_progress(*, member_id: int, pool_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_progress
        WHERE member_id = ?
          AND pool_key = ?
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key)),
    )


def list_sop_progress_for_members(*, member_ids: list[int] | None = None, pool_key: str = "") -> list[dict[str, Any]]:
    normalized_member_ids = [int(item) for item in (member_ids or []) if str(item).strip()]
    normalized_pool_key = _normalized_text(pool_key)
    params: list[Any] = []
    sql = """
    SELECT *
    FROM automation_sop_progress
    WHERE 1 = 1
    """
    if normalized_member_ids:
        placeholders = ",".join("?" for _ in normalized_member_ids)
        sql += f" AND member_id IN ({placeholders})"
        params.extend(normalized_member_ids)
    if normalized_pool_key:
        sql += " AND pool_key = ?"
        params.append(normalized_pool_key)
    sql += " ORDER BY pool_key ASC, member_id ASC, id ASC"
    return _fetchall_dicts(sql, tuple(params))


def save_sop_progress(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_progress(
        member_id=int(payload.get("member_id") or 0),
        pool_key=_normalized_text(payload.get("pool_key")),
    )
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_progress
            SET first_entered_at = ?,
                last_entered_at = ?,
                sop_anchor_date = ?,
                first_effective_in_pool_at = ?,
                last_in_pool_at = ?,
                last_sent_day = ?,
                last_sent_at = ?,
                completed_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _normalized_text(payload.get("first_entered_at")),
                _normalized_text(payload.get("last_entered_at")),
                _normalized_text(payload.get("sop_anchor_date")),
                _normalized_text(payload.get("first_effective_in_pool_at")),
                _normalized_text(payload.get("last_in_pool_at")),
                int(payload.get("last_sent_day") or 0),
                _normalized_text(payload.get("last_sent_at")),
                _normalized_text(payload.get("completed_at")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_progress (
            member_id,
            pool_key,
            first_entered_at,
            last_entered_at,
            sop_anchor_date,
            first_effective_in_pool_at,
            last_in_pool_at,
            last_sent_day,
            last_sent_at,
            completed_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("member_id") or 0),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("first_entered_at")),
            _normalized_text(payload.get("last_entered_at")),
            _normalized_text(payload.get("sop_anchor_date")),
            _normalized_text(payload.get("first_effective_in_pool_at")),
            _normalized_text(payload.get("last_in_pool_at")),
            int(payload.get("last_sent_day") or 0),
            _normalized_text(payload.get("last_sent_at")),
            _normalized_text(payload.get("completed_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_sop_batch(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_sop_batch (
            pool_key,
            day_index,
            template_id,
            scheduled_for,
            status,
            total_count,
            success_count,
            skipped_count,
            failed_count,
            summary_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            payload.get("template_id"),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_dumps(payload.get("summary_json") or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_sop_batch(batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_sop_batch
        SET pool_key = ?,
            day_index = ?,
            template_id = ?,
            scheduled_for = ?,
            status = ?,
            total_count = ?,
            success_count = ?,
            skipped_count = ?,
            failed_count = ?,
            summary_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            payload.get("template_id"),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_dumps(payload.get("summary_json") or {}),
            int(batch_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_sop_batch(batch_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch
        WHERE id = ?
        LIMIT 1
        """,
        (int(batch_id),),
    )


def list_sop_batches(*, pool_key: str = "", limit: int = 50) -> list[dict[str, Any]]:
    normalized_pool_key = _normalized_text(pool_key)
    params: list[Any] = []
    sql = """
    SELECT *
    FROM automation_sop_batch
    WHERE 1 = 1
    """
    if normalized_pool_key:
        lookup_keys = _sop_pool_lookup_keys(normalized_pool_key)
        sql += f" AND pool_key IN ({', '.join('?' for _ in lookup_keys)})"
        params.extend(lookup_keys)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    return _fetchall_dicts(sql, tuple(params))


def try_acquire_sop_pool_run_lock(*, pool_key: str) -> bool:
    normalized_pool_key = _normalized_text(pool_key)
    if not normalized_pool_key or get_db_backend() != "postgres":
        return True
    row = get_db().execute(
        """
        SELECT pg_try_advisory_xact_lock(?, hashtext(?)) AS locked
        """,
        (_AUTOMATION_SOP_POOL_LOCK_NAMESPACE, normalized_pool_key),
    ).fetchone()
    return _row_bool((row or {}).get("locked"))


def get_successful_sop_batch_item(*, member_id: int, pool_key: str, day_index: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE member_id = ?
          AND pool_key = ?
          AND day_index = ?
          AND status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key), int(day_index)),
    )


def get_sop_batch_item_for_member_day(*, member_id: int, pool_key: str, day_index_snapshot: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE member_id = ?
          AND pool_key = ?
          AND day_index_snapshot = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key), int(day_index_snapshot)),
    )


def insert_sop_batch_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_sop_batch_item (
            batch_id,
            member_id,
            pool_key,
            day_index,
            day_index_snapshot,
            external_userid,
            status,
            error_message,
            content_snapshot,
            images_snapshot,
            sent_record_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            int(payload.get("day_index_snapshot") or payload.get("day_index") or 0),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("content_snapshot")),
            _json_dumps(payload.get("images_snapshot") or []),
            payload.get("sent_record_id"),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_sop_batch_item(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_sop_batch_item
        SET batch_id = ?,
            member_id = ?,
            pool_key = ?,
            day_index = ?,
            day_index_snapshot = ?,
            external_userid = ?,
            status = ?,
            error_message = ?,
            content_snapshot = ?,
            images_snapshot = ?,
            sent_record_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            int(payload.get("day_index_snapshot") or payload.get("day_index") or 0),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("content_snapshot")),
            _json_dumps(payload.get("images_snapshot") or []),
            payload.get("sent_record_id"),
            int(item_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_sop_batch_items(*, batch_id: int, limit: int = 200) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE batch_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(batch_id), max(1, int(limit))),
    )


def get_default_channel(*, program_id: int | None = None) -> dict[str, Any] | None:
    if program_id is not None:
        row = _fetchone_dict(
            """
            SELECT *
            FROM automation_channel
            WHERE program_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(program_id),),
        )
        if row:
            return row
        return _fetchone_dict(
            """
            SELECT *
            FROM automation_channel
            WHERE channel_code = ?
              AND program_id IS NULL
            LIMIT 1
            """,
            ("default_qrcode",),
        )
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE channel_code = 'default_qrcode'
        LIMIT 1
        """
    )


def get_channel_by_id(channel_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE id = ?
        LIMIT 1
        """,
        (int(channel_id),),
    )


def find_channel_by_scene_value(scene_value: str) -> dict[str, Any] | None:
    normalized = _normalized_text(scene_value)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE scene_value = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def save_channel(payload: dict[str, Any]) -> dict[str, Any]:
    program_id = int(payload.get("program_id") or 0) or None
    channel_code = _normalized_text(payload.get("channel_code"))
    if program_id and channel_code == "default_qrcode":
        channel_code = f"program_{program_id}_default_qrcode"
    is_default_channel_code = channel_code == "default_qrcode" or bool(
        program_id and channel_code == f"program_{program_id}_default_qrcode"
    )
    existing = get_default_channel(program_id=program_id) if is_default_channel_code else None
    db = get_db()
    params = (
        program_id,
        channel_code,
        _normalized_text(payload.get("channel_name")),
        _normalized_text(payload.get("qr_url")),
        _normalized_text(payload.get("qr_ticket")),
        _normalized_text(payload.get("scene_value")),
        _normalized_text(payload.get("welcome_message")),
        _db_bool(bool(payload.get("auto_accept_friend"))),
        _normalized_text(payload.get("entry_tag_id")),
        _normalized_text(payload.get("entry_tag_name")),
        _normalized_text(payload.get("entry_tag_group_name")),
        _normalized_text(payload.get("owner_staff_id")),
        _normalized_text(payload.get("status")),
    )
    if existing:
        row = db.execute(
            """
            UPDATE automation_channel
            SET program_id = ?,
                channel_code = ?,
                channel_name = ?,
                qr_url = ?,
                qr_ticket = ?,
                scene_value = ?,
                welcome_message = ?,
                auto_accept_friend = ?,
                entry_tag_id = ?,
                entry_tag_name = ?,
                entry_tag_group_name = ?,
                owner_staff_id = ?,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                program_id,
                channel_code,
                _normalized_text(payload.get("channel_name")),
                _normalized_text(payload.get("qr_url")),
                _normalized_text(payload.get("qr_ticket")),
                _normalized_text(payload.get("scene_value")),
                _normalized_text(payload.get("welcome_message")),
                _db_bool(bool(payload.get("auto_accept_friend"))),
                _normalized_text(payload.get("entry_tag_id")),
                _normalized_text(payload.get("entry_tag_name")),
                _normalized_text(payload.get("entry_tag_group_name")),
                _normalized_text(payload.get("owner_staff_id")),
                _normalized_text(payload.get("status")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_channel (
            program_id,
            channel_code,
            channel_name,
            qr_url,
            qr_ticket,
            scene_value,
            welcome_message,
            auto_accept_friend,
            entry_tag_id,
            entry_tag_name,
            entry_tag_group_name,
            owner_staff_id,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def get_stage_counts() -> dict[str, int]:
    rows = _fetchall_dicts(
        """
        SELECT current_pool, COUNT(*) AS total
        FROM automation_member
        GROUP BY current_pool
        """
    )
    return {_normalized_text(row.get("current_pool")): int(row.get("total") or 0) for row in rows}


def get_stage_metrics() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT
            current_audience_code AS current_pool,
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN follow_type = 'focus' THEN 1 ELSE 0 END), 0) AS focus_count,
            COALESCE(SUM(CASE WHEN follow_type = 'normal' THEN 1 ELSE 0 END), 0) AS normal_count,
            COALESCE(SUM(CASE WHEN joined_at IS NOT NULL AND joined_at <> '' AND DATE(joined_at) = DATE(CURRENT_TIMESTAMP) THEN 1 ELSE 0 END), 0) AS today_new_count
        FROM automation_member
        WHERE current_audience_code IN ('pending_questionnaire', 'operating', 'converted')
        GROUP BY current_audience_code
        """
    )


def get_overview_counts() -> dict[str, int]:
    row = _fetchone_dict(
        """
        SELECT
            COALESCE(SUM(CASE WHEN in_pool THEN 1 ELSE 0 END), 0) AS in_pool_total,
            COALESCE(SUM(CASE WHEN joined_at IS NOT NULL AND joined_at <> '' AND DATE(joined_at) = DATE(CURRENT_TIMESTAMP) THEN 1 ELSE 0 END), 0) AS today_joined,
            COALESCE(SUM(CASE WHEN current_audience_code = 'pending_questionnaire' THEN 1 ELSE 0 END), 0) AS questionnaire_pending,
            COALESCE(SUM(CASE WHEN current_audience_code = 'operating' THEN 1 ELSE 0 END), 0) AS operating_total,
            COALESCE(SUM(CASE WHEN current_audience_code = 'converted' THEN 1 ELSE 0 END), 0) AS converted_total
        FROM automation_member
        """
    ) or {}
    return {key: int(row.get(key) or 0) for key in row}


def get_latest_questionnaire_submission(
    *,
    questionnaire_id: int,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
) -> dict[str, Any] | None:
    normalized_external_contact_ids = [
        _normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)
    ]
    normalized_phone = _normalized_text(phone)
    filters: list[str] = []
    params: list[Any] = [int(questionnaire_id)]
    if normalized_external_contact_ids:
        placeholders = ",".join("?" for _ in normalized_external_contact_ids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_contact_ids)
    if normalized_phone:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_phone)
    if not filters:
        return None
    sql = """
    SELECT *
    FROM questionnaire_submissions
    WHERE questionnaire_id = ?
      AND (
    """
    sql += " OR ".join(filters)
    sql += """
      )
    ORDER BY submitted_at DESC, id DESC
    LIMIT 1
    """
    return _fetchone_dict(sql, tuple(params))


def get_latest_any_questionnaire_submission(
    *,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
) -> dict[str, Any] | None:
    normalized_external_contact_ids = [
        _normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)
    ]
    normalized_phone = _normalized_text(phone)
    filters: list[str] = []
    params: list[Any] = []
    if normalized_external_contact_ids:
        placeholders = ",".join("?" for _ in normalized_external_contact_ids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_contact_ids)
    if normalized_phone:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_phone)
    if not filters:
        return None
    sql = """
    SELECT *
    FROM questionnaire_submissions
    WHERE (
    """
    sql += " OR ".join(filters)
    sql += """
      )
    ORDER BY submitted_at DESC, id DESC
    LIMIT 1
    """
    return _fetchone_dict(sql, tuple(params))


def list_questionnaire_submission_answers(submission_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM questionnaire_submission_answers
        WHERE submission_id = ?
        ORDER BY id ASC
        """,
        (int(submission_id),),
    )


def list_stage_members(*, current_pool: str, keyword: str = "", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    normalized_keyword = _normalized_text(keyword)
    normalized_pool = _normalized_text(current_pool)
    params: list[Any] = [normalized_pool]
    if normalized_pool in {"pending_questionnaire", "operating", "converted"}:
        sql = """
        SELECT *
        FROM automation_member
        WHERE current_audience_code = ?
        """
    else:
        sql = """
        SELECT *
        FROM automation_member
        WHERE current_pool = ?
        """
    if normalized_keyword:
        sql += """
          AND (
            external_contact_id LIKE ?
            OR phone LIKE ?
          )
        """
        like_value = f"%{normalized_keyword}%"
        params.extend([like_value, like_value])
    sql += """
    ORDER BY updated_at DESC, id DESC
    LIMIT ?
    OFFSET ?
    """
    params.extend([int(limit), int(offset)])
    return _fetchall_dicts(sql, tuple(params))


def list_stage_members_for_manual_send(*, current_pool: str) -> list[dict[str, Any]]:
    normalized_pool = _normalized_text(current_pool)
    if normalized_pool not in {"pending_questionnaire", "operating", "converted"}:
        return []
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_member
        WHERE current_audience_code = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (normalized_pool,),
    )


def count_stage_members(*, current_pool: str, keyword: str = "") -> int:
    normalized_keyword = _normalized_text(keyword)
    normalized_pool = _normalized_text(current_pool)
    params: list[Any] = [normalized_pool]
    if normalized_pool in {"pending_questionnaire", "operating", "converted"}:
        sql = """
        SELECT COUNT(*) AS total
        FROM automation_member
        WHERE current_audience_code = ?
        """
    else:
        sql = """
        SELECT COUNT(*) AS total
        FROM automation_member
        WHERE current_pool = ?
        """
    if normalized_keyword:
        like_value = f"%{normalized_keyword}%"
        sql += """
          AND (
            external_contact_id LIKE ?
            OR phone LIKE ?
          )
        """
        params.extend([like_value, like_value])
    row = _fetchone_dict(sql, tuple(params)) or {}
    return int(row.get("total") or 0)


def list_members_for_silent_refresh() -> list[dict[str, Any]]:
    return []


def list_members_for_message_activity_sync(*, current_pools: list[str]) -> list[dict[str, Any]]:
    normalized_pools = [_normalized_text(item) for item in current_pools if _normalized_text(item)]
    if not normalized_pools:
        return []
    placeholders = ",".join("?" for _ in normalized_pools)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE in_pool = ?
          AND current_pool IN ({placeholders})
        ORDER BY current_pool ASC, updated_at DESC, id ASC
        """,
        (_db_bool(True), *normalized_pools),
    )


def list_recent_debug_events(*, external_contact_id: str = "", phone: str = "", limit: int = 10) -> list[dict[str, Any]]:
    member = get_member_by_external_contact_id(external_contact_id) or get_member_by_phone(phone)
    if not member:
        return []
    return list_recent_events(int(member["id"]), limit=int(limit))


def deserialize_event_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "before_snapshot": _json_loads(row.get("before_snapshot"), default={}),
        "after_snapshot": _json_loads(row.get("after_snapshot"), default={}),
    }


def deserialize_ai_push_log_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "request_payload": _json_loads(row.get("request_payload"), default={}),
    }


def deserialize_message_activity_sync_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "summary_json": _json_loads(row.get("summary_json"), default={}),
    }


def deserialize_message_activity_sync_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "before_snapshot": _json_loads(row.get("before_snapshot"), default={}),
        "after_snapshot": _json_loads(row.get("after_snapshot"), default={}),
    }


def deserialize_reply_monitor_config_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "enabled": _row_bool(row.get("enabled")),
        "last_capture_summary_json": _json_loads(row.get("last_capture_summary_json"), default={}),
        "last_dispatch_summary_json": _json_loads(row.get("last_dispatch_summary_json"), default={}),
    }


def deserialize_reply_monitor_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "message_ids_json": _json_loads(row.get("message_ids_json"), default=[]),
        "payload_snapshot_json": _json_loads(row.get("payload_snapshot_json"), default={}),
    }


def deserialize_laohuang_chat_job_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "request_payload_json": _json_loads(row.get("request_payload_json"), default={}),
        "accepted_payload_json": _json_loads(row.get("accepted_payload_json"), default={}),
        "callback_payload_json": _json_loads(row.get("callback_payload_json"), default={}),
        "send_result_json": _json_loads(row.get("send_result_json"), default={}),
    }


def deserialize_agent_prompt_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "enabled": _row_bool(row.get("enabled")),
    }


def deserialize_agent_router_config_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "enabled": _row_bool((row or {}).get("enabled")),
        "fallback_strategy_json": _json_loads((row or {}).get("fallback_strategy_json"), default={}),
        "request_sample_json": _json_loads((row or {}).get("request_sample_json"), default={}),
        "response_sample_json": _json_loads((row or {}).get("response_sample_json"), default={}),
    }


def deserialize_agent_config_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "enabled": _row_bool((row or {}).get("enabled")),
        "submitted_for_publish": _row_bool((row or {}).get("submitted_for_publish")),
        "pool_keys_json": _json_loads((row or {}).get("pool_keys_json"), default=[]),
        "draft_variables_json": _json_loads((row or {}).get("draft_variables_json"), default=[]),
        "draft_output_schema_json": _json_loads((row or {}).get("draft_output_schema_json"), default=[]),
        "published_variables_json": _json_loads((row or {}).get("published_variables_json"), default=[]),
        "published_output_schema_json": _json_loads((row or {}).get("published_output_schema_json"), default=[]),
    }


def deserialize_agent_skill_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "enabled": _row_bool((row or {}).get("enabled")),
        "pool_keys_json": _json_loads((row or {}).get("pool_keys_json"), default=[]),
        "read_capabilities_json": _json_loads((row or {}).get("read_capabilities_json"), default=[]),
        "write_capabilities_json": _json_loads((row or {}).get("write_capabilities_json"), default=[]),
        "input_schema_json": _json_loads((row or {}).get("input_schema_json"), default={}),
        "output_schema_json": _json_loads((row or {}).get("output_schema_json"), default={}),
        "example_request_json": _json_loads((row or {}).get("example_request_json"), default={}),
        "example_response_json": _json_loads((row or {}).get("example_response_json"), default={}),
    }


def deserialize_agent_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "input_snapshot_json": _json_loads((row or {}).get("input_snapshot_json"), default={}),
        "variables_snapshot_json": _json_loads((row or {}).get("variables_snapshot_json"), default={}),
    }


def deserialize_agent_output_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "normalized_output_json": _json_loads((row or {}).get("normalized_output_json"), default={}),
        "need_human_review": _row_bool((row or {}).get("need_human_review")),
    }


def deserialize_agent_output_export_job_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "filters_json": _json_loads((row or {}).get("filters_json"), default={}),
    }


def deserialize_agent_skill_call_audit_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "request_payload_json": _json_loads((row or {}).get("request_payload_json"), default={}),
        "response_payload_json": _json_loads((row or {}).get("response_payload_json"), default={}),
    }


def deserialize_focus_send_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row or {})


def deserialize_focus_send_batch_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "result_payload": _json_loads(row.get("result_payload"), default={}),
    }


def deserialize_sop_template_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "images_json": _json_loads(row.get("images_json"), default=[]),
        "enabled": _row_bool(row.get("enabled")),
    }


def deserialize_sop_progress_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row or {})


def deserialize_sop_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "summary_json": _json_loads(row.get("summary_json"), default={}),
    }


def deserialize_sop_batch_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "images_snapshot": _json_loads((row or {}).get("images_snapshot"), default=[]),
    }
