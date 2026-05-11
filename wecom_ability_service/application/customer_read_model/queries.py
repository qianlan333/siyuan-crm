from __future__ import annotations

from typing import cast

from .dto import (
    CustomerChatContextQueryDTO,
    CustomerChatContextResultDTO,
    CustomerDetailQueryDTO,
    CustomerDetailResultDTO,
    CustomerListQueryDTO,
    CustomerListResultDTO,
    CustomerTimelineQueryDTO,
    CustomerTimelineResultDTO,
    RecentMessagesQueryDTO,
    RecentMessagesResultDTO,
)


def _require_external_userid(external_userid: str) -> str:
    value = str(external_userid or "").strip()
    if not value:
        raise ValueError("external_userid is required")
    return value


def _default_timeline_payload(external_userid: str, *, timeline_limit: int) -> dict[str, object]:
    return {
        "external_userid": external_userid,
        "items": [],
        "count": 0,
        "limit": timeline_limit,
        "offset": 0,
        "filters": {"event_type": "", "limit": str(timeline_limit), "offset": "0"},
        "total": 0,
    }


class ListCustomersQuery:
    """Wave 1 skeleton that delegates to ``customer_center.service._list_customers_impl``."""

    def __call__(self, dto: CustomerListQueryDTO | None = None) -> CustomerListResultDTO:
        # Wave 1 skeleton: keep request normalization thin while routing through
        # the private legacy implementation instead of the public compatibility wrapper.
        from ...customer_center.routes import parse_customer_filters
        from ...customer_center.service import _list_customers_impl

        query = dto or CustomerListQueryDTO()
        filters = parse_customer_filters(
            {
                "owner_userid": query.owner_userid,
                "tag": query.tag,
                "status": query.status,
                "is_bound": query.is_bound,
                "marketing_segment": query.marketing_segment,
                "marketing_main_stage": query.marketing_main_stage,
                "marketing_sub_stage": query.marketing_sub_stage,
                "eligible_for_conversion": query.eligible_for_conversion,
                "mobile": query.mobile,
                "keyword": query.keyword,
                "limit": query.limit,
                "offset": query.offset,
            }
        )
        return cast(CustomerListResultDTO, _list_customers_impl(filters))

    execute = __call__


class GetCustomerDetailQuery:
    """Wave 1 skeleton that delegates to ``customer_center.service._get_customer_detail_impl``."""

    def __call__(self, dto: CustomerDetailQueryDTO) -> CustomerDetailResultDTO:
        from ...customer_center.service import _get_customer_detail_impl

        return cast(
            CustomerDetailResultDTO,
            _get_customer_detail_impl(
                _require_external_userid(dto.external_userid),
                refresh_tags=bool(dto.refresh_tags),
            ),
        )

    execute = __call__


class GetCustomerTimelineQuery:
    """Wave 1 skeleton that delegates to ``customer_timeline.service._get_customer_timeline_impl``."""

    def __call__(self, dto: CustomerTimelineQueryDTO) -> CustomerTimelineResultDTO:
        from ...customer_timeline.routes import parse_timeline_filters
        from ...customer_timeline.service import _get_customer_timeline_impl

        filters = parse_timeline_filters(
            {
                "event_type": dto.event_type,
                "limit": dto.limit,
                "offset": dto.offset,
            }
        )
        return cast(
            CustomerTimelineResultDTO,
            _get_customer_timeline_impl(
                _require_external_userid(dto.external_userid),
                filters,
            ),
        )

    execute = __call__


class GetCustomerChatContextQuery:
    """Wave 1 skeleton that delegates to customer read-model queries for detail/timeline/recent messages."""

    def __call__(self, dto: CustomerChatContextQueryDTO) -> CustomerChatContextResultDTO:
        external_userid = _require_external_userid(dto.external_userid)
        timeline_limit = int(dto.timeline_limit)
        customer = GetCustomerDetailQuery()(
            CustomerDetailQueryDTO(
                external_userid=external_userid,
                refresh_tags=bool(dto.refresh_tags),
            )
        )
        timeline = GetCustomerTimelineQuery()(
            CustomerTimelineQueryDTO(
                external_userid=external_userid,
                limit=timeline_limit,
                offset=0,
                event_type="",
            )
        )
        recent_messages_payload = ListRecentMessagesQuery()(
            RecentMessagesQueryDTO(
                external_userid=external_userid,
                limit=int(dto.recent_message_limit),
            )
        )
        recent_messages = list(recent_messages_payload.get("messages") or [])
        normalized_timeline = timeline or _default_timeline_payload(
            external_userid,
            timeline_limit=timeline_limit,
        )
        return {
            "external_userid": external_userid,
            "customer": customer,
            "recent_messages": recent_messages,
            "timeline": normalized_timeline,
            "recent_timeline_events": list(normalized_timeline.get("items") or []),
            "source_status": "live",
            "degraded": False,
            "warnings": [],
        }

    execute = __call__


class ListRecentMessagesQuery:
    """Wave 1 skeleton that delegates to ``integration_gateway.DispatchMcpToolCommand`` -> infra MCP runtime for ``get_recent_messages``."""

    def __call__(self, dto: RecentMessagesQueryDTO) -> RecentMessagesResultDTO:
        from ..integration_gateway import DispatchMcpToolCommand

        command = DispatchMcpToolCommand()
        result = command(
            "get_recent_messages",
            {
                "external_userid": _require_external_userid(dto.external_userid),
                "limit": int(dto.limit),
                "chat_type": dto.chat_type,
            },
        )
        return cast(RecentMessagesResultDTO, result.get("structuredContent") or {})

    execute = __call__


__all__ = [
    "GetCustomerChatContextQuery",
    "GetCustomerDetailQuery",
    "GetCustomerTimelineQuery",
    "ListCustomersQuery",
    "ListRecentMessagesQuery",
]
