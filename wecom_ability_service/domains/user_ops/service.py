from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

import requests
from flask import current_app, has_request_context, session

from ...db import get_db, get_db_backend
from ...infra.helpers import stringify_db_timestamp as _stringify_db_timestamp
from ...infra.constants import (
    LEGACY_USER_OPS_POOL_STATUS_ORDER,
    USER_OPS_ACTIVATION_STATUS_DEFINITIONS,
    USER_OPS_ACTIVATION_STATUS_LABELS,
    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
    USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS,
    USER_OPS_HUANGXIAOCAN_ACTIVATION_SOURCE_STATES,
    USER_OPS_LEAD_POOL_ACTIVATION_STATE_DEFINITIONS,
    USER_OPS_LEAD_POOL_ACTIVATION_STATE_LABELS,
)
from ..class_user import service as class_user_domain_service
from ..identity import service as identity_domain_service
from ..routing_config.service import get_owner_class_term_backfill_entry_source_override
from ..tags import repo as tags_repo
from ..tags import service as tags_domain_service
from . import (
    user_ops_class_term_service,
    user_ops_deferred_job_service,
    user_ops_import_service,
    user_ops_pool_core_service,
    user_ops_sidebar_service,
    user_ops_tag_refresh_service,
)

owner_backfill_logger = logging.getLogger("owner_backfill")

# Default legacy fallbacks for direct domain callers. Application/shim layers may
# still override these symbols with stricter delegates during Wave 2 routing.
_normalize_mobile = identity_domain_service.normalize_mobile
resolve_person_identity = identity_domain_service.resolve_person_identity
get_contact_binding_status = identity_domain_service.get_contact_binding_status
_list_contact_tag_ids_for_user = tags_repo.list_contact_tag_ids_for_user
save_tag_snapshot = tags_repo.save_tag_snapshot
remove_tag_snapshot = tags_repo.remove_tag_snapshot
remove_tag_snapshots_for_other_users = tags_repo.remove_tag_snapshots_for_other_users
remove_all_tag_snapshots_for_other_users = tags_repo.remove_all_tag_snapshots_for_other_users
get_signup_status_definition_by_tag_name = tags_domain_service.get_signup_status_definition_by_tag_name
get_class_user_status_definition = class_user_domain_service.get_class_user_status_definition
get_class_user_status_current = class_user_domain_service.get_class_user_status_current
upsert_class_user_status_current = class_user_domain_service.upsert_class_user_status_current
append_class_user_status_history = class_user_domain_service.append_class_user_status_history
update_class_user_status_sync_result = class_user_domain_service.update_class_user_status_sync_result


class ThirdPartyUserSyncError(RuntimeError):
    pass


def _db_bool(value: Any) -> bool | int:
    return value if get_db_backend() == "postgres" else (1 if bool(value) else 0)


def get_user_ops_deferred_job_counts() -> dict[str, int]:
    return user_ops_deferred_job_service.get_user_ops_deferred_job_counts()


def _normalize_legacy_user_ops_current_status(signup_status: str) -> str:
    normalized = str(signup_status or "").strip()
    if normalized == "signed_3999":
        return "signed_3999"
    if normalized == "signed_999":
        return "signed_999"
    return "lead_trial"


def _legacy_user_ops_status_rank(current_status: str) -> int:
    return LEGACY_USER_OPS_POOL_STATUS_ORDER.get(str(current_status or "").strip(), 1)


def _user_ops_merge_key(row: dict[str, Any]) -> str:
    mobile = str(row.get("mobile") or "").strip()
    external_userid = str(row.get("external_userid") or "").strip()
    if mobile:
        return f"mobile:{mobile}"
    return f"external:{external_userid}"


def _user_ops_contact_client():
    from ...wecom_client import WeComClient

    return WeComClient.from_contact_app()


def _normalize_user_ops_strategy_tag_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_groups = (
        payload.get("strategy_tag_group")
        or payload.get("strategy_tag_list")
        or payload.get("strategy_tag")
        or payload.get("tag_group")
        or []
    )
    normalized_groups: list[dict[str, Any]] = []
    for group in raw_groups:
        group_name = str((group or {}).get("group_name") or (group or {}).get("name") or "").strip()
        group_id = str((group or {}).get("group_id") or (group or {}).get("id") or "").strip()
        strategy_id = str((group or {}).get("strategy_id") or "").strip()
        normalized_tags: list[dict[str, Any]] = []
        for tag in ((group or {}).get("tag") or (group or {}).get("tag_list") or (group or {}).get("tags") or []):
            tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not tag_id or not tag_name:
                continue
            normalized_tags.append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                }
            )
        if not group_name:
            continue
        normalized_groups.append(
            {
                "strategy_id": strategy_id,
                "group_id": group_id,
                "group_name": group_name,
                "tags": normalized_tags,
            }
        )
    return normalized_groups


def _ensure_class_term_tag_mapping_seed() -> None:
    db = get_db()
    active_value = _db_bool(True)
    existing_rows = db.execute(
        """
        SELECT id, strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active
        FROM class_term_tag_mapping
        WHERE tag_group_name = ?
        ORDER BY id ASC
        """,
        (USER_OPS_CLASS_TERM_TAG_GROUP_NAME,),
    ).fetchall()
    by_tag_id = {
        str(row.get("tag_id") or "").strip(): dict(row)
        for row in existing_rows
        if str(row.get("tag_id") or "").strip()
    }
    by_group_name = {
        (str(row.get("tag_group_name") or "").strip(), str(row.get("tag_name") or "").strip()): dict(row)
        for row in existing_rows
    }
    for item in USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS:
        normalized_tag_id = str(item.get("tag_id") or "").strip()
        normalized_group_name = str(item.get("tag_group_name") or "").strip()
        normalized_tag_name = str(item.get("tag_name") or "").strip()
        existing = None
        if normalized_tag_id:
            existing = by_tag_id.get(normalized_tag_id)
        if existing is None:
            existing = by_group_name.get((normalized_group_name, normalized_tag_name))
        if existing is None:
            db.execute(
                """
                INSERT INTO class_term_tag_mapping (
                    strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    str(item.get("strategy_id") or "").strip(),
                    str(item.get("group_id") or "").strip(),
                    normalized_tag_id,
                    normalized_group_name,
                    normalized_tag_name,
                    int(item["class_term_no"]),
                    item["class_term_label"],
                    active_value,
                ),
            )
            continue
        db.execute(
            """
            UPDATE class_term_tag_mapping
            SET strategy_id = ?,
                group_id = ?,
                tag_id = ?,
                tag_group_name = ?,
                tag_name = ?,
                class_term_no = ?,
                class_term_label = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                str(existing.get("strategy_id") or "").strip() or str(item.get("strategy_id") or "").strip(),
                str(existing.get("group_id") or "").strip() or str(item.get("group_id") or "").strip(),
                str(existing.get("tag_id") or "").strip() or normalized_tag_id,
                normalized_group_name or str(existing.get("tag_group_name") or "").strip(),
                normalized_tag_name or str(existing.get("tag_name") or "").strip(),
                int(item["class_term_no"]),
                item["class_term_label"],
                active_value,
                int(existing["id"]),
            ),
        )
    db.commit()


