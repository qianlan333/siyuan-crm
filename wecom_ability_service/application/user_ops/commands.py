from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...domains.user_ops import service as user_ops_domain_service
from . import _runtime
from .dto import (
    BackfillOwnerClassTermsCommandDTO,
    BackfillOwnerClassTermsResultDTO,
    ImportActivationStatusCommandDTO,
    ImportActivationStatusResultDTO,
    ImportExperienceLeadsCommandDTO,
    ImportExperienceLeadsResultDTO,
    ImportMobileClassTermCommandDTO,
    ImportMobileClassTermResultDTO,
    RefreshUserOpsContactTagsCommandDTO,
    RefreshUserOpsContactTagsResultDTO,
    RunDueUserOpsDeferredJobsCommandDTO,
    RunDueUserOpsDeferredJobsResultDTO,
    ScheduleUserOpsAutoAssignClassTermJobCommandDTO,
    ScheduleUserOpsAutoAssignClassTermJobResultDTO,
    UpsertLeadPoolMemberCommandDTO,
    UpsertLeadPoolMemberResultDTO,
    WriteLeadPoolHistoryCommandDTO,
    WriteLeadPoolHistoryResultDTO,
)

UpsertSidebarLeadPoolClassTermResultDTO = dict[str, Any]
RefreshContactTagsForExternalUseridResultDTO = dict[str, Any]
BackfillClassTermForOwnerResultDTO = dict[str, Any]
UpsertUserOpsHuangxiaocanActivationSourceResultDTO = dict[str, Any]
MigrateLegacyUserOpsPoolToLeadPoolResultDTO = dict[str, Any]


@dataclass(slots=True)
class UpsertSidebarLeadPoolClassTermCommandDTO:
    external_userid: str
    owner_userid: str = ""
    class_term_no: int = 0
    operator: str = ""


@dataclass(slots=True)
class RefreshContactTagsForExternalUseridCommandDTO:
    external_userid: str
    owner_userid: str = ""
    scoped_tag_ids: list[str] | None = None


@dataclass(slots=True)
class BackfillClassTermForOwnerCommandDTO:
    owner_userid: str
    dry_run: bool = True
    operator: str = ""


@dataclass(slots=True)
class UpsertUserOpsHuangxiaocanActivationSourceCommandDTO:
    mobile: str
    activation_state: str
    activation_remark: str = ""
    is_active: bool = True
    created_by: str = ""
    import_batch_id: int | str | None = None


@dataclass(slots=True)
class MigrateLegacyUserOpsPoolToLeadPoolCommandDTO:
    operator: str = ""


class UpsertLeadPoolMemberCommand:
    def __call__(self, dto: UpsertLeadPoolMemberCommandDTO) -> UpsertLeadPoolMemberResultDTO:
        _runtime.bind_user_ops_runtime()
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

    execute = __call__


class WriteLeadPoolHistoryCommand:
    def __call__(self, dto: WriteLeadPoolHistoryCommandDTO) -> WriteLeadPoolHistoryResultDTO:
        _runtime.bind_user_ops_runtime()
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

    execute = __call__


class ScheduleUserOpsAutoAssignClassTermJobCommand:
    def __call__(
        self,
        dto: ScheduleUserOpsAutoAssignClassTermJobCommandDTO,
    ) -> ScheduleUserOpsAutoAssignClassTermJobResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.schedule_user_ops_auto_assign_class_term_job(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
            delay_seconds=dto.run_after_seconds if dto.delay_seconds is None else int(dto.delay_seconds),
            operator=str(dto.operator or "").strip(),
        )

    execute = __call__


class RunDueUserOpsDeferredJobsCommand:
    def __call__(
        self,
        dto: RunDueUserOpsDeferredJobsCommandDTO | None = None,
    ) -> RunDueUserOpsDeferredJobsResultDTO:
        effective_dto = dto or RunDueUserOpsDeferredJobsCommandDTO()
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.run_due_user_ops_deferred_jobs(limit=int(effective_dto.limit))

    execute = __call__


class ImportExperienceLeadsCommand:
    def __call__(self, dto: ImportExperienceLeadsCommandDTO) -> ImportExperienceLeadsResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.import_experience_leads(
            pasted_text=str(dto.pasted_text or ""),
            file_name=str(dto.file_name or ""),
            file_bytes=dto.file_bytes,
            created_by=str(dto.created_by or "").strip(),
        )

    execute = __call__


class ImportMobileClassTermCommand:
    def __call__(self, dto: ImportMobileClassTermCommandDTO) -> ImportMobileClassTermResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.import_mobile_class_term_source(
            pasted_text=str(dto.pasted_text or ""),
            file_name=str(dto.file_name or ""),
            file_bytes=dto.file_bytes,
            created_by=str(dto.created_by or "").strip(),
        )

    execute = __call__


class ImportActivationStatusCommand:
    def __call__(self, dto: ImportActivationStatusCommandDTO) -> ImportActivationStatusResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.import_activation_status_source(
            pasted_text=str(dto.pasted_text or ""),
            file_name=str(dto.file_name or ""),
            file_bytes=dto.file_bytes,
            created_by=str(dto.created_by or "").strip(),
        )

    execute = __call__


