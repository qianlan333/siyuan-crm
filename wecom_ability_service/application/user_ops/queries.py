from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import _legacy_delegate
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
    """Wave 2 user-ops query that delegates to ``domains.user_ops.page_service.get_user_ops_overview`` via ``_legacy_delegate`` for admin overview callers."""

    def __call__(
        self,
        dto: GetUserOpsOverviewQueryDTO | None = None,
    ) -> GetUserOpsOverviewResultDTO:
        return _legacy_delegate.get_user_ops_overview_legacy(dto or GetUserOpsOverviewQueryDTO())

    execute = __call__


class ListLeadPoolQuery:
    """Wave 2 user-ops query that delegates to ``domains.user_ops.page_service.list_user_ops_pool`` via ``_legacy_delegate`` for admin list callers."""

    def __call__(
        self,
        dto: ListLeadPoolQueryDTO | None = None,
    ) -> ListLeadPoolResultDTO:
        return _legacy_delegate.list_lead_pool_legacy(dto or ListLeadPoolQueryDTO())

    execute = __call__


class ListUserOpsHistoryQuery:
    """Wave 2 user-ops query that delegates to ``domains.user_ops.service.list_user_ops_history`` via ``_legacy_delegate`` for admin history callers."""

    def __call__(
        self,
        dto: ListUserOpsHistoryQueryDTO | None = None,
    ) -> ListUserOpsHistoryResultDTO:
        return _legacy_delegate.list_user_ops_history_legacy(dto or ListUserOpsHistoryQueryDTO())

    execute = __call__


class ExportUserOpsPoolQuery:
    """Wave 2 user-ops query that delegates to ``domains.user_ops.page_service.export_user_ops_pool`` via ``_legacy_delegate`` for admin export callers."""

    def __call__(
        self,
        dto: ExportUserOpsPoolQueryDTO | None = None,
    ) -> ExportUserOpsPoolResultDTO:
        return _legacy_delegate.export_user_ops_pool_legacy(dto or ExportUserOpsPoolQueryDTO())

    execute = __call__


class GetSidebarLeadPoolStatusQuery:
    """Wave 2 user-ops query that delegates to ``domains.user_ops.service.get_sidebar_lead_pool_status`` via ``_legacy_delegate`` for sidebar callers after caller cutover."""

    def __call__(self, dto: GetSidebarLeadPoolStatusQueryDTO) -> GetSidebarLeadPoolStatusResultDTO:
        _legacy_delegate._bind_user_ops_runtime()
        return _legacy_delegate.user_ops_domain_service.get_sidebar_lead_pool_status(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
        )

    execute = __call__


class GetUserOpsDeferredJobCountsQuery:
    """Wave 2 user-ops query that delegates to ``domains.user_ops.service.get_user_ops_deferred_job_counts`` via ``_legacy_delegate`` for admin jobs console and runtime status callers after caller cutover."""

    def __call__(self) -> GetUserOpsDeferredJobCountsResultDTO:
        _legacy_delegate._bind_user_ops_runtime()
        return _legacy_delegate.user_ops_domain_service.get_user_ops_deferred_job_counts()

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
