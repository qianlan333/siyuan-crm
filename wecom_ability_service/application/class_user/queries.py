from __future__ import annotations

from typing import Any

from ...domains.class_user import service as class_user_domain_service
from ...domains.contacts import repo as contacts_repo
from ...domains.tags import service as tags_domain_service
from ..identity_contact.dto import ResolvePersonIdentityQueryDTO
from ..identity_contact.queries import ResolvePersonIdentityQuery
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


def _get_contact_row_by_external_userid(external_userid: str) -> dict[str, Any] | None:
    row = contacts_repo.get_contact_row_by_external_userid(str(external_userid or "").strip())
    return dict(row) if row else None


def _resolve_person_identity_for_snapshot(*, external_userid: str = "", **_: Any) -> dict[str, Any]:
    return ResolvePersonIdentityQuery()(
        ResolvePersonIdentityQueryDTO(external_userid=str(external_userid or "").strip())
    )


class GetClassUserStatusDefinitionQuery:
    def __call__(
        self,
        dto: GetClassUserStatusDefinitionQueryDTO,
    ) -> GetClassUserStatusDefinitionResultDTO:
        return class_user_domain_service.get_class_user_status_definition(
            str(dto.signup_status or "").strip()
        )

    execute = __call__


class GetClassUserStatusCurrentQuery:
    def __call__(
        self,
        dto: GetClassUserStatusCurrentQueryDTO,
    ) -> GetClassUserStatusCurrentResultDTO:
        return class_user_domain_service.get_class_user_status_current(
            str(dto.external_userid or "").strip()
        )

    execute = __call__


class GetClassUserSnapshotQuery:
    def __call__(self, dto: GetClassUserSnapshotQueryDTO) -> GetClassUserSnapshotResultDTO:
        return class_user_domain_service.get_class_user_snapshot(
            str(dto.external_userid or "").strip(),
            str(dto.owner_userid or "").strip(),
            contact_loader=_get_contact_row_by_external_userid,
            person_identity_resolver=_resolve_person_identity_for_snapshot,
        )

    execute = __call__


class ListSignupScopeExternalUseridsQuery:
    def __call__(self, corp_id: str) -> list[str]:
        return class_user_domain_service.list_signup_scope_external_userids(
            str(corp_id or "").strip()
        )

    execute = __call__


class ListClassUserLiveBaseRowsQuery:
    def __call__(self, corp_id: str) -> list[dict[str, object]]:
        return class_user_domain_service.list_class_user_live_base_rows(
            str(corp_id or "").strip()
        )

    execute = __call__


class ListClassUserStatusHistoryQuery:
    def __call__(
        self,
        dto: ListClassUserStatusHistoryQueryDTO | None = None,
    ) -> ListClassUserStatusHistoryResultDTO:
        dto = dto or ListClassUserStatusHistoryQueryDTO()
        return class_user_domain_service.list_class_user_status_history(limit=int(dto.limit))

    execute = __call__


class ListClassUserManagementRecordsQuery:
    def __call__(
        self,
        dto: ListClassUserManagementRecordsQueryDTO | None = None,
    ) -> ListClassUserManagementRecordsResultDTO:
        dto = dto or ListClassUserManagementRecordsQueryDTO()
        return class_user_domain_service.list_class_user_management_records(
            signup_status=str(dto.signup_status or "").strip(),
            get_signup_status_definitions=tags_domain_service.get_signup_status_definitions,
        )

    execute = __call__


class ExportClassUserManagementRecordsQuery:
    def __call__(
        self,
        dto: ExportClassUserManagementRecordsQueryDTO | None = None,
    ) -> ExportClassUserManagementRecordsResultDTO:
        dto = dto or ExportClassUserManagementRecordsQueryDTO()
        return class_user_domain_service.export_class_user_management_records(
            signup_status=str(dto.signup_status or "").strip(),
            get_signup_status_definitions=tags_domain_service.get_signup_status_definitions,
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
