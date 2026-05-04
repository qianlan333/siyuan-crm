from __future__ import annotations

from typing import Any

from ...domains.class_user import service as class_user_domain_service
from ...domains.contacts import repo as contacts_repo
from ...domains.tags import service as tags_domain_service
from ..identity_contact.dto import ResolvePersonIdentityQueryDTO
from ..identity_contact.queries import ResolvePersonIdentityQuery
from .dto import (
    ApplyClassUserStatusChangeCommandDTO,
    ExportClassUserManagementRecordsQueryDTO,
    ClearClassUserStatusCurrentCommandDTO,
    GetClassUserSnapshotQueryDTO,
    GetClassUserStatusCurrentQueryDTO,
    GetClassUserStatusDefinitionQueryDTO,
    ListClassUserManagementRecordsQueryDTO,
    ListClassUserStatusHistoryQueryDTO,
    MigrateClassUserStatusFromContactTagsCommandDTO,
    UpdateClassUserStatusSyncResultCommandDTO,
)


def _get_contact_row_by_external_userid(external_userid: str) -> dict[str, Any] | None:
    row = contacts_repo.get_contact_row_by_external_userid(str(external_userid or "").strip())
    return dict(row) if row else None


def _resolve_person_identity_for_snapshot(*, external_userid: str = "", **_: Any) -> dict[str, Any]:
    return ResolvePersonIdentityQuery()(
        ResolvePersonIdentityQueryDTO(external_userid=str(external_userid or "").strip())
    )


def get_class_user_status_definition_legacy(dto: GetClassUserStatusDefinitionQueryDTO) -> dict[str, Any] | None:
    return class_user_domain_service.get_class_user_status_definition(str(dto.signup_status or "").strip())


def get_class_user_status_current_legacy(dto: GetClassUserStatusCurrentQueryDTO) -> dict[str, Any] | None:
    return class_user_domain_service.get_class_user_status_current(str(dto.external_userid or "").strip())


def get_class_user_snapshot_legacy(dto: GetClassUserSnapshotQueryDTO) -> dict[str, str]:
    return class_user_domain_service.get_class_user_snapshot(
        str(dto.external_userid or "").strip(),
        str(dto.owner_userid or "").strip(),
        contact_loader=_get_contact_row_by_external_userid,
        person_identity_resolver=_resolve_person_identity_for_snapshot,
    )


def list_signup_scope_external_userids_legacy(corp_id: str) -> list[str]:
    return class_user_domain_service.list_signup_scope_external_userids(str(corp_id or "").strip())


def list_class_user_live_base_rows_legacy(corp_id: str) -> list[dict[str, Any]]:
    return class_user_domain_service.list_class_user_live_base_rows(str(corp_id or "").strip())


def list_class_user_status_history_legacy(dto: ListClassUserStatusHistoryQueryDTO) -> dict[str, Any]:
    return class_user_domain_service.list_class_user_status_history(limit=int(dto.limit))


def list_class_user_management_records_legacy(
    dto: ListClassUserManagementRecordsQueryDTO,
) -> dict[str, Any]:
    return class_user_domain_service.list_class_user_management_records(
        signup_status=str(dto.signup_status or "").strip(),
        get_signup_status_definitions=tags_domain_service.get_signup_status_definitions,
    )


def export_class_user_management_records_legacy(
    dto: ExportClassUserManagementRecordsQueryDTO,
) -> dict[str, Any]:
    return class_user_domain_service.export_class_user_management_records(
        signup_status=str(dto.signup_status or "").strip(),
        get_signup_status_definitions=tags_domain_service.get_signup_status_definitions,
    )


def apply_class_user_status_change_legacy(
    dto: ApplyClassUserStatusChangeCommandDTO,
) -> dict[str, Any]:
    return class_user_domain_service.apply_class_user_status_change(
        external_userid=str(dto.external_userid or "").strip(),
        signup_status=str(dto.signup_status or "").strip(),
        set_by_userid=str(dto.set_by_userid or "").strip(),
        customer_name_snapshot=str(dto.customer_name_snapshot or "").strip(),
        owner_userid_snapshot=str(dto.owner_userid_snapshot or "").strip(),
        mobile_snapshot=str(dto.mobile_snapshot or "").strip(),
    )


def clear_class_user_status_current_legacy(
    dto: ClearClassUserStatusCurrentCommandDTO,
) -> None:
    return class_user_domain_service.clear_class_user_status_current(
        external_userid=str(dto.external_userid or "").strip(),
        set_by_userid=str(dto.set_by_userid or "").strip(),
        customer_name_snapshot=str(dto.customer_name_snapshot or "").strip(),
        owner_userid_snapshot=str(dto.owner_userid_snapshot or "").strip(),
        mobile_snapshot=str(dto.mobile_snapshot or "").strip(),
    )


def update_class_user_status_sync_result_legacy(
    dto: UpdateClassUserStatusSyncResultCommandDTO,
) -> None:
    return class_user_domain_service.update_class_user_status_sync_result(
        str(dto.external_userid or "").strip(),
        wecom_tag_sync_status=str(dto.wecom_tag_sync_status or "").strip(),
        wecom_tag_sync_error=str(dto.wecom_tag_sync_error or "").strip(),
    )


def migrate_class_user_status_from_contact_tags_legacy(
    _: MigrateClassUserStatusFromContactTagsCommandDTO | None = None,
) -> dict[str, Any]:
    return class_user_domain_service.migrate_class_user_status_from_contact_tags(
        get_signup_status_definition_by_tag_name=tags_domain_service.get_signup_status_definition_by_tag_name,
    )


def upsert_class_user_status_current_legacy(**kwargs: Any) -> None:
    return class_user_domain_service.upsert_class_user_status_current(**kwargs)


def append_class_user_status_history_legacy(**kwargs: Any) -> None:
    return class_user_domain_service.append_class_user_status_history(**kwargs)
