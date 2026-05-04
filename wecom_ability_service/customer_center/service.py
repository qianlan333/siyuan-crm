from __future__ import annotations

from typing import Any

from ..services import refresh_contact_tags_for_external_userid
from ..domains.marketing_automation.service import get_customer_marketing_profile
from .pulse_service import build_customer_pulse, is_customer_pulse_enabled
from .dto import (
    CustomerBindingDTO,
    CustomerClassStatusDTO,
    CustomerDetailDTO,
    CustomerFollowUserDTO,
    CustomerIdentityDTO,
    CustomerListItemDTO,
    CustomerMarketingSummaryDTO,
    CustomerTagDTO,
)
from .repo import (
    count_customer_scope_external_userids,
    fetch_binding_map,
    fetch_class_status_map,
    fetch_contact_map,
    fetch_customer_last_dispatch_at,
    fetch_customer_last_dispatch_at_map,
    fetch_customer_marketing_state_current,
    fetch_customer_marketing_state_current_map,
    fetch_customer_value_segment_current,
    fetch_customer_value_segment_current_map,
    fetch_follow_users_map,
    fetch_identity_map,
    fetch_last_message_map,
    fetch_owner_role_map,
    fetch_tag_map,
    list_customer_scope_external_userids,
    list_scope_external_userids,
)


def _normalize_bool_filter(value: str | None) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError("is_bound must be one of true/false/1/0")


def _normalize_optional_bool_filter(value: str | None, *, field_name: str) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"{field_name} must be one of true/false/1/0")


def _normalize_limit(value: str | int | None) -> int:
    try:
        limit = int(value or 50)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    return max(1, min(limit, 200))


def _normalize_offset(value: str | int | None) -> int:
    try:
        offset = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("offset must be an integer") from exc
    return max(offset, 0)


def _tag_dto_from_row(row: dict[str, Any]) -> CustomerTagDTO:
    return CustomerTagDTO(
        tag_id=str(row.get("tag_id") or "").strip(),
        tag_name=str(row.get("tag_name") or "").strip(),
        userid=str(row.get("userid") or "").strip(),
        created_at=str(row.get("created_at") or "").strip(),
    )


def _resolve_owner_userid(
    external_userid: str,
    contact: dict[str, Any],
    class_status: dict[str, Any],
    binding: dict[str, Any],
    identity: dict[str, Any],
    follow_users: list[dict[str, Any]],
) -> str:
    primary_follow_user = next((item for item in follow_users if item.get("is_primary")), follow_users[0] if follow_users else {})
    return (
        str(class_status.get("owner_userid_snapshot") or "").strip()
        or str(contact.get("owner_userid") or "").strip()
        or str(binding.get("last_owner_userid") or "").strip()
        or str(binding.get("first_owner_userid") or "").strip()
        or str(identity.get("follow_user_userid") or "").strip()
        or str(primary_follow_user.get("userid") or "").strip()
        or ""
    )


def _resolve_customer_name(contact: dict[str, Any], class_status: dict[str, Any], identity: dict[str, Any]) -> str:
    return (
        str(class_status.get("customer_name_snapshot") or "").strip()
        or str(contact.get("customer_name") or "").strip()
        or str(identity.get("name") or "").strip()
        or ""
    )


def _resolve_mobile(binding: dict[str, Any], class_status: dict[str, Any]) -> str:
    return (
        str(binding.get("mobile") or "").strip()
        or str(class_status.get("mobile_snapshot") or "").strip()
        or ""
    )


def _resolve_updated_at(contact: dict[str, Any], binding: dict[str, Any], class_status: dict[str, Any], last_message_at: str) -> str:
    return (
        str(class_status.get("updated_at") or "").strip()
        or str(contact.get("updated_at") or "").strip()
        or str(binding.get("updated_at") or "").strip()
        or str(last_message_at or "").strip()
    )


