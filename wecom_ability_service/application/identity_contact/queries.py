from __future__ import annotations

from ...domains.identity import service as identity_domain_service
from ...infra.helpers import db_bool as _db_bool
from . import _runtime
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
    def __call__(
        self,
        dto: ResolvePersonIdentityQueryDTO | None = None,
    ) -> ResolvePersonIdentityResultDTO:
        dto = dto or ResolvePersonIdentityQueryDTO()
        return _runtime.resolve_person_identity(
            external_userid=str(dto.external_userid or "").strip(),
            mobile=str(dto.mobile or "").strip(),
            unionid=str(dto.unionid or "").strip(),
            corp_id=str(dto.corp_id or "").strip(),
        )

    execute = __call__


class GetContactBindingStatusQuery:
    def __call__(self, dto: GetContactBindingStatusQueryDTO) -> GetContactBindingStatusResultDTO:
        return _runtime.get_contact_binding_status(
            str(dto.external_userid or "").strip(),
            str(dto.owner_userid or "").strip(),
        )

    execute = __call__


class ResolveExternalContactIdentityQuery:
    def __call__(
        self,
        dto: ResolveExternalContactIdentityQueryDTO,
    ) -> ResolveExternalContactIdentityResultDTO:
        corp_id = str(dto.corp_id or "").strip() or identity_domain_service.person_identity_corp_id()
        return identity_domain_service.resolve_external_contact_identity(
            corp_id,
            unionid=str(dto.unionid or "").strip(),
            openid=str(dto.openid or "").strip(),
            external_userid=str(dto.external_userid or "").strip(),
        )

    execute = __call__


class CountExternalContactIdentityMapsQuery:
    def __call__(
        self,
        dto: CountExternalContactIdentityMapsQueryDTO | None = None,
    ) -> CountExternalContactIdentityMapsResultDTO:
        del dto
        return identity_domain_service.count_external_contact_identity_maps()

    execute = __call__


class GetPrimaryFollowUserUseridQuery:
    def __call__(
        self,
        dto: GetPrimaryFollowUserUseridQueryDTO,
    ) -> GetPrimaryFollowUserUseridResultDTO:
        return identity_domain_service.get_primary_follow_user_userid(
            str(dto.external_userid or "").strip(),
            corp_id=str(dto.corp_id or "").strip(),
            active_value=_db_bool(True),
            contact_loader=_runtime.get_contact_by_external_userid,
            resolve_identity=lambda corp_id, value: identity_domain_service.resolve_external_contact_identity(
                corp_id,
                external_userid=value,
            ),
        )

    execute = __call__


class ListIdentityExternalUseridsForCorpQuery:
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
