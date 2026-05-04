"""Customer read-model application skeleton for Wave 1."""

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
from .queries import (
    GetCustomerChatContextQuery,
    GetCustomerDetailQuery,
    GetCustomerTimelineQuery,
    ListCustomersQuery,
    ListRecentMessagesQuery,
)

__all__ = [
    "CustomerChatContextQueryDTO",
    "CustomerChatContextResultDTO",
    "CustomerDetailQueryDTO",
    "CustomerDetailResultDTO",
    "CustomerListQueryDTO",
    "CustomerListResultDTO",
    "CustomerTimelineQueryDTO",
    "CustomerTimelineResultDTO",
    "GetCustomerChatContextQuery",
    "GetCustomerDetailQuery",
    "GetCustomerTimelineQuery",
    "ListCustomersQuery",
    "ListRecentMessagesQuery",
    "RecentMessagesQueryDTO",
    "RecentMessagesResultDTO",
]
