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
    SaveOwnerRoleSettingCommandDTO,
    SaveOwnerRoleSettingResultDTO,
    SaveRoutingRuleSettingCommandDTO,
    SaveRoutingRuleSettingResultDTO,
)


def get_owner_role_legacy(dto: GetOwnerRoleQueryDTO) -> GetOwnerRoleQueryResultDTO:
    return routing_domain_service.get_owner_role(str(dto.userid or "").strip())


def get_owner_role_map_legacy(dto: GetOwnerRoleMapQueryDTO) -> GetOwnerRoleMapResultDTO:
    return routing_domain_service.list_owner_role_map(active_only=bool(dto.active_only))


def save_owner_role_setting_legacy(dto: SaveOwnerRoleSettingCommandDTO) -> SaveOwnerRoleSettingResultDTO:
    return routing_domain_service.save_owner_role_map_item(
        userid=str(dto.userid or "").strip(),
        display_name=str(dto.display_name or "").strip(),
        role=str(dto.role or "").strip(),
        active=dto.active,
    )


def get_routing_rule_legacy(dto: GetRoutingRuleQueryDTO) -> GetRoutingRuleQueryResultDTO:
    return routing_domain_service.get_routing_rule(str(dto.rule_key or "").strip())


def get_routing_rule_config_legacy(dto: GetRoutingRuleConfigQueryDTO) -> GetRoutingRuleConfigResultDTO:
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


def save_routing_rule_setting_legacy(
    dto: SaveRoutingRuleSettingCommandDTO,
) -> SaveRoutingRuleSettingResultDTO:
    return routing_domain_service.save_routing_rule_config_item(
        rule_key=str(dto.rule_key or "").strip(),
        routing_alias=str(dto.routing_alias or "").strip(),
        route_owner_userid=str(dto.route_owner_userid or "").strip(),
        route_owner_role=str(dto.route_owner_role or "").strip(),
        routing_target=str(dto.routing_target or "").strip(),
        fallback_target=str(dto.fallback_target or "").strip(),
        when_owner_role_sales=str(dto.when_owner_role_sales or "").strip(),
        when_owner_role_delivery=str(dto.when_owner_role_delivery or "").strip(),
        active=dto.active,
    )


def resolve_contact_routing_context_legacy(
    dto: ResolveContactRoutingContextQueryDTO,
) -> ResolveContactRoutingContextResultDTO:
    return routing_domain_service.resolve_contact_routing_context(
        owner_userid=str(dto.owner_userid or "").strip(),
        owner_role=str(dto.owner_role or "").strip(),
        signup_status=str(dto.signup_status or "").strip(),
        routing_alias=str(dto.routing_alias or "").strip(),
    )
