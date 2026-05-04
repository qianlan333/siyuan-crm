from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import _legacy_delegate
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
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.upsert_user_ops_lead_pool_member`` via ``_legacy_delegate``. Compatibility note: this is still a lead-pool primitive-shaped write owner, and future caller cutovers should prefer higher-level commands instead of calling it directly."""

    def __call__(self, dto: UpsertLeadPoolMemberCommandDTO) -> UpsertLeadPoolMemberResultDTO:
        return _legacy_delegate.upsert_lead_pool_member_legacy(dto)

    execute = __call__


class WriteLeadPoolHistoryCommand:
    """Internal Wave 2 user-ops primitive that delegates to ``domains.user_ops.service.write_user_ops_lead_pool_history`` via ``_legacy_delegate``. Compatibility shim only; future callers must use formal application commands instead of invoking this primitive directly."""

    def __call__(self, dto: WriteLeadPoolHistoryCommandDTO) -> WriteLeadPoolHistoryResultDTO:
        return _legacy_delegate.write_lead_pool_history_legacy(dto)

    execute = __call__


class ScheduleUserOpsAutoAssignClassTermJobCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.schedule_user_ops_auto_assign_class_term_job`` via ``_legacy_delegate`` for callback and background-job callers once they cut over."""

    def __call__(
        self,
        dto: ScheduleUserOpsAutoAssignClassTermJobCommandDTO,
    ) -> ScheduleUserOpsAutoAssignClassTermJobResultDTO:
        return _legacy_delegate.schedule_user_ops_auto_assign_class_term_job_legacy(dto)

    execute = __call__


class RunDueUserOpsDeferredJobsCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.run_due_user_ops_deferred_jobs`` via ``_legacy_delegate`` for admin jobs and background-job callers once they cut over."""

    def __call__(
        self,
        dto: RunDueUserOpsDeferredJobsCommandDTO | None = None,
    ) -> RunDueUserOpsDeferredJobsResultDTO:
        return _legacy_delegate.run_due_user_ops_deferred_jobs_legacy(
            dto or RunDueUserOpsDeferredJobsCommandDTO()
        )

    execute = __call__


class ImportExperienceLeadsCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.import_experience_leads`` via ``_legacy_delegate`` for admin import callers once they cut over."""

    def __call__(self, dto: ImportExperienceLeadsCommandDTO) -> ImportExperienceLeadsResultDTO:
        return _legacy_delegate.import_experience_leads_legacy(dto)

    execute = __call__


class ImportMobileClassTermCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.import_mobile_class_term_source`` via ``_legacy_delegate`` for admin import callers once they cut over."""

    def __call__(self, dto: ImportMobileClassTermCommandDTO) -> ImportMobileClassTermResultDTO:
        return _legacy_delegate.import_mobile_class_term_legacy(dto)

    execute = __call__


class ImportActivationStatusCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.import_activation_status_source`` via ``_legacy_delegate`` for admin import callers once they cut over."""

    def __call__(self, dto: ImportActivationStatusCommandDTO) -> ImportActivationStatusResultDTO:
        return _legacy_delegate.import_activation_status_legacy(dto)

    execute = __call__


class BackfillOwnerClassTermsCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.backfill_owner_class_terms_into_lead_pool`` via ``_legacy_delegate`` for admin and maintenance callers once they cut over."""

    def __call__(self, dto: BackfillOwnerClassTermsCommandDTO) -> BackfillOwnerClassTermsResultDTO:
        return _legacy_delegate.backfill_owner_class_terms_legacy(dto)

    execute = __call__


class RefreshUserOpsContactTagsCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.refresh_user_ops_contact_tags_for_external_userid`` or ``refresh_user_ops_contact_tags_for_owner`` via ``_legacy_delegate`` for maintenance callers once they cut over."""

    def __call__(
        self,
        dto: RefreshUserOpsContactTagsCommandDTO,
    ) -> RefreshUserOpsContactTagsResultDTO:
        return _legacy_delegate.refresh_user_ops_contact_tags_legacy(dto)

    execute = __call__


class RefreshContactTagsForExternalUseridCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.refresh_contact_tags_for_external_userid`` via ``_legacy_delegate`` for maintenance callers that need full or scoped tag snapshot refresh semantics."""

    def __call__(
        self,
        dto: RefreshContactTagsForExternalUseridCommandDTO,
    ) -> RefreshContactTagsForExternalUseridResultDTO:
        return _legacy_delegate.refresh_contact_tags_for_external_userid_legacy(dto)

    execute = __call__


class UpsertSidebarLeadPoolClassTermCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.upsert_sidebar_lead_pool_class_term`` via ``_legacy_delegate`` for sidebar class-term patch callers after caller cutover."""

    def __call__(
        self,
        dto: UpsertSidebarLeadPoolClassTermCommandDTO,
    ) -> UpsertSidebarLeadPoolClassTermResultDTO:
        _legacy_delegate._bind_user_ops_runtime()
        return _legacy_delegate.user_ops_domain_service.upsert_sidebar_lead_pool_class_term(
            external_userid=str(dto.external_userid or "").strip(),
            owner_userid=str(dto.owner_userid or "").strip(),
            class_term_no=int(dto.class_term_no),
            operator=str(dto.operator or "").strip(),
        )

    execute = __call__


class BackfillClassTermForOwnerCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.backfill_class_term_for_owner`` via ``_legacy_delegate`` for compatibility callers that still use the legacy owner-level maintenance entry."""

    def __call__(
        self,
        dto: BackfillClassTermForOwnerCommandDTO,
    ) -> BackfillClassTermForOwnerResultDTO:
        return _legacy_delegate.backfill_class_term_for_owner_legacy(dto)

    execute = __call__


class UpsertUserOpsHuangxiaocanActivationSourceCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.upsert_user_ops_huangxiaocan_activation_source`` via ``_legacy_delegate`` for import and patch compatibility callers."""

    def __call__(
        self,
        dto: UpsertUserOpsHuangxiaocanActivationSourceCommandDTO,
    ) -> UpsertUserOpsHuangxiaocanActivationSourceResultDTO:
        return _legacy_delegate.upsert_user_ops_huangxiaocan_activation_source_legacy(dto)

    execute = __call__


class MigrateLegacyUserOpsPoolToLeadPoolCommand:
    """Wave 2 user-ops command that delegates to ``domains.user_ops.service.migrate_legacy_user_ops_pool_to_lead_pool`` via ``_legacy_delegate`` for one-time compatibility migration callers."""

    def __call__(
        self,
        dto: MigrateLegacyUserOpsPoolToLeadPoolCommandDTO | None = None,
    ) -> MigrateLegacyUserOpsPoolToLeadPoolResultDTO:
        return _legacy_delegate.migrate_legacy_user_ops_pool_to_lead_pool_legacy(
            dto or MigrateLegacyUserOpsPoolToLeadPoolCommandDTO()
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
