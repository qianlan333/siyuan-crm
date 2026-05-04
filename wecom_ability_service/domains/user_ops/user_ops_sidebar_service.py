from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from flask import current_app

from ...db import get_db
from . import user_ops_class_term_service


@dataclass(frozen=True)
class SidebarRuntime:
    """Internal-only dependency bag for user-ops sidebar flows."""

    current_operator_resolver: Callable[[], str]
    normalize_mobile: Callable[[str], str]
    get_contact_binding_status: Callable[[str, str], dict[str, Any]]
    list_user_ops_lead_pool_matches: Callable[..., list[dict[str, Any]]]
    serialize_user_ops_lead_pool_current_row: Callable[[dict[str, Any] | None], dict[str, Any]]
    upsert_user_ops_lead_pool_member: Callable[..., dict[str, Any]]
    write_user_ops_lead_pool_history: Callable[..., Any]
    list_other_ownerids_with_scoped_tag_snapshots: Callable[..., list[str]]
    save_tag_snapshot: Callable[[str, str, list[str], dict[str, str]], None]
    remove_tag_snapshot: Callable[[str, str, list[str]], None]
    remove_tag_snapshots_for_other_users: Callable[[str, list[str], list[str]], None]
    class_term_runtime: user_ops_class_term_service.ClassTermRuntime


def _sync_sidebar_lead_pool_class_term_tag(
    *,
    external_userid: str,
    owner_userid: str,
    class_term_no: int,
    runtime: SidebarRuntime,
) -> dict[str, Any]:
    """Internal only: sidebar tag patch implementation."""

    # Import lazily here to avoid widening the existing services <-> wecom_client
    # dependency loop while still making the hot path explicit and testable.
    from ...wecom_client import WeComClient

    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")

    mapping = user_ops_class_term_service.get_active_class_term_mapping_by_no(
        class_term_no,
        runtime=runtime.class_term_runtime,
    )
    if not mapping:
        raise ValueError("class_term_no is invalid")

    target_tag_id = str(mapping.get("tag_id") or "").strip()
    target_tag_name = str(mapping.get("tag_name") or mapping.get("class_term_label") or "").strip()
    if not target_tag_id:
        raise ValueError("class term tag is not initialized")

    active_mappings = user_ops_class_term_service.list_active_class_term_mappings(
        runtime=runtime.class_term_runtime,
    )
    remove_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in active_mappings
            if str(item.get("tag_id") or "").strip()
            and int(item.get("class_term_no") or 0) != int(mapping["class_term_no"])
        }
    )
    scoped_class_term_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in active_mappings
            if str(item.get("tag_id") or "").strip()
        }
    )

    testing_applier = current_app.config.get("SIDEBAR_LEAD_POOL_TAG_APPLIER")
    if callable(testing_applier):
        testing_applier(
            external_userid=normalized_external_userid,
            owner_userid=normalized_owner_userid,
            add_tags=[target_tag_id],
            remove_tags=remove_tag_ids,
        )
    else:
        client = WeComClient.from_app()
        client.mark_external_contact_tags(
            external_userid=normalized_external_userid,
            follow_user_userid=normalized_owner_userid,
            add_tags=[target_tag_id],
            remove_tags=remove_tag_ids,
        )

    other_follow_user_userids = runtime.list_other_ownerids_with_scoped_tag_snapshots(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        scoped_tag_ids=scoped_class_term_tag_ids,
    )
    for other_follow_user_userid in other_follow_user_userids:
        if callable(testing_applier):
            testing_applier(
                external_userid=normalized_external_userid,
                owner_userid=other_follow_user_userid,
                add_tags=[],
                remove_tags=scoped_class_term_tag_ids,
            )
        else:
            client.mark_external_contact_tags(
                external_userid=normalized_external_userid,
                follow_user_userid=other_follow_user_userid,
                add_tags=[],
                remove_tags=scoped_class_term_tag_ids,
            )

    runtime.save_tag_snapshot(
        normalized_owner_userid,
        normalized_external_userid,
        [target_tag_id],
        {target_tag_id: target_tag_name},
    )
    if remove_tag_ids:
        runtime.remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, remove_tag_ids)
    runtime.remove_tag_snapshots_for_other_users(
        normalized_external_userid,
        [normalized_owner_userid],
        scoped_class_term_tag_ids,
    )
    return {
        "class_term_no": int(mapping["class_term_no"]),
        "class_term_label": str(mapping.get("class_term_label") or "").strip(),
        "tag_id": target_tag_id,
        "tag_name": target_tag_name,
        "removed_tag_ids": remove_tag_ids,
    }


