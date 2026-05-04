from __future__ import annotations

from ...domains.identity import service as identity_domain_service
from . import _legacy_delegate
from .dto import (
    CountExternalContactIdentityMapsQueryDTO,
    CountExternalContactIdentityMapsResultDTO,
    GetContactBindingStatusQueryDTO,
    GetContactBindingStatusResultDTO,
    GetPrimaryFollowUserUseridQueryDTO,
    GetPrimaryFollowUserUseridResultDTO,
    ResolveExternalContactIdentityQueryDTO,
    ResolveExternalContactIdentityResultDTO,
    ResolvePersonIdentityQueryDTO,
    ResolvePersonIdentityResultDTO,
)


class ResolvePersonIdentityQuery:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.resolve_person_identity`` via ``_legacy_delegate`` for HTTP identity callers and future questionnaire/user-ops readers."""

    def __call__(self, dto: ResolvePersonIdentityQueryDTO | None = None) -> ResolvePersonIdentityResultDTO:
        return _legacy_delegate.resolve_person_identity_legacy(dto or ResolvePersonIdentityQueryDTO())

    execute = __call__


class GetContactBindingStatusQuery:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.get_contact_binding_status`` via ``_legacy_delegate`` for sidebar and future admin support readers."""

    def __call__(self, dto: GetContactBindingStatusQueryDTO) -> GetContactBindingStatusResultDTO:
        return _legacy_delegate.get_contact_binding_status_legacy(dto)

    execute = __call__


class ResolveExternalContactIdentityQuery:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.resolve_external_contact_identity`` via ``_legacy_delegate`` for questionnaire and sync callers."""

    def __call__(
        self,
        dto: ResolveExternalContactIdentityQueryDTO,
    ) -> ResolveExternalContactIdentityResultDTO:
        return _legacy_delegate.resolve_external_contact_identity_legacy(dto)

    execute = __call__


class CountExternalContactIdentityMapsQuery:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.count_external_contact_identity_maps`` via ``_legacy_delegate`` for sync summary callers."""

    def __call__(
        self,
        dto: CountExternalContactIdentityMapsQueryDTO | None = None,
    ) -> CountExternalContactIdentityMapsResultDTO:
        return _legacy_delegate.count_external_contact_identity_maps_legacy(
            dto or CountExternalContactIdentityMapsQueryDTO()
        )

    execute = __call__


class GetPrimaryFollowUserUseridQuery:
    """Wave 2 identity skeleton that delegates to ``domains.identity.service.get_primary_follow_user_userid`` via ``_legacy_delegate`` for sidebar and admin support callers."""

    def __call__(
        self,
        dto: GetPrimaryFollowUserUseridQueryDTO,
    ) -> GetPrimaryFollowUserUseridResultDTO:
        return _legacy_delegate.get_primary_follow_user_userid_legacy(dto)

    execute = __call__


class ListIdentityExternalUseridsForCorpQuery:
    """Wave 2 identity query that delegates to ``domains.identity.service.list_identity_external_userids_for_corp`` for sync callers until the corp-scoped read model is formalized."""

    def __call__(self, corp_id: str) -> list[str]:
        return identity_domain_service.list_identity_external_userids_for_corp(str(corp_id or "").strip())

    execute = __call__


__all__ = [
    "CountExternalContactIdentityMapsQuery",
    "GetContactBindingStatusQuery",
    "GetPrimaryFollowUserUseridQuery",
    "ListIdentityExternalUseridsForCorpQuery",
    "ResolveExternalContactIdentityQuery",
    "ResolvePersonIdentityQuery",
]
