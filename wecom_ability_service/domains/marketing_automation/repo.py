from __future__ import annotations

import json
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
from ...db import get_db, get_db_backend


def _db_bool(value: bool) -> bool | int:
    return value if get_db_backend() == "postgres" else (1 if value else 0)


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _nullable_timestamp_text(value: Any) -> str | None:
    normalized = _normalized_text(value)
    return normalized or None


def _json_dumps(value: Any) -> str:
    return json.dumps({} if value is None else value, ensure_ascii=False)


def get_owner_role_item(userid: str) -> dict[str, Any]:
    normalized_userid = _normalized_text(userid)
    if not normalized_userid:
        return {}
    return fetch_owner_role_map([normalized_userid]).get(normalized_userid, {})


def get_marketing_automation_config(automation_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM marketing_automation_configs
        WHERE automation_key = ?
        """,
        (_normalized_text(automation_key),),
    )


def list_marketing_automation_question_rules(automation_config_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM marketing_automation_question_rules
        WHERE automation_config_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(automation_config_id),),
    )


def upsert_marketing_automation_config(
    *,
    automation_key: str,
    automation_name: str,
    target_event: str,
    channel_type: str,
    status: str,
    do_not_start_after_hour: int,
    config_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(automation_key),
        _normalized_text(automation_name),
        _normalized_text(target_event),
        _normalized_text(channel_type),
        _normalized_text(status),
        int(do_not_start_after_hour),
        _json_dumps(config_payload),
    )
    if get_db_backend() == "postgres":
        row = db.execute(
            """
            INSERT INTO marketing_automation_configs (
                automation_key,
                automation_name,
                target_event,
                channel_type,
                status,
                do_not_start_after_hour,
                config_payload_json,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (automation_key) DO UPDATE SET
                automation_name = EXCLUDED.automation_name,
                target_event = EXCLUDED.target_event,
                channel_type = EXCLUDED.channel_type,
                status = EXCLUDED.status,
                do_not_start_after_hour = EXCLUDED.do_not_start_after_hour,
                config_payload_json = EXCLUDED.config_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    else:
        row = db.execute(
            """
            INSERT INTO marketing_automation_configs (
                automation_key,
                automation_name,
                target_event,
                channel_type,
                status,
                do_not_start_after_hour,
                config_payload_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (automation_key) DO UPDATE SET
                automation_name = excluded.automation_name,
                target_event = excluded.target_event,
                channel_type = excluded.channel_type,
                status = excluded.status,
                do_not_start_after_hour = excluded.do_not_start_after_hour,
                config_payload_json = excluded.config_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    return dict(row) if row else {}


def replace_marketing_automation_question_rules(
    *,
    automation_config_id: int,
    questionnaire_id: int,
    rules: list[dict[str, Any]],
) -> None:
    db = get_db()
    db.execute(
        "DELETE FROM marketing_automation_question_rules WHERE automation_config_id = ?",
        (int(automation_config_id),),
    )
    for item in rules:
        params = (
            int(automation_config_id),
            int(questionnaire_id),
            int(item["questionnaire_question_id"]),
            _normalized_text(item["rule_code"]),
            _normalized_text(item["rule_name"]),
            "any_of",
            _json_dumps(item.get("hit_option_ids_json") or []),
            int(item.get("sort_order") or 0),
            _json_dumps(item.get("rule_payload") or {}),
        )
        if get_db_backend() == "postgres":
            db.execute(
                """
                INSERT INTO marketing_automation_question_rules (
                    automation_config_id,
                    questionnaire_id,
                    question_id,
                    rule_code,
                    rule_name,
                    answer_match_type,
                    answer_match_value_json,
                    score_delta,
                    segment_hint,
                    stage_hint,
                    is_active,
                    sort_order,
                    rule_payload_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 0, '', '', TRUE, %s, %s::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                params,
            )
        else:
            db.execute(
                """
                INSERT INTO marketing_automation_question_rules (
                    automation_config_id,
                    questionnaire_id,
                    question_id,
                    rule_code,
                    rule_name,
                    answer_match_type,
                    answer_match_value_json,
                    score_delta,
                    segment_hint,
                    stage_hint,
                    is_active,
                    sort_order,
                    rule_payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', '', 1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                params,
                )


def list_external_userids_by_person(person_id: int) -> list[str]:
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


def get_person_mobile(person_id: int) -> str:
    row = _fetchone_dict(
        """
        SELECT mobile
        FROM people
        WHERE id = ?
        """,
        (int(person_id),),
    )
    return _normalized_text((row or {}).get("mobile"))


def get_latest_questionnaire_submission_for_value_segment(
    questionnaire_id: int,
    *,
    external_userids: list[str] | None = None,
    mobile_snapshot: str = "",
) -> dict[str, Any] | None:
    normalized_external_userids = [_normalized_text(item) for item in external_userids or [] if _normalized_text(item)]
    normalized_mobile = _normalized_text(mobile_snapshot)
    filters: list[str] = []
    params: list[Any] = [int(questionnaire_id)]
    if normalized_external_userids:
        placeholders = ",".join("?" for _ in normalized_external_userids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_userids)
    if normalized_mobile:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_mobile)
    if not filters:
        return None
    return _fetchone_dict(
        f"""
        SELECT *
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
          AND ({' OR '.join(filters)})
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )


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


def get_customer_value_segment_current(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_value_segment_current
        WHERE external_userid = ?
        """,
        (_normalized_text(external_userid),),
    )


def upsert_customer_value_segment_current(
    *,
    external_userid: str,
    segment: str,
    segment_rank: int,
    score: int,
    scoring_version: str,
    computed_reason: str,
    submission_id: int | None,
    matched_question_ids: list[int],
    source_payload: dict[str, Any] | None,
    evaluated_at: str,
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(external_userid),
        _normalized_text(segment),
        int(segment_rank),
        int(score),
        _normalized_text(scoring_version),
        _normalized_text(computed_reason),
        submission_id,
        _json_dumps(matched_question_ids),
        _json_dumps(source_payload),
        _normalized_text(evaluated_at),
    )
    if get_db_backend() == "postgres":
        row = db.execute(
            """
            INSERT INTO customer_value_segment_current (
                external_userid,
                segment,
                segment_rank,
                score,
                scoring_version,
                computed_reason,
                submission_id,
                matched_question_ids_json,
                source_payload_json,
                evaluated_at,
                computed_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::timestamptz, %s::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (external_userid) DO UPDATE SET
                segment = EXCLUDED.segment,
                segment_rank = EXCLUDED.segment_rank,
                score = EXCLUDED.score,
                scoring_version = EXCLUDED.scoring_version,
                computed_reason = EXCLUDED.computed_reason,
                submission_id = EXCLUDED.submission_id,
                matched_question_ids_json = EXCLUDED.matched_question_ids_json,
                source_payload_json = EXCLUDED.source_payload_json,
                evaluated_at = EXCLUDED.evaluated_at,
                computed_at = EXCLUDED.computed_at,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params + (_normalized_text(evaluated_at),),
        ).fetchone()
    else:
        row = db.execute(
            """
            INSERT INTO customer_value_segment_current (
                external_userid,
                segment,
                segment_rank,
                score,
                scoring_version,
                computed_reason,
                submission_id,
                matched_question_ids_json,
                source_payload_json,
                evaluated_at,
                computed_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (external_userid) DO UPDATE SET
                segment = excluded.segment,
                segment_rank = excluded.segment_rank,
                score = excluded.score,
                scoring_version = excluded.scoring_version,
                computed_reason = excluded.computed_reason,
                submission_id = excluded.submission_id,
                matched_question_ids_json = excluded.matched_question_ids_json,
                source_payload_json = excluded.source_payload_json,
                evaluated_at = excluded.evaluated_at,
                computed_at = excluded.computed_at,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params + (_normalized_text(evaluated_at),),
        ).fetchone()
    return dict(row) if row else {}


def insert_customer_value_segment_history(
    *,
    external_userid: str,
    segment: str,
    segment_rank: int,
    score: int,
    scoring_version: str,
    change_reason: str,
    submission_id: int | None,
    matched_question_ids: list[int],
    source_payload: dict[str, Any] | None,
    evaluated_at: str,
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(external_userid),
        _normalized_text(segment),
        int(segment_rank),
        int(score),
        _normalized_text(scoring_version),
        _normalized_text(change_reason),
        submission_id,
        _json_dumps(matched_question_ids),
        _json_dumps(source_payload),
        _normalized_text(evaluated_at),
    )
    if get_db_backend() == "postgres":
        row = db.execute(
            """
            INSERT INTO customer_value_segment_history (
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
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::timestamptz, %s::timestamptz, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            params + (_normalized_text(evaluated_at),),
        ).fetchone()
    else:
        row = db.execute(
            """
            INSERT INTO customer_value_segment_history (
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
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            params + (_normalized_text(evaluated_at),),
        ).fetchone()
    return dict(row) if row else {}


def count_customer_value_segment_history(external_userid: str) -> int:
    row = _fetchone_dict(
        """
        SELECT COUNT(*) AS total
        FROM customer_value_segment_history
        WHERE external_userid = ?
        """,
        (_normalized_text(external_userid),),
    )
    return int((row or {}).get("total") or 0)


def get_binding_snapshot_for_external_userid(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return None
    return fetch_binding_map([normalized_external_userid]).get(normalized_external_userid)


def get_signal_mobile_for_external_userid(external_userid: str) -> str:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return ""
    binding = fetch_binding_map([normalized_external_userid]).get(normalized_external_userid, {})
    if _normalized_text(binding.get("mobile")):
        return _normalized_text(binding.get("mobile"))
    class_status = fetch_class_status_map([normalized_external_userid]).get(normalized_external_userid, {})
    if _normalized_text(class_status.get("mobile_snapshot")):
        return _normalized_text(class_status.get("mobile_snapshot"))
    row = _fetchone_dict(
        """
        SELECT mobile
        FROM user_ops_lead_pool_current
        WHERE external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_external_userid,),
    )
    return _normalized_text((row or {}).get("mobile"))


def has_live_external_userid(external_userid: str) -> bool:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return False
    row = _fetchone_dict(
        """
        SELECT 1 AS found
        FROM (
            SELECT external_userid
            FROM contacts
            WHERE external_userid = ?
            UNION
            SELECT external_userid
            FROM external_contact_bindings
            WHERE external_userid = ?
            UNION
            SELECT external_userid
            FROM wecom_external_contact_identity_map
            WHERE external_userid = ? AND status = 'active'
            UNION
            SELECT external_userid
            FROM wecom_external_contact_follow_users
            WHERE external_userid = ? AND relation_status = 'active'
            UNION
            SELECT external_userid
            FROM user_ops_lead_pool_current
            WHERE external_userid = ?
        ) AS signals
        LIMIT 1
        """,
        (
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
        ),
    )
    return bool(row)


def list_class_status_rows(external_userids: list[str]) -> list[dict[str, Any]]:
    normalized_external_userids = [_normalized_text(item) for item in external_userids if _normalized_text(item)]
    if not normalized_external_userids:
        return []
    result = fetch_class_status_map(normalized_external_userids)
    return [dict(result[external_userid]) for external_userid in normalized_external_userids if external_userid in result]


def list_user_ops_lead_pool_rows_for_marketing_state(
    *,
    external_userids: list[str] | None = None,
    mobile: str = "",
) -> list[dict[str, Any]]:
    normalized_external_userids = [_normalized_text(item) for item in external_userids or [] if _normalized_text(item)]
    normalized_mobile = _normalized_text(mobile)
    filters: list[str] = []
    params: list[Any] = []
    if normalized_external_userids:
        placeholders = ",".join("?" for _ in normalized_external_userids)
        filters.append(f"external_userid IN ({placeholders})")
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
    normalized_external_userids = [_normalized_text(item) for item in external_userids or [] if _normalized_text(item)]
    normalized_mobile = _normalized_text(mobile)
    filters: list[str] = []
    params: list[Any] = []
    if normalized_external_userids:
        placeholders = ",".join("?" for _ in normalized_external_userids)
        filters.append(f"external_userid IN ({placeholders})")
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
                1 if final_external_userid else int(bool(existing.get("is_wecom_bound"))),
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
                1 if final_external_userid else 0,
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


def get_huangxiaocan_activation_source_by_mobile(mobile: str) -> dict[str, Any] | None:
    normalized_mobile = _normalized_text(mobile)
    if not normalized_mobile:
        return None
    return _fetchone_dict(
        """
        SELECT
            mobile,
            activation_state,
            is_active,
            created_at,
            updated_at
        FROM user_ops_huangxiaocan_activation_source
        WHERE mobile = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_mobile,),
    )


def get_latest_message_at_for_external_userids(external_userids: list[str]) -> str:
    normalized_external_userids = [_normalized_text(item) for item in external_userids if _normalized_text(item)]
    if not normalized_external_userids:
        return ""
    message_map = fetch_last_message_map(normalized_external_userids)
    timestamps = [_normalized_text(message_map.get(external_userid)) for external_userid in normalized_external_userids]
    timestamps = [item for item in timestamps if item]
    return max(timestamps) if timestamps else ""


def list_pool_batch_send_candidates(pool_key: str) -> list[dict[str, Any]]:
    normalized_pool_key = _normalized_text(pool_key)
    if not normalized_pool_key:
        return []
    return _fetchall_dicts(
        """
        SELECT
            current.id AS marketing_state_id,
            current.person_id,
            COALESCE(current.external_userid, '') AS external_userid,
            COALESCE(current.entered_at, '') AS entered_at,
            COALESCE(current.last_activation_at, '') AS last_activation_at,
            COALESCE(current.state_payload_json, '{}') AS state_payload_json,
            COALESCE(contact.customer_name, '') AS customer_name,
            COALESCE(contact.owner_userid, '') AS contact_owner_userid,
            COALESCE(owner_map.display_name, '') AS owner_display_name,
            COALESCE(people.mobile, '') AS person_mobile
        FROM customer_marketing_state_current current
        LEFT JOIN contacts contact
          ON contact.external_userid = current.external_userid
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = contact.owner_userid
        LEFT JOIN people people
          ON people.id = current.person_id
        WHERE current.main_stage = 'pool'
          AND current.sub_stage = ?
        ORDER BY current.updated_at DESC, current.id DESC
        """,
        (normalized_pool_key,),
    )


def list_active_do_not_disturb_rows(
    *,
    external_userids: list[str] | None = None,
    mobiles: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_external_userids = [_normalized_text(item) for item in (external_userids or []) if _normalized_text(item)]
    normalized_mobiles = [_normalized_text(item) for item in (mobiles or []) if _normalized_text(item)]
    filters: list[str] = []
    params: list[Any] = [_db_bool(True)]
    if normalized_external_userids:
        filters.append(f"external_userid IN ({', '.join(['?'] * len(normalized_external_userids))})")
        params.extend(normalized_external_userids)
    if normalized_mobiles:
        filters.append(f"mobile IN ({', '.join(['?'] * len(normalized_mobiles))})")
        params.extend(normalized_mobiles)
    if not filters:
        return []
    return _fetchall_dicts(
        f"""
        SELECT
            COALESCE(external_userid, '') AS external_userid,
            COALESCE(mobile, '') AS mobile,
            COALESCE(source_type, '') AS source_type,
            COALESCE(reason_code, '') AS reason_code,
            COALESCE(reason_text, '') AS reason_text,
            is_active,
            created_at,
            updated_at
        FROM user_ops_do_not_disturb
        WHERE is_active = ?
          AND ({' OR '.join(filters)})
        ORDER BY updated_at DESC, id DESC
        """,
        tuple(params),
    )


def resolve_customer_identity_by_mobile(mobile: str) -> dict[str, Any] | None:
    normalized_mobile = _normalized_text(mobile)
    if not normalized_mobile:
        return None
    return _fetchone_dict(
        """
        SELECT
            people.id AS person_id,
            people.mobile,
            COALESCE(bindings.external_userid, '') AS external_userid,
            COALESCE(contact.customer_name, '') AS customer_name,
            COALESCE(contact.owner_userid, '') AS owner_userid
        FROM people people
        LEFT JOIN external_contact_bindings bindings
          ON bindings.person_id = people.id
        LEFT JOIN contacts contact
          ON contact.external_userid = bindings.external_userid
        WHERE people.mobile = ?
        ORDER BY COALESCE(bindings.updated_at, bindings.created_at) DESC, bindings.external_userid ASC
        LIMIT 1
        """,
        (normalized_mobile,),
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
    if get_db_backend() == "postgres":
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
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (mobile) DO UPDATE SET
                activation_state = EXCLUDED.activation_state,
                import_batch_id = EXCLUDED.import_batch_id,
                created_by = EXCLUDED.created_by,
                is_active = EXCLUDED.is_active,
                updated_at = EXCLUDED.updated_at
            """,
            params,
        )
    else:
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
                activation_state = excluded.activation_state,
                import_batch_id = excluded.import_batch_id,
                created_by = excluded.created_by,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
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
        placeholders = ",".join("?" for _ in duplicate_ids)
        db.execute(f"DELETE FROM customer_marketing_state_current WHERE id IN ({placeholders})", tuple(duplicate_ids))
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
        if get_db_backend() == "postgres":
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
                    state_payload_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                RETURNING *
                """,
                params + (row_id,),
            ).fetchone()
    else:
        if get_db_backend() == "postgres":
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
    if get_db_backend() == "postgres":
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
    else:
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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


def get_latest_class_user_restore_status(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return None
    return _fetchone_dict(
        """
        SELECT
            old_signup_status,
            old_label_name,
            customer_name_snapshot,
            owner_userid_snapshot,
            mobile_snapshot,
            set_by_userid,
            set_at,
            created_at
        FROM class_user_status_history
        WHERE external_userid = ?
          AND old_signup_status <> ''
          AND old_signup_status NOT LIKE 'signed_%'
        ORDER BY id DESC
        LIMIT 1
        """,
        (normalized_external_userid,),
    )


def get_conversion_dispatch_log(batch_id: int, external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM conversion_dispatch_log
        WHERE batch_id = ? AND external_userid = ?
        """,
        (int(batch_id), _normalized_text(external_userid)),
    )


def upsert_conversion_dispatch_log(
    *,
    automation_key: str,
    batch_id: int,
    external_userid: str,
    dispatch_status: str,
    dispatch_channel: str,
    dispatch_payload: dict[str, Any] | None,
    dispatch_note: str,
    dispatched_at: str = "",
    acked_at: str = "",
) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(automation_key),
        int(batch_id),
        _normalized_text(external_userid),
        _normalized_text(dispatch_status),
        _normalized_text(dispatch_channel),
        _json_dumps(dispatch_payload),
        _normalized_text(dispatch_note),
        _normalized_text(dispatched_at),
        _normalized_text(acked_at),
    )
    if get_db_backend() == "postgres":
        row = db.execute(
            """
            INSERT INTO conversion_dispatch_log (
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
            )
            VALUES (?, ?, ?, ?, ?, ?::jsonb, ?, NULLIF(?, '')::timestamptz, NULLIF(?, '')::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (batch_id, external_userid) DO UPDATE SET
                automation_key = EXCLUDED.automation_key,
                dispatch_status = EXCLUDED.dispatch_status,
                dispatch_channel = EXCLUDED.dispatch_channel,
                dispatch_payload_json = EXCLUDED.dispatch_payload_json,
                dispatch_note = EXCLUDED.dispatch_note,
                dispatched_at = CASE
                    WHEN EXCLUDED.dispatched_at IS NOT NULL THEN EXCLUDED.dispatched_at
                    ELSE conversion_dispatch_log.dispatched_at
                END,
                acked_at = CASE
                    WHEN EXCLUDED.acked_at IS NOT NULL THEN EXCLUDED.acked_at
                    ELSE conversion_dispatch_log.acked_at
                END,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    else:
        row = db.execute(
            """
            INSERT INTO conversion_dispatch_log (
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
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULLIF(?, ''), NULLIF(?, ''), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (batch_id, external_userid) DO UPDATE SET
                automation_key = excluded.automation_key,
                dispatch_status = excluded.dispatch_status,
                dispatch_channel = excluded.dispatch_channel,
                dispatch_payload_json = excluded.dispatch_payload_json,
                dispatch_note = excluded.dispatch_note,
                dispatched_at = CASE
                    WHEN excluded.dispatched_at IS NOT NULL THEN excluded.dispatched_at
                    ELSE conversion_dispatch_log.dispatched_at
                END,
                acked_at = CASE
                    WHEN excluded.acked_at IS NOT NULL THEN excluded.acked_at
                    ELSE conversion_dispatch_log.acked_at
                END,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    return dict(row) if row else {}


def list_conversion_dispatch_logs(
    *,
    external_userid: str = "",
    batch_id: int | None = None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    normalized_external_userid = _normalized_text(external_userid)
    if batch_id is not None:
        filters.append("batch_id = ?")
        params.append(int(batch_id))
    if normalized_external_userid:
        filters.append("external_userid = ?")
        params.append(normalized_external_userid)
    if not filters:
        return []
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM conversion_dispatch_log
        WHERE {' AND '.join(filters)}
        ORDER BY updated_at DESC, id DESC
        """,
        tuple(params),
    )


def get_marketing_state_current(external_userid: str, *, scenario_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM marketing_state_current
        WHERE scenario_key = ? AND external_userid = ?
        """,
        (scenario_key, external_userid),
    )


def get_marketing_value_segment_current(external_userid: str, *, scenario_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM marketing_value_segment_current
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
    if get_db_backend() == "postgres":
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULLIF(%s, '')::timestamptz, NULLIF(%s, '')::timestamptz, %s, %s::jsonb)
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
    else:
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (scenario_key, external_userid) DO UPDATE SET
                marketing_phase = excluded.marketing_phase,
                phase_label = excluded.phase_label,
                phase_reason = excluded.phase_reason,
                lifecycle_status = excluded.lifecycle_status,
                last_batch_id = excluded.last_batch_id,
                last_batch_status = excluded.last_batch_status,
                last_batch_window_start = excluded.last_batch_window_start,
                last_batch_window_end = excluded.last_batch_window_end,
                last_trigger_message_at = excluded.last_trigger_message_at,
                entered_at = excluded.entered_at,
                exited_at = excluded.exited_at,
                exit_reason = excluded.exit_reason,
                source_payload_json = excluded.source_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    db.commit()
    return dict(row) if row else {}


def upsert_marketing_value_segment_current(
    *,
    scenario_key: str,
    external_userid: str,
    value_segment: str,
    segment_label: str,
    score: int,
    score_breakdown: dict[str, Any] | None,
    source_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    db = get_db()
    params = (
        scenario_key,
        external_userid,
        value_segment,
        segment_label,
        int(score),
        _json_dumps(score_breakdown),
        _json_dumps(source_payload),
    )
    if get_db_backend() == "postgres":
        row = db.execute(
            """
            INSERT INTO marketing_value_segment_current (
                scenario_key,
                external_userid,
                value_segment,
                segment_label,
                score,
                score_breakdown_json,
                source_payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (scenario_key, external_userid) DO UPDATE SET
                value_segment = EXCLUDED.value_segment,
                segment_label = EXCLUDED.segment_label,
                score = EXCLUDED.score,
                score_breakdown_json = EXCLUDED.score_breakdown_json,
                source_payload_json = EXCLUDED.source_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    else:
        row = db.execute(
            """
            INSERT INTO marketing_value_segment_current (
                scenario_key,
                external_userid,
                value_segment,
                segment_label,
                score,
                score_breakdown_json,
                source_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (scenario_key, external_userid) DO UPDATE SET
                value_segment = excluded.value_segment,
                segment_label = excluded.segment_label,
                score = excluded.score,
                score_breakdown_json = excluded.score_breakdown_json,
                source_payload_json = excluded.source_payload_json,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            params,
        ).fetchone()
    db.commit()
    return dict(row) if row else {}


def get_questionnaire_signal(external_userid: str) -> dict[str, Any]:
    if get_db_backend() == "postgres":
        row = _fetchone_dict(
            """
            SELECT COUNT(*) AS submission_count, COALESCE(MAX(submitted_at)::text, '') AS last_submitted_at
            FROM questionnaire_submissions
            WHERE external_userid = ?
            """,
            (external_userid,),
        )
    else:
        row = _fetchone_dict(
            """
            SELECT COUNT(*) AS submission_count, COALESCE(MAX(submitted_at), '') AS last_submitted_at
            FROM questionnaire_submissions
            WHERE external_userid = ?
            """,
            (external_userid,),
        )
    return row or {"submission_count": 0, "last_submitted_at": ""}


def get_customer_inbound_message_signal(external_userid: str) -> dict[str, Any]:
    db = get_db()
    if get_db_backend() == "postgres":
        row = db.execute(
            """
            SELECT
                COALESCE(MAX(send_time), '') AS last_customer_text_at,
                SUM(
                    CASE
                        WHEN send_time >= TO_CHAR(NOW() - INTERVAL '72 hours', 'YYYY-MM-DD HH24:MI:SS') THEN 1
                        ELSE 0
                    END
                ) AS customer_text_72h_count
            FROM archived_messages
            WHERE external_userid = %s AND sender = %s AND msgtype = 'text'
            """,
            (external_userid, external_userid),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT
                COALESCE(MAX(send_time), '') AS last_customer_text_at,
                SUM(CASE WHEN send_time >= datetime('now', '-72 hours') THEN 1 ELSE 0 END) AS customer_text_72h_count
            FROM archived_messages
            WHERE external_userid = ? AND sender = ? AND msgtype = 'text'
            """,
            (external_userid, external_userid),
        ).fetchone()
    return dict(row) if row else {"last_customer_text_at": "", "customer_text_72h_count": 0}


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
