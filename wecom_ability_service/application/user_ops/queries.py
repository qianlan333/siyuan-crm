from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...domains.user_ops import page_service as user_ops_page_service
from ...domains.user_ops import service as user_ops_domain_service
from . import _runtime
from .dto import (
    ExportUserOpsPoolQueryDTO,
    ExportUserOpsPoolResultDTO,
    GetUserOpsOverviewQueryDTO,
    GetUserOpsOverviewResultDTO,
    ListLeadPoolQueryDTO,
    ListLeadPoolResultDTO,
    ListUserOpsHistoryQueryDTO,
    ListUserOpsHistoryResultDTO,
)

GetSidebarLeadPoolStatusResultDTO = dict[str, Any]
GetUserOpsDeferredJobCountsResultDTO = dict[str, Any]


@dataclass(slots=True)
class GetSidebarLeadPoolStatusQueryDTO:
    external_userid: str
    owner_userid: str = ""


class GetUserOpsOverviewQuery:
    def __call__(
        self,
        dto: GetUserOpsOverviewQueryDTO | None = None,
    ) -> GetUserOpsOverviewResultDTO:
        effective_dto = dto or GetUserOpsOverviewQueryDTO()
        return user_ops_page_service.get_user_ops_overview(**_runtime.filters_to_kwargs(effective_dto))

    execute = __call__


class ListLeadPoolQuery:
    def __call__(
        self,
        dto: ListLeadPoolQueryDTO | None = None,
    ) -> ListLeadPoolResultDTO:
        effective_dto = dto or ListLeadPoolQueryDTO()
        return user_ops_page_service.list_user_ops_pool(**_runtime.filters_to_kwargs(effective_dto))

    execute = __call__


class ListUserOpsHistoryQuery:
    def __call__(
        self,
        dto: ListUserOpsHistoryQueryDTO | None = None,
    ) -> ListUserOpsHistoryResultDTO:
        effective_dto = dto or ListUserOpsHistoryQueryDTO()
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.list_user_ops_history(limit=int(effective_dto.limit))

    execute = __call__


class ExportUserOpsPoolQuery:
    def __call__(
        self,
        dto: ExportUserOpsPoolQueryDTO | None = None,
    ) -> ExportUserOpsPoolResultDTO:
        effective_dto = dto or ExportUserOpsPoolQueryDTO()
        return user_ops_page_service.export_user_ops_pool(**_runtime.filters_to_kwargs(effective_dto))

    execute = __call__


class GetSidebarLeadPoolStatusQuery:
    def __call__(self, dto: GetSidebarLeadPoolStatusQueryDTO) -> GetSidebarLeadPoolStatusResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.get_sidebar_lead_pool_status(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
        )

    execute = __call__


class GetUserOpsDeferredJobCountsQuery:
    def __call__(self) -> GetUserOpsDeferredJobCountsResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.get_user_ops_deferred_job_counts()

    execute = __call__


__all__ = [
    "ExportUserOpsPoolQuery",
    "GetUserOpsDeferredJobCountsQuery",
    "GetUserOpsDeferredJobCountsResultDTO",
    "GetUserOpsOverviewQuery",
    "GetSidebarLeadPoolStatusQuery",
    "GetSidebarLeadPoolStatusQueryDTO",
    "GetSidebarLeadPoolStatusResultDTO",
    "ListLeadPoolQuery",
    "ListUserOpsHistoryQuery",
]
