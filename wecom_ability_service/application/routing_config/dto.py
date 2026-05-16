from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


GetOwnerRoleQueryResultDTO = dict[str, Any] | None
GetOwnerRoleMapResultDTO = list[dict[str, Any]]
GetRoutingRuleQueryResultDTO = dict[str, Any] | None
GetRoutingRuleConfigResultDTO = dict[str, Any]
ResolveContactRoutingContextResultDTO = dict[str, Any]


@dataclass(slots=True)
class GetOwnerRoleQueryDTO:
    userid: str


@dataclass(slots=True)
class GetOwnerRoleMapQueryDTO:
    active_only: bool = False


@dataclass(slots=True)
class GetRoutingRuleQueryDTO:
    rule_key: str


@dataclass(slots=True)
class GetRoutingRuleConfigQueryDTO:
    active_only: bool = False
    signup_tag_rules: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolveContactRoutingContextQueryDTO:
    owner_userid: str = ""
    owner_role: str = ""
    signup_status: str = ""
    routing_alias: str = ""


__all__ = [
    "GetOwnerRoleMapQueryDTO",
    "GetOwnerRoleMapResultDTO",
    "GetOwnerRoleQueryDTO",
    "GetOwnerRoleQueryResultDTO",
    "GetRoutingRuleConfigQueryDTO",
    "GetRoutingRuleConfigResultDTO",
    "GetRoutingRuleQueryDTO",
    "GetRoutingRuleQueryResultDTO",
    "ResolveContactRoutingContextQueryDTO",
    "ResolveContactRoutingContextResultDTO",
]
