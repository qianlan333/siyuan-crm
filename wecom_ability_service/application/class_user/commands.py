from __future__ import annotations

from typing import Any

from . import _legacy_delegate
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
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.apply_class_user_status_change`` via ``_legacy_delegate`` for admin-support, marketing-automation, and future user-ops callers."""

    def __call__(
        self,
        dto: ApplyClassUserStatusChangeCommandDTO,
    ) -> ApplyClassUserStatusChangeResultDTO:
        return _legacy_delegate.apply_class_user_status_change_legacy(dto)

    execute = __call__


class UpdateClassUserStatusSyncResultCommand:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.update_class_user_status_sync_result`` via ``_legacy_delegate`` for admin-support sync-result writers."""

    def __call__(
        self,
        dto: UpdateClassUserStatusSyncResultCommandDTO,
    ) -> UpdateClassUserStatusSyncResultResultDTO:
        return _legacy_delegate.update_class_user_status_sync_result_legacy(dto)

    execute = __call__


class ClearClassUserStatusCurrentCommand:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.clear_class_user_status_current`` via ``_legacy_delegate`` for marketing-automation callers that clear the current class-user state."""

    def __call__(
        self,
        dto: ClearClassUserStatusCurrentCommandDTO,
    ) -> ClearClassUserStatusCurrentResultDTO:
        return _legacy_delegate.clear_class_user_status_current_legacy(dto)

    execute = __call__


class MigrateClassUserStatusFromContactTagsCommand:
    """Wave 2 class-user skeleton that delegates to ``domains.class_user.service.migrate_class_user_status_from_contact_tags`` via ``_legacy_delegate`` for admin class-user and operations-shell callers."""

    def __call__(
        self,
        dto: MigrateClassUserStatusFromContactTagsCommandDTO | None = None,
    ) -> MigrateClassUserStatusFromContactTagsResultDTO:
        return _legacy_delegate.migrate_class_user_status_from_contact_tags_legacy(
            dto or MigrateClassUserStatusFromContactTagsCommandDTO()
        )

    execute = __call__


def upsert_class_user_status_current_primitive(**kwargs: Any) -> None:
    """Internal Wave 2 class-user primitive that delegates to ``domains.class_user.service.upsert_class_user_status_current`` via ``_legacy_delegate``. Compatibility shim only; future callers must use formal application commands instead of invoking this primitive directly."""

    return _legacy_delegate.upsert_class_user_status_current_legacy(**kwargs)


def append_class_user_status_history_primitive(**kwargs: Any) -> None:
    """Internal Wave 2 class-user primitive that delegates to ``domains.class_user.service.append_class_user_status_history`` via ``_legacy_delegate``. Compatibility shim only; future callers must use formal application commands instead of invoking this primitive directly."""

    return _legacy_delegate.append_class_user_status_history_legacy(**kwargs)


__all__ = [
    "ApplyClassUserStatusChangeCommand",
    "ClearClassUserStatusCurrentCommand",
    "MigrateClassUserStatusFromContactTagsCommand",
    "UpdateClassUserStatusSyncResultCommand",
]
