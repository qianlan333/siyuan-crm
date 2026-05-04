from __future__ import annotations

import json
import re
from typing import Any, Callable

from flask import current_app

from . import repo


class ContactBindingConflictError(ValueError):
    pass


def normalize_external_contact_identity(
    corp_id: str,
    payload: dict[str, Any],
    *,
    follow_user_userid: str = "",
    status: str = "active",
) -> dict[str, Any]:
    external_contact = payload.get("external_contact") or payload
    follow_users = payload.get("follow_user") or []
    matched_follow_user = {}
    if follow_user_userid:
        matched_follow_user = next((item for item in follow_users if item.get("userid") == follow_user_userid), {}) or {}
    if not matched_follow_user and follow_users:
        matched_follow_user = follow_users[0]
    external_userid = external_contact.get("external_userid", "")
    return {
        "corp_id": corp_id,
        "external_userid": external_userid,
        "unionid": external_contact.get("unionid", "") or "",
        "openid": external_contact.get("openid", "") or "",
        "follow_user_userid": matched_follow_user.get("userid", "") or follow_user_userid or "",
        "name": external_contact.get("name", "") or "",
        "type": external_contact.get("type"),
        "avatar": external_contact.get("avatar", "") or "",
        "gender": external_contact.get("gender"),
        "status": status,
        "raw_profile": json.dumps(payload, ensure_ascii=False),
    }


def count_external_contact_identity_maps() -> int:
    return repo.count_external_contact_identity_maps()


def list_identity_external_userids_for_corp(corp_id: str) -> list[str]:
    return repo.list_identity_external_userids_for_corp(corp_id)


def replace_external_contact_follow_users(
    corp_id: str,
    external_userid: str,
    follow_users: list[dict[str, object]],
    *,
    preferred_userid: str = "",
) -> None:
    repo.replace_external_contact_follow_users(
        corp_id,
        external_userid,
        follow_users,
        preferred_userid=preferred_userid,
    )


def mark_external_contact_follow_user_status(corp_id: str, external_userid: str, *, user_id: str = "", status: str) -> None:
    repo.mark_external_contact_follow_user_status(
        corp_id,
        external_userid,
        user_id=user_id,
        status=status,
    )


def refresh_external_contact_identity_owner(corp_id: str, external_userid: str) -> None:
    repo.refresh_external_contact_identity_owner(corp_id, external_userid)


def upsert_external_contact_identity(record: dict[str, object]) -> int:
    return repo.upsert_external_contact_identity(record)


def mark_external_contact_identity_status(corp_id: str, external_userid: str, *, status: str, follow_user_userid: str = "") -> None:
    repo.mark_external_contact_identity_status(
        corp_id,
        external_userid,
        status=status,
        follow_user_userid=follow_user_userid,
    )


