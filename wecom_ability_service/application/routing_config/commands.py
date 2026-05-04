from __future__ import annotations

from . import _legacy_delegate
from .dto import (
    SaveOwnerRoleSettingCommandDTO,
    SaveOwnerRoleSettingResultDTO,
    SaveRoutingRuleSettingCommandDTO,
    SaveRoutingRuleSettingResultDTO,
)


class SaveOwnerRoleSettingCommand:
    """Wave 2 routing-config skeleton that delegates to ``domains.routing_config.service.save_owner_role_map_item`` via ``_legacy_delegate`` for admin config writers and future config automation callers."""

    def __call__(self, dto: SaveOwnerRoleSettingCommandDTO) -> SaveOwnerRoleSettingResultDTO:
        return _legacy_delegate.save_owner_role_setting_legacy(dto)

    execute = __call__


class SaveRoutingRuleSettingCommand:
    """Wave 2 routing-config skeleton that delegates to ``domains.routing_config.service.save_routing_rule_config_item`` via ``_legacy_delegate`` for admin config writers and future config automation callers."""

    def __call__(self, dto: SaveRoutingRuleSettingCommandDTO) -> SaveRoutingRuleSettingResultDTO:
        return _legacy_delegate.save_routing_rule_setting_legacy(dto)

    execute = __call__


__all__ = [
    "SaveOwnerRoleSettingCommand",
    "SaveRoutingRuleSettingCommand",
]
