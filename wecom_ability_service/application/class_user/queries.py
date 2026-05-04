from __future__ import annotations

from . import _legacy_delegate
from .dto import (
    ExportClassUserManagementRecordsQueryDTO,
    ExportClassUserManagementRecordsResultDTO,
    GetClassUserSnapshotQueryDTO,
    GetClassUserSnapshotResultDTO,
    GetClassUserStatusCurrentQueryDTO,
    GetClassUserStatusCurrentResultDTO,
    GetClassUserStatusDefinitionQueryDTO,
    GetClassUserStatusDefinitionResultDTO,
    ListClassUserManagementRecordsQueryDTO,
    ListClassUserManagementRecordsResultDTO,
    ListClassUserStatusHistoryQueryDTO,
    ListClassUserStatusHistoryResultDTO,
)


class GetClassUserStatusDefinitionQuery:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.get_class_user_status_definition`` via ``_legacy_delegate`` for marketing automation and future user-ops callers."""

    def __call__(
        self,
        dto: GetClassUserStatusDefinitionQueryDTO,
    ) -> GetClassUserStatusDefinitionResultDTO:
        return _legacy_delegate.get_class_user_status_definition_legacy(dto)

    execute = __call__


class GetClassUserStatusCurrentQuery:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.get_class_user_status_current`` via ``_legacy_delegate`` for sidebar, admin, and customer-read callers."""

    def __call__(
        self,
        dto: GetClassUserStatusCurrentQueryDTO,
    ) -> GetClassUserStatusCurrentResultDTO:
        return _legacy_delegate.get_class_user_status_current_legacy(dto)

    execute = __call__


class GetClassUserSnapshotQuery:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.get_class_user_snapshot`` via ``_legacy_delegate`` for admin-support and marketing-automation callers."""

    def __call__(self, dto: GetClassUserSnapshotQueryDTO) -> GetClassUserSnapshotResultDTO:
        return _legacy_delegate.get_class_user_snapshot_legacy(dto)

    execute = __call__


class ListSignupScopeExternalUseridsQuery:
    """Wave 2 class-user helper query that delegates to ``domains.class_user.service.list_signup_scope_external_userids`` via ``_legacy_delegate`` for admin-support live-read callers."""

    def __call__(self, corp_id: str) -> list[str]:
        return _legacy_delegate.list_signup_scope_external_userids_legacy(str(corp_id or "").strip())

    execute = __call__


class ListClassUserLiveBaseRowsQuery:
    """Wave 2 class-user helper query that delegates to ``domains.class_user.service.list_class_user_live_base_rows`` via ``_legacy_delegate`` for admin-support live-read callers."""

    def __call__(self, corp_id: str) -> list[dict[str, object]]:
        return _legacy_delegate.list_class_user_live_base_rows_legacy(str(corp_id or "").strip())

    execute = __call__


class ListClassUserStatusHistoryQuery:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.list_class_user_status_history`` via ``_legacy_delegate`` for admin class-user and operations-shell callers."""

    def __call__(
        self,
        dto: ListClassUserStatusHistoryQueryDTO | None = None,
    ) -> ListClassUserStatusHistoryResultDTO:
        return _legacy_delegate.list_class_user_status_history_legacy(
            dto or ListClassUserStatusHistoryQueryDTO()
        )

    execute = __call__


class ListClassUserManagementRecordsQuery:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.list_class_user_management_records`` via ``_legacy_delegate`` for admin class-user and operations-shell callers."""

    def __call__(
        self,
        dto: ListClassUserManagementRecordsQueryDTO | None = None,
    ) -> ListClassUserManagementRecordsResultDTO:
        return _legacy_delegate.list_class_user_management_records_legacy(
            dto or ListClassUserManagementRecordsQueryDTO()
        )

    execute = __call__


class ExportClassUserManagementRecordsQuery:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.export_class_user_management_records`` via ``_legacy_delegate`` for admin export callers."""

    def __call__(
        self,
        dto: ExportClassUserManagementRecordsQueryDTO | None = None,
    ) -> ExportClassUserManagementRecordsResultDTO:
        return _legacy_delegate.export_class_user_management_records_legacy(
            dto or ExportClassUserManagementRecordsQueryDTO()
        )

    execute = __call__


__all__ = [
    "ExportClassUserManagementRecordsQuery",
    "GetClassUserSnapshotQuery",
    "GetClassUserStatusCurrentQuery",
    "GetClassUserStatusDefinitionQuery",
    "ListClassUserLiveBaseRowsQuery",
    "ListClassUserManagementRecordsQuery",
    "ListSignupScopeExternalUseridsQuery",
    "ListClassUserStatusHistoryQuery",
]
