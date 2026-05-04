from __future__ import annotations

from typing import Any

from ...domains.identity import service as identity_domain_service
from . import _legacy_delegate
from .dto import (
    BindExternalContactIdentityCommandDTO,
    BindExternalContactIdentityResultDTO,
    MarkExternalContactFollowUserStatusCommandDTO,
    MarkExternalContactFollowUserStatusResultDTO,
    MarkExternalContactIdentityStatusCommandDTO,
    MarkExternalContactIdentityStatusResultDTO,
    RefreshExternalContactIdentityOwnerCommandDTO,
    RefreshExternalContactIdentityOwnerResultDTO,
    ReplaceFollowUsersCommandDTO,
    ReplaceFollowUsersResultDTO,
    UpsertExternalContactIdentityCommandDTO,
    UpsertExternalContactIdentityResultDTO,
)


class BindExternalContactIdentityCommand:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.bind_mobile_to_external_contact`` or ``bind_openid_to_external_contact`` via ``_legacy_delegate`` for sidebar and questionnaire callers."""

    def __call__(
        self,
        dto: BindExternalContactIdentityCommandDTO,
    ) -> BindExternalContactIdentityResultDTO:
        return _legacy_delegate.bind_external_contact_identity_legacy(dto)

    execute = __call__


class UpsertExternalContactIdentityCommand:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.upsert_external_contact_identity`` via ``_legacy_delegate`` for callback, sync, and admin support callers."""

    def __call__(
        self,
        dto: UpsertExternalContactIdentityCommandDTO,
    ) -> UpsertExternalContactIdentityResultDTO:
        return _legacy_delegate.upsert_external_contact_identity_legacy(dto)

    execute = __call__


class ReplaceFollowUsersCommand:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.replace_external_contact_follow_users`` via ``_legacy_delegate`` for callback, sync, and admin support callers."""

    def __call__(self, dto: ReplaceFollowUsersCommandDTO) -> ReplaceFollowUsersResultDTO:
        return _legacy_delegate.replace_follow_users_legacy(dto)

    execute = __call__


class RefreshExternalContactIdentityOwnerCommand:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.refresh_external_contact_identity_owner`` via ``_legacy_delegate`` for callback, sync, and admin support callers."""

    def __call__(
        self,
        dto: RefreshExternalContactIdentityOwnerCommandDTO,
    ) -> RefreshExternalContactIdentityOwnerResultDTO:
        return _legacy_delegate.refresh_external_contact_identity_owner_legacy(dto)

    execute = __call__


class MarkExternalContactIdentityStatusCommand:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.mark_external_contact_identity_status`` via ``_legacy_delegate`` for callback and sync lifecycle callers."""

    def __call__(
        self,
        dto: MarkExternalContactIdentityStatusCommandDTO,
    ) -> MarkExternalContactIdentityStatusResultDTO:
        return _legacy_delegate.mark_external_contact_identity_status_legacy(dto)

    execute = __call__


class MarkExternalContactFollowUserStatusCommand:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.mark_external_contact_follow_user_status`` via ``_legacy_delegate`` for callback and sync lifecycle callers."""

    def __call__(
        self,
        dto: MarkExternalContactFollowUserStatusCommandDTO,
    ) -> MarkExternalContactFollowUserStatusResultDTO:
        return _legacy_delegate.mark_external_contact_follow_user_status_legacy(dto)

    execute = __call__


class BuildExternalContactIdentityRecordCommand:
    """Wave 2 identity helper that delegates to ``domains.identity.service.normalize_external_contact_identity`` for callback, sync, and admin support callers while write ownership moves into application commands."""

    def __call__(
        self,
        *,
        corp_id: str,
        detail: dict[str, Any],
        follow_user_userid: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        return identity_domain_service.normalize_external_contact_identity(
            str(corp_id or "").strip(),
            dict(detail or {}),
            follow_user_userid=str(follow_user_userid or "").strip(),
            status=str(status or "").strip(),
        )

    execute = __call__


__all__ = [
    "BindExternalContactIdentityCommand",
    "BuildExternalContactIdentityRecordCommand",
    "MarkExternalContactFollowUserStatusCommand",
    "MarkExternalContactIdentityStatusCommand",
    "RefreshExternalContactIdentityOwnerCommand",
    "ReplaceFollowUsersCommand",
    "UpsertExternalContactIdentityCommand",
]
