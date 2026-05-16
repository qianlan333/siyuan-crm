from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import requests
from flask import current_app, has_request_context, session

from ...db import get_db
from ...db.helpers import fetchall_dicts
from ...infra.helpers import db_bool as _db_bool
from ...infra.helpers import stringify_db_timestamp as _stringify_db_timestamp
from ...infra.constants import (
    LEGACY_USER_OPS_POOL_STATUS_ORDER,
)
from ..class_user import service as class_user_domain_service
from ..identity import service as identity_domain_service
from ..routing_config.service import get_owner_class_term_backfill_entry_source_override
from ..tags import repo as tags_repo
from ..tags import service as tags_domain_service
from . import (
    page_service,
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
    return user_ops_class_term_service._normalize_user_ops_strategy_tag_groups(payload)  # type: ignore[attr-defined]


def _ensure_class_term_tag_mapping_seed() -> None:
    user_ops_class_term_service.ensure_class_term_tag_mapping_seed(
        runtime=_user_ops_class_term_runtime()
    )


def ensure_class_term_tag_mapping_seed() -> None:
    user_ops_class_term_service.ensure_class_term_tag_mapping_seed(
        runtime=_user_ops_class_term_runtime()
    )


def sync_user_ops_class_term_tag_definitions() -> dict[str, Any]:
    return user_ops_class_term_service.sync_user_ops_class_term_tag_definitions(
        runtime=_user_ops_class_term_runtime()
    )


def _list_user_ops_crm_source_rows() -> list[dict[str, Any]]:
    return fetchall_dicts(
        get_db(),
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
    )


def _list_user_ops_experience_lead_rows() -> list[dict[str, Any]]:
    # W06/W09 note: class-term import currently reuses user_ops_experience_leads
    # as the phone anchor so phone-only rows can participate in pool reload.
    # The actual class-term values still land on the pool projection.
    return fetchall_dicts(
        get_db(),
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
    )


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
    return fetchall_dicts(
        get_db(),
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
    )


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
    return user_ops_class_term_service._confirmed_class_term_mappings_by_no()  # type: ignore[attr-defined]


def _infer_user_ops_class_term_no_from_tag_name(tag_name: str) -> int | None:
    return user_ops_class_term_service._infer_user_ops_class_term_no_from_tag_name(tag_name)  # type: ignore[attr-defined]


def _list_live_user_ops_class_term_tags(tag_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return user_ops_class_term_service._list_live_user_ops_class_term_tags(tag_payload)  # type: ignore[attr-defined]


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
    return user_ops_class_term_service._list_owner_backfill_candidate_external_userids(owner_userid)  # type: ignore[attr-defined]


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


def list_user_ops_pool(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    return page_service.list_user_ops_pool(
        wecom_status=wecom_status,
        mobile_binding_status=mobile_binding_status,
        activation_bucket=activation_bucket,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        keyword=keyword,
        mobile=mobile,
        owner_userid=owner_userid,
        query=query,
    )


def get_user_ops_overview(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    return page_service.get_user_ops_overview(
        wecom_status=wecom_status,
        mobile_binding_status=mobile_binding_status,
        activation_bucket=activation_bucket,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        keyword=keyword,
        mobile=mobile,
        owner_userid=owner_userid,
        query=query,
    )


def list_user_ops_history(limit: int = 100) -> dict[str, Any]:
    return user_ops_pool_core_service.list_user_ops_history(
        limit=limit,
        runtime=_user_ops_pool_core_runtime(),
    )


def export_user_ops_pool(
    *,
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    return page_service.export_user_ops_pool(
        wecom_status=wecom_status,
        mobile_binding_status=mobile_binding_status,
        activation_bucket=activation_bucket,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        keyword=keyword,
        mobile=mobile,
        owner_userid=owner_userid,
        query=query,
    )


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
    activation_remark: str = "",
    import_batch_id: str = "",
    created_by: str = "",
    is_active: bool = True,
) -> dict[str, Any]:
    return user_ops_import_service.upsert_user_ops_huangxiaocan_activation_source(
        mobile=mobile,
        activation_state=activation_state,
        activation_remark=activation_remark,
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
