from __future__ import annotations

from typing import Any

from ...domains.identity import service as identity_domain_service
from ...domains.user_ops import service as user_ops_domain_service
from . import _runtime
from .dto import (
    BindExternalContactIdentityCommandDTO,
    BindExternalContactIdentityResultDTO,
    BindExternalContactMobileFromIdentitySourcesCommandDTO,
    BindExternalContactMobileFromIdentitySourcesResultDTO,
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
    def __call__(
        self,
        dto: BindExternalContactIdentityCommandDTO,
    ) -> BindExternalContactIdentityResultDTO:
        normalized_mobile = str(dto.mobile or "").strip()
        if normalized_mobile:
            _runtime.bind_user_ops_runtime()
            return identity_domain_service.bind_mobile_to_external_contact(
                external_userid=str(dto.external_userid or "").strip(),
                owner_userid=str(dto.owner_userid or "").strip(),
                bind_by_userid=str(dto.bind_by_userid or "").strip(),
                mobile=normalized_mobile,
                force_rebind=bool(dto.force_rebind),
                resolve_binding_owner_userid=user_ops_domain_service._resolve_binding_owner_userid,
                contact_profile_loader=user_ops_domain_service._sidebar_contact_profile,
                resolve_third_party_user_id_by_mobile=user_ops_domain_service._resolve_third_party_user_id_by_mobile,
                merge_lead_pool_after_mobile_bind=user_ops_domain_service._merge_lead_pool_after_mobile_bind,
                conflict_error_cls=identity_domain_service.ContactBindingConflictError,
                sync_error_cls=user_ops_domain_service.ThirdPartyUserSyncError,
            )

        normalized_openid = str(dto.openid or "").strip()
        if normalized_openid:
            corp_id = str(dto.corp_id or "").strip() or identity_domain_service.person_identity_corp_id()
            return identity_domain_service.bind_openid_to_external_contact(
                corp_id,
                str(dto.external_userid or "").strip(),
                normalized_openid,
                unionid=str(dto.unionid or "").strip(),
            )

        raise ValueError("mobile or openid is required")

    execute = __call__


class BindExternalContactMobileFromIdentitySourcesCommand:
    def __call__(
        self,
        dto: BindExternalContactMobileFromIdentitySourcesCommandDTO,
    ) -> BindExternalContactMobileFromIdentitySourcesResultDTO:
        _runtime.bind_user_ops_runtime()
        return identity_domain_service.bind_mobile_to_external_contact_from_identity_sources(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
            bind_by_userid=str(dto.bind_by_userid or "").strip(),
            force_rebind=bool(dto.force_rebind),
            resolve_binding_owner_userid=user_ops_domain_service._resolve_binding_owner_userid,
            contact_profile_loader=user_ops_domain_service._sidebar_contact_profile,
            resolve_third_party_user_id_by_mobile=user_ops_domain_service._resolve_third_party_user_id_by_mobile,
            merge_lead_pool_after_mobile_bind=user_ops_domain_service._merge_lead_pool_after_mobile_bind,
            conflict_error_cls=identity_domain_service.ContactBindingConflictError,
            sync_error_cls=user_ops_domain_service.ThirdPartyUserSyncError,
        )

    execute = __call__


class UpsertExternalContactIdentityCommand:
    def __call__(
        self,
        dto: UpsertExternalContactIdentityCommandDTO,
    ) -> UpsertExternalContactIdentityResultDTO:
        return identity_domain_service.upsert_external_contact_identity(dict(dto.record or {}))

    execute = __call__


class ReplaceFollowUsersCommand:
    def __call__(self, dto: ReplaceFollowUsersCommandDTO) -> ReplaceFollowUsersResultDTO:
        return identity_domain_service.replace_external_contact_follow_users(
            str(dto.corp_id or "").strip(),
            str(dto.external_userid or "").strip(),
            list(dto.follow_users or []),
            preferred_userid=str(dto.preferred_userid or "").strip(),
        )

    execute = __call__


class RefreshExternalContactIdentityOwnerCommand:
    def __call__(
        self,
        dto: RefreshExternalContactIdentityOwnerCommandDTO,
    ) -> RefreshExternalContactIdentityOwnerResultDTO:
        return identity_domain_service.refresh_external_contact_identity_owner(
            str(dto.corp_id or "").strip(),
            str(dto.external_userid or "").strip(),
        )

    execute = __call__


class MarkExternalContactIdentityStatusCommand:
    def __call__(
        self,
        dto: MarkExternalContactIdentityStatusCommandDTO,
    ) -> MarkExternalContactIdentityStatusResultDTO:
        return identity_domain_service.mark_external_contact_identity_status(
            str(dto.corp_id or "").strip(),
            str(dto.external_userid or "").strip(),
            status=str(dto.status or "").strip(),
            follow_user_userid=str(dto.follow_user_userid or "").strip(),
        )

    execute = __call__


class MarkExternalContactFollowUserStatusCommand:
    def __call__(
        self,
        dto: MarkExternalContactFollowUserStatusCommandDTO,
    ) -> MarkExternalContactFollowUserStatusResultDTO:
        return identity_domain_service.mark_external_contact_follow_user_status(
            str(dto.corp_id or "").strip(),
            str(dto.external_userid or "").strip(),
            user_id=str(dto.user_id or "").strip(),
            status=str(dto.status or "").strip(),
        )

    execute = __call__


class BuildExternalContactIdentityRecordCommand:
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
    "BindExternalContactMobileFromIdentitySourcesCommand",
    "BuildExternalContactIdentityRecordCommand",
    "MarkExternalContactFollowUserStatusCommand",
    "MarkExternalContactIdentityStatusCommand",
    "RefreshExternalContactIdentityOwnerCommand",
    "ReplaceFollowUsersCommand",
    "UpsertExternalContactIdentityCommand",
]
