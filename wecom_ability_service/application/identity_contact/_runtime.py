"""Application-level wiring for identity_contact.

Stitches multiple domains (identity / contacts / tags / class_user / user_ops /
routing_config) together with helper functions and a one-shot runtime binding
that injects callables into ``user_ops_domain_service``. Kept as a private
module because the wiring is internal to this application package.
"""

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


def enrich_contact_context(contact: dict[str, Any]) -> dict[str, Any]:
    return contacts_domain_service.enrich_contact_context(
        contact,
        get_owner_role=get_owner_role,
        get_contact_tag_snapshots=tags_repo.get_contact_tag_snapshots,
        resolve_signup_status_from_tags=tags_domain_service.resolve_signup_status_from_tags,
        resolve_contact_routing_context=_resolve_contact_routing_context_from_signup_status,
    )


def refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
) -> dict[str, Any]:
    bind_user_ops_runtime()
    return user_ops_domain_service.refresh_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
        scoped_tag_ids=scoped_tag_ids,
    )


def get_contact_by_external_userid(external_userid: str, *, refresh_tags: bool = False) -> dict[str, Any] | None:
    return contacts_domain_service.get_contact_by_external_userid(
        external_userid,
        refresh_tags=refresh_tags,
        refresh_contact_tags_for_external_userid=refresh_contact_tags_for_external_userid,
        enrich_contact_context=enrich_contact_context,
    )


def _resolve_signup_status_for_contact(external_userid: str, owner_userid: str) -> str:
    payload = enrich_contact_context(
        {
            "external_userid": str(external_userid or "").strip(),
            "owner_userid": str(owner_userid or "").strip(),
        }
    )
    return str(payload.get("signup_status") or "").strip()


def resolve_person_identity(
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


def get_contact_binding_status(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    return identity_domain_service.get_contact_binding_status(
        external_userid,
        owner_userid,
        contact_profile_loader=user_ops_domain_service._sidebar_contact_profile,
    )


def bind_user_ops_runtime() -> None:
    user_ops_domain_service._user_ops_contact_client = _user_ops_contact_client
    user_ops_domain_service._resolve_third_party_user_id_by_mobile = user_ops_domain_service._resolve_third_party_user_id_by_mobile
    user_ops_domain_service._db_bool = _db_bool
    user_ops_domain_service._normalize_mobile = identity_domain_service.normalize_mobile
    user_ops_domain_service._list_contact_tag_ids_for_user = tags_repo.list_contact_tag_ids_for_user
    user_ops_domain_service._stringify_db_timestamp = _stringify_db_timestamp
    user_ops_domain_service.resolve_person_identity = resolve_person_identity
    user_ops_domain_service.get_contact_binding_status = get_contact_binding_status
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


__all__ = [
    "bind_user_ops_runtime",
    "enrich_contact_context",
    "get_contact_binding_status",
    "get_contact_by_external_userid",
    "refresh_contact_tags_for_external_userid",
    "resolve_person_identity",
]
