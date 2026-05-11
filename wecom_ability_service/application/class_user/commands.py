from __future__ import annotations

from typing import Any

from ...domains.class_user import service as class_user_domain_service
from ...domains.tags import service as tags_domain_service
from .dto import (
    ApplyClassUserStatusChangeCommandDTO,
    ApplyClassUserStatusChangeResultDTO,
    ClearClassUserStatusCurrentCommandDTO,
    ClearClassUserStatusCurrentResultDTO,
    MigrateClassUserStatusFromContactTagsCommandDTO,
    MigrateClassUserStatusFromContactTagsResultDTO,
    UpdateClassUserStatusSyncResultCommandDTO,
    UpdateClassUserStatusSyncResultResultDTO,
)


class ApplyClassUserStatusChangeCommand:
    def __call__(
        self,
        dto: ApplyClassUserStatusChangeCommandDTO,
    ) -> ApplyClassUserStatusChangeResultDTO:
        return class_user_domain_service.apply_class_user_status_change(
            external_userid=str(dto.external_userid or "").strip(),
            signup_status=str(dto.signup_status or "").strip(),
            set_by_userid=str(dto.set_by_userid or "").strip(),
            customer_name_snapshot=str(dto.customer_name_snapshot or "").strip(),
            owner_userid_snapshot=str(dto.owner_userid_snapshot or "").strip(),
            mobile_snapshot=str(dto.mobile_snapshot or "").strip(),
        )

    execute = __call__


class UpdateClassUserStatusSyncResultCommand:
    def __call__(
        self,
        dto: UpdateClassUserStatusSyncResultCommandDTO,
    ) -> UpdateClassUserStatusSyncResultResultDTO:
        return class_user_domain_service.update_class_user_status_sync_result(
            str(dto.external_userid or "").strip(),
            wecom_tag_sync_status=str(dto.wecom_tag_sync_status or "").strip(),
            wecom_tag_sync_error=str(dto.wecom_tag_sync_error or "").strip(),
        )

    execute = __call__


class ClearClassUserStatusCurrentCommand:
    def __call__(
        self,
        dto: ClearClassUserStatusCurrentCommandDTO,
    ) -> ClearClassUserStatusCurrentResultDTO:
        return class_user_domain_service.clear_class_user_status_current(
            external_userid=str(dto.external_userid or "").strip(),
            set_by_userid=str(dto.set_by_userid or "").strip(),
            customer_name_snapshot=str(dto.customer_name_snapshot or "").strip(),
            owner_userid_snapshot=str(dto.owner_userid_snapshot or "").strip(),
            mobile_snapshot=str(dto.mobile_snapshot or "").strip(),
        )

    execute = __call__


class MigrateClassUserStatusFromContactTagsCommand:
    def __call__(
        self,
        dto: MigrateClassUserStatusFromContactTagsCommandDTO | None = None,
    ) -> MigrateClassUserStatusFromContactTagsResultDTO:
        _ = dto or MigrateClassUserStatusFromContactTagsCommandDTO()
        return class_user_domain_service.migrate_class_user_status_from_contact_tags(
            get_signup_status_definition_by_tag_name=tags_domain_service.get_signup_status_definition_by_tag_name,
        )

    execute = __call__


def upsert_class_user_status_current_primitive(**kwargs: Any) -> None:
    return class_user_domain_service.upsert_class_user_status_current(**kwargs)


def append_class_user_status_history_primitive(**kwargs: Any) -> None:
    return class_user_domain_service.append_class_user_status_history(**kwargs)


__all__ = [
    "ApplyClassUserStatusChangeCommand",
    "ClearClassUserStatusCurrentCommand",
    "MigrateClassUserStatusFromContactTagsCommand",
    "UpdateClassUserStatusSyncResultCommand",
]
