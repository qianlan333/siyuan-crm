"""Application-level wiring for user_ops.

Bridges multiple application/domain layers (identity_contact / class_user /
tags / routing_config / user_ops domain) and provides a runtime binding that
injects callables into ``user_ops_domain_service`` at boundary entry.
"""

from __future__ import annotations

from typing import Any

from ...domains.identity import service as identity_domain_service
from ...domains.routing_config.service import get_owner_class_term_backfill_entry_source_override
from ...domains.tags import repo as tags_repo
from ...domains.tags import service as tags_domain_service
from ...domains.user_ops import service as user_ops_domain_service
from ...infra.helpers import db_bool as _db_bool
from ...infra.helpers import stringify_db_timestamp as _stringify_db_timestamp
from ..class_user.commands import (
    UpdateClassUserStatusSyncResultCommand,
    append_class_user_status_history_primitive,
    upsert_class_user_status_current_primitive,
)
from ..class_user.dto import (
    GetClassUserStatusCurrentQueryDTO,
    GetClassUserStatusDefinitionQueryDTO,
    UpdateClassUserStatusSyncResultCommandDTO,
)
from ..class_user.queries import GetClassUserStatusCurrentQuery, GetClassUserStatusDefinitionQuery
from ..identity_contact.dto import GetContactBindingStatusQueryDTO, ResolvePersonIdentityQueryDTO
from ..identity_contact.queries import GetContactBindingStatusQuery, ResolvePersonIdentityQuery


def filters_to_kwargs(dto) -> dict[str, str]:
    filters = dto.filters
    return {
        "wecom_status": str(filters.wecom_status or "").strip(),
        "mobile_binding_status": str(filters.mobile_binding_status or "").strip(),
        "activation_bucket": str(filters.activation_bucket or "").strip(),
        "is_wecom_added": str(filters.is_wecom_added or "").strip(),
        "is_mobile_bound": str(filters.is_mobile_bound or "").strip(),
        "huangxiaocan_activation_state": str(filters.huangxiaocan_activation_state or "").strip(),
        "class_term_no": str(filters.class_term_no or "").strip(),
        "keyword": str(filters.keyword or "").strip(),
        "mobile": str(filters.mobile or "").strip(),
        "owner_userid": str(filters.owner_userid or "").strip(),
        "query": str(filters.query or "").strip(),
    }


def _resolve_person_identity(
    *,
    external_userid: str = "",
    mobile: str = "",
    unionid: str = "",
    corp_id: str = "",
) -> dict[str, Any]:
    return ResolvePersonIdentityQuery()(
        ResolvePersonIdentityQueryDTO(
            external_userid=str(external_userid or "").strip(),
            mobile=str(mobile or "").strip(),
            unionid=str(unionid or "").strip(),
            corp_id=str(corp_id or "").strip(),
        )
    )


def _get_contact_binding_status(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    return GetContactBindingStatusQuery()(
        GetContactBindingStatusQueryDTO(
            external_userid=str(external_userid or "").strip(),
            owner_userid=str(owner_userid or "").strip(),
        )
    )


def _get_class_user_status_definition(signup_status: str) -> dict[str, Any] | None:
    return GetClassUserStatusDefinitionQuery()(
        GetClassUserStatusDefinitionQueryDTO(signup_status=str(signup_status or "").strip())
    )


def _get_class_user_status_current(external_userid: str) -> dict[str, Any] | None:
    return GetClassUserStatusCurrentQuery()(
        GetClassUserStatusCurrentQueryDTO(external_userid=str(external_userid or "").strip())
    )


def _update_class_user_status_sync_result(
    external_userid: str,
    *,
    wecom_tag_sync_status: str = "",
    wecom_tag_sync_error: str = "",
) -> None:
    return UpdateClassUserStatusSyncResultCommand()(
        UpdateClassUserStatusSyncResultCommandDTO(
            external_userid=str(external_userid or "").strip(),
            wecom_tag_sync_status=str(wecom_tag_sync_status or "").strip(),
            wecom_tag_sync_error=str(wecom_tag_sync_error or "").strip(),
        )
    )


def bind_user_ops_runtime() -> None:
    from ... import services as services_compat

    # Keep the historical services.py monkeypatch hooks alive while the formal
    # owner sits under application/user_ops.
    user_ops_domain_service._user_ops_contact_client = services_compat._user_ops_contact_client
    user_ops_domain_service._resolve_third_party_user_id_by_mobile = (
        services_compat._resolve_third_party_user_id_by_mobile
    )
    user_ops_domain_service._db_bool = _db_bool
    user_ops_domain_service._normalize_mobile = identity_domain_service.normalize_mobile
    user_ops_domain_service._list_contact_tag_ids_for_user = tags_repo.list_contact_tag_ids_for_user
    user_ops_domain_service._stringify_db_timestamp = _stringify_db_timestamp
    user_ops_domain_service.resolve_person_identity = _resolve_person_identity
    user_ops_domain_service.get_contact_binding_status = _get_contact_binding_status
    user_ops_domain_service.save_tag_snapshot = tags_repo.save_tag_snapshot
    user_ops_domain_service.remove_tag_snapshot = tags_repo.remove_tag_snapshot
    user_ops_domain_service.remove_tag_snapshots_for_other_users = (
        tags_repo.remove_tag_snapshots_for_other_users
    )
    user_ops_domain_service.remove_all_tag_snapshots_for_other_users = (
        tags_repo.remove_all_tag_snapshots_for_other_users
    )
    user_ops_domain_service.get_owner_class_term_backfill_entry_source_override = (
        get_owner_class_term_backfill_entry_source_override
    )
    user_ops_domain_service.get_signup_status_definition_by_tag_name = (
        tags_domain_service.get_signup_status_definition_by_tag_name
    )
    user_ops_domain_service.get_class_user_status_definition = _get_class_user_status_definition
    user_ops_domain_service.get_class_user_status_current = _get_class_user_status_current
    user_ops_domain_service.upsert_class_user_status_current = upsert_class_user_status_current_primitive
    user_ops_domain_service.append_class_user_status_history = append_class_user_status_history_primitive
    user_ops_domain_service.update_class_user_status_sync_result = _update_class_user_status_sync_result


__all__ = [
    "bind_user_ops_runtime",
    "filters_to_kwargs",
]