def ensure_class_term_tag_mapping_seed() -> None:
    user_ops_class_term_service.ensure_class_term_tag_mapping_seed(
        runtime=_user_ops_class_term_runtime()
    )


def sync_user_ops_class_term_tag_definitions() -> dict[str, Any]:
    return user_ops_class_term_service.sync_user_ops_class_term_tag_definitions(
        runtime=_user_ops_class_term_runtime()
    )


def _list_user_ops_crm_source_rows() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        WITH candidate_external_userids AS (
            SELECT external_userid
            FROM class_user_status_current
            WHERE COALESCE(external_userid, '') <> ''
            UNION
            SELECT external_userid
            FROM contacts
            WHERE COALESCE(external_userid, '') <> ''
            UNION
            SELECT external_userid
            FROM external_contact_bindings
            WHERE COALESCE(external_userid, '') <> ''
        )
        SELECT
            'crm' AS source_kind,
            candidate.external_userid,
            COALESCE(status.signup_status, '') AS signup_status,
            COALESCE(status.signup_label_name, '') AS signup_label_name,
            COALESCE(status.customer_name_snapshot, '') AS status_customer_name,
            COALESCE(status.owner_userid_snapshot, '') AS status_owner_userid,
            COALESCE(status.mobile_snapshot, '') AS status_mobile,
            COALESCE(status.updated_at, status.set_at) AS status_updated_at,
            COALESCE(c.customer_name, '') AS contact_customer_name,
            COALESCE(c.owner_userid, '') AS contact_owner_userid,
            c.updated_at AS contact_updated_at,
            bindings.person_id,
            COALESCE(bindings.updated_at, bindings.created_at) AS binding_updated_at,
            COALESCE(p.mobile, '') AS bound_mobile,
            COALESCE(p.updated_at, p.created_at) AS person_updated_at,
            '' AS lead_mobile,
            '' AS lead_source_type,
            NULL AS lead_updated_at
        FROM candidate_external_userids candidate
        LEFT JOIN class_user_status_current status
          ON status.external_userid = candidate.external_userid
        LEFT JOIN contacts c
          ON c.external_userid = candidate.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = candidate.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        ORDER BY candidate.external_userid ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _list_user_ops_experience_lead_rows() -> list[dict[str, Any]]:
    # W06/W09 note: class-term import currently reuses user_ops_experience_leads
    # as the phone anchor so phone-only rows can participate in pool reload.
    # The actual class-term values still land on the pool projection.
    rows = get_db().execute(
        """
        SELECT
            'experience_import' AS source_kind,
            COALESCE(bindings.external_userid, '') AS external_userid,
            COALESCE(status.signup_status, '') AS signup_status,
            COALESCE(status.signup_label_name, '') AS signup_label_name,
            COALESCE(status.customer_name_snapshot, '') AS status_customer_name,
            COALESCE(status.owner_userid_snapshot, '') AS status_owner_userid,
            COALESCE(status.mobile_snapshot, '') AS status_mobile,
            COALESCE(status.updated_at, status.set_at) AS status_updated_at,
            COALESCE(c.customer_name, '') AS contact_customer_name,
            COALESCE(c.owner_userid, '') AS contact_owner_userid,
            c.updated_at AS contact_updated_at,
            bindings.person_id,
            COALESCE(bindings.updated_at, bindings.created_at) AS binding_updated_at,
            COALESCE(p.mobile, '') AS bound_mobile,
            COALESCE(p.updated_at, p.created_at) AS person_updated_at,
            leads.mobile AS lead_mobile,
            COALESCE(leads.source_type, 'experience_import') AS lead_source_type,
            COALESCE(leads.updated_at, leads.created_at) AS lead_updated_at
        FROM user_ops_experience_leads leads
        LEFT JOIN people p
          ON p.mobile = leads.mobile
        LEFT JOIN external_contact_bindings bindings
          ON bindings.person_id = p.id
        LEFT JOIN contacts c
          ON c.external_userid = bindings.external_userid
        LEFT JOIN class_user_status_current status
          ON status.external_userid = bindings.external_userid
        WHERE leads.is_active = ?
        ORDER BY leads.mobile ASC, bindings.updated_at DESC, bindings.external_userid ASC
        """,
        (_db_bool(True),),
    ).fetchall()
    return [dict(row) for row in rows]


