from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CustomerListResultDTO = dict[str, Any]
CustomerDetailResultDTO = dict[str, Any] | None
CustomerTimelineResultDTO = dict[str, Any] | None
CustomerChatContextResultDTO = dict[str, Any]
RecentMessagesResultDTO = dict[str, Any]
InternalAuthResultDTO = Any
McpRuntimeToolListResultDTO = list[dict[str, Any]]
SignupConversionBatchListResultDTO = dict[str, Any]
SignupConversionBatchDetailResultDTO = dict[str, Any] | None


@dataclass(slots=True)
class CustomerListQueryDTO:
    owner_userid: str = ""
    tag: str = ""
    status: str = ""
    is_bound: str = ""
    marketing_segment: str = ""
    marketing_main_stage: str = ""
    marketing_sub_stage: str = ""
    eligible_for_conversion: str = ""
    mobile: str = ""
    keyword: str = ""
    limit: int | str = ""
    offset: int | str = ""


@dataclass(slots=True)
class CustomerDetailQueryDTO:
    external_userid: str
    refresh_tags: bool = False


@dataclass(slots=True)
class CustomerTimelineQueryDTO:
    external_userid: str
    event_type: str = ""
    limit: int | str = 50
    offset: int | str = 0
    customer_pulse_tenant_context: dict[str, Any] | None = None


@dataclass(slots=True)
class CustomerChatContextQueryDTO:
    external_userid: str
    recent_message_limit: int = 20
    timeline_limit: int = 20
    refresh_tags: bool = False


@dataclass(slots=True)
class RecentMessagesQueryDTO:
    external_userid: str
    limit: int = 20
    chat_type: str | None = None


@dataclass(slots=True)
class InternalAuthQueryDTO:
    token_keys: tuple[str, ...] = ()
    legacy_header_names: tuple[str, ...] = ()
    require_configured: bool = False


@dataclass(slots=True)
class McpRuntimeToolListQueryDTO:
    enabled_only: bool = True


@dataclass(slots=True)
class SignupConversionBatchListQueryDTO:
    limit: int = 20
    cursor: str = ""
    scenario_key: str = ""


@dataclass(slots=True)
class SignupConversionBatchDetailQueryDTO:
    batch_id: int
    scenario_key: str = ""


__all__ = [
    "CustomerChatContextQueryDTO",
    "CustomerChatContextResultDTO",
    "CustomerDetailQueryDTO",
    "CustomerDetailResultDTO",
    "CustomerListQueryDTO",
    "CustomerListResultDTO",
    "CustomerTimelineQueryDTO",
    "CustomerTimelineResultDTO",
    "InternalAuthQueryDTO",
    "InternalAuthResultDTO",
    "McpRuntimeToolListQueryDTO",
    "McpRuntimeToolListResultDTO",
    "RecentMessagesQueryDTO",
    "RecentMessagesResultDTO",
    "SignupConversionBatchDetailQueryDTO",
    "SignupConversionBatchDetailResultDTO",
    "SignupConversionBatchListQueryDTO",
    "SignupConversionBatchListResultDTO",
]
