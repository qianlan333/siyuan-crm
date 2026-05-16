from __future__ import annotations

from datetime import datetime
from typing import Any

from ...customer_center.repo import (
    fetch_binding_map,
    fetch_class_status_map,
    fetch_contact_map,
    fetch_follow_users_map,
    fetch_identity_map,
    fetch_last_message_map,
    fetch_owner_role_map,
    fetch_tag_map,
)
from ...db import get_db
from ._repo_helpers import (  # noqa: F401  shared helpers — 阶段 5.2
    _db_bool,
    _fetchall_dicts,
    _fetchone_dict,
    _json_dumps,
    _normalized_text,
    _normalized_text_list,
    _nullable_timestamp_text,
    _placeholders,
)
from ._repo_config import (  # noqa: F401  marketing_automation config + owner_role + question_rules — 阶段 5.4
    get_marketing_automation_config,
    get_owner_role_item,
    list_marketing_automation_question_rules,
    replace_marketing_automation_question_rules,
    upsert_marketing_automation_config,
)
from ._repo_value_segment import (  # noqa: F401  customer_value_segment + marketing_value_segment — 阶段 5.4
    count_customer_value_segment_history,
    get_customer_value_segment_current,
    get_latest_questionnaire_submission_for_value_segment,
    get_marketing_value_segment_current,
    insert_customer_value_segment_history,
    upsert_customer_value_segment_current,
    upsert_marketing_value_segment_current,
)
from ._repo_dispatch import (  # noqa: F401  conversion_dispatch_log — 阶段 5.4
    get_conversion_dispatch_log,
    list_conversion_dispatch_logs,
    upsert_conversion_dispatch_log,
)
from ._repo_externals import (  # noqa: F401  cross-domain glue (class_status / lead_pool / message_signal / questionnaire / etc) + person/contact lookup — 阶段 5.4
    get_binding_snapshot_for_external_userid,
    get_customer_inbound_message_signal,
    get_huangxiaocan_activation_source_by_mobile,
    get_latest_class_user_restore_status,
    get_latest_message_at_for_external_userids,
    get_person_mobile,
    get_questionnaire_signal,
    get_signal_mobile_for_external_userid,
    has_live_external_userid,
    list_active_do_not_disturb_rows,
    list_class_status_rows,
    list_external_userids_by_person,
    list_pool_batch_send_candidates,
    list_questionnaire_submission_answers,
    resolve_customer_identity_by_mobile,
)

def list_user_ops_lead_pool_rows_for_marketing_state(
    *,
    external_userids: list[str] | None = None,
    mobile: str = "",
) -> list[dict[str, Any]]:
    normalized_external_userids = _normalized_text_list(external_userids)
    normalized_mobile = _normalized_text(mobile)
    filters: list[str] = []
    params: list[Any] = []
    if normalized_external_userids:
        filters.append(f"external_userid IN ({_placeholders(normalized_external_userids)})")
        params.extend(normalized_external_userids)
    if normalized_mobile:
        filters.append("mobile = ?")
        params.append(normalized_mobile)
    if not filters:
        return []
    return _fetchall_dicts(
        f"""
        SELECT
            id,
            mobile,
            external_userid,
            huangxiaocan_activation_state,
            owner_userid,
            updated_at,
            created_at
        FROM user_ops_lead_pool_current
        WHERE {' OR '.join(filters)}
        ORDER BY updated_at DESC, id DESC
        """,
        tuple(params),
    )


