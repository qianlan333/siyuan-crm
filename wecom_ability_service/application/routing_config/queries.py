from __future__ import annotations

from . import _legacy_delegate
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
)


class GetOwnerRoleQuery:
    """Wave 2 routing-config skeleton that delegates to ``domains.routing_config.service.get_owner_role`` via ``_legacy_delegate`` for contact enrichment and admin config callers."""

    def __call__(self, dto: GetOwnerRoleQueryDTO) -> GetOwnerRoleQueryResultDTO:
        return _legacy_delegate.get_owner_role_legacy(dto)

    execute = __call__


class GetOwnerRoleMapQuery:
    """Wave 2 routing-config skeleton that delegates to ``domains.routing_config.service.list_owner_role_map`` via ``_legacy_delegate`` for admin config, MCP, and compatibility-service callers."""

    def __call__(
        self,
        dto: GetOwnerRoleMapQueryDTO | None = None,
    ) -> GetOwnerRoleMapResultDTO:
        return _legacy_delegate.get_owner_role_map_legacy(dto or GetOwnerRoleMapQueryDTO())

    execute = __call__


class GetRoutingRuleQuery:
    """Wave 2 routing-config skeleton that delegates to ``domains.routing_config.service.get_routing_rule`` via ``_legacy_delegate`` for admin config edit flows."""

    def __call__(self, dto: GetRoutingRuleQueryDTO) -> GetRoutingRuleQueryResultDTO:
        return _legacy_delegate.get_routing_rule_legacy(dto)

    execute = __call__


class GetRoutingRuleConfigQuery:
    """Wave 2 routing-config skeleton that delegates to ``domains.routing_config.service.build_routing_config`` and related legacy reads via ``_legacy_delegate`` for admin config and compatibility-service callers."""

    def __call__(
        self,
        dto: GetRoutingRuleConfigQueryDTO | None = None,
    ) -> GetRoutingRuleConfigResultDTO:
        return _legacy_delegate.get_routing_rule_config_legacy(dto or GetRoutingRuleConfigQueryDTO())

    execute = __call__


class ResolveContactRoutingContextQuery:
    """Wave 2 routing-config skeleton that delegates to ``domains.routing_config.service.resolve_contact_routing_context`` via ``_legacy_delegate`` for contact enrichment and compatibility-service callers."""

    def __call__(
        self,
        dto: ResolveContactRoutingContextQueryDTO,
    ) -> ResolveContactRoutingContextResultDTO:
        return _legacy_delegate.resolve_contact_routing_context_legacy(dto)

    execute = __call__


__all__ = [
    "GetOwnerRoleMapQuery",
    "GetOwnerRoleQuery",
    "GetRoutingRuleConfigQuery",
    "GetRoutingRuleQuery",
    "ResolveContactRoutingContextQuery",
]
