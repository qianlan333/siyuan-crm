from __future__ import annotations

from typing import Any

from ...domains.identity import service as identity_domain_service
from ...domains.routing_config.service import get_owner_class_term_backfill_entry_source_override
from ...domains.tags import repo as tags_repo
from ...domains.tags import service as tags_domain_service
from ...domains.user_ops import page_service as user_ops_page_service
from ...domains.user_ops import service as user_ops_domain_service
from ...infra import user_ops_runtime
from ...infra.helpers import db_bool as _db_bool
from ...infra.helpers import stringify_db_timestamp as _stringify_db_timestamp
from ..class_user.commands import (
    UpdateClassUserStatusSyncResultCommand,
    append_class_user_status_history_primitive,
    upsert_class_user_status_current_primitive,
)
from ..class_user.dto import UpdateClassUserStatusSyncResultCommandDTO
from ..class_user.dto import (
    GetClassUserStatusCurrentQueryDTO,
    GetClassUserStatusDefinitionQueryDTO,
)
from ..class_user.queries import GetClassUserStatusCurrentQuery, GetClassUserStatusDefinitionQuery
from ..identity_contact.dto import GetContactBindingStatusQueryDTO, ResolvePersonIdentityQueryDTO
from ..identity_contact.queries import GetContactBindingStatusQuery, ResolvePersonIdentityQuery
from .dto import (
    BackfillOwnerClassTermsCommandDTO,
    ExportUserOpsPoolQueryDTO,
    GetUserOpsOverviewQueryDTO,
    ImportActivationStatusCommandDTO,
    ImportExperienceLeadsCommandDTO,
    ImportMobileClassTermCommandDTO,
    ListLeadPoolQueryDTO,
    ListUserOpsHistoryQueryDTO,
    RefreshUserOpsContactTagsCommandDTO,
    RunDueUserOpsDeferredJobsCommandDTO,
    ScheduleUserOpsAutoAssignClassTermJobCommandDTO,
    UpsertLeadPoolMemberCommandDTO,
    WriteLeadPoolHistoryCommandDTO,
)


def _filters_to_kwargs(
    dto: GetUserOpsOverviewQueryDTO | ListLeadPoolQueryDTO | ExportUserOpsPoolQueryDTO,
) -> dict[str, str]:
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


def _bind_user_ops_runtime() -> None:
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


def get_user_ops_overview_legacy(dto: GetUserOpsOverviewQueryDTO) -> dict[str, Any]:
    return user_ops_page_service.get_user_ops_overview(**_filters_to_kwargs(dto))


def list_lead_pool_legacy(dto: ListLeadPoolQueryDTO) -> dict[str, Any]:
    return user_ops_page_service.list_user_ops_pool(**_filters_to_kwargs(dto))


