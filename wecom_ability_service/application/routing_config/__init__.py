"""Routing config application skeleton for Wave 2."""

from .commands import (
    SaveOwnerRoleSettingCommand,
    SaveRoutingRuleSettingCommand,
)
from .dto import (
    GetOwnerRoleMapQueryDTO,
    GetOwnerRoleMapResultDTO,
    GetOwnerRoleQueryDTO,
    GetOwnerRoleQueryResultDTO,
    GetRoutingRuleConfigQueryDTO,
    GetRoutingRuleConfigResultDTO,
    GetRoutingRuleQueryDTO,
    GetRoutingRuleQueryResultDTO,
    ResolveContactRoutingContextQueryDTO,
    ResolveContactRoutingContextResultDTO,
    SaveOwnerRoleSettingCommandDTO,
    SaveOwnerRoleSettingResultDTO,
    SaveRoutingRuleSettingCommandDTO,
    SaveRoutingRuleSettingResultDTO,
)
from .queries import (
    GetOwnerRoleMapQuery,
    GetOwnerRoleQuery,
    GetRoutingRuleConfigQuery,
    GetRoutingRuleQuery,
    ResolveContactRoutingContextQuery,
)

__all__ = [
    "GetOwnerRoleMapQuery",
    "GetOwnerRoleMapQueryDTO",
    "GetOwnerRoleMapResultDTO",
    "GetOwnerRoleQuery",
    "GetOwnerRoleQueryDTO",
    "GetOwnerRoleQueryResultDTO",
    "GetRoutingRuleConfigQuery",
    "GetRoutingRuleConfigQueryDTO",
    "GetRoutingRuleConfigResultDTO",
    "GetRoutingRuleQuery",
    "GetRoutingRuleQueryDTO",
    "GetRoutingRuleQueryResultDTO",
    "ResolveContactRoutingContextQuery",
    "ResolveContactRoutingContextQueryDTO",
    "ResolveContactRoutingContextResultDTO",
    "SaveOwnerRoleSettingCommand",
    "SaveOwnerRoleSettingCommandDTO",
    "SaveOwnerRoleSettingResultDTO",
    "SaveRoutingRuleSettingCommand",
    "SaveRoutingRuleSettingCommandDTO",
    "SaveRoutingRuleSettingResultDTO",
]