def _build_context(external_userids: list[str]) -> dict[str, Any]:
    contact_map = fetch_contact_map(external_userids)
    binding_map = fetch_binding_map(external_userids)
    identity_map = fetch_identity_map(external_userids)
    follow_users_map = fetch_follow_users_map(external_userids)
    tag_map = fetch_tag_map(external_userids)
    class_status_map = fetch_class_status_map(external_userids)
    last_message_map = fetch_last_message_map(external_userids)
    marketing_state_map = fetch_customer_marketing_state_current_map(external_userids)
    marketing_value_segment_map = fetch_customer_value_segment_current_map(external_userids)
    last_dispatch_at_map = fetch_customer_last_dispatch_at_map(external_userids)

    owner_candidates: list[str] = []
    for external_userid in external_userids:
        contact = contact_map.get(external_userid, {})
        binding = binding_map.get(external_userid, {})
        identity = identity_map.get(external_userid, {})
        class_status = class_status_map.get(external_userid, {})
        follow_users = follow_users_map.get(external_userid, [])
        owner_candidates.extend(
            [
                str(class_status.get("owner_userid_snapshot") or "").strip(),
                str(contact.get("owner_userid") or "").strip(),
                str(binding.get("last_owner_userid") or "").strip(),
                str(binding.get("first_owner_userid") or "").strip(),
                str(identity.get("follow_user_userid") or "").strip(),
            ]
        )
        owner_candidates.extend(str(item.get("userid") or "").strip() for item in follow_users)

    owner_role_map = fetch_owner_role_map(owner_candidates)
    return {
        "contacts": contact_map,
        "bindings": binding_map,
        "identities": identity_map,
        "follow_users": follow_users_map,
        "tags": tag_map,
        "class_statuses": class_status_map,
        "last_messages": last_message_map,
        "marketing_states": marketing_state_map,
        "marketing_value_segments": marketing_value_segment_map,
        "last_dispatch_ats": last_dispatch_at_map,
        "owner_roles": owner_role_map,
    }


def _build_customer_list_item(external_userid: str, context: dict[str, Any]) -> CustomerListItemDTO:
    contact = context["contacts"].get(external_userid, {})
    binding = context["bindings"].get(external_userid, {})
    identity = context["identities"].get(external_userid, {})
    follow_users = context["follow_users"].get(external_userid, [])
    class_status = context["class_statuses"].get(external_userid, {})
    last_message_at = context["last_messages"].get(external_userid, "")
    tags = [_tag_dto_from_row(item) for item in context["tags"].get(external_userid, [])]
    owner_userid = _resolve_owner_userid(external_userid, contact, class_status, binding, identity, follow_users)
    owner_role = context["owner_roles"].get(owner_userid, {})
    customer_name = _resolve_customer_name(contact, class_status, identity)
    mobile = _resolve_mobile(binding, class_status)

    return CustomerListItemDTO(
        external_userid=external_userid,
        customer_name=customer_name,
        owner_userid=owner_userid,
        owner_display_name=str(owner_role.get("display_name") or "").strip() or owner_userid,
        remark=str(contact.get("remark") or "").strip(),
        description=str(contact.get("description") or "").strip(),
        mobile=mobile,
        is_bound=bool(binding),
        binding_status="bound" if binding else "unbound",
        follow_user_userids=[str(item.get("userid") or "").strip() for item in follow_users if str(item.get("userid") or "").strip()],
        tags=tags,
        class_user_status=CustomerClassStatusDTO(
            signup_status=str(class_status.get("signup_status") or "").strip(),
            signup_label_name=str(class_status.get("signup_label_name") or "").strip(),
            set_by_userid=str(class_status.get("set_by_userid") or "").strip(),
            set_at=str(class_status.get("set_at") or "").strip(),
            wecom_tag_sync_status=str(class_status.get("wecom_tag_sync_status") or "").strip(),
            wecom_tag_sync_error=str(class_status.get("wecom_tag_sync_error") or "").strip(),
            status_flags_json=str(class_status.get("status_flags_json") or "{}"),
            updated_at=str(class_status.get("updated_at") or "").strip(),
        ),
        last_message_at=str(last_message_at or "").strip(),
        last_touch_at=str(last_message_at or "").strip(),
        updated_at=_resolve_updated_at(contact, binding, class_status, str(last_message_at or "").strip()),
    )


def _build_marketing_summary(external_userid: str) -> CustomerMarketingSummaryDTO:
    state_row = fetch_customer_marketing_state_current(external_userid) or {}
    value_segment_row = fetch_customer_value_segment_current(external_userid) or {}
    marketing_profile = get_customer_marketing_profile(external_userid)
    return _build_marketing_summary_from_profile(
        external_userid=external_userid,
        state_row=state_row,
        value_segment_row=value_segment_row,
        marketing_profile=marketing_profile,
        last_dispatch_at=fetch_customer_last_dispatch_at(external_userid),
    )


def _split_stage_key(stage_key: Any) -> tuple[str, str]:
    normalized = str(stage_key or "").strip()
    if not normalized:
        return "", ""
    if "/" not in normalized:
        return normalized, ""
    return tuple(normalized.split("/", 1))  # type: ignore[return-value]