def _materialize_user_ops_crm_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    external_userid = str(row.get("external_userid") or "").strip()
    if not external_userid:
        return None
    bound_mobile = str(row.get("bound_mobile") or "").strip()
    status_mobile = str(row.get("status_mobile") or "").strip()
    mobile = bound_mobile or status_mobile
    customer_name = (
        str(row.get("status_customer_name") or "").strip()
        or str(row.get("contact_customer_name") or "").strip()
    )
    owner_userid = (
        str(row.get("status_owner_userid") or "").strip()
        or str(row.get("contact_owner_userid") or "").strip()
    )
    current_status = _normalize_legacy_user_ops_current_status(str(row.get("signup_status") or "").strip())
    is_wecom_bound = bool(external_userid and bound_mobile and row.get("person_id") is not None)
    updated_candidates = [
        _stringify_db_timestamp(row.get("status_updated_at")),
        _stringify_db_timestamp(row.get("contact_updated_at")),
        _stringify_db_timestamp(row.get("binding_updated_at")),
        _stringify_db_timestamp(row.get("person_updated_at")),
    ]
    updated_at = max([item for item in updated_candidates if item], default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {
        "mobile": mobile,
        "external_userid": external_userid,
        "customer_name": customer_name,
        "owner_userid": owner_userid,
        "current_status": current_status,
        "is_wecom_bound": is_wecom_bound,
        "activation_status": "not_activated",
        "activation_remark": "",
        "activation_source_present": False,
        "class_term_no": None,
        "class_term_label": "",
        "source_type": "crm_bound",
        "updated_at": updated_at,
    }


def _materialize_user_ops_experience_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    mobile = str(row.get("lead_mobile") or "").strip()
    if not mobile:
        return None
    external_userid = str(row.get("external_userid") or "").strip()
    bound_mobile = str(row.get("bound_mobile") or "").strip()
    customer_name = (
        str(row.get("status_customer_name") or "").strip()
        or str(row.get("contact_customer_name") or "").strip()
    )
    owner_userid = (
        str(row.get("status_owner_userid") or "").strip()
        or str(row.get("contact_owner_userid") or "").strip()
    )
    current_status = _normalize_legacy_user_ops_current_status(str(row.get("signup_status") or "").strip())
    is_wecom_bound = bool(external_userid and bound_mobile and row.get("person_id") is not None and bound_mobile == mobile)
    updated_candidates = [
        _stringify_db_timestamp(row.get("lead_updated_at")),
        _stringify_db_timestamp(row.get("status_updated_at")),
        _stringify_db_timestamp(row.get("contact_updated_at")),
        _stringify_db_timestamp(row.get("binding_updated_at")),
        _stringify_db_timestamp(row.get("person_updated_at")),
    ]
    updated_at = max([item for item in updated_candidates if item], default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {
        "mobile": mobile,
        "external_userid": external_userid,
        "customer_name": customer_name,
        "owner_userid": owner_userid,
        "current_status": current_status,
        "is_wecom_bound": is_wecom_bound,
        "activation_status": "not_activated",
        "activation_remark": "",
        "activation_source_present": False,
        "class_term_no": None,
        "class_term_label": "",
        "source_type": str(row.get("lead_source_type") or "").strip() or "experience_import",
        "updated_at": updated_at,
    }


def _materialize_user_ops_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    if str(row.get("source_kind") or "").strip() == "experience_import":
        return _materialize_user_ops_experience_candidate(row)
    return _materialize_user_ops_crm_candidate(row)


def _merge_user_ops_candidate(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    if _legacy_user_ops_status_rank(candidate["current_status"]) >= _legacy_user_ops_status_rank(existing["current_status"]):
        merged["current_status"] = candidate["current_status"]
    if candidate.get("is_wecom_bound"):
        merged["is_wecom_bound"] = True
    for key in ["mobile", "external_userid", "customer_name", "owner_userid"]:
        if not merged.get(key) and candidate.get(key):
            merged[key] = candidate[key]
    if str(candidate.get("source_type") or "").strip() == "experience_import":
        merged["source_type"] = "experience_import"
    if candidate.get("updated_at", "") > merged.get("updated_at", ""):
        merged["updated_at"] = candidate["updated_at"]
    return merged


def _list_user_ops_activation_source_rows() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT
            mobile,
            activation_status,
            activation_remark,
            import_batch_id,
            created_by,
            COALESCE(updated_at, created_at) AS source_updated_at
        FROM user_ops_activation_status_source
        WHERE is_active = ?
        ORDER BY mobile ASC
        """,
        (_db_bool(True),),
    ).fetchall()
    return [dict(row) for row in rows]


def _apply_user_ops_activation_sources(next_map: dict[str, dict[str, Any]]) -> None:
    # Activation import remains a separate phone-keyed source and never writes
    # external_userid directly.
    for row in _list_user_ops_activation_source_rows():
        mobile = str(row.get("mobile") or "").strip()
        if not mobile:
            continue
        merge_key = f"mobile:{mobile}"
        candidate = next_map.get(merge_key)
        if candidate is None:
            candidate = {
                "mobile": mobile,
                "external_userid": "",
                "customer_name": "",
                "owner_userid": "",
                "current_status": "lead_trial",
                "is_wecom_bound": False,
                "activation_status": "not_activated",
                "activation_remark": "",
                "activation_source_present": False,
                "class_term_no": None,
                "class_term_label": "",
                "source_type": "activation_import",
                "updated_at": _stringify_db_timestamp(row.get("source_updated_at")) or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        candidate["activation_status"] = str(row.get("activation_status") or "").strip() or "not_activated"
        candidate["activation_remark"] = str(row.get("activation_remark") or "").strip()
        candidate["activation_source_present"] = True
        candidate["updated_at"] = max(
            candidate.get("updated_at", ""),
            _stringify_db_timestamp(row.get("source_updated_at")) or candidate.get("updated_at", ""),
        )
        next_map[merge_key] = candidate


def _overlay_user_ops_previous_projection(candidate: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return candidate
    merged = dict(candidate)
    previous_activation_status = str(previous.get("activation_status") or "").strip()
    previous_activation_remark = str(previous.get("activation_remark") or "").strip()
    previous_class_term_no = previous.get("class_term_no")
    previous_class_term_label = str(previous.get("class_term_label") or "").strip()
    if previous_activation_status and not merged.get("activation_source_present"):
        merged["activation_status"] = previous_activation_status
    if previous_activation_remark and not merged.get("activation_source_present"):
        merged["activation_remark"] = previous_activation_remark
    if previous_class_term_no not in (None, ""):
        merged["class_term_no"] = int(previous_class_term_no)
    if previous_class_term_label:
        merged["class_term_label"] = previous_class_term_label
    if str(previous.get("source_type") or "").strip() == "experience_import":
        merged["source_type"] = "experience_import"
    return merged


def _serialize_user_ops_current_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "mobile": str(row.get("mobile") or "").strip(),
        "external_userid": str(row.get("external_userid") or "").strip(),
        "customer_name": str(row.get("customer_name") or "").strip(),
        "owner_userid": str(row.get("owner_userid") or "").strip(),
        "current_status": str(row.get("current_status") or "").strip() or "lead_trial",
        "is_wecom_bound": bool(row.get("is_wecom_bound")),
        "activation_status": str(row.get("activation_status") or "").strip() or "not_activated",
        "activation_remark": str(row.get("activation_remark") or "").strip(),
        "activation_source_present": bool(row.get("activation_source_present")),
        "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
        "class_term_label": str(row.get("class_term_label") or "").strip(),
        "source_type": str(row.get("source_type") or "").strip() or "manual",
    }


def _load_existing_user_ops_pool_map() -> dict[str, dict[str, Any]]:
    rows = get_db().execute(
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
        """
    ).fetchall()
    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _serialize_user_ops_current_row(dict(row))
        item["id"] = row.get("id")
        item["created_at"] = _stringify_db_timestamp(row.get("created_at"))
        item["updated_at"] = _stringify_db_timestamp(row.get("updated_at"))
        payload[_user_ops_merge_key(item)] = item
    return payload


def reload_user_ops_pool() -> dict[str, Any]:
    # Legacy maintenance helper only. Admin V2 no longer reads or depends on
    # `user_ops_pool_current`; keep this helper only as rollback/migration
    # support while old tables remain in the schema.
    # Rebuild the phone-centric projection from CRM-bound rows, mobile-anchor
    # rows, and activation source rows. external_userid / is_wecom_bound always
    # come from existing binding relations; class term and activation are
    # overlaid back onto user_ops_pool_current as projection fields.
    _ensure_class_term_tag_mapping_seed()
    previous_map = _load_existing_user_ops_pool_map()
    candidates = _list_user_ops_crm_source_rows() + _list_user_ops_experience_lead_rows()
    next_map: dict[str, dict[str, Any]] = {}
    for source_row in candidates:
        candidate = _materialize_user_ops_candidate(source_row)
        if candidate is None:
            continue
        merge_key = _user_ops_merge_key(candidate)
        if merge_key in next_map:
            next_map[merge_key] = _merge_user_ops_candidate(next_map[merge_key], candidate)
        else:
            next_map[merge_key] = candidate
    _apply_user_ops_activation_sources(next_map)

    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("DELETE FROM user_ops_pool_current")

    inserted_count = 0
    changed_count = 0
    removed_count = 0
    history_written = 0

    for merge_key, item in next_map.items():
        previous = previous_map.get(merge_key)
        item = _overlay_user_ops_previous_projection(item, previous)
        created_at = str((previous or {}).get("created_at") or now).strip()
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
                activation_status, activation_remark, class_term_no, class_term_label, source_type,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["mobile"],
                item["external_userid"],
                item["customer_name"],
                item["owner_userid"],
                item["current_status"],
                _db_bool(bool(item["is_wecom_bound"])),
                item["activation_status"],
                item["activation_remark"],
                item["class_term_no"],
                item["class_term_label"],
                item["source_type"],
                created_at,
                now,
            ),
        )
        inserted_count += 1

        previous_payload = _serialize_user_ops_current_row(previous or {})
        next_payload = _serialize_user_ops_current_row(item)
        if previous is None or previous_payload != next_payload:
            changed_count += 1
            db.execute(
                """
                INSERT INTO user_ops_pool_history (
                    pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None,
                    item["mobile"],
                    item["external_userid"],
                    "pool_reload_upsert",
                    json.dumps(previous_payload, ensure_ascii=False),
                    json.dumps(next_payload, ensure_ascii=False),
                    "system_reload",
                    item["source_type"],
                    now,
                ),
            )
            history_written += 1

    for merge_key, previous in previous_map.items():
        if merge_key in next_map:
            continue
        removed_count += 1
        db.execute(
            """
            INSERT INTO user_ops_pool_history (
                pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                previous.get("id"),
                previous.get("mobile", ""),
                previous.get("external_userid", ""),
                "pool_reload_remove",
                json.dumps(_serialize_user_ops_current_row(previous), ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                "system_reload",
                str(previous.get("source_type") or "").strip() or "manual",
                now,
            ),
        )
        history_written += 1

    db.commit()
    return {
        "ok": True,
        "total": len(next_map),
        "inserted_count": inserted_count,
        "changed_count": changed_count,
        "removed_count": removed_count,
        "history_written": history_written,
        "reloaded_at": now,
    }


def _user_ops_class_term_options() -> list[dict[str, Any]]:
    return user_ops_class_term_service.list_user_ops_class_term_options(
        runtime=_user_ops_class_term_runtime()
    )


def _list_active_class_term_mappings() -> list[dict[str, Any]]:
    return user_ops_class_term_service.list_active_class_term_mappings(
        runtime=_user_ops_class_term_runtime()
    )


def _get_active_class_term_mapping_by_no(class_term_no: int | None) -> dict[str, Any] | None:
    return user_ops_class_term_service.get_active_class_term_mapping_by_no(
        class_term_no,
        runtime=_user_ops_class_term_runtime(),
    )


def _confirmed_class_term_mappings_by_no() -> dict[int, dict[str, Any]]:
    return {
        int(item["class_term_no"]): {
            "strategy_id": str(item.get("strategy_id") or "").strip(),
            "group_id": str(item.get("group_id") or "").strip(),
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_group_name": str(item.get("tag_group_name") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
            "class_term_no": int(item["class_term_no"]),
            "class_term_label": str(item.get("class_term_label") or "").strip(),
        }
        for item in USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS
    }


def _infer_user_ops_class_term_no_from_tag_name(tag_name: str) -> int | None:
    normalized_tag_name = str(tag_name or "").strip()
    if not normalized_tag_name:
        return None
    if "首期" in normalized_tag_name:
        return 1
    matched = re.search(r"第\s*(\d+)\s*期", normalized_tag_name)
    if matched:
        return int(matched.group(1))
    matched = re.fullmatch(r"(\d+)\s*期", normalized_tag_name)
    if matched:
        return int(matched.group(1))
    return None


def _list_live_user_ops_class_term_tags(tag_payload: dict[str, Any]) -> list[dict[str, Any]]:
    groups = _normalize_user_ops_strategy_tag_groups(tag_payload)
    items: list[dict[str, Any]] = []
    seen_tag_ids: set[str] = set()
    for group in groups:
        if str(group.get("group_name") or "").strip() != USER_OPS_CLASS_TERM_TAG_GROUP_NAME:
            continue
        for tag in group.get("tags") or []:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            if not tag_id or tag_id in seen_tag_ids:
                continue
            seen_tag_ids.add(tag_id)
            inferred_no = _infer_user_ops_class_term_no_from_tag_name(tag_name)
            items.append(
                {
                    "strategy_id": str(group.get("strategy_id") or "").strip(),
                    "group_id": str(group.get("group_id") or "").strip(),
                    "tag_group_name": USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "class_term_no": inferred_no,
                    "class_term_label": f"{inferred_no}期" if inferred_no is not None else "",
                }
            )
    return items


def _resolve_owner_backfill_class_term_mappings(
    *,
    class_term_min: int,
    class_term_max: int,
    tag_payload: dict[str, Any],
) -> dict[str, Any]:
    return user_ops_class_term_service._resolve_owner_backfill_class_term_mappings(  # type: ignore[attr-defined]
        class_term_min=class_term_min,
        class_term_max=class_term_max,
        tag_payload=tag_payload,
    )


def _list_owner_backfill_candidate_external_userids(owner_userid: str) -> list[dict[str, Any]]:
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    rows = get_db().execute(
        """
        WITH candidates AS (
            SELECT external_userid, 1 AS from_follow_relation, 0 AS from_contact_owner
            FROM wecom_external_contact_follow_users
            WHERE user_id = ?
              AND relation_status = 'active'
              AND COALESCE(external_userid, '') <> ''
            UNION ALL
            SELECT external_userid, 0 AS from_follow_relation, 1 AS from_contact_owner
            FROM contacts
            WHERE owner_userid = ?
              AND COALESCE(external_userid, '') <> ''
        )
        SELECT
            external_userid,
            MAX(from_follow_relation) AS from_follow_relation,
            MAX(from_contact_owner) AS from_contact_owner
        FROM candidates
        GROUP BY external_userid
        ORDER BY external_userid ASC
        """,
        (normalized_owner_userid, normalized_owner_userid),
    ).fetchall()
    return [
        {
            "external_userid": str(row.get("external_userid") or "").strip(),
            "from_follow_relation": bool(row.get("from_follow_relation")),
            "from_contact_owner": bool(row.get("from_contact_owner")),
        }
        for row in rows
        if str(row.get("external_userid") or "").strip()
    ]


def _get_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
) -> dict[str, Any]:
    return user_ops_class_term_service._get_owner_scoped_live_contact_tags(  # type: ignore[attr-defined]
        external_userid=external_userid,
        owner_userid=owner_userid,
        runtime=_user_ops_class_term_runtime(),
    )