def get_explicit_trial_opening_fact(
    *,
    external_userids: list[str] | None = None,
    mobile: str = "",
) -> dict[str, Any] | None:
    normalized_external_userids = _normalized_text_list(external_userids)
    normalized_mobile = _normalized_text(mobile)
    filters: list[str] = []
    params: list[Any] = []
    if normalized_external_userids:
        filters.append(f"external_userid IN ({_placeholders(normalized_external_userids)})")
        params.extend(normalized_external_userids)
    if normalized_mobile:
        filters.append("mobile = ?")
        params.append(normalized_mobile)
    if not filters:
        return None
    return _fetchone_dict(
        f"""
        SELECT
            id,
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            current_status,
            is_wecom_bound,
            activation_status,
            activation_remark,
            class_term_no,
            class_term_label,
            source_type,
            created_at,
            updated_at
        FROM user_ops_pool_current
        WHERE current_status = 'lead_trial' AND ({' OR '.join(filters)})
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )


def upsert_explicit_trial_opening_fact(
    *,
    mobile: str,
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    source_type: str = "automation_conversion",
    opened_at: str = "",
) -> dict[str, Any]:
    normalized_mobile = _normalized_text(mobile)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_mobile and not normalized_external_userid:
        raise ValueError("mobile or external_userid is required")

    existing = get_explicit_trial_opening_fact(
        external_userids=[normalized_external_userid] if normalized_external_userid else [],
        mobile=normalized_mobile,
    )
    if existing is None:
        existing = _fetchone_dict(
            """
            SELECT
                id,
                mobile,
                external_userid,
                customer_name,
                owner_userid,
                current_status,
                is_wecom_bound,
                activation_status,
                activation_remark,
                class_term_no,
                class_term_label,
                source_type,
                created_at,
                updated_at
            FROM user_ops_pool_current
            WHERE (? <> '' AND external_userid = ?) OR (? <> '' AND mobile = ?)
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (
                normalized_external_userid,
                normalized_external_userid,
                normalized_mobile,
                normalized_mobile,
            ),
        )

    final_mobile = normalized_mobile or _normalized_text((existing or {}).get("mobile"))
    final_external_userid = normalized_external_userid or _normalized_text((existing or {}).get("external_userid"))
    final_customer_name = _normalized_text(customer_name) or _normalized_text((existing or {}).get("customer_name"))
    final_owner_userid = _normalized_text(owner_userid) or _normalized_text((existing or {}).get("owner_userid"))
    final_source_type = _normalized_text(source_type) or _normalized_text((existing or {}).get("source_type")) or "automation_conversion"
    timestamp = (
        _normalized_text(opened_at)
        or _normalized_text((existing or {}).get("updated_at"))
        or _normalized_text((existing or {}).get("created_at"))
        or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    created_at = _normalized_text((existing or {}).get("created_at")) or timestamp

    db = get_db()
    if existing:
        db.execute(
            """
            UPDATE user_ops_pool_current
            SET mobile = ?,
                external_userid = ?,
                customer_name = ?,
                owner_userid = ?,
                current_status = 'lead_trial',
                is_wecom_bound = ?,
                activation_status = ?,
                activation_remark = ?,
                class_term_no = ?,
                class_term_label = ?,
                source_type = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                final_mobile,
                final_external_userid,
                final_customer_name,
                final_owner_userid,
                bool(final_external_userid) or bool(existing.get("is_wecom_bound")),
                _normalized_text(existing.get("activation_status")) or "not_activated",
                _normalized_text(existing.get("activation_remark")),
                existing.get("class_term_no"),
                _normalized_text(existing.get("class_term_label")),
                final_source_type,
                timestamp,
                int(existing["id"]),
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile,
                external_userid,
                customer_name,
                owner_userid,
                current_status,
                is_wecom_bound,
                activation_status,
                activation_remark,
                class_term_no,
                class_term_label,
                source_type,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 'lead_trial', ?, 'not_activated', '', NULL, '', ?, ?, ?)
            """,
            (
                final_mobile,
                final_external_userid,
                final_customer_name,
                final_owner_userid,
                bool(final_external_userid),
                final_source_type,
                created_at,
                timestamp,
            ),
        )
    return (
        get_explicit_trial_opening_fact(
            external_userids=[final_external_userid] if final_external_userid else [],
            mobile=final_mobile,
        )
        or {}
    )


def upsert_activation_webhook_source(
    *,
    mobile: str,
    signal_at: str,
    import_batch_id: str,
    created_by: str,
) -> dict[str, Any]:
    normalized_mobile = _normalized_text(mobile)
    normalized_signal_at = _normalized_text(signal_at) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized_import_batch_id = _normalized_text(import_batch_id) or "activation_webhook"
    normalized_created_by = _normalized_text(created_by) or "activation_webhook"
    db = get_db()
    params = (
        normalized_mobile,
        "activated",
        normalized_import_batch_id,
        normalized_created_by,
        _db_bool(True),
        normalized_signal_at,
        normalized_signal_at,
    )
    db.execute(
        """
        INSERT INTO user_ops_huangxiaocan_activation_source (
            mobile,
            activation_state,
            import_batch_id,
            created_by,
            is_active,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (mobile) DO UPDATE SET
            activation_state = EXCLUDED.activation_state,
            import_batch_id = EXCLUDED.import_batch_id,
            created_by = EXCLUDED.created_by,
            is_active = EXCLUDED.is_active,
            updated_at = EXCLUDED.updated_at
        """,
        params,
    )
    db.execute(
        """
        UPDATE user_ops_pool_current
        SET activation_status = 'activated',
            activation_remark = ?,
            updated_at = ?
        WHERE mobile = ?
        """,
        ("activation webhook", normalized_signal_at, normalized_mobile),
    )
    db.commit()
    return (
        get_huangxiaocan_activation_source_by_mobile(normalized_mobile)
        or {
            "mobile": normalized_mobile,
            "activation_state": "activated",
            "import_batch_id": normalized_import_batch_id,
            "created_by": normalized_created_by,
            "is_active": True,
            "created_at": normalized_signal_at,
            "updated_at": normalized_signal_at,
        }
    )


def _list_customer_marketing_state_current_candidates(
    *,
    external_userid: str,
    person_id: int | None,
) -> list[dict[str, Any]]:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_person_id = int(person_id) if person_id is not None else None
    filters: list[str] = []
    params: list[Any] = []
    if normalized_person_id is not None:
        filters.append("person_id = ?")
        params.append(normalized_person_id)
    if normalized_external_userid:
        filters.append("external_userid = ?")
        params.append(normalized_external_userid)
    if not filters:
        return []
    sql = f"""
        SELECT *
        FROM customer_marketing_state_current
        WHERE {' OR '.join(filters)}
    """
    if normalized_person_id is not None:
        sql += " ORDER BY CASE WHEN person_id = ? THEN 0 ELSE 1 END, updated_at DESC, id DESC"
        params.append(normalized_person_id)
    else:
        sql += " ORDER BY updated_at DESC, id DESC"
    return _fetchall_dicts(sql, tuple(params))


def get_customer_marketing_state_current(
    *,
    external_userid: str = "",
    person_id: int | None = None,
) -> dict[str, Any] | None:
    rows = _list_customer_marketing_state_current_candidates(
        external_userid=external_userid,
        person_id=person_id,
    )
    return rows[0] if rows else None


def upsert_customer_marketing_state_current(
    *,
    external_userid: str,
    person_id: int | None,
    automation_key: str,
    main_stage: str,
    sub_stage: str,
    activated: bool,
    converted: bool,
    eligible_for_conversion: bool,
    lifecycle_status: str,
    last_activation_at: str,
    last_conversion_marked_at: str,
    last_message_at: str,
    last_batch_id: int | None,
    last_batch_status: str,
    last_batch_window_start: str,
    last_batch_window_end: str,
    last_trigger_message_at: str,
    entered_at: str | None,
    exited_at: str | None,
    exit_reason: str,
    state_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db = get_db()
    existing_rows = _list_customer_marketing_state_current_candidates(
        external_userid=external_userid,
        person_id=person_id,
    )
    target = existing_rows[0] if existing_rows else None
    duplicate_ids = [int(row["id"]) for row in existing_rows[1:]]
    if duplicate_ids:
        db.execute(
            f"DELETE FROM customer_marketing_state_current WHERE id IN ({_placeholders(duplicate_ids)})",
            tuple(duplicate_ids),
        )
    params = (
        int(person_id) if person_id is not None else None,
        _normalized_text(external_userid),
        _normalized_text(automation_key),
        _normalized_text(main_stage),
        _normalized_text(sub_stage),
        bool(activated),
        bool(converted),
        bool(eligible_for_conversion),
        _normalized_text(lifecycle_status),
        _normalized_text(last_activation_at),
        _normalized_text(last_conversion_marked_at),
        _normalized_text(last_message_at),
        last_batch_id,
        _normalized_text(last_batch_status),
        _normalized_text(last_batch_window_start),
        _normalized_text(last_batch_window_end),
        _normalized_text(last_trigger_message_at),
        _nullable_timestamp_text(entered_at),
        _nullable_timestamp_text(exited_at),
        _normalized_text(exit_reason),
        _json_dumps(state_payload),
    )
    if target:
        row_id = int(target["id"])
        row = db.execute(
            """
            UPDATE customer_marketing_state_current
            SET
                person_id = ?,
                external_userid = ?,
                automation_key = ?,
                main_stage = ?,
                sub_stage = ?,
                activated = ?,
                converted = ?,
                eligible_for_conversion = ?,
                lifecycle_status = ?,
                last_activation_at = ?,
                last_conversion_marked_at = ?,
                last_message_at = ?,
                last_batch_id = ?,
                last_batch_status = ?,
                last_batch_window_start = ?,
                last_batch_window_end = ?,
                last_trigger_message_at = ?,
                entered_at = ?,
                exited_at = ?,
                exit_reason = ?,
                state_payload_json = ?::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            params + (row_id,),
        ).fetchone()
    else:
        row = db.execute(
            """
            INSERT INTO customer_marketing_state_current (
                person_id,
                external_userid,
                automation_key,
                main_stage,
                sub_stage,
                activated,
                converted,
                eligible_for_conversion,
                lifecycle_status,
                last_activation_at,
                last_conversion_marked_at,
                last_message_at,
                last_batch_id,
                last_batch_status,
                last_batch_window_start,
                last_batch_window_end,
                last_trigger_message_at,
                entered_at,
                exited_at,
                exit_reason,
                state_payload_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            params,
        ).fetchone()
    return dict(row) if row else {}


def insert_customer_marketing_state_history(
    *,
    external_userid: str,
    person_id: int | None,
    automation_key: str,
    main_stage: str,
    sub_stage: str,
    activated: bool,
    converted: bool,
    eligible_for_conversion: bool,
    batch_id: int | None,
    lifecycle_status: str,
    exit_reason: str,
    last_activation_at: str,
    last_conversion_marked_at: str,
    last_message_at: str,
    change_reason: str,
    state_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db = get_db()
    params = (
        int(person_id) if person_id is not None else None,
        _normalized_text(external_userid),
        _normalized_text(automation_key),
        _normalized_text(main_stage),
        _normalized_text(sub_stage),
        bool(activated),
        bool(converted),
        bool(eligible_for_conversion),
        batch_id,
        _normalized_text(lifecycle_status),
        _normalized_text(exit_reason),
        _normalized_text(last_activation_at),
        _normalized_text(last_conversion_marked_at),
        _normalized_text(last_message_at),
        _normalized_text(change_reason),
        _json_dumps(state_payload),
    )
    row = db.execute(
        """
        INSERT INTO customer_marketing_state_history (
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
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def count_customer_marketing_state_history(
    *,
    external_userid: str = "",
    person_id: int | None = None,
) -> int:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_person_id = int(person_id) if person_id is not None else None
    filters: list[str] = []
    params: list[Any] = []
    if normalized_person_id is not None:
        filters.append("person_id = ?")
        params.append(normalized_person_id)
    if normalized_external_userid:
        filters.append("external_userid = ?")
        params.append(normalized_external_userid)
    if not filters:
        return 0
    row = _fetchone_dict(
        f"""
        SELECT COUNT(*) AS total
        FROM customer_marketing_state_history
        WHERE {' OR '.join(filters)}
        """,
        tuple(params),
    )
    return int((row or {}).get("total") or 0)


def get_marketing_state_current(external_userid: str, *, scenario_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM marketing_state_current
        WHERE scenario_key = ? AND external_userid = ?
        """,
        (scenario_key, external_userid),
    )


def upsert_marketing_state_current(
    *,
    scenario_key: str,
    external_userid: str,
    marketing_phase: str,
    phase_label: str,
    phase_reason: str,
    lifecycle_status: str,
    last_batch_id: int | None,
    last_batch_status: str,
    last_batch_window_start: str,
    last_batch_window_end: str,
    last_trigger_message_at: str,
    entered_at: str,
    exited_at: str,
    exit_reason: str,
    source_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db = get_db()
    params = (
        scenario_key,
        external_userid,
        marketing_phase,
        phase_label,
        phase_reason,
        lifecycle_status,
        last_batch_id,
        last_batch_status,
        last_batch_window_start,
        last_batch_window_end,
        last_trigger_message_at,
        entered_at,
        exited_at,
        exit_reason,
        _json_dumps(source_payload),
    )
    row = db.execute(
        """
        INSERT INTO marketing_state_current (
            scenario_key,
            external_userid,
            marketing_phase,
            phase_label,
            phase_reason,
            lifecycle_status,
            last_batch_id,
            last_batch_status,
            last_batch_window_start,
            last_batch_window_end,
            last_trigger_message_at,
            entered_at,
            exited_at,
            exit_reason,
            source_payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULLIF(?, '')::timestamptz, NULLIF(?, '')::timestamptz, ?, ?::jsonb)
        ON CONFLICT (scenario_key, external_userid) DO UPDATE SET
            marketing_phase = EXCLUDED.marketing_phase,
            phase_label = EXCLUDED.phase_label,
            phase_reason = EXCLUDED.phase_reason,
            lifecycle_status = EXCLUDED.lifecycle_status,
            last_batch_id = EXCLUDED.last_batch_id,
            last_batch_status = EXCLUDED.last_batch_status,
            last_batch_window_start = EXCLUDED.last_batch_window_start,
            last_batch_window_end = EXCLUDED.last_batch_window_end,
            last_trigger_message_at = EXCLUDED.last_trigger_message_at,
            entered_at = EXCLUDED.entered_at,
            exited_at = EXCLUDED.exited_at,
            exit_reason = EXCLUDED.exit_reason,
            source_payload_json = EXCLUDED.source_payload_json,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """,
        params,
    ).fetchone()
    db.commit()
    return dict(row) if row else {}


def load_customer_marketing_base(external_userid: str) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    contact = fetch_contact_map([normalized_external_userid]).get(normalized_external_userid, {})
    binding = fetch_binding_map([normalized_external_userid]).get(normalized_external_userid, {})
    identity = fetch_identity_map([normalized_external_userid]).get(normalized_external_userid, {})
    follow_users = fetch_follow_users_map([normalized_external_userid]).get(normalized_external_userid, [])
    tags = fetch_tag_map([normalized_external_userid]).get(normalized_external_userid, [])
    class_status = fetch_class_status_map([normalized_external_userid]).get(normalized_external_userid, {})
    last_message_at = fetch_last_message_map([normalized_external_userid]).get(normalized_external_userid, "")
    questionnaire_signal = get_questionnaire_signal(normalized_external_userid)
    inbound_signal = get_customer_inbound_message_signal(normalized_external_userid)

    primary_follow_user = next((item for item in follow_users if item.get("is_primary")), follow_users[0] if follow_users else {})
    owner_userid = (
        _normalized_text(class_status.get("owner_userid_snapshot"))
        or _normalized_text(contact.get("owner_userid"))
        or _normalized_text(binding.get("last_owner_userid"))
        or _normalized_text(binding.get("first_owner_userid"))
        or _normalized_text(identity.get("follow_user_userid"))
        or _normalized_text(primary_follow_user.get("userid"))
    )
    owner_role = fetch_owner_role_map([owner_userid]).get(owner_userid, {}) if owner_userid else {}

    return {
        "external_userid": normalized_external_userid,
        "customer_name": (
            _normalized_text(class_status.get("customer_name_snapshot"))
            or _normalized_text(contact.get("customer_name"))
            or _normalized_text(identity.get("name"))
            or normalized_external_userid
        ),
        "owner_userid": owner_userid,
        "owner_display_name": _normalized_text(owner_role.get("display_name")) or owner_userid,
        "mobile": _normalized_text(binding.get("mobile")) or _normalized_text(class_status.get("mobile_snapshot")),
        "is_bound": bool(binding),
        "signup_status": _normalized_text(class_status.get("signup_status")),
        "signup_label_name": _normalized_text(class_status.get("signup_label_name")),
        "tags": tags,
        "last_message_at": _normalized_text(last_message_at),
        "questionnaire_submission_count": int(questionnaire_signal.get("submission_count") or 0),
        "last_questionnaire_submitted_at": _normalized_text(questionnaire_signal.get("last_submitted_at")),
        "last_customer_text_at": _normalized_text(inbound_signal.get("last_customer_text_at")),
        "customer_text_72h_count": int(inbound_signal.get("customer_text_72h_count") or 0),
    }
