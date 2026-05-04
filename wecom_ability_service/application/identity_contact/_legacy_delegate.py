from __future__ import annotations

from typing import Any

from ...domains.class_user import service as class_user_domain_service
from ...domains.contacts import service as contacts_domain_service
from ...domains.identity import service as identity_domain_service
from ...domains.routing_config.service import (
    get_owner_class_term_backfill_entry_source_override,
    get_owner_role,
    resolve_contact_routing_context as _resolve_contact_routing_context,
)
from ...domains.tags import repo as tags_repo
from ...domains.tags import service as tags_domain_service
from ...domains.user_ops import service as user_ops_domain_service
from ...infra.helpers import db_bool as _db_bool
from ...infra.helpers import stringify_db_timestamp as _stringify_db_timestamp
from ...infra.wecom_runtime import get_contact_runtime_client
from .dto import (
    BindExternalContactIdentityCommandDTO,
    CountExternalContactIdentityMapsQueryDTO,
    GetContactBindingStatusQueryDTO,
    GetPrimaryFollowUserUseridQueryDTO,
    MarkExternalContactFollowUserStatusCommandDTO,
    MarkExternalContactIdentityStatusCommandDTO,
    RefreshExternalContactIdentityOwnerCommandDTO,
    ReplaceFollowUsersCommandDTO,
    ResolveExternalContactIdentityQueryDTO,
    ResolvePersonIdentityQueryDTO,
    UpsertExternalContactIdentityCommandDTO,
)


def _user_ops_contact_client():
    return get_contact_runtime_client()


def _resolve_contact_routing_context_from_signup_status(
    owner_userid: str,
    owner_role: str,
    signup_status: str,
) -> dict[str, Any]:
    definition = tags_domain_service.get_signup_status_definition(signup_status)
    return _resolve_contact_routing_context(
        owner_userid=owner_userid,
        owner_role=owner_role,
        signup_status=signup_status,
        routing_alias=str((definition or {}).get("routing_alias") or ""),
    )


def _enrich_contact_context(contact: dict[str, Any]) -> dict[str, Any]:
    return contacts_domain_service.enrich_contact_context(
        contact,
        get_owner_role=get_owner_role,
        get_contact_tag_snapshots=tags_repo.get_contact_tag_snapshots,
        resolve_signup_status_from_tags=tags_domain_service.resolve_signup_status_from_tags,
        resolve_contact_routing_context=_resolve_contact_routing_context_from_signup_status,
    )


def _refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.refresh_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
        scoped_tag_ids=scoped_tag_ids,
    )


def _get_contact_by_external_userid(external_userid: str, *, refresh_tags: bool = False) -> dict[str, Any] | None:
    return contacts_domain_service.get_contact_by_external_userid(
        external_userid,
        refresh_tags=refresh_tags,
        refresh_contact_tags_for_external_userid=_refresh_contact_tags_for_external_userid,
        enrich_contact_context=_enrich_contact_context,
    )


def _resolve_signup_status_for_contact(external_userid: str, owner_userid: str) -> str:
    payload = _enrich_contact_context(
        {
            "external_userid": str(external_userid or "").strip(),
            "owner_userid": str(owner_userid or "").strip(),
        }
    )
    return str(payload.get("signup_status") or "").strip()


def _resolve_person_identity(
    *,
    external_userid: str = "",
    mobile: str = "",
    unionid: str = "",
    corp_id: str = "",
) -> dict[str, Any]:
    return identity_domain_service.resolve_person_identity(
        external_userid=external_userid,
        mobile=mobile,
        unionid=unionid,
        corp_id=corp_id,
        resolve_signup_status_for_contact=_resolve_signup_status_for_contact,
    )