def _persist_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
    tags: list[dict[str, str]],
) -> None:
    user_ops_class_term_service._persist_owner_scoped_live_contact_tags(  # type: ignore[attr-defined]
        external_userid=external_userid,
        owner_userid=owner_userid,
        tags=tags,
        runtime=_user_ops_class_term_runtime(),
    )


def _plan_user_ops_lead_pool_member_upsert(
    *,
    mobile: str = "",
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    is_wecom_added: bool | None = None,
    is_mobile_bound: bool | None = None,
    huangxiaocan_activation_state: str = "unknown",
    class_term_no: int | None = None,
    class_term_label: str = "",
    entry_source: str = "",
) -> dict[str, Any]:
    return user_ops_pool_core_service.plan_user_ops_lead_pool_member_upsert(
        mobile=mobile,
        external_userid=external_userid,
        customer_name=customer_name,
        owner_userid=owner_userid,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        class_term_label=class_term_label,
        entry_source=entry_source,
        runtime=_user_ops_pool_core_runtime(),
    )


def _default_owner_class_term_backfill_entry_source(owner_userid: str) -> str:
    return user_ops_class_term_service._default_owner_class_term_backfill_entry_source(  # type: ignore[attr-defined]
        owner_userid,
        runtime=_user_ops_class_term_runtime(),
    )


