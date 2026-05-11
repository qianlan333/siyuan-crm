from __future__ import annotations

from ...domains.routing_config import service as routing_domain_service
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
    def __call__(self, dto: GetOwnerRoleQueryDTO) -> GetOwnerRoleQueryResultDTO:
        return routing_domain_service.get_owner_role(str(dto.userid or "").strip())

    execute = __call__


class GetOwnerRoleMapQuery:
    def __call__(
        self,
        dto: GetOwnerRoleMapQueryDTO | None = None,
    ) -> GetOwnerRoleMapResultDTO:
        dto = dto or GetOwnerRoleMapQueryDTO()
        return routing_domain_service.list_owner_role_map(active_only=bool(dto.active_only))

    execute = __call__


class GetRoutingRuleQuery:
    def __call__(self, dto: GetRoutingRuleQueryDTO) -> GetRoutingRuleQueryResultDTO:
        return routing_domain_service.get_routing_rule(str(dto.rule_key or "").strip())

    execute = __call__


class GetRoutingRuleConfigQuery:
    def __call__(
        self,
        dto: GetRoutingRuleConfigQueryDTO | None = None,
    ) -> GetRoutingRuleConfigResultDTO:
        dto = dto or GetRoutingRuleConfigQueryDTO()
        owner_role_map = routing_domain_service.list_owner_role_map(active_only=bool(dto.active_only))
        routing_rules = {
            str(item.get("rule_key") or "").strip(): dict(item)
            for item in routing_domain_service.list_routing_rules(active_only=bool(dto.active_only))
        }
        payload = routing_domain_service.build_routing_config(
            owner_role_map=owner_role_map,
            signup_tag_rules=dict(dto.signup_tag_rules or {}),
        )
        payload["routing_rules"] = routing_rules
        payload["owner_role_options"] = list(routing_domain_service.OWNER_ROLE_OPTIONS)
        payload["routing_target_options"] = list(routing_domain_service.ROUTING_TARGET_OPTIONS)
        return payload

    execute = __call__


class ResolveContactRoutingContextQuery:
    def __call__(
        self,
        dto: ResolveContactRoutingContextQueryDTO,
    ) -> ResolveContactRoutingContextResultDTO:
        return routing_domain_service.resolve_contact_routing_context(
            owner_userid=str(dto.owner_userid or "").strip(),
            owner_role=str(dto.owner_role or "").strip(),
            signup_status=str(dto.signup_status or "").strip(),
            routing_alias=str(dto.routing_alias or "").strip(),
        )

    execute = __call__


__all__ = [
    "GetOwnerRoleMapQuery",
    "GetOwnerRoleQuery",
    "GetRoutingRuleConfigQuery",
    "GetRoutingRuleQuery",
    "ResolveContactRoutingContextQuery",
]