def _get_contact_binding_status(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    return identity_domain_service.get_contact_binding_status(
        external_userid,
        owner_userid,
        contact_profile_loader=user_ops_domain_service._sidebar_contact_profile,
    )


def _bind_user_ops_runtime() -> None:
    user_ops_domain_service._user_ops_contact_client = _user_ops_contact_client
    user_ops_domain_service._resolve_third_party_user_id_by_mobile = user_ops_domain_service._resolve_third_party_user_id_by_mobile
    user_ops_domain_service._db_bool = _db_bool
    user_ops_domain_service._normalize_mobile = identity_domain_service.normalize_mobile
    user_ops_domain_service._list_contact_tag_ids_for_user = tags_repo.list_contact_tag_ids_for_user
    user_ops_domain_service._stringify_db_timestamp = _stringify_db_timestamp
    user_ops_domain_service.resolve_person_identity = _resolve_person_identity
    user_ops_domain_service.get_contact_binding_status = _get_contact_binding_status
    user_ops_domain_service.save_tag_snapshot = tags_repo.save_tag_snapshot
    user_ops_domain_service.remove_tag_snapshot = tags_repo.remove_tag_snapshot
    user_ops_domain_service.remove_tag_snapshots_for_other_users = tags_repo.remove_tag_snapshots_for_other_users
    user_ops_domain_service.remove_all_tag_snapshots_for_other_users = tags_repo.remove_all_tag_snapshots_for_other_users
    user_ops_domain_service.get_owner_class_term_backfill_entry_source_override = (
        get_owner_class_term_backfill_entry_source_override
    )
    user_ops_domain_service.get_signup_status_definition_by_tag_name = (
        tags_domain_service.get_signup_status_definition_by_tag_name
    )
    user_ops_domain_service.get_class_user_status_definition = class_user_domain_service.get_class_user_status_definition
    user_ops_domain_service.get_class_user_status_current = class_user_domain_service.get_class_user_status_current
    user_ops_domain_service.upsert_class_user_status_current = class_user_domain_service.upsert_class_user_status_current
    user_ops_domain_service.append_class_user_status_history = class_user_domain_service.append_class_user_status_history
    user_ops_domain_service.update_class_user_status_sync_result = (
        class_user_domain_service.update_class_user_status_sync_result
    )


def resolve_person_identity_legacy(dto: ResolvePersonIdentityQueryDTO) -> dict[str, Any]:
    return _resolve_person_identity(
        external_userid=str(dto.external_userid or "").strip(),
        mobile=str(dto.mobile or "").strip(),
        unionid=str(dto.unionid or "").strip(),
        corp_id=str(dto.corp_id or "").strip(),
    )


def get_contact_binding_status_legacy(dto: GetContactBindingStatusQueryDTO) -> dict[str, Any]:
    return _get_contact_binding_status(
        str(dto.external_userid or "").strip(),
        str(dto.owner_userid or "").strip(),
    )


def resolve_external_contact_identity_legacy(
    dto: ResolveExternalContactIdentityQueryDTO,
) -> dict[str, Any] | None:
    corp_id = str(dto.corp_id or "").strip() or identity_domain_service.person_identity_corp_id()
    return identity_domain_service.resolve_external_contact_identity(
        corp_id,
        unionid=str(dto.unionid or "").strip(),
        openid=str(dto.openid or "").strip(),
        external_userid=str(dto.external_userid or "").strip(),
    )


def count_external_contact_identity_maps_legacy(_: CountExternalContactIdentityMapsQueryDTO | None = None) -> int:
    return identity_domain_service.count_external_contact_identity_maps()


def get_primary_follow_user_userid_legacy(dto: GetPrimaryFollowUserUseridQueryDTO) -> str:
    return identity_domain_service.get_primary_follow_user_userid(
        str(dto.external_userid or "").strip(),
        corp_id=str(dto.corp_id or "").strip(),
        active_value=_db_bool(True),
        contact_loader=_get_contact_by_external_userid,
        resolve_identity=lambda corp_id, value: identity_domain_service.resolve_external_contact_identity(
            corp_id,
            external_userid=value,
        ),
    )


def bind_external_contact_identity_legacy(
    dto: BindExternalContactIdentityCommandDTO,
) -> dict[str, Any] | None:
    normalized_mobile = str(dto.mobile or "").strip()
    if normalized_mobile:
        _bind_user_ops_runtime()
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


def upsert_external_contact_identity_legacy(dto: UpsertExternalContactIdentityCommandDTO) -> int:
    return identity_domain_service.upsert_external_contact_identity(dict(dto.record or {}))


def replace_follow_users_legacy(dto: ReplaceFollowUsersCommandDTO) -> None:
    return identity_domain_service.replace_external_contact_follow_users(
        str(dto.corp_id or "").strip(),
        str(dto.external_userid or "").strip(),
        list(dto.follow_users or []),
        preferred_userid=str(dto.preferred_userid or "").strip(),
    )


def refresh_external_contact_identity_owner_legacy(
    dto: RefreshExternalContactIdentityOwnerCommandDTO,
) -> None:
    return identity_domain_service.refresh_external_contact_identity_owner(
        str(dto.corp_id or "").strip(),
        str(dto.external_userid or "").strip(),
    )


def mark_external_contact_identity_status_legacy(
    dto: MarkExternalContactIdentityStatusCommandDTO,
) -> None:
    return identity_domain_service.mark_external_contact_identity_status(
        str(dto.corp_id or "").strip(),
        str(dto.external_userid or "").strip(),
        status=str(dto.status or "").strip(),
        follow_user_userid=str(dto.follow_user_userid or "").strip(),
    )


def mark_external_contact_follow_user_status_legacy(
    dto: MarkExternalContactFollowUserStatusCommandDTO,
) -> None:
    return identity_domain_service.mark_external_contact_follow_user_status(
        str(dto.corp_id or "").strip(),
        str(dto.external_userid or "").strip(),
        user_id=str(dto.user_id or "").strip(),
        status=str(dto.status or "").strip(),
    )


__all__ = [
    "bind_external_contact_identity_legacy",
    "count_external_contact_identity_maps_legacy",
    "get_contact_binding_status_legacy",
    "get_primary_follow_user_userid_legacy",
    "mark_external_contact_follow_user_status_legacy",
    "mark_external_contact_identity_status_legacy",
    "refresh_external_contact_identity_owner_legacy",
    "replace_follow_users_legacy",
    "resolve_external_contact_identity_legacy",
    "resolve_person_identity_legacy",
    "upsert_external_contact_identity_legacy",
]