def _is_owner_backfill_invalid_test_candidate(external_userid: str) -> bool:
    return user_ops_class_term_service._is_owner_backfill_invalid_test_candidate(  # type: ignore[attr-defined]
        external_userid
    )


def backfill_owner_class_terms_into_lead_pool(
    *,
    owner_userid: str,
    class_term_min: int = 1,
    class_term_max: int = 5,
    dry_run: bool = True,
    operator: str = "",
    entry_source: str = "",
    sample_limit: int = 20,
    offset: int = 0,
    max_candidates: int | None = None,
) -> dict[str, Any]:
    return user_ops_class_term_service.backfill_owner_class_terms_into_lead_pool(
        owner_userid=owner_userid,
        class_term_min=class_term_min,
        class_term_max=class_term_max,
        dry_run=dry_run,
        operator=operator,
        entry_source=entry_source,
        sample_limit=sample_limit,
        offset=offset,
        max_candidates=max_candidates,
        runtime=_user_ops_class_term_runtime(),
    )


def _list_user_ops_pool_external_userids_for_owner(owner_userid: str) -> list[str]:
    return user_ops_tag_refresh_service.list_user_ops_pool_external_userids_for_owner(owner_userid)


def refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
) -> dict[str, Any]:
    return user_ops_tag_refresh_service.refresh_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
        scoped_tag_ids=scoped_tag_ids,
        runtime=_user_ops_tag_refresh_runtime(),
    )


def refresh_user_ops_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
) -> dict[str, Any]:
    return user_ops_tag_refresh_service.refresh_user_ops_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
        runtime=_user_ops_tag_refresh_runtime(),
    )


def refresh_user_ops_contact_tags_for_owner(owner_userid: str) -> dict[str, Any]:
    return user_ops_tag_refresh_service.refresh_user_ops_contact_tags_for_owner(
        owner_userid,
        runtime=_user_ops_tag_refresh_runtime(),
    )


def _list_other_ownerids_with_scoped_tag_snapshots(
    *,
    external_userid: str,
    owner_userid: str,
    scoped_tag_ids: list[str],
) -> list[str]:
    return user_ops_tag_refresh_service.list_other_ownerids_with_scoped_tag_snapshots(
        external_userid=external_userid,
        owner_userid=owner_userid,
        scoped_tag_ids=scoped_tag_ids,
    )


def _sync_sidebar_lead_pool_class_term_tag(
    *,
    external_userid: str,
    owner_userid: str,
    class_term_no: int,
) -> dict[str, Any]:
    return user_ops_sidebar_service._sync_sidebar_lead_pool_class_term_tag(  # type: ignore[attr-defined]
        external_userid=external_userid,
        owner_userid=owner_userid,
        class_term_no=class_term_no,
        runtime=_user_ops_sidebar_runtime(),
    )


def _build_user_ops_backfill_preview(owner_userid: str) -> list[dict[str, Any]]:
    return user_ops_class_term_service.build_user_ops_backfill_preview(
        owner_userid,
        runtime=_user_ops_class_term_runtime(),
    )