def load_sidebar_contact_profile(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    """Internal stable owner for sidebar contact profile loading."""

    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {
            "customer_name": "",
            "remark": "",
            "display_name": "",
            "owner_userid": normalized_owner_userid,
        }

    db = get_db()
    contact = db.execute(
        """
        SELECT external_userid, COALESCE(customer_name, '') AS customer_name, COALESCE(owner_userid, '') AS owner_userid,
               COALESCE(remark, '') AS remark
        FROM contacts
        WHERE external_userid = ?
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    if contact:
        fallback_owner_userid = str(contact.get("owner_userid") or "").strip()
        customer_name = str(contact.get("customer_name") or "").strip()
        remark = str(contact.get("remark") or "").strip()
    else:
        fallback_owner_userid = ""
        customer_name = ""
        remark = ""

    if not remark:
        follow_user = None
        if normalized_owner_userid:
            follow_user = db.execute(
                """
                SELECT COALESCE(remark, '') AS remark
                FROM wecom_external_contact_follow_users
                WHERE corp_id = ? AND external_userid = ? AND user_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (
                    current_app.config.get("WECOM_CORP_ID", ""),
                    normalized_external_userid,
                    normalized_owner_userid,
                ),
            ).fetchone()
        if not follow_user:
            follow_user = db.execute(
                """
                SELECT COALESCE(remark, '') AS remark
                FROM wecom_external_contact_follow_users
                WHERE corp_id = ? AND external_userid = ?
                ORDER BY is_primary DESC, updated_at DESC, id DESC
                LIMIT 1
                """,
                (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid),
            ).fetchone()
        remark = str((follow_user or {}).get("remark") or "").strip()

    display_name = customer_name or remark
    if not display_name:
        suffix = normalized_external_userid[-6:] if len(normalized_external_userid) > 6 else normalized_external_userid
        display_name = f"客户 {suffix}" if suffix else "当前客户"

    return {
        "customer_name": customer_name,
        "remark": remark,
        "display_name": display_name,
        "owner_userid": normalized_owner_userid or fallback_owner_userid,
    }


def resolve_binding_owner_userid(external_userid: str, owner_userid: str = "") -> str:
    """Internal stable owner for sidebar binding-owner resolution."""

    profile = load_sidebar_contact_profile(external_userid, owner_userid)
    resolved_owner_userid = str(profile.get("owner_userid") or "").strip()
    if resolved_owner_userid:
        return resolved_owner_userid
    row = get_db().execute(
        """
        SELECT COALESCE(follow_user_userid, '') AS follow_user_userid
        FROM wecom_external_contact_identity_map
        WHERE corp_id = ? AND external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (current_app.config.get("WECOM_CORP_ID", ""), str(external_userid or "").strip()),
    ).fetchone()
    return str((row or {}).get("follow_user_userid") or "").strip()


def select_user_ops_lead_pool_member_for_sidebar(
    *,
    external_userid: str,
    mobile: str = "",
    owner_userid: str = "",
    runtime: SidebarRuntime,
) -> dict[str, Any] | None:
    """Internal stable owner for sidebar lead-pool member selection."""

    normalized_external_userid = str(external_userid or "").strip()
    normalized_mobile = str(mobile or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    matches = runtime.list_user_ops_lead_pool_matches(
        mobile=normalized_mobile,
        external_userid=normalized_external_userid,
    )
    if normalized_owner_userid:
        matches = [
            item for item in matches if str(item.get("owner_userid") or "").strip() == normalized_owner_userid
        ]
    if normalized_mobile:
        target = next((item for item in matches if item["mobile"] == normalized_mobile), None)
        if target is not None:
            return target
    if normalized_external_userid:
        target = next((item for item in matches if item["external_userid"] == normalized_external_userid), None)
        if target is not None:
            return target
    return matches[0] if matches else None


def get_sidebar_lead_pool_status(
    *,
    external_userid: str,
    owner_userid: str = "",
    runtime: SidebarRuntime,
) -> dict[str, Any]:
    """Internal stable owner for sidebar status payloads."""

    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_requested_owner_userid = str(owner_userid or "").strip()
    normalized_owner_userid = normalized_requested_owner_userid or resolve_binding_owner_userid(
        normalized_external_userid,
        owner_userid,
    )
    binding = runtime.get_contact_binding_status(normalized_external_userid, normalized_owner_userid)
    member = select_user_ops_lead_pool_member_for_sidebar(
        external_userid=normalized_external_userid,
        mobile=str(binding.get("mobile") or "").strip(),
        owner_userid=normalized_owner_userid,
        runtime=runtime,
    ) or {}
    match_payload = user_ops_class_term_service.list_class_term_matches_for_external_contact(
        normalized_external_userid,
        normalized_owner_userid,
        runtime=runtime.class_term_runtime,
    )
    matched_terms = list(match_payload["matched_terms"])
    current_class_term_no = member.get("class_term_no")
    current_class_term_label = str(member.get("class_term_label") or "").strip()
    if current_class_term_no in (None, "") and len(matched_terms) == 1:
        current_class_term_no = int(matched_terms[0]["class_term_no"])
        current_class_term_label = str(matched_terms[0].get("class_term_label") or "").strip()

    return {
        "external_userid": normalized_external_userid,
        "owner_userid": str(binding.get("owner_userid") or normalized_owner_userid).strip(),
        "display_name": str(binding.get("display_name") or "").strip(),
        "customer_name": str(binding.get("customer_name") or "").strip(),
        "mobile": str(binding.get("mobile") or "").strip(),
        "is_wecom_added": True,
        "is_mobile_bound": bool(binding.get("is_bound")),
        "class_term_options": user_ops_class_term_service.list_user_ops_class_term_options(
            runtime=runtime.class_term_runtime,
        ),
        "current_class_term_no": int(current_class_term_no) if current_class_term_no not in (None, "") else None,
        "current_class_term_label": current_class_term_label,
        "current_tag_names": list(match_payload["tag_names"]),
        "member": member,
    }


def upsert_sidebar_lead_pool_class_term(
    *,
    external_userid: str,
    owner_userid: str = "",
    class_term_no: int,
    operator: str = "",
    runtime: SidebarRuntime,
) -> dict[str, Any]:
    """Internal stable owner for sidebar class-term patch writes."""

    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_requested_owner_userid = str(owner_userid or "").strip()
    normalized_owner_userid = normalized_requested_owner_userid or resolve_binding_owner_userid(
        normalized_external_userid,
        owner_userid,
    )
    actor = str(operator or runtime.current_operator_resolver()).strip() or "sidebar_class_term"
    mapping = user_ops_class_term_service.get_active_class_term_mapping_by_no(
        class_term_no,
        runtime=runtime.class_term_runtime,
    )
    if not mapping:
        raise ValueError("class_term_no is invalid")

    binding = runtime.get_contact_binding_status(normalized_external_userid, normalized_owner_userid)
    upsert_result = runtime.upsert_user_ops_lead_pool_member(
        mobile=str(binding.get("mobile") or "").strip(),
        external_userid=normalized_external_userid,
        customer_name=str(binding.get("customer_name") or "").strip(),
        owner_userid=normalized_owner_userid,
        is_wecom_added=True,
        is_mobile_bound=bool(binding.get("is_bound")),
        class_term_no=int(mapping["class_term_no"]),
        class_term_label=str(mapping.get("class_term_label") or "").strip(),
        entry_source="sidebar_class_term",
        operator=actor,
        remark=f"sidebar class term set external_userid={normalized_external_userid}",
    )
    tag_result = _sync_sidebar_lead_pool_class_term_tag(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        class_term_no=int(mapping["class_term_no"]),
        runtime=runtime,
    )
    return {
        "ok": True,
        "member": upsert_result.get("member"),
        "action_type": upsert_result.get("action_type"),
        "tag_sync": tag_result,
    }


def merge_lead_pool_after_mobile_bind(
    *,
    external_userid: str,
    owner_userid: str,
    mobile: str,
    operator: str = "",
    runtime: SidebarRuntime,
) -> dict[str, Any]:
    """Internal stable owner for sidebar mobile-bind merge behavior."""

    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    normalized_mobile = runtime.normalize_mobile(mobile)
    actor = str(operator or runtime.current_operator_resolver()).strip() or "sidebar_bind_mobile"

    matches = runtime.list_user_ops_lead_pool_matches(
        mobile=normalized_mobile,
        external_userid=normalized_external_userid,
    )
    external_row = next((item for item in matches if item["external_userid"] == normalized_external_userid), None)
    mobile_row = next((item for item in matches if item["mobile"] == normalized_mobile), None)
    profile = load_sidebar_contact_profile(normalized_external_userid, normalized_owner_userid)
    merge_before_payload = runtime.serialize_user_ops_lead_pool_current_row(external_row or {})
    merged_class_term_no = (
        mobile_row.get("class_term_no")
        if mobile_row and mobile_row.get("class_term_no") not in (None, "")
        else (external_row.get("class_term_no") if external_row else None)
    )
    merged_class_term_label = (
        str(mobile_row.get("class_term_label") or "").strip()
        if mobile_row and str(mobile_row.get("class_term_label") or "").strip()
        else str((external_row or {}).get("class_term_label") or "").strip()
    )
    merged_activation_state = (
        str(mobile_row.get("huangxiaocan_activation_state") or "").strip()
        if mobile_row and str(mobile_row.get("huangxiaocan_activation_state") or "").strip() not in ("", "unknown")
        else str((external_row or {}).get("huangxiaocan_activation_state") or "").strip()
    )
    merge_required = bool(
        external_row
        and (
            not str(external_row.get("mobile") or "").strip()
            or (mobile_row is not None and int(mobile_row["id"]) != int(external_row["id"]))
        )
    )

    if external_row is not None and mobile_row is not None and int(external_row["id"]) != int(mobile_row["id"]):
        get_db().execute(
            "DELETE FROM user_ops_lead_pool_current WHERE id = ?",
            (int(external_row["id"]),),
        )
        get_db().commit()

    result = runtime.upsert_user_ops_lead_pool_member(
        mobile=normalized_mobile,
        external_userid=normalized_external_userid,
        customer_name=str(profile.get("customer_name") or "").strip(),
        owner_userid=normalized_owner_userid,
        is_wecom_added=True,
        is_mobile_bound=True,
        huangxiaocan_activation_state=merged_activation_state or "unknown",
        class_term_no=int(merged_class_term_no) if merged_class_term_no not in (None, "") else None,
        class_term_label=merged_class_term_label,
        entry_source="mobile_bind",
        operator=actor,
        remark=f"bind mobile external_userid={normalized_external_userid}",
    )
    member = dict(result.get("member") or {})
    if merge_required:
        runtime.write_user_ops_lead_pool_history(
            mobile=str(member.get("mobile") or normalized_mobile).strip(),
            external_userid=str(member.get("external_userid") or normalized_external_userid).strip(),
            action_type="mobile_bind_merge",
            source_type="mobile_bind",
            operator=actor,
            before_payload=merge_before_payload,
            after_payload=runtime.serialize_user_ops_lead_pool_current_row(member),
            remark=(
                f"canonical mobile={normalized_mobile}; "
                f"absorbed_external_row_id={int(external_row['id']) if external_row else 0}; "
                f"mobile_row_id={int(mobile_row['id']) if mobile_row else 0}"
            ),
        )
        get_db().commit()
    return {
        "ok": True,
        "merge_applied": merge_required,
        "member": member,
        "merged_duplicate_ids": list(result.get("merged_duplicate_ids") or []),
        "action_type": result.get("action_type"),
    }


__all__ = [
    "SidebarRuntime",
    "get_sidebar_lead_pool_status",
    "load_sidebar_contact_profile",
    "merge_lead_pool_after_mobile_bind",
    "resolve_binding_owner_userid",
    "select_user_ops_lead_pool_member_for_sidebar",
    "upsert_sidebar_lead_pool_class_term",
]
