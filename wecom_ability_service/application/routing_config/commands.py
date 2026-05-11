from __future__ import annotations

from ...domains.routing_config import service as routing_domain_service
from .dto import (
    SaveOwnerRoleSettingCommandDTO,
    SaveOwnerRoleSettingResultDTO,
    SaveRoutingRuleSettingCommandDTO,
    SaveRoutingRuleSettingResultDTO,
)


class SaveOwnerRoleSettingCommand:
    def __call__(self, dto: SaveOwnerRoleSettingCommandDTO) -> SaveOwnerRoleSettingResultDTO:
        return routing_domain_service.save_owner_role_map_item(
            userid=str(dto.userid or "").strip(),
            display_name=str(dto.display_name or "").strip(),
            role=str(dto.role or "").strip(),
            active=dto.active,
        )

    execute = __call__


class SaveRoutingRuleSettingCommand:
    def __call__(self, dto: SaveRoutingRuleSettingCommandDTO) -> SaveRoutingRuleSettingResultDTO:
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

    execute = __call__


__all__ = [
    "SaveOwnerRoleSettingCommand",
    "SaveRoutingRuleSettingCommand",
]