def _build_backfill_class_term_summary(
    *,
    owner_userid: str,
    dry_run: bool,
    tag_definition_sync: dict[str, Any],
    tag_refresh: dict[str, Any],
    preview_items: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    return user_ops_class_term_service._build_backfill_class_term_summary(  # type: ignore[attr-defined]
        owner_userid=owner_userid,
        dry_run=dry_run,
        tag_definition_sync=tag_definition_sync,
        tag_refresh=tag_refresh,
        preview_items=preview_items,
        mappings=mappings,
    )


def _log_backfill_class_term_conflict(db, item: dict[str, Any], *, actor: str, now: str) -> None:
    user_ops_class_term_service._log_backfill_class_term_conflict(  # type: ignore[attr-defined]
        db,
        item,
        actor=actor,
        now=now,
    )


def _apply_backfill_class_term_update(
    db,
    item: dict[str, Any],
    *,
    matched: dict[str, Any],
    actor: str,
    now: str,
) -> None:
    user_ops_class_term_service._apply_backfill_class_term_update(  # type: ignore[attr-defined]
        db,
        item,
        matched=matched,
        actor=actor,
        now=now,
    )


def backfill_class_term_for_owner(
    *,
    owner_userid: str,
    dry_run: bool = True,
    operator: str = "",
) -> dict[str, Any]:
    return user_ops_class_term_service.backfill_class_term_for_owner(
        owner_userid=owner_userid,
        dry_run=dry_run,
        operator=operator,
        runtime=_user_ops_class_term_runtime(),
    )


def _user_ops_class_term_runtime() -> user_ops_class_term_service.ClassTermRuntime:
    return user_ops_class_term_service.ClassTermRuntime(
        db_bool=_db_bool,
        current_operator_resolver=_current_user_ops_operator,
        contact_client_loader=_user_ops_contact_client,
        list_contact_tag_ids_for_user=_list_contact_tag_ids_for_user,
        save_tag_snapshot=save_tag_snapshot,
        remove_tag_snapshot=remove_tag_snapshot,
        get_owner_class_term_backfill_entry_source_override=get_owner_class_term_backfill_entry_source_override,
        resolve_person_identity=resolve_person_identity,
        plan_lead_pool_member_upsert=_plan_user_ops_lead_pool_member_upsert,
        upsert_user_ops_lead_pool_member=upsert_user_ops_lead_pool_member,
        refresh_user_ops_contact_tags_for_owner=refresh_user_ops_contact_tags_for_owner,
    )


def _user_ops_tag_refresh_runtime() -> user_ops_tag_refresh_service.TagRefreshRuntime:
    class_term_runtime = _user_ops_class_term_runtime()
    return user_ops_tag_refresh_service.TagRefreshRuntime(
        contact_client_loader=_user_ops_contact_client,
        list_active_class_term_mappings=lambda: user_ops_class_term_service.list_active_class_term_mappings(
            runtime=class_term_runtime,
        ),
        list_contact_tag_ids_for_user=_list_contact_tag_ids_for_user,
        save_tag_snapshot=save_tag_snapshot,
        remove_tag_snapshot=remove_tag_snapshot,
        remove_all_tag_snapshots_for_other_users=remove_all_tag_snapshots_for_other_users,
    )


def _user_ops_pool_core_runtime() -> user_ops_pool_core_service.PoolCoreRuntime:
    return user_ops_pool_core_service.PoolCoreRuntime(
        db_bool=_db_bool,
        normalize_mobile=_normalize_mobile,
        stringify_db_timestamp=_stringify_db_timestamp,
        current_operator_resolver=_current_user_ops_operator,
    )


def _user_ops_sidebar_runtime() -> user_ops_sidebar_service.SidebarRuntime:
    return user_ops_sidebar_service.SidebarRuntime(
        current_operator_resolver=_current_user_ops_operator,
        normalize_mobile=_normalize_mobile,
        get_contact_binding_status=get_contact_binding_status,
        list_user_ops_lead_pool_matches=_list_user_ops_lead_pool_matches,
        serialize_user_ops_lead_pool_current_row=_serialize_user_ops_lead_pool_current_row,
        upsert_user_ops_lead_pool_member=upsert_user_ops_lead_pool_member,
        write_user_ops_lead_pool_history=write_user_ops_lead_pool_history,
        list_other_ownerids_with_scoped_tag_snapshots=lambda external_userid, owner_userid, scoped_tag_ids: user_ops_tag_refresh_service.list_other_ownerids_with_scoped_tag_snapshots(
            external_userid=external_userid,
            owner_userid=owner_userid,
            scoped_tag_ids=scoped_tag_ids,
        ),
        save_tag_snapshot=save_tag_snapshot,
        remove_tag_snapshot=remove_tag_snapshot,
        remove_tag_snapshots_for_other_users=remove_tag_snapshots_for_other_users,
        class_term_runtime=_user_ops_class_term_runtime(),
    )


def _user_ops_deferred_job_runtime() -> user_ops_deferred_job_service.DeferredJobRuntime:
    class_term_runtime = _user_ops_class_term_runtime()
    return user_ops_deferred_job_service.DeferredJobRuntime(
        current_operator_resolver=_current_user_ops_operator,
        stringify_db_timestamp=_stringify_db_timestamp,
        build_user_ops_backfill_preview=lambda owner_userid: user_ops_class_term_service.build_user_ops_backfill_preview(
            owner_userid,
            runtime=class_term_runtime,
        ),
        list_class_term_matches_for_external_contact=lambda external_userid, owner_userid="": user_ops_class_term_service.list_class_term_matches_for_external_contact(
            external_userid,
            owner_userid,
            runtime=class_term_runtime,
        ),
        sync_user_ops_class_term_tag_definitions=lambda: user_ops_class_term_service.sync_user_ops_class_term_tag_definitions(
            runtime=class_term_runtime,
        ),
        refresh_user_ops_contact_tags_for_external_userid=refresh_user_ops_contact_tags_for_external_userid,
        resolve_person_identity=resolve_person_identity,
        upsert_user_ops_lead_pool_member=upsert_user_ops_lead_pool_member,
    )


def _user_ops_import_runtime() -> user_ops_import_service.ImportRuntime:
    return user_ops_import_service.ImportRuntime(
        db_bool=_db_bool,
        normalize_mobile=_normalize_mobile,
        current_operator_resolver=_current_user_ops_operator,
        normalize_lead_pool_activation_state=_normalize_user_ops_lead_pool_activation_state,
        apply_activation_source_to_existing_member=apply_user_ops_huangxiaocan_activation_source_to_existing_member,
        upsert_user_ops_lead_pool_member=upsert_user_ops_lead_pool_member,
    )


def schedule_user_ops_auto_assign_class_term_job(
    *,
    external_userid: str,
    owner_userid: str,
    delay_seconds: int = 10,
    operator: str = "",
) -> dict[str, Any]:
    return user_ops_deferred_job_service.schedule_user_ops_auto_assign_class_term_job(
        external_userid=external_userid,
        owner_userid=owner_userid,
        delay_seconds=delay_seconds,
        operator=operator,
        runtime=_user_ops_deferred_job_runtime(),
    )


def _list_class_term_matches_for_external_contact(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    return user_ops_class_term_service.list_class_term_matches_for_external_contact(
        external_userid,
        owner_userid,
        runtime=_user_ops_class_term_runtime(),
    )


def run_due_user_ops_deferred_jobs(limit: int = 20) -> dict[str, Any]:
    return user_ops_deferred_job_service.run_due_user_ops_deferred_jobs(
        limit=limit,
        runtime=_user_ops_deferred_job_runtime(),
    )


def _user_ops_owner_options() -> list[dict[str, str]]:
    rows = get_db().execute(
        """
        SELECT DISTINCT
            current.owner_userid,
            COALESCE(owner_map.display_name, '') AS display_name
        FROM user_ops_lead_pool_current current
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = current.owner_userid
        WHERE current.owner_userid <> ''
        ORDER BY current.owner_userid ASC
        """
    ).fetchall()
    return [
        {
            "owner_userid": str(row.get("owner_userid") or "").strip(),
            "label": str(row.get("display_name") or "").strip() or str(row.get("owner_userid") or "").strip(),
        }
        for row in rows
    ]


def list_user_ops_pool(
    *,
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    _ensure_class_term_tag_mapping_seed()
    normalized_is_wecom_added = str(is_wecom_added or "").strip().lower()
    normalized_is_mobile_bound = str(is_mobile_bound or "").strip().lower()
    normalized_activation_state = str(huangxiaocan_activation_state or "").strip()
    normalized_class_term_no = str(class_term_no or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    normalized_query = str(query or "").strip()

    sql = """
        SELECT
            current.id,
            current.mobile,
            current.external_userid,
            current.customer_name,
            current.owner_userid,
            current.is_wecom_added,
            current.is_mobile_bound,
            current.huangxiaocan_activation_state,
            current.class_term_no,
            current.class_term_label,
            current.first_entry_source,
            current.last_entry_source,
            current.created_at,
            current.updated_at,
            COALESCE(owner_map.display_name, '') AS owner_display_name
        FROM user_ops_lead_pool_current current
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = current.owner_userid
        WHERE 1 = 1
    """
    params: list[Any] = []
    if normalized_is_wecom_added in {"1", "true", "yes"}:
        sql += " AND current.is_wecom_added = ?"
        params.append(_db_bool(True))
    elif normalized_is_wecom_added in {"0", "false", "no"}:
        sql += " AND current.is_wecom_added = ?"
        params.append(_db_bool(False))
    if normalized_is_mobile_bound in {"1", "true", "yes"}:
        sql += " AND current.is_mobile_bound = ?"
        params.append(_db_bool(True))
    elif normalized_is_mobile_bound in {"0", "false", "no"}:
        sql += " AND current.is_mobile_bound = ?"
        params.append(_db_bool(False))
    if normalized_activation_state:
        sql += " AND current.huangxiaocan_activation_state = ?"
        params.append(normalized_activation_state)
    if normalized_class_term_no:
        sql += " AND CAST(COALESCE(current.class_term_no, 0) AS TEXT) = ?"
        params.append(normalized_class_term_no)
    if normalized_owner_userid:
        sql += " AND current.owner_userid = ?"
        params.append(normalized_owner_userid)
    if normalized_query:
        sql += " AND (current.mobile LIKE ? OR current.external_userid LIKE ? OR current.customer_name LIKE ?)"
        like_value = f"%{normalized_query}%"
        params.extend([like_value, like_value, like_value])
    sql += " ORDER BY current.updated_at DESC, current.id DESC"

    rows = get_db().execute(sql, tuple(params)).fetchall()
    items = [
        {
            "id": int(row["id"]),
            "mobile": str(row.get("mobile") or "").strip(),
            "external_userid": str(row.get("external_userid") or "").strip(),
            "customer_name": str(row.get("customer_name") or "").strip(),
            "owner_userid": str(row.get("owner_userid") or "").strip(),
            "owner_display_name": str(row.get("owner_display_name") or "").strip() or str(row.get("owner_userid") or "").strip(),
            "is_wecom_added": bool(row.get("is_wecom_added")),
            "is_mobile_bound": bool(row.get("is_mobile_bound")),
            "huangxiaocan_activation_state": str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown",
            "huangxiaocan_activation_state_label": USER_OPS_LEAD_POOL_ACTIVATION_STATE_LABELS.get(
                str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown",
                str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown",
            ),
            "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
            "class_term_label": str(row.get("class_term_label") or "").strip(),
            "first_entry_source": str(row.get("first_entry_source") or "").strip(),
            "last_entry_source": str(row.get("last_entry_source") or "").strip(),
            "created_at": _stringify_db_timestamp(row.get("created_at")),
            "updated_at": _stringify_db_timestamp(row.get("updated_at")),
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "filters": {
            "is_wecom_added": normalized_is_wecom_added,
            "is_mobile_bound": normalized_is_mobile_bound,
            "huangxiaocan_activation_state": normalized_activation_state,
            "class_term_no": normalized_class_term_no,
            "owner_userid": normalized_owner_userid,
            "query": normalized_query,
        },
        "filter_options": {
            "activation_states": list(USER_OPS_LEAD_POOL_ACTIVATION_STATE_DEFINITIONS),
            "class_terms": _user_ops_class_term_options(),
            "owners": _user_ops_owner_options(),
        },
        "meta": {
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def get_user_ops_overview() -> dict[str, Any]:
    rows = get_db().execute(
        """
        SELECT
            mobile,
            external_userid,
            is_wecom_added,
            is_mobile_bound,
            huangxiaocan_activation_state,
            class_term_no,
            class_term_label
        FROM user_ops_lead_pool_current
        """
    ).fetchall()
    total = len(rows)
    wecom_added_count = 0
    mobile_bound_count = 0
    activated_count = 0
    not_activated_count = 0
    unknown_count = 0
    for row in rows:
        if bool(row.get("is_wecom_added")):
            wecom_added_count += 1
        if bool(row.get("is_mobile_bound")):
            mobile_bound_count += 1
        activation_state = str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown"
        if activation_state == "activated":
            activated_count += 1
        elif activation_state == "not_activated":
            not_activated_count += 1
        else:
            unknown_count += 1
    return {
        "lead_pool_total_count": total,
        "wecom_added_count": wecom_added_count,
        "wecom_not_added_count": total - wecom_added_count,
        "mobile_bound_count": mobile_bound_count,
        "mobile_unbound_count": total - mobile_bound_count,
        "huangxiaocan_activated_count": activated_count,
        "huangxiaocan_not_activated_count": not_activated_count,
        "huangxiaocan_unknown_count": unknown_count,
        "cards": [
            {"key": "lead_pool_total_count", "label": "引流品总数", "value": total},
            {"key": "wecom_added_count", "label": "已加微", "value": wecom_added_count},
            {"key": "wecom_not_added_count", "label": "未加微", "value": total - wecom_added_count},
            {"key": "mobile_bound_count", "label": "已绑手机号", "value": mobile_bound_count},
            {"key": "mobile_unbound_count", "label": "未绑手机号", "value": total - mobile_bound_count},
            {"key": "huangxiaocan_activated_count", "label": "黄小璨已激活", "value": activated_count},
            {"key": "huangxiaocan_not_activated_count", "label": "黄小璨未激活", "value": not_activated_count},
            {"key": "huangxiaocan_unknown_count", "label": "激活待录入", "value": unknown_count},
        ],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def list_user_ops_history(limit: int = 100) -> dict[str, Any]:
    return user_ops_pool_core_service.list_user_ops_history(
        limit=limit,
        runtime=_user_ops_pool_core_runtime(),
    )


def export_user_ops_pool(
    *,
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    result = list_user_ops_pool(
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        owner_userid=owner_userid,
        query=query,
    )
    headers = ["手机号", "是否已加微", "是否已绑手机号", "班期", "黄小璨激活状态", "客户昵称", "external_userid", "跟进人", "首次入表来源", "最后入表来源", "更新时间"]
    rows = [
        [
            item.get("mobile", ""),
            "已加微" if item.get("is_wecom_added") else "未加微",
            "已绑定" if item.get("is_mobile_bound") else "未绑定",
            item.get("class_term_label", "") or (f"{item['class_term_no']}期" if item.get("class_term_no") else ""),
            item.get("huangxiaocan_activation_state_label", ""),
            item.get("customer_name", ""),
            item.get("external_userid", ""),
            item.get("owner_display_name", ""),
            item.get("first_entry_source", ""),
            item.get("last_entry_source", ""),
            item.get("updated_at", ""),
        ]
        for item in result["items"]
    ]
    return {
        "headers": headers,
        "rows": rows,
        "filename": f"user-ops-pool-{datetime.now().strftime('%Y%m%d%H%M%S')}.xls",
    }


def migrate_class_user_status_from_contact_tags() -> dict[str, Any]:
    from ...application.class_user.commands import MigrateClassUserStatusFromContactTagsCommand

    return MigrateClassUserStatusFromContactTagsCommand()()


def apply_class_user_status_change(
    *,
    external_userid: str,
    signup_status: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> dict[str, Any]:
    from ...application.class_user.commands import ApplyClassUserStatusChangeCommand
    from ...application.class_user.dto import ApplyClassUserStatusChangeCommandDTO

    return ApplyClassUserStatusChangeCommand()(
        ApplyClassUserStatusChangeCommandDTO(
            external_userid=str(external_userid or "").strip(),
            signup_status=str(signup_status or "").strip(),
            set_by_userid=str(set_by_userid or "").strip(),
            customer_name_snapshot=str(customer_name_snapshot or "").strip(),
            owner_userid_snapshot=str(owner_userid_snapshot or "").strip(),
            mobile_snapshot=str(mobile_snapshot or "").strip(),
        )
    )

def _normalize_user_ops_lead_pool_activation_state(value: str, *, allow_unknown: bool = True) -> str:
    return user_ops_pool_core_service.normalize_user_ops_lead_pool_activation_state(
        value,
        allow_unknown=allow_unknown,
    )


def _serialize_user_ops_lead_pool_current_row(row: dict[str, Any]) -> dict[str, Any]:
    return user_ops_pool_core_service.serialize_user_ops_lead_pool_current_row(row)


def _get_user_ops_lead_pool_current_row_by_id(row_id: int) -> dict[str, Any] | None:
    return user_ops_pool_core_service.get_user_ops_lead_pool_current_row_by_id(
        row_id,
        runtime=_user_ops_pool_core_runtime(),
    )


def _list_user_ops_lead_pool_matches(*, mobile: str, external_userid: str) -> list[dict[str, Any]]:
    return user_ops_pool_core_service.list_user_ops_lead_pool_matches(
        mobile=mobile,
        external_userid=external_userid,
        runtime=_user_ops_pool_core_runtime(),
    )


def write_user_ops_lead_pool_history(
    *,
    mobile: str = "",
    external_userid: str = "",
    action_type: str,
    source_type: str,
    operator: str = "",
    before_payload: dict[str, Any] | None = None,
    after_payload: dict[str, Any] | None = None,
    remark: str = "",
) -> None:
    return user_ops_pool_core_service.write_user_ops_lead_pool_history(
        mobile=mobile,
        external_userid=external_userid,
        action_type=action_type,
        source_type=source_type,
        operator=operator,
        before_payload=before_payload,
        after_payload=after_payload,
        remark=remark,
        runtime=_user_ops_pool_core_runtime(),
    )


def upsert_user_ops_lead_pool_member(
    *,
    mobile: str = "",
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    is_wecom_added: bool | None = None,
    is_mobile_bound: bool | None = None,
    huangxiaocan_activation_state: str = "unknown",
    class_term_no: int | None = None,
    class_term_label: str = "",
    entry_source: str = "",
    operator: str = "",
    remark: str = "",
) -> dict[str, Any]:
    return user_ops_pool_core_service.upsert_user_ops_lead_pool_member(
        mobile=mobile,
        external_userid=external_userid,
        customer_name=customer_name,
        owner_userid=owner_userid,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        class_term_label=class_term_label,
        entry_source=entry_source,
        operator=operator,
        remark=remark,
        runtime=_user_ops_pool_core_runtime(),
    )


def apply_user_ops_huangxiaocan_activation_source_to_existing_member(
    *,
    mobile: str,
    activation_state: str,
    operator: str = "",
    source_type: str = "huangxiaocan_activation_source",
    remark: str = "",
) -> dict[str, Any]:
    return user_ops_pool_core_service.apply_user_ops_huangxiaocan_activation_source_to_existing_member(
        mobile=mobile,
        activation_state=activation_state,
        operator=operator,
        source_type=source_type,
        remark=remark,
        runtime=_user_ops_pool_core_runtime(),
    )


def _current_user_ops_operator() -> str:
    if has_request_context():
        for key in ("userid", "user_id", "username"):
            value = str(session.get(key) or "").strip()
            if value:
                return value
    return "admin_user_ops"


def upsert_user_ops_huangxiaocan_activation_source(
    *,
    mobile: str,
    activation_state: str,
    import_batch_id: str = "",
    created_by: str = "",
    is_active: bool = True,
) -> dict[str, Any]:
    return user_ops_import_service.upsert_user_ops_huangxiaocan_activation_source(
        mobile=mobile,
        activation_state=activation_state,
        import_batch_id=import_batch_id,
        created_by=created_by,
        is_active=is_active,
        runtime=_user_ops_import_runtime(),
    )


def import_experience_leads(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    return user_ops_import_service.import_experience_leads(
        pasted_text=pasted_text,
        file_name=file_name,
        file_bytes=file_bytes,
        created_by=created_by,
        runtime=_user_ops_import_runtime(),
    )


def import_mobile_class_term_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    return user_ops_import_service.import_mobile_class_term_source(
        pasted_text=pasted_text,
        file_name=file_name,
        file_bytes=file_bytes,
        created_by=created_by,
        runtime=_user_ops_import_runtime(),
    )


def import_activation_status_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    return user_ops_import_service.import_activation_status_source(
        pasted_text=pasted_text,
        file_name=file_name,
        file_bytes=file_bytes,
        created_by=created_by,
        runtime=_user_ops_import_runtime(),
    )


def migrate_legacy_user_ops_pool_to_lead_pool(*, operator: str = "") -> dict[str, Any]:
    return user_ops_import_service.migrate_legacy_user_ops_pool_to_lead_pool(
        operator=operator,
        runtime=_user_ops_import_runtime(),
    )


def _extract_third_party_user_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("third_party_user_id", "user_id", "id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        for key in ("data", "result", "user", "person"):
            value = _extract_third_party_user_id(payload.get(key))
            if value:
                return value
    elif isinstance(payload, list):
        for item in payload:
            value = _extract_third_party_user_id(item)
            if value:
                return value
    return ""


def _resolve_third_party_user_id_by_mobile(mobile: str) -> str:
    existing = current_app.config.get("SIDEBAR_THIRD_PARTY_RESOLVER")
    if callable(existing):
        resolved = str(existing(mobile) or "").strip()
        if resolved:
            return resolved

    api_url = str(current_app.config.get("SIDEBAR_THIRD_PARTY_API_URL", "") or "").strip()
    api_token = str(current_app.config.get("SIDEBAR_THIRD_PARTY_API_TOKEN", "") or "").strip()
    timeout = int(current_app.config.get("SIDEBAR_THIRD_PARTY_TIMEOUT_SECONDS", 10))
    if api_url:
        headers = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        from ...infra.http_client import OutboundHttpError, get_outbound_client

        client = get_outbound_client("sidebar_third_party_sync", timeout=float(timeout), retry_max=2)
        try:
            response = client.post(
                api_url,
                json={"mobile": mobile},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except OutboundHttpError as exc:
            raise ThirdPartyUserSyncError(f"third-party sync request failed: {exc}") from exc
        except requests.RequestException as exc:
            raise ThirdPartyUserSyncError(f"third-party sync request failed: {exc}") from exc
        except ValueError as exc:
            raise ThirdPartyUserSyncError("third-party sync returned invalid JSON") from exc

        third_party_user_id = _extract_third_party_user_id(payload)
        if third_party_user_id:
            return third_party_user_id
        raise ThirdPartyUserSyncError("third-party sync response missing third_party_user_id")

    if current_app.testing or current_app.config.get("DEBUG"):
        return f"mocktp_{mobile}"

    raise ThirdPartyUserSyncError("third-party resolver is not configured")


def _sidebar_contact_profile(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    return user_ops_sidebar_service.load_sidebar_contact_profile(external_userid, owner_userid)


def _resolve_binding_owner_userid(external_userid: str, owner_userid: str = "") -> str:
    return user_ops_sidebar_service.resolve_binding_owner_userid(external_userid, owner_userid)


def _select_user_ops_lead_pool_member_for_sidebar(
    *,
    external_userid: str,
    mobile: str = "",
    owner_userid: str = "",
) -> dict[str, Any] | None:
    return user_ops_sidebar_service.select_user_ops_lead_pool_member_for_sidebar(
        external_userid=external_userid,
        mobile=mobile,
        owner_userid=owner_userid,
        runtime=_user_ops_sidebar_runtime(),
    )


def get_sidebar_lead_pool_status(*, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    return user_ops_sidebar_service.get_sidebar_lead_pool_status(
        external_userid=external_userid,
        owner_userid=owner_userid,
        runtime=_user_ops_sidebar_runtime(),
    )


def upsert_sidebar_lead_pool_class_term(
    *,
    external_userid: str,
    owner_userid: str = "",
    class_term_no: int,
    operator: str = "",
) -> dict[str, Any]:
    return user_ops_sidebar_service.upsert_sidebar_lead_pool_class_term(
        external_userid=external_userid,
        owner_userid=owner_userid,
        class_term_no=class_term_no,
        operator=operator,
        runtime=_user_ops_sidebar_runtime(),
    )


def _merge_lead_pool_after_mobile_bind(
    *,
    external_userid: str,
    owner_userid: str,
    mobile: str,
    operator: str = "",
) -> dict[str, Any]:
    return user_ops_sidebar_service.merge_lead_pool_after_mobile_bind(
        external_userid=external_userid,
        owner_userid=owner_userid,
        mobile=mobile,
        operator=operator,
        runtime=_user_ops_sidebar_runtime(),
    )