def _build_marketing_summary_from_profile(
    *,
    external_userid: str,
    state_row: dict[str, Any],
    value_segment_row: dict[str, Any],
    marketing_profile: dict[str, Any],
    last_dispatch_at: str = "",
) -> CustomerMarketingSummaryDTO:
    profile_summary = dict((marketing_profile or {}).get("summary") or {})
    main_stage, sub_stage = _split_stage_key(profile_summary.get("current_stage"))
    return CustomerMarketingSummaryDTO(
        main_stage=main_stage,
        sub_stage=sub_stage,
        segment=str(profile_summary.get("current_segment") or "").strip() or "unknown",
        hit_count=int(value_segment_row.get("score") or 0),
        eligible_for_conversion=bool(profile_summary.get("eligible_for_conversion")),
        last_activation_at=str(state_row.get("last_activation_at") or "").strip(),
        last_conversion_marked_at=str(state_row.get("last_conversion_marked_at") or "").strip(),
        last_dispatch_at=str(last_dispatch_at or "").strip(),
    )


def _build_marketing_summary_from_context(external_userid: str, context: dict[str, Any]) -> CustomerMarketingSummaryDTO:
    state_row = context["marketing_states"].get(external_userid, {})
    value_segment_row = context["marketing_value_segments"].get(external_userid, {})
    last_dispatch_at = context.get("last_dispatch_ats", {}).get(external_userid, "")
    marketing_profile = get_customer_marketing_profile(external_userid)
    return _build_marketing_summary_from_profile(
        external_userid=external_userid,
        state_row=state_row,
        value_segment_row=value_segment_row,
        marketing_profile=marketing_profile,
        last_dispatch_at=last_dispatch_at,
    )


def _matches_filters(item: CustomerListItemDTO, filters: dict[str, Any], marketing_summary: CustomerMarketingSummaryDTO) -> bool:
    owner_userid = str(filters.get("owner_userid") or "").strip()
    tag = str(filters.get("tag") or "").strip()
    status = str(filters.get("status") or "").strip()
    mobile = str(filters.get("mobile") or "").strip()
    keyword = str(filters.get("keyword") or "").strip().lower()
    is_bound = _normalize_bool_filter(filters.get("is_bound"))
    marketing_segment = str(filters.get("marketing_segment") or "").strip().lower()
    marketing_main_stage = str(filters.get("marketing_main_stage") or "").strip().lower()
    marketing_sub_stage = str(filters.get("marketing_sub_stage") or "").strip().lower()
    eligible_for_conversion = _normalize_optional_bool_filter(
        filters.get("eligible_for_conversion"),
        field_name="eligible_for_conversion",
    )

    if owner_userid and owner_userid not in {item.owner_userid, item.owner_display_name}:
        return False
    if tag:
        tag_pool = {tag_item.tag_id for tag_item in item.tags} | {tag_item.tag_name for tag_item in item.tags}
        if item.class_user_status.signup_label_name:
            tag_pool.add(item.class_user_status.signup_label_name)
        if tag not in tag_pool:
            return False
    if status and item.class_user_status.signup_status != status:
        return False
    if is_bound is not None and item.is_bound != is_bound:
        return False
    if marketing_segment and marketing_summary.segment.lower() != marketing_segment:
        return False
    if marketing_main_stage and marketing_summary.main_stage.lower() != marketing_main_stage:
        return False
    if marketing_sub_stage and marketing_summary.sub_stage.lower() != marketing_sub_stage:
        return False
    if eligible_for_conversion is not None and marketing_summary.eligible_for_conversion != eligible_for_conversion:
        return False
    if mobile and mobile not in item.mobile:
        return False
    if keyword:
        haystack = " ".join(
            [
                item.external_userid,
                item.customer_name,
                item.owner_userid,
                item.owner_display_name,
                item.remark,
                item.description,
                item.mobile,
                item.class_user_status.signup_status,
                item.class_user_status.signup_label_name,
            ]
        ).lower()
        if keyword not in haystack:
            return False
    return True


def _has_marketing_filters(filters: dict[str, Any]) -> bool:
    return any(
        str(filters.get(key) or "").strip().lower() not in {"", "all"}
        for key in (
            "marketing_segment",
            "marketing_main_stage",
            "marketing_sub_stage",
            "eligible_for_conversion",
        )
    )