def resolve_external_contact_identity(
    corp_id: str,
    *,
    unionid: str = "",
    openid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    row = repo.resolve_external_contact_identity_row(
        corp_id,
        unionid=unionid,
        openid=openid,
        external_userid=external_userid,
    )
    return dict(row) if row else None


def bind_openid_to_external_contact(corp_id: str, external_userid: str, openid: str, unionid: str = "") -> dict[str, Any] | None:
    target = resolve_external_contact_identity(corp_id, external_userid=external_userid)
    if not target:
        return None
    resolved_by_union = resolve_external_contact_identity(corp_id, unionid=unionid) if unionid else None
    if resolved_by_union and resolved_by_union.get("external_userid") != external_userid:
        return target
    current_openid = target.get("openid", "") or ""
    current_unionid = target.get("unionid", "") or ""
    next_openid = current_openid or (openid or "")
    next_unionid = current_unionid or (unionid or "")
    if next_openid == current_openid and next_unionid == current_unionid:
        return resolve_external_contact_identity(corp_id, external_userid=external_userid)
    repo.update_identity_openid_unionid(corp_id, external_userid, next_openid, next_unionid)
    return resolve_external_contact_identity(corp_id, external_userid=external_userid)


def get_primary_follow_user_userid(
    external_userid: str,
    *,
    corp_id: str = "",
    active_value: bool | int = True,
    contact_loader: Callable[[str], dict[str, Any] | None],
    resolve_identity: Callable[[str, str], dict[str, Any] | None],
) -> str:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return ""
    resolved_corp_id = str(corp_id or "").strip() or person_identity_corp_id()
    row = repo.get_primary_follow_user_row(resolved_corp_id, normalized_external_userid, active_value)
    if row and row.get("user_id"):
        return str(row["user_id"]).strip()
    contact = contact_loader(normalized_external_userid)
    if contact and contact.get("owner_userid"):
        return str(contact["owner_userid"]).strip()
    identity = resolve_identity(resolved_corp_id, normalized_external_userid)
    if identity and identity.get("follow_user_userid"):
        return str(identity["follow_user_userid"]).strip()
    return ""


def person_identity_corp_id() -> str:
    return str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()


def empty_resolved_person_identity(*, external_userid: str, mobile: str, unionid: str) -> dict[str, Any]:
    return {
        "person_id": None,
        "mobile": mobile,
        "external_userid": external_userid,
        "unionid": unionid,
        "customer_name": "",
        "owner_userid": "",
        "remark": "",
        "openid": "",
        "follow_user_userid": "",
        "signup_status": "",
        "is_bound": False,
    }


def serialize_resolved_person_identity(
    row,
    *,
    fallback_external_userid: str,
    fallback_unionid: str,
    resolve_signup_status_for_contact: Callable[[str, str], str],
) -> dict[str, Any]:
    resolved_external_userid = str(row.get("external_userid") or "").strip()
    resolved_owner_userid = (
        str(row.get("owner_userid") or "").strip()
        or str(row.get("last_owner_userid") or "").strip()
        or str(row.get("first_owner_userid") or "").strip()
        or str(row.get("follow_user_userid") or "").strip()
    )
    signup_status = ""
    if resolved_external_userid:
        signup_status = resolve_signup_status_for_contact(resolved_external_userid, resolved_owner_userid)
    return {
        "person_id": int(row["person_id"]) if row.get("person_id") is not None else None,
        "mobile": str(row.get("mobile") or "").strip(),
        "external_userid": resolved_external_userid or fallback_external_userid,
        "customer_name": str(row.get("customer_name") or "").strip(),
        "owner_userid": resolved_owner_userid,
        "remark": str(row.get("remark") or "").strip(),
        "unionid": str(row.get("unionid") or fallback_unionid or "").strip(),
        "openid": str(row.get("openid") or "").strip(),
        "follow_user_userid": str(row.get("follow_user_userid") or "").strip(),
        "signup_status": signup_status,
        "is_bound": bool(row.get("person_id") is not None and resolved_external_userid),
    }


def resolve_person_identity(
    *,
    external_userid: str = "",
    mobile: str = "",
    unionid: str = "",
    corp_id: str = "",
    resolve_signup_status_for_contact: Callable[[str, str], str],
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_mobile = str(mobile or "").strip()
    normalized_unionid = str(unionid or "").strip()
    if not normalized_external_userid and not normalized_mobile and not normalized_unionid:
        raise ValueError("external_userid, mobile or unionid is required")
    resolved_corp_id = str(corp_id or "").strip() or person_identity_corp_id()
    if normalized_external_userid:
        row = repo.resolve_person_identity_row_by_external_userid(resolved_corp_id, normalized_external_userid)
    elif normalized_mobile:
        row = repo.resolve_person_identity_row_by_mobile(resolved_corp_id, normalized_mobile)
    else:
        row = repo.resolve_person_identity_row_by_unionid(resolved_corp_id, normalized_unionid)
    if not row:
        return empty_resolved_person_identity(
            external_userid=normalized_external_userid,
            mobile=normalized_mobile,
            unionid=normalized_unionid,
        )
    return serialize_resolved_person_identity(
        row,
        fallback_external_userid=normalized_external_userid,
        fallback_unionid=normalized_unionid,
        resolve_signup_status_for_contact=resolve_signup_status_for_contact,
    )


def get_contact_binding_status(
    external_userid: str,
    owner_userid: str = "",
    *,
    contact_profile_loader: Callable[[str, str], dict[str, str]],
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    profile = contact_profile_loader(normalized_external_userid, normalized_owner_userid)
    row = repo.get_contact_binding_row(normalized_external_userid)
    if not row:
        return {
            "is_bound": False,
            "external_userid": normalized_external_userid,
            "owner_userid": profile.get("owner_userid", ""),
            "customer_name": profile.get("customer_name", ""),
            "remark": profile.get("remark", ""),
            "display_name": profile.get("display_name", ""),
        }
    return {
        "is_bound": True,
        "person_id": int(row["person_id"]),
        "external_userid": row["external_userid"],
        "owner_userid": profile.get("owner_userid", "") or row.get("last_owner_userid") or row.get("first_owner_userid") or "",
        "customer_name": profile.get("customer_name", ""),
        "remark": profile.get("remark", ""),
        "display_name": profile.get("display_name", ""),
        "mobile": row["mobile"],
        "third_party_user_id": row.get("third_party_user_id") or "",
        "first_bound_by_userid": row.get("first_bound_by_userid") or "",
        "first_owner_userid": row.get("first_owner_userid") or "",
        "last_owner_userid": row.get("last_owner_userid") or "",
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",
    }


def normalize_mobile(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or "").strip())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if not re.fullmatch(r"1\d{10}", digits):
        raise ValueError("mobile must be a valid mainland China mobile number")
    return digits


def _sync_person_third_party_user_id(
    *,
    person_id: int,
    mobile: str,
    existing_third_party_user_id: str,
    resolve_third_party_user_id_by_mobile: Callable[[str], str],
    sync_error_cls: type[Exception],
) -> str:
    if existing_third_party_user_id:
        return ""
    try:
        third_party_user_id = resolve_third_party_user_id_by_mobile(mobile)
        repo.update_person_third_party_user_id(person_id, third_party_user_id)
        return ""
    except sync_error_cls as exc:
        return str(exc)


def bind_mobile_to_external_contact(
    *,
    external_userid: str,
    owner_userid: str,
    bind_by_userid: str,
    mobile: str,
    force_rebind: bool = False,
    resolve_binding_owner_userid: Callable[[str, str], str],
    contact_profile_loader: Callable[[str, str], dict[str, Any]],
    resolve_third_party_user_id_by_mobile: Callable[[str], str],
    merge_lead_pool_after_mobile_bind: Callable[..., dict[str, Any]],
    conflict_error_cls: type[Exception] = ContactBindingConflictError,
    sync_error_cls: type[Exception] = Exception,
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = resolve_binding_owner_userid(normalized_external_userid, owner_userid)
    normalized_bind_by_userid = str(bind_by_userid or "").strip() or normalized_owner_userid
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not normalized_bind_by_userid:
        normalized_bind_by_userid = "sidebar_bind"
    normalized_mobile = normalize_mobile(mobile)

    existing = get_contact_binding_status(
        normalized_external_userid,
        normalized_owner_userid,
        contact_profile_loader=contact_profile_loader,
    )
    if existing.get("is_bound"):
        if existing.get("mobile") != normalized_mobile and not force_rebind:
            raise conflict_error_cls("external_userid already bound to another mobile")
        if existing.get("mobile") == normalized_mobile:
            return existing

    person_id, existing_third_party_user_id = repo.get_or_create_person_for_mobile(normalized_mobile)
    repo.upsert_external_contact_binding_record(
        existing=existing,
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        bind_by_userid=normalized_bind_by_userid,
        person_id=person_id,
        force_rebind=force_rebind,
    )

    third_party_sync_error = _sync_person_third_party_user_id(
        person_id=person_id,
        mobile=normalized_mobile,
        existing_third_party_user_id=existing_third_party_user_id,
        resolve_third_party_user_id_by_mobile=resolve_third_party_user_id_by_mobile,
        sync_error_cls=sync_error_cls,
    )
    lead_pool_merge = merge_lead_pool_after_mobile_bind(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        mobile=normalized_mobile,
        operator=normalized_bind_by_userid,
    )

    result = get_contact_binding_status(
        normalized_external_userid,
        normalized_owner_userid,
        contact_profile_loader=contact_profile_loader,
    )
    if third_party_sync_error:
        result["third_party_sync_status"] = "pending"
        result["third_party_sync_error"] = third_party_sync_error
    else:
        result["third_party_sync_status"] = "success" if result.get("third_party_user_id") else "empty"
    result["lead_pool_merge"] = lead_pool_merge
    return result