class BackfillOwnerClassTermsCommand:
    def __call__(self, dto: BackfillOwnerClassTermsCommandDTO) -> BackfillOwnerClassTermsResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.backfill_owner_class_terms_into_lead_pool(
            owner_userid=str(dto.owner_userid or "").strip(),
            class_term_min=int(dto.class_term_min),
            class_term_max=int(dto.class_term_max),
            dry_run=bool(dto.dry_run),
            operator=str(dto.operator or "").strip(),
            entry_source=str(dto.entry_source or "").strip(),
        )

    execute = __call__


class RefreshUserOpsContactTagsCommand:
    def __call__(
        self,
        dto: RefreshUserOpsContactTagsCommandDTO,
    ) -> RefreshUserOpsContactTagsResultDTO:
        _runtime.bind_user_ops_runtime()
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

    execute = __call__


class RefreshContactTagsForExternalUseridCommand:
    def __call__(
        self,
        dto: RefreshContactTagsForExternalUseridCommandDTO,
    ) -> RefreshContactTagsForExternalUseridResultDTO:
        _runtime.bind_user_ops_runtime()
        scoped_tag_ids = dto.scoped_tag_ids
        if scoped_tag_ids is not None:
            scoped_tag_ids = list(scoped_tag_ids or [])
        return user_ops_domain_service.refresh_contact_tags_for_external_userid(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
            scoped_tag_ids=scoped_tag_ids,
        )

    execute = __call__


class UpsertSidebarLeadPoolClassTermCommand:
    def __call__(
        self,
        dto: UpsertSidebarLeadPoolClassTermCommandDTO,
    ) -> UpsertSidebarLeadPoolClassTermResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.upsert_sidebar_lead_pool_class_term(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
            class_term_no=int(dto.class_term_no),
            operator=str(dto.operator or "").strip(),
        )

    execute = __call__


class BackfillClassTermForOwnerCommand:
    def __call__(
        self,
        dto: BackfillClassTermForOwnerCommandDTO,
    ) -> BackfillClassTermForOwnerResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.backfill_class_term_for_owner(
            owner_userid=str(dto.owner_userid or "").strip(),
            dry_run=bool(dto.dry_run),
            operator=str(dto.operator or "").strip(),
        )

    execute = __call__


class UpsertUserOpsHuangxiaocanActivationSourceCommand:
    def __call__(
        self,
        dto: UpsertUserOpsHuangxiaocanActivationSourceCommandDTO,
    ) -> UpsertUserOpsHuangxiaocanActivationSourceResultDTO:
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.upsert_user_ops_huangxiaocan_activation_source(
            mobile=str(dto.mobile or "").strip(),
            activation_state=str(dto.activation_state or "").strip(),
            import_batch_id=dto.import_batch_id,
            created_by=str(dto.created_by or "").strip(),
            is_active=bool(dto.is_active),
        )

    execute = __call__


class MigrateLegacyUserOpsPoolToLeadPoolCommand:
    def __call__(
        self,
        dto: MigrateLegacyUserOpsPoolToLeadPoolCommandDTO | None = None,
    ) -> MigrateLegacyUserOpsPoolToLeadPoolResultDTO:
        effective_dto = dto or MigrateLegacyUserOpsPoolToLeadPoolCommandDTO()
        _runtime.bind_user_ops_runtime()
        return user_ops_domain_service.migrate_legacy_user_ops_pool_to_lead_pool(
            operator=str(effective_dto.operator or "").strip(),
        )

    execute = __call__


__all__ = [
    "BackfillClassTermForOwnerCommand",
    "BackfillClassTermForOwnerCommandDTO",
    "BackfillClassTermForOwnerResultDTO",
    "BackfillOwnerClassTermsCommand",
    "ImportActivationStatusCommand",
    "ImportExperienceLeadsCommand",
    "ImportMobileClassTermCommand",
    "MigrateLegacyUserOpsPoolToLeadPoolCommand",
    "MigrateLegacyUserOpsPoolToLeadPoolCommandDTO",
    "MigrateLegacyUserOpsPoolToLeadPoolResultDTO",
    "RefreshContactTagsForExternalUseridCommand",
    "RefreshContactTagsForExternalUseridCommandDTO",
    "RefreshContactTagsForExternalUseridResultDTO",
    "RefreshUserOpsContactTagsCommand",
    "RunDueUserOpsDeferredJobsCommand",
    "ScheduleUserOpsAutoAssignClassTermJobCommand",
    "UpsertUserOpsHuangxiaocanActivationSourceCommand",
    "UpsertUserOpsHuangxiaocanActivationSourceCommandDTO",
    "UpsertUserOpsHuangxiaocanActivationSourceResultDTO",
    "UpsertSidebarLeadPoolClassTermCommand",
    "UpsertSidebarLeadPoolClassTermCommandDTO",
    "UpsertSidebarLeadPoolClassTermResultDTO",
    "UpsertLeadPoolMemberCommand",
    "WriteLeadPoolHistoryCommand",
]
