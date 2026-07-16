from __future__ import annotations

from .admin_config.service_period_grid_accounts import ServicePeriodGridAccountService
from .service_period_grid_ports import FixtureServicePeriodGridAccountGateway
from .service_period.member_grid_sharing import ServicePeriodMemberGridAccessService
from .shared.runtime import fixture_mode


def build_service_period_member_grid_access_service() -> ServicePeriodMemberGridAccessService:
    account_gateway = (
        FixtureServicePeriodGridAccountGateway()
        if fixture_mode()
        else ServicePeriodGridAccountService()
    )
    return ServicePeriodMemberGridAccessService(account_gateway=account_gateway)
