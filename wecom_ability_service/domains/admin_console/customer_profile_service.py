from __future__ import annotations

from typing import Any

from ...application.customer_read_model import (
    CustomerDetailQueryDTO,
    CustomerListQueryDTO,
    GetCustomerDetailQuery,
    ListCustomersQuery,
)
from ...domains.archive.service import extract_roomid_from_raw_payload, format_message_row
from ...domains.marketing_automation.presenter import business_marketing_display
from ...domains.group_chats.repo import get_group_chat_map
from ...infra.wecom_runtime import get_contact_runtime_client
from . import customer_profile_repo as repo

CUSTOMER_PAGE_LIMIT = 50
CUSTOMER_DEFAULT_MESSAGE_LIMIT = 30
CUSTOMER_MAX_MESSAGE_LIMIT = 200
CUSTOMER_FETCH_ALL_MESSAGE_LIMIT = 1000


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_limit(value: Any, *, default: int, maximum: int) -> int:
    try:
        limit = int(value or default)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, maximum))


def _normalize_offset(value: Any) -> int:
    try:
        offset = int(value or 0)
    except (TypeError, ValueError):
        offset = 0
    return max(offset, 0)


def _normalize_bool(value: Any) -> bool:
    return _normalized_text(value).lower() in {"1", "true", "yes", "on"}


def _customer_profile_contact_client():
    return get_contact_runtime_client()


def _empty_marketing_summary() -> dict[str, Any]:
    return {
        "main_stage": "",
        "sub_stage": "",
        "segment": "unknown",
        "hit_count": 0,
        "eligible_for_conversion": False,
        "last_activation_at": "",
        "last_conversion_marked_at": "",
        "last_dispatch_at": "",
    }


def _build_customer_page_marketing_summary(
    marketing_summary: dict[str, Any],
    marketing_profile: dict[str, Any],
) -> dict[str, Any]:
    preview_summary = dict((marketing_profile or {}).get("summary") or {})
    fallback_display = business_marketing_display(
        main_stage=marketing_summary.get("main_stage"),
        sub_stage=marketing_summary.get("sub_stage"),
        segment=marketing_summary.get("segment"),
        eligible_for_conversion=marketing_summary.get("eligible_for_conversion"),
    )
    return {
        "stage_label": _normalized_text(preview_summary.get("current_stage_display")) or fallback_display["stage_label"],
        "segment_label": _normalized_text(preview_summary.get("current_segment_display")) or fallback_display["segment_label"],
        "hit_count": int(preview_summary.get("hit_count") or 0),
        "eligibility_label": _normalized_text(preview_summary.get("eligibility_display")) or fallback_display["eligibility_label"],
        "ineligible_reason_label": _normalized_text(preview_summary.get("ineligible_reason_display"))
        or fallback_display["ineligible_reason_label"],
        "last_activation_at": _normalized_text(marketing_summary.get("last_activation_at")),
        "last_conversion_marked_at": _normalized_text(marketing_summary.get("last_conversion_marked_at")),
        "last_dispatch_at": _normalized_text(marketing_summary.get("last_dispatch_at")),
    }


def _legacy_tab_to_section(tab: str) -> str:
    normalized_tab = _normalized_text(tab)
    mapping = {
        "basic": "customer-basic",
        "tags": "customer-live-tags",
        "questionnaires": "customer-questionnaire-answers",
        "recent-messages": "customer-message-records",
        "timeline": "customer-basic",
        "tasks": "customer-basic",
        "routing": "customer-basic",
    }
    return mapping.get(normalized_tab, "customer-basic")


def _message_speaker(message: dict[str, Any], customer: dict[str, Any]) -> str:
    sender = _normalized_text(message.get("sender"))
    external_userid = _normalized_text(customer.get("external_userid"))
    owner_userid = _normalized_text(customer.get("owner_userid"))
    customer_name = _normalized_text(customer.get("customer_name")) or "客户"
    owner_name = _normalized_text(customer.get("owner_display_name")) or owner_userid or "负责人"

    if sender == external_userid:
        return customer_name
    if sender and sender == owner_userid:
        return owner_name
    if sender:
        return sender
    return customer_name


