from __future__ import annotations

from typing import Any

from ..db import get_db, get_db_backend
from ..services import (
    get_class_user_status_current,
    get_contact_binding_status,
    get_contact_by_external_userid,
    get_contact_tag_snapshots,
    get_owner_role,
    get_signup_status_definitions,
    resolve_person_identity,
)
from .dto import (
    CustomerBindingDTO,
    CustomerClassStatusDTO,
    CustomerDetailDTO,
    CustomerFollowUserDTO,
    CustomerIdentityDTO,
    CustomerListItemDTO,
    CustomerTagDTO,
)


def _tag_dto_from_row(row: dict[str, Any]) -> CustomerTagDTO:
    return CustomerTagDTO(
        tag_id=str(row.get("tag_id") or "").strip(),
        tag_name=str(row.get("tag_name") or "").strip(),
        userid=str(row.get("userid") or "").strip(),
        created_at=str(row.get("created_at") or "").strip(),
    )


def _normalize_bool_filter(value: str) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError("is_bound must be one of true/false/1/0")


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _fetch_scope_external_userids() -> list[str]:
    rows = _fetchall_dict(
        """
        SELECT external_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid FROM external_contact_bindings
            UNION
            SELECT external_userid FROM wecom_external_contact_identity_map
            UNION
            SELECT external_userid FROM wecom_external_contact_follow_users
            UNION
            SELECT external_userid FROM contact_tags
            UNION
            SELECT external_userid FROM class_user_status_current
        ) scope
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY external_userid ASC
        """
    )
    return [str(item.get("external_userid") or "").strip() for item in rows if str(item.get("external_userid") or "").strip()]