def _customer_list_result(
    *,
    items: list[CustomerListItemDTO],
    total: int,
    limit: int,
    offset: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    serialized = [item.to_dict() for item in items]
    return {
        "customers": serialized,
        "count": int(total),
        "items": serialized,
        "total": int(total),
        "limit": int(limit),
        "offset": int(offset),
        "filters": {
            "owner_userid": str(filters.get("owner_userid", "") or ""),
            "tag": str(filters.get("tag", "") or ""),
            "status": str(filters.get("status", "") or ""),
            "is_bound": str(filters.get("is_bound", "") or ""),
            "marketing_segment": str(filters.get("marketing_segment", "") or ""),
            "marketing_main_stage": str(filters.get("marketing_main_stage", "") or ""),
            "marketing_sub_stage": str(filters.get("marketing_sub_stage", "") or ""),
            "eligible_for_conversion": str(filters.get("eligible_for_conversion", "") or ""),
            "mobile": str(filters.get("mobile", "") or ""),
            "keyword": str(filters.get("keyword", "") or ""),
            "limit": str(limit),
            "offset": str(offset),
        },
    }


def _list_customers_with_marketing_filters(
    normalized_filters: dict[str, Any],
    *,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    external_userids = list_scope_external_userids()
    context = _build_context(external_userids)

    items: list[CustomerListItemDTO] = []
    for external_userid in external_userids:
        item = _build_customer_list_item(external_userid, context)
        marketing_summary = _build_marketing_summary_from_context(external_userid, context)
        if _matches_filters(item, normalized_filters, marketing_summary):
            items.append(item)

    items.sort(key=lambda item: (item.updated_at, item.external_userid), reverse=True)
    sliced = items[offset : offset + limit]
    return _customer_list_result(
        items=sliced,
        total=len(items),
        limit=limit,
        offset=offset,
        filters=normalized_filters,
    )


def _list_customers_impl(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_filters = {key: str(value or "").strip() for key, value in (filters or {}).items()}
    limit = _normalize_limit(normalized_filters.get("limit"))
    offset = _normalize_offset(normalized_filters.get("offset"))
    _normalize_bool_filter(normalized_filters.get("is_bound"))
    if _has_marketing_filters(normalized_filters):
        _normalize_optional_bool_filter(
            normalized_filters.get("eligible_for_conversion"),
            field_name="eligible_for_conversion",
        )
        return _list_customers_with_marketing_filters(normalized_filters, limit=limit, offset=offset)

    total = count_customer_scope_external_userids(normalized_filters)
    external_userids = list_customer_scope_external_userids(
        normalized_filters,
        limit=limit,
        offset=offset,
    )
    context = _build_context(external_userids)
    item_by_external_userid = {
        external_userid: _build_customer_list_item(external_userid, context)
        for external_userid in external_userids
    }
    items = [
        item_by_external_userid[external_userid]
        for external_userid in external_userids
        if external_userid in item_by_external_userid
    ]
    return _customer_list_result(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        filters=normalized_filters,
    )


def list_customers(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Legacy compatibility wrapper around the Wave 1 customer read-model query."""

    from ..application.customer_read_model import CustomerListQueryDTO, ListCustomersQuery

    raw_filters = dict(filters or {})
    return ListCustomersQuery()(
        CustomerListQueryDTO(
            owner_userid=str(raw_filters.get("owner_userid", "") or ""),
            tag=str(raw_filters.get("tag", "") or ""),
            status=str(raw_filters.get("status", "") or ""),
            is_bound=str(raw_filters.get("is_bound", "") or ""),
            marketing_segment=str(raw_filters.get("marketing_segment", "") or ""),
            marketing_main_stage=str(raw_filters.get("marketing_main_stage", "") or ""),
            marketing_sub_stage=str(raw_filters.get("marketing_sub_stage", "") or ""),
            eligible_for_conversion=str(raw_filters.get("eligible_for_conversion", "") or ""),
            mobile=str(raw_filters.get("mobile", "") or ""),
            keyword=str(raw_filters.get("keyword", "") or ""),
            limit=raw_filters.get("limit", ""),
            offset=raw_filters.get("offset", ""),
        )
    )


def _get_customer_detail_impl(external_userid: str, *, refresh_tags: bool = False) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None

    external_userids = list_scope_external_userids()
    if normalized_external_userid not in set(external_userids):
        return None
    if refresh_tags:
        # NOTE: Stays synchronous because callers (MCP tools, admin UI)
        # contractually expect the returned payload to reflect the freshest
        # WeCom-side tags. A queued/async variant would require an additive
        # parameter (e.g. ``async_refresh=True``) plus a coordinated UI
        # change; tracked as a follow-up rather than silently changing the
        # legacy contract here.
        refresh_contact_tags_for_external_userid(external_userid=normalized_external_userid)

    context = _build_context([normalized_external_userid])
    list_item = _build_customer_list_item(normalized_external_userid, context)
    binding = context["bindings"].get(normalized_external_userid, {})
    identity = context["identities"].get(normalized_external_userid, {})
    follow_users_raw = context["follow_users"].get(normalized_external_userid, [])
    owner_role = context["owner_roles"].get(list_item.owner_userid, {})
    marketing_summary = _build_marketing_summary_from_context(normalized_external_userid, context)
    marketing_profile = get_customer_marketing_profile(normalized_external_userid)

    detail = CustomerDetailDTO(
        external_userid=list_item.external_userid,
        customer_name=list_item.customer_name,
        owner_userid=list_item.owner_userid,
        owner_display_name=str(owner_role.get("display_name") or "").strip() or list_item.owner_userid,
        remark=list_item.remark,
        description=list_item.description,
        mobile=list_item.mobile,
        is_bound=list_item.is_bound,
        binding_status=list_item.binding_status,
        follow_user_userids=list_item.follow_user_userids,
        tags=list_item.tags,
        class_user_status=list_item.class_user_status,
        last_message_at=list_item.last_message_at,
        last_touch_at=list_item.last_touch_at,
        updated_at=list_item.updated_at,
        binding=CustomerBindingDTO(
            is_bound=bool(binding),
            person_id=binding.get("person_id"),
            mobile=str(binding.get("mobile") or "").strip(),
            third_party_user_id=str(binding.get("third_party_user_id") or "").strip(),
            first_bound_by_userid=str(binding.get("first_bound_by_userid") or "").strip(),
            first_owner_userid=str(binding.get("first_owner_userid") or "").strip(),
            last_owner_userid=str(binding.get("last_owner_userid") or "").strip(),
            created_at=str(binding.get("created_at") or "").strip(),
            updated_at=str(binding.get("updated_at") or "").strip(),
        ),
        identity=CustomerIdentityDTO(
            person_id=binding.get("person_id"),
            unionid=str(identity.get("unionid") or "").strip(),
            openid=str(identity.get("openid") or "").strip(),
            follow_user_userid=str(identity.get("follow_user_userid") or "").strip(),
            status=str(identity.get("status") or "").strip(),
            created_at=str(identity.get("created_at") or "").strip(),
            updated_at=str(identity.get("updated_at") or "").strip(),
        ),
        follow_users=[CustomerFollowUserDTO(**item) for item in follow_users_raw],
        marketing_summary=marketing_summary,
        marketing_profile=marketing_profile,
        contact={
            "external_userid": normalized_external_userid,
            "customer_name": str(context["contacts"].get(normalized_external_userid, {}).get("customer_name") or "").strip(),
            "owner_userid": str(context["contacts"].get(normalized_external_userid, {}).get("owner_userid") or "").strip(),
            "remark": str(context["contacts"].get(normalized_external_userid, {}).get("remark") or "").strip(),
            "description": str(context["contacts"].get(normalized_external_userid, {}).get("description") or "").strip(),
            "updated_at": str(context["contacts"].get(normalized_external_userid, {}).get("updated_at") or "").strip(),
        },
        sidebar_context={
            "binding_status": list_item.binding_status,
            "is_bound": list_item.is_bound,
            "mobile": list_item.mobile,
            "follow_user_userids": list_item.follow_user_userids,
            "signup_tag_status": {
                "current_signup_status": list_item.class_user_status.signup_status,
                "current_tag": list_item.class_user_status.signup_label_name,
                "wecom_tag_sync_status": list_item.class_user_status.wecom_tag_sync_status,
                "wecom_tag_sync_error": list_item.class_user_status.wecom_tag_sync_error,
            },
            "marketing_profile": marketing_profile,
        },
    )
    detail_payload = detail.to_dict()
    if is_customer_pulse_enabled():
        detail_payload["customer_pulse"] = build_customer_pulse(normalized_external_userid)
    return detail_payload


def get_customer_detail(external_userid: str, *, refresh_tags: bool = False) -> dict[str, Any] | None:
    """Legacy compatibility wrapper around the Wave 1 customer read-model query."""

    from ..application.customer_read_model import CustomerDetailQueryDTO, GetCustomerDetailQuery

    return GetCustomerDetailQuery()(
        CustomerDetailQueryDTO(
            external_userid=external_userid,
            refresh_tags=refresh_tags,
        )
    )