def list_user_ops_history_legacy(dto: ListUserOpsHistoryQueryDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.list_user_ops_history(limit=int(dto.limit))


def export_user_ops_pool_legacy(dto: ExportUserOpsPoolQueryDTO) -> dict[str, Any]:
    return user_ops_page_service.export_user_ops_pool(**_filters_to_kwargs(dto))


def upsert_lead_pool_member_legacy(dto: UpsertLeadPoolMemberCommandDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.upsert_user_ops_lead_pool_member(
        mobile=str(dto.mobile or "").strip(),
        external_userid=str(dto.external_userid or "").strip(),
        customer_name=str(dto.customer_name or "").strip(),
        owner_userid=str(dto.owner_userid or "").strip(),
        is_wecom_added=bool(dto.is_wecom_added),
        is_mobile_bound=bool(dto.is_mobile_bound),
        huangxiaocan_activation_state=str(dto.huangxiaocan_activation_state or "").strip(),
        class_term_no=dto.class_term_no,
        class_term_label=str(dto.class_term_label or "").strip(),
        entry_source=str(dto.entry_source or "").strip(),
        operator=str(dto.operator or "").strip(),
        remark=str(dto.remark or "").strip(),
    )


def write_lead_pool_history_legacy(dto: WriteLeadPoolHistoryCommandDTO) -> None:
    _bind_user_ops_runtime()
    return user_ops_domain_service.write_user_ops_lead_pool_history(
        mobile=str(dto.mobile or "").strip(),
        external_userid=str(dto.external_userid or "").strip(),
        action_type=str(dto.action_type or "").strip(),
        source_type=str(dto.source_type or "").strip(),
        operator=str(dto.operator or "").strip(),
        before_payload=dto.before_payload,
        after_payload=dto.after_payload,
        remark=str(dto.remark or "").strip(),
    )


def schedule_user_ops_auto_assign_class_term_job_legacy(
    dto: ScheduleUserOpsAutoAssignClassTermJobCommandDTO,
) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.schedule_user_ops_auto_assign_class_term_job(
        external_userid=str(dto.external_userid or "").strip(),
        owner_userid=str(dto.owner_userid or "").strip(),
        delay_seconds=dto.run_after_seconds if dto.delay_seconds is None else int(dto.delay_seconds),
        operator=str(dto.operator or "").strip(),
    )


def run_due_user_ops_deferred_jobs_legacy(dto: RunDueUserOpsDeferredJobsCommandDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.run_due_user_ops_deferred_jobs(limit=int(dto.limit))


def import_experience_leads_legacy(dto: ImportExperienceLeadsCommandDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.import_experience_leads(
        pasted_text=str(dto.pasted_text or ""),
        file_name=str(dto.file_name or ""),
        file_bytes=dto.file_bytes,
        created_by=str(dto.created_by or "").strip(),
    )


def import_mobile_class_term_legacy(dto: ImportMobileClassTermCommandDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.import_mobile_class_term_source(
        pasted_text=str(dto.pasted_text or ""),
        file_name=str(dto.file_name or ""),
        file_bytes=dto.file_bytes,
        created_by=str(dto.created_by or "").strip(),
    )


def import_activation_status_legacy(dto: ImportActivationStatusCommandDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.import_activation_status_source(
        pasted_text=str(dto.pasted_text or ""),
        file_name=str(dto.file_name or ""),
        file_bytes=dto.file_bytes,
        created_by=str(dto.created_by or "").strip(),
    )


def backfill_owner_class_terms_legacy(dto: BackfillOwnerClassTermsCommandDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.backfill_owner_class_terms_into_lead_pool(
        owner_userid=str(dto.owner_userid or "").strip(),
        class_term_min=int(dto.class_term_min),
        class_term_max=int(dto.class_term_max),
        dry_run=bool(dto.dry_run),
        operator=str(dto.operator or "").strip(),
        entry_source=str(dto.entry_source or "").strip(),
    )


def refresh_contact_tags_for_external_userid_legacy(dto: Any) -> dict[str, Any]:
    _bind_user_ops_runtime()
    scoped_tag_ids = dto.scoped_tag_ids
    if scoped_tag_ids is not None:
        scoped_tag_ids = list(scoped_tag_ids or [])
    return user_ops_domain_service.refresh_contact_tags_for_external_userid(
        external_userid=str(dto.external_userid or "").strip(),
        owner_userid=str(dto.owner_userid or "").strip(),
        scoped_tag_ids=scoped_tag_ids,
    )


def refresh_user_ops_contact_tags_legacy(dto: RefreshUserOpsContactTagsCommandDTO) -> dict[str, Any]:
    _bind_user_ops_runtime()
    refresh_scope = str(dto.refresh_scope or "").strip().lower() or "external_userid"
    if refresh_scope == "owner":
        return user_ops_domain_service.refresh_user_ops_contact_tags_for_owner(
            str(dto.owner_userid or "").strip()
        )
    if dto.scoped_tag_ids:
        return user_ops_domain_service.refresh_contact_tags_for_external_userid(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
            scoped_tag_ids=list(dto.scoped_tag_ids or []),
        )
    return user_ops_domain_service.refresh_user_ops_contact_tags_for_external_userid(
        external_userid=str(dto.external_userid or "").strip(),
        owner_userid=str(dto.owner_userid or "").strip(),
    )


def backfill_class_term_for_owner_legacy(dto: Any) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.backfill_class_term_for_owner(
        owner_userid=str(dto.owner_userid or "").strip(),
        dry_run=bool(dto.dry_run),
        operator=str(dto.operator or "").strip(),
    )


def upsert_user_ops_huangxiaocan_activation_source_legacy(dto: Any) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.upsert_user_ops_huangxiaocan_activation_source(
        mobile=str(dto.mobile or "").strip(),
        activation_state=str(dto.activation_state or "").strip(),
        import_batch_id=dto.import_batch_id,
        created_by=str(dto.created_by or "").strip(),
        is_active=bool(dto.is_active),
    )


def migrate_legacy_user_ops_pool_to_lead_pool_legacy(dto: Any) -> dict[str, Any]:
    _bind_user_ops_runtime()
    return user_ops_domain_service.migrate_legacy_user_ops_pool_to_lead_pool(
        operator=str(dto.operator or "").strip(),
    )