def _fetch_contact_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, customer_name, owner_userid, remark, description, updated_at
        FROM contacts
        WHERE external_userid IN ({placeholders})
        """,
        tuple(external_userids),
    )
    return {str(item.get("external_userid") or "").strip(): item for item in rows}


def _fetch_follow_users_map(external_userids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    bool_true = True if get_db_backend() == "postgres" else 1
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            user_id,
            relation_status,
            is_primary,
            remark,
            description,
            add_way,
            oper_userid,
            createtime,
            updated_at
        FROM wecom_external_contact_follow_users
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, is_primary DESC, updated_at DESC, id DESC
        """,
        tuple(external_userids),
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        result.setdefault(external_userid, []).append(
            {
                "userid": str(row.get("user_id") or "").strip(),
                "relation_status": str(row.get("relation_status") or "").strip(),
                "is_primary": bool(row.get("is_primary") == bool_true or row.get("is_primary") is True or row.get("is_primary") == 1),
                "remark": str(row.get("remark") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "add_way": row.get("add_way"),
                "oper_userid": str(row.get("oper_userid") or "").strip(),
                "createtime": row.get("createtime"),
                "updated_at": str(row.get("updated_at") or "").strip(),
            }
        )
    return result


def _fetch_identity_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, unionid, openid, follow_user_userid, status, created_at, updated_at
        FROM wecom_external_contact_identity_map
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, updated_at DESC, id DESC
        """,
        tuple(external_userids),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid and external_userid not in result:
            result[external_userid] = row
    return result


def _resolve_owner_userid(
    external_userid: str,
    contact: dict[str, Any],
    class_status: dict[str, Any],
    binding_status: dict[str, Any],
    identity: dict[str, Any],
    follow_users: list[dict[str, Any]],
) -> str:
    primary_follow_user = next((item for item in follow_users if item.get("is_primary")), follow_users[0] if follow_users else {})
    return (
        str(class_status.get("owner_userid_snapshot") or "").strip()
        or str(contact.get("owner_userid") or "").strip()
        or str(binding_status.get("owner_userid") or "").strip()
        or str(identity.get("follow_user_userid") or "").strip()
        or str(primary_follow_user.get("userid") or "").strip()
        or ""
    )


def _resolve_customer_name(
    external_userid: str,
    contact: dict[str, Any],
    binding_status: dict[str, Any],
    class_status: dict[str, Any],
) -> str:
    return (
        str(class_status.get("customer_name_snapshot") or "").strip()
        or str(contact.get("customer_name") or "").strip()
        or str(binding_status.get("customer_name") or "").strip()
        or ""
    )


def _resolve_mobile(binding_status: dict[str, Any], class_status: dict[str, Any], person_identity: dict[str, Any]) -> str:
    return (
        str(binding_status.get("mobile") or "").strip()
        or str(person_identity.get("mobile") or "").strip()
        or str(class_status.get("mobile_snapshot") or "").strip()
        or ""
    )


def _build_customer_detail(external_userid: str) -> CustomerDetailDTO:
    contact = get_contact_by_external_userid(external_userid) or {}
    binding_status = get_contact_binding_status(external_userid) or {}
    class_status = get_class_user_status_current(external_userid) or {}
    identity = resolve_person_identity(external_userid=external_userid) or {}
    identity_row = _fetch_identity_map([external_userid]).get(external_userid, {})
    tags = [_tag_dto_from_row(item) for item in get_contact_tag_snapshots(external_userid)]
    follow_users_raw = _fetch_follow_users_map([external_userid]).get(external_userid, [])
    follow_users = [CustomerFollowUserDTO(**item) for item in follow_users_raw]
    owner_userid = _resolve_owner_userid(external_userid, contact, class_status, binding_status, identity, follow_users_raw)
    owner_role = get_owner_role(owner_userid) or {}
    customer_name = _resolve_customer_name(external_userid, contact, binding_status, class_status)
    display_name = str(binding_status.get("display_name") or "").strip() or customer_name or external_userid
    mobile = _resolve_mobile(binding_status, class_status, identity)

    sidebar_context = {
        "binding_status": binding_status,
        "signup_tag_status": {
            "definitions": get_signup_status_definitions(),
            "current_signup_status": str(class_status.get("signup_status") or "").strip(),
            "current_tag": str(class_status.get("signup_label_name") or "").strip(),
            "wecom_tag_sync_status": str(class_status.get("wecom_tag_sync_status") or "").strip(),
            "wecom_tag_sync_error": str(class_status.get("wecom_tag_sync_error") or "").strip(),
        },
    }

    return CustomerDetailDTO(
        external_userid=external_userid,
        customer_name=customer_name,
        display_name=display_name,
        owner_userid=owner_userid,
        owner_display_name=str(owner_role.get("display_name") or "").strip() or owner_userid,
        remark=str(contact.get("remark") or binding_status.get("remark") or "").strip(),
        description=str(contact.get("description") or "").strip(),
        mobile=mobile,
        is_bound=bool(binding_status.get("is_bound")),
        tags=tags,
        follow_users=follow_users,
        binding=CustomerBindingDTO(
            is_bound=bool(binding_status.get("is_bound")),
            person_id=binding_status.get("person_id"),
            mobile=str(binding_status.get("mobile") or "").strip(),
            third_party_user_id=str(binding_status.get("third_party_user_id") or "").strip(),
            first_bound_by_userid=str(binding_status.get("first_bound_by_userid") or "").strip(),
            first_owner_userid=str(binding_status.get("first_owner_userid") or "").strip(),
            last_owner_userid=str(binding_status.get("last_owner_userid") or "").strip(),
            created_at=str(binding_status.get("created_at") or "").strip(),
            updated_at=str(binding_status.get("updated_at") or "").strip(),
        ),
        identity=CustomerIdentityDTO(
            person_id=identity.get("person_id"),
            unionid=str(identity.get("unionid") or "").strip(),
            openid=str(identity.get("openid") or "").strip(),
            follow_user_userid=str(identity.get("follow_user_userid") or "").strip(),
            status=str(identity_row.get("status") or "").strip(),
            created_at=str(identity_row.get("created_at") or "").strip(),
            updated_at=str(identity_row.get("updated_at") or "").strip(),
        ),
        class_status=CustomerClassStatusDTO(
            signup_status=str(class_status.get("signup_status") or "").strip(),
            signup_label_name=str(class_status.get("signup_label_name") or "").strip(),
            set_by_userid=str(class_status.get("set_by_userid") or "").strip(),
            set_at=str(class_status.get("set_at") or "").strip(),
            wecom_tag_sync_status=str(class_status.get("wecom_tag_sync_status") or "").strip(),
            wecom_tag_sync_error=str(class_status.get("wecom_tag_sync_error") or "").strip(),
            status_flags_json=str(class_status.get("status_flags_json") or "{}"),
            updated_at=str(class_status.get("updated_at") or "").strip(),
        ),
        sidebar_context=sidebar_context,
        contact={
            "external_userid": external_userid,
            "customer_name": str(contact.get("customer_name") or "").strip(),
            "owner_userid": str(contact.get("owner_userid") or "").strip(),
            "remark": str(contact.get("remark") or "").strip(),
            "description": str(contact.get("description") or "").strip(),
            "updated_at": str(contact.get("updated_at") or "").strip(),
        },
    )


def _matches_filters(item: CustomerListItemDTO, filters: dict[str, str]) -> bool:
    owner = str(filters.get("owner") or "").strip()
    tag = str(filters.get("tag") or "").strip()
    status = str(filters.get("status") or "").strip()
    mobile = str(filters.get("mobile") or "").strip()
    keyword = str(filters.get("keyword") or "").strip().lower()
    is_bound = _normalize_bool_filter(filters.get("is_bound", ""))

    if owner and owner not in {item.owner_userid, item.owner_display_name}:
        return False
    if tag:
        tag_pool = {tag_item.tag_id for tag_item in item.tags} | {tag_item.tag_name for tag_item in item.tags}
        if item.signup_label_name:
            tag_pool.add(item.signup_label_name)
        if tag not in tag_pool:
            return False
    if status and item.signup_status != status:
        return False
    if is_bound is not None and item.is_bound != is_bound:
        return False
    if mobile and mobile not in item.mobile:
        return False
    if keyword:
        haystack = " ".join(
            [
                item.external_userid,
                item.customer_name,
                item.display_name,
                item.owner_userid,
                item.owner_display_name,
                item.mobile,
                item.signup_status,
                item.signup_label_name,
            ]
        ).lower()
        if keyword not in haystack:
            return False
    return True


def list_customers(filters: dict[str, str] | None = None) -> dict[str, Any]:
    normalized_filters = {key: str(value or "").strip() for key, value in (filters or {}).items()}
    external_userids = _fetch_scope_external_userids()
    contact_map = _fetch_contact_map(external_userids)
    follow_users_map = _fetch_follow_users_map(external_userids)
    items: list[CustomerListItemDTO] = []

    for external_userid in external_userids:
        contact = contact_map.get(external_userid, {})
        binding_status = get_contact_binding_status(external_userid)
        class_status = get_class_user_status_current(external_userid) or {}
        identity = resolve_person_identity(external_userid=external_userid) or {}
        follow_users = follow_users_map.get(external_userid, [])
        owner_userid = _resolve_owner_userid(external_userid, contact, class_status, binding_status, identity, follow_users)
        owner_role = get_owner_role(owner_userid) or {}
        customer_name = _resolve_customer_name(external_userid, contact, binding_status, class_status)
        display_name = str(binding_status.get("display_name") or "").strip() or customer_name or external_userid
        mobile = _resolve_mobile(binding_status, class_status, identity)
        tags = [_tag_dto_from_row(item) for item in get_contact_tag_snapshots(external_userid)]
        item = CustomerListItemDTO(
            external_userid=external_userid,
            customer_name=customer_name,
            display_name=display_name,
            owner_userid=owner_userid,
            owner_display_name=str(owner_role.get("display_name") or "").strip() or owner_userid,
            mobile=mobile,
            is_bound=bool(binding_status.get("is_bound")),
            signup_status=str(class_status.get("signup_status") or "").strip(),
            signup_label_name=str(class_status.get("signup_label_name") or "").strip(),
            tags=tags,
            updated_at=(
                str(class_status.get("updated_at") or "").strip()
                or str(contact.get("updated_at") or "").strip()
                or str(binding_status.get("updated_at") or "").strip()
            ),
        )
        if _matches_filters(item, normalized_filters):
            items.append(item)

    items.sort(key=lambda item: (item.updated_at, item.external_userid), reverse=True)
    return {
        "items": [item.to_dict() for item in items],
        "total": len(items),
        "filters": normalized_filters,
    }


def get_customer_detail(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    if normalized_external_userid not in set(_fetch_scope_external_userids()):
        return None
    return _build_customer_detail(normalized_external_userid).to_dict()
