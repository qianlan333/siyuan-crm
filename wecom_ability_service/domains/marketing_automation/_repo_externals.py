"""cross-domain glue (class_status / lead_pool / message_signal / questionnaire / etc) + person/contact lookup (阶段 5.4).

Extracted from repo.py. External callers keep using
``marketing_automation.repo.X``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ...customer_center.repo import (
    fetch_binding_map,
    fetch_class_status_map,
    fetch_last_message_map,
)
from ...db import get_db
from ._repo_helpers import (  # noqa: F401
    _db_bool,
    _fetchall_dicts,
    _fetchone_dict,
    _normalized_text,
    _normalized_text_list,
    _placeholders,
)


def _local_timestamp_text(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    return value


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
    normalized_external_userids = _normalized_text_list(external_userids)
    if not normalized_external_userids:
        return []
    result = fetch_class_status_map(normalized_external_userids)
    return [dict(result[external_userid]) for external_userid in normalized_external_userids if external_userid in result]


def get_huangxiaocan_activation_source_by_mobile(mobile: str) -> dict[str, Any] | None:
    normalized_mobile = _normalized_text(mobile)
    if not normalized_mobile:
        return None
    row = _fetchone_dict(
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
    if not row:
        return None
    return {
        **row,
        "created_at": _local_timestamp_text(row.get("created_at")),
        "updated_at": _local_timestamp_text(row.get("updated_at")),
    }


def get_latest_message_at_for_external_userids(external_userids: list[str]) -> str:
    normalized_external_userids = _normalized_text_list(external_userids)
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
            COALESCE(current.entered_at::text, '') AS entered_at,
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
    normalized_external_userids = _normalized_text_list(external_userids)
    normalized_mobiles = _normalized_text_list(mobiles)
    filters: list[str] = []
    params: list[Any] = [_db_bool(True)]
    if normalized_external_userids:
        filters.append(f"external_userid IN ({_placeholders(normalized_external_userids)})")
        params.extend(normalized_external_userids)
    if normalized_mobiles:
        filters.append(f"mobile IN ({_placeholders(normalized_mobiles)})")
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
          AND old_signup_status NOT LIKE 'signed_%%'
        ORDER BY id DESC
        LIMIT 1
        """,
        (normalized_external_userid,),
    )


def get_questionnaire_signal(external_userid: str) -> dict[str, Any]:
    row = _fetchone_dict(
        """
        SELECT COUNT(*) AS submission_count, COALESCE(MAX(submitted_at)::text, '') AS last_submitted_at
        FROM questionnaire_submissions
        WHERE external_userid = ?
        """,
        (external_userid,),
    )
    return row or {"submission_count": 0, "last_submitted_at": ""}


def get_customer_inbound_message_signal(external_userid: str) -> dict[str, Any]:
    db = get_db()
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
        WHERE external_userid = ? AND sender = ? AND msgtype = 'text'
        """,
        (external_userid, external_userid),
    ).fetchone()
    return dict(row) if row else {"last_customer_text_at": "", "customer_text_72h_count": 0}




__all__ = [
    "get_binding_snapshot_for_external_userid",
    "get_customer_inbound_message_signal",
    "get_huangxiaocan_activation_source_by_mobile",
    "get_latest_class_user_restore_status",
    "get_latest_message_at_for_external_userids",
    "get_person_mobile",
    "get_questionnaire_signal",
    "get_signal_mobile_for_external_userid",
    "has_live_external_userid",
    "list_active_do_not_disturb_rows",
    "list_class_status_rows",
    "list_external_userids_by_person",
    "list_pool_batch_send_candidates",
    "list_questionnaire_submission_answers",
    "resolve_customer_identity_by_mobile",
]