def _load_customer_detail_with_lookup(
    *,
    external_userid: str = "",
    mobile: str = "",
    user_id: str = "",
    refresh_tags: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
    lookup = repo.resolve_profile_lookup(
        external_userid=external_userid,
        mobile=mobile,
        user_id=user_id,
    )
    if not lookup:
        return None, None
    resolved_external_userid = _normalized_text(lookup.get("external_userid"))
    detail = GetCustomerDetailQuery()(
        CustomerDetailQueryDTO(
            external_userid=resolved_external_userid,
            refresh_tags=refresh_tags,
        )
    )
    if not detail:
        return None, None
    return lookup, detail


def _profile_payload_from_detail(detail: dict[str, Any], *, lookup: dict[str, Any]) -> dict[str, Any]:
    external_userid = _normalized_text(detail.get("external_userid"))
    identity = dict(detail.get("identity") or {})
    return {
        "profile": {
            "customer_name": _normalized_text(detail.get("customer_name")) or external_userid or "未命名客户",
            "mobile": _normalized_text(detail.get("mobile")),
            "owner": _normalized_text(detail.get("owner_display_name")) or _normalized_text(detail.get("owner_userid")),
            "owner_userid": _normalized_text(detail.get("owner_userid")),
            "user_id": external_userid,
            "external_userid": external_userid,
            "unionid": _normalized_text(identity.get("unionid")),
            "marketing_profile": dict(detail.get("marketing_profile") or {}),
            "marketing_summary": dict(detail.get("marketing_summary") or _empty_marketing_summary()),
        },
        "lookup": dict(lookup or {}),
    }


def build_customer_list_payload(args: Any) -> dict[str, Any]:
    keyword = _normalized_text(getattr(args, "get", lambda *_: "")("keyword"))
    owner = _normalized_text(getattr(args, "get", lambda *_: "")("owner")) or _normalized_text(
        getattr(args, "get", lambda *_: "")("owner_userid")
    )
    mobile = _normalized_text(getattr(args, "get", lambda *_: "")("mobile"))
    tag = _normalized_text(getattr(args, "get", lambda *_: "")("tag"))
    offset = _normalized_text(getattr(args, "get", lambda *_: "")("offset")) or "0"
    payload = ListCustomersQuery()(
        CustomerListQueryDTO(
            keyword=keyword,
            owner_userid=owner,
            mobile=mobile,
            tag=tag,
            limit=CUSTOMER_PAGE_LIMIT,
            offset=offset,
        )
    )
    rows = payload.get("items") or payload.get("customers") or []
    customers = [
        {
            "external_userid": _normalized_text(item.get("external_userid")),
            "customer_name": _normalized_text(item.get("customer_name")) or _normalized_text(item.get("external_userid")) or "未命名客户",
            "owner_userid": _normalized_text(item.get("owner_userid")),
            "owner_display_name": _normalized_text(item.get("owner_display_name")) or _normalized_text(item.get("owner_userid")),
            "mobile": _normalized_text(item.get("mobile")),
        }
        for item in rows
    ]
    limit = CUSTOMER_PAGE_LIMIT
    current_offset = _normalize_offset(payload.get("offset"))
    total = int(payload.get("total") or payload.get("count") or len(customers))
    next_offset = current_offset + limit
    prev_offset = max(current_offset - limit, 0)
    return {
        "customers": customers,
        "filters": {
            "keyword": keyword,
            "owner": owner,
            "mobile": mobile,
            "tag": tag,
        },
        "pagination": {
            "total": total,
            "offset": current_offset,
            "limit": limit,
            "has_prev": current_offset > 0,
            "has_next": next_offset < total,
            "prev_offset": prev_offset,
            "next_offset": next_offset,
        },
    }


def get_customer_profile_payload(
    *,
    external_userid: str = "",
    mobile: str = "",
    user_id: str = "",
) -> dict[str, Any] | None:
    lookup, detail = _load_customer_detail_with_lookup(
        external_userid=external_userid,
        mobile=mobile,
        user_id=user_id,
    )
    if not lookup or not detail:
        return None
    return _profile_payload_from_detail(detail, lookup=lookup)


def build_customer_detail_payload(external_userid: str, *, legacy_tab: str = "") -> dict[str, Any] | None:
    lookup, detail = _load_customer_detail_with_lookup(external_userid=external_userid)
    if not lookup or not detail:
        return None
    payload = _profile_payload_from_detail(detail, lookup=lookup)
    marketing_summary = dict(payload["profile"].get("marketing_summary") or _empty_marketing_summary())
    marketing_profile = dict(payload["profile"].get("marketing_profile") or {})
    marketing_page_summary = _build_customer_page_marketing_summary(marketing_summary, marketing_profile)
    payload["profile"]["marketing_summary"] = marketing_summary
    payload["profile"]["marketing_page_summary"] = marketing_page_summary
    payload["profile"]["marketing_display"] = {
        "stage_label": marketing_page_summary["stage_label"],
        "segment_label": marketing_page_summary["segment_label"],
        "eligibility_label": marketing_page_summary["eligibility_label"],
        "ineligible_reason_label": marketing_page_summary["ineligible_reason_label"],
    }
    return {
        "customer": payload["profile"],
        "lookup": payload.get("lookup") or {},
        "initial_section": _legacy_tab_to_section(legacy_tab),
    }


def get_customer_profile_tags_payload(*, external_userid: str) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid 不能为空")
    detail = _customer_profile_contact_client().get_contact(normalized_external_userid)
    tags: list[dict[str, str]] = []
    seen_tag_ids: set[str] = set()
    for follow_user in detail.get("follow_user") or []:
        owner_userid = _normalized_text((follow_user or {}).get("userid"))
        for tag in (follow_user or {}).get("tags") or []:
            tag_id = _normalized_text((tag or {}).get("tag_id") or (tag or {}).get("id"))
            tag_name = _normalized_text((tag or {}).get("tag_name") or (tag or {}).get("name"))
            if not tag_id or tag_id in seen_tag_ids:
                continue
            seen_tag_ids.add(tag_id)
            tags.append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "owner_userid": owner_userid,
                }
            )
    return {
        "external_userid": normalized_external_userid,
        "tags": tags,
    }


def get_customer_questionnaire_answers_payload(
    *,
    external_userid: str = "",
    mobile: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    profile_payload = get_customer_profile_payload(
        external_userid=external_userid,
        mobile=mobile,
        user_id=user_id,
    )
    if not profile_payload:
        raise LookupError("customer not found")
    profile = profile_payload["profile"]
    lookup = profile_payload.get("lookup") or {}
    answers = repo.list_customer_questionnaire_answers(
        external_userid=_normalized_text(profile.get("external_userid")),
        mobile=_normalized_text(profile.get("mobile")),
    )
    return {
        "external_userid": _normalized_text(profile.get("external_userid")),
        "mobile": _normalized_text(profile.get("mobile")),
        "answers": answers,
        "count": len(answers),
        "lookup": lookup,
    }


def get_customer_messages_payload(
    *,
    external_userid: str = "",
    mobile: str = "",
    user_id: str = "",
    limit: Any = "",
    fetch_all: Any = "",
) -> dict[str, Any]:
    profile_payload = get_customer_profile_payload(
        external_userid=external_userid,
        mobile=mobile,
        user_id=user_id,
    )
    if not profile_payload:
        raise LookupError("customer not found")
    profile = profile_payload["profile"]
    normalized_fetch_all = _normalize_bool(fetch_all)
    effective_limit = (
        CUSTOMER_FETCH_ALL_MESSAGE_LIMIT
        if normalized_fetch_all
        else _normalize_limit(limit, default=CUSTOMER_DEFAULT_MESSAGE_LIMIT, maximum=CUSTOMER_MAX_MESSAGE_LIMIT)
    )
    rows = repo.list_customer_message_rows(_normalized_text(profile.get("external_userid")), limit=effective_limit)
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    messages = []
    for row in reversed(rows):
        formatted = format_message_row(row, group_map=group_map)
        messages.append(
            {
                "id": int(row["id"]),
                "send_time": _normalized_text(row.get("send_time")) or _normalized_text(row.get("created_at")),
                "speaker": _message_speaker(row, profile),
                "content": _normalized_text(formatted.get("content") or row.get("content")),
                "sender": _normalized_text(row.get("sender")),
                "receiver": _normalized_text(row.get("receiver")),
                "msgtype": _normalized_text(formatted.get("msgtype") or row.get("msgtype")),
            }
        )
    return {
        "external_userid": _normalized_text(profile.get("external_userid")),
        "mobile": _normalized_text(profile.get("mobile")),
        "fetch_all": normalized_fetch_all,
        "limit": effective_limit,
        "messages": messages,
        "count": len(messages),
        "lookup": profile_payload.get("lookup") or {},
    }


