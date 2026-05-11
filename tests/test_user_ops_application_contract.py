from __future__ import annotations

from wecom_ability_service import services
from wecom_ability_service.application.user_ops import (
    BackfillOwnerClassTermsCommand,
    ExportUserOpsPoolQuery,
    GetUserOpsOverviewQuery,
    ImportActivationStatusCommand,
    ImportExperienceLeadsCommand,
    ImportMobileClassTermCommand,
    LeadPoolFiltersDTO,
    ListLeadPoolQuery,
    ListUserOpsHistoryQuery,
    RefreshUserOpsContactTagsCommand,
    RunDueUserOpsDeferredJobsCommand,
    ScheduleUserOpsAutoAssignClassTermJobCommand,
    UpsertLeadPoolMemberCommand,
)
from wecom_ability_service.application.user_ops import commands as user_ops_commands
from wecom_ability_service.application.user_ops import queries as user_ops_queries
from wecom_ability_service.application.user_ops.commands import WriteLeadPoolHistoryCommand
from wecom_ability_service.application.user_ops.dto import (
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


def test_user_ops_application_api_is_importable():
    assert GetUserOpsOverviewQuery
    assert ListLeadPoolQuery
    assert ListUserOpsHistoryQuery
    assert ExportUserOpsPoolQuery
    assert UpsertLeadPoolMemberCommand
    assert WriteLeadPoolHistoryCommand
    assert ScheduleUserOpsAutoAssignClassTermJobCommand
    assert RunDueUserOpsDeferredJobsCommand
    assert ImportExperienceLeadsCommand
    assert ImportMobileClassTermCommand
    assert ImportActivationStatusCommand
    assert BackfillOwnerClassTermsCommand
    assert RefreshUserOpsContactTagsCommand


def test_services_user_ops_wrappers_route_through_application(monkeypatch):
    calls: dict[str, object] = {}

    class FakeGetUserOpsOverviewQuery:
        def __call__(self, dto):
            calls["get_user_ops_overview"] = dto
            return {"kind": "get_user_ops_overview"}

    class FakeListLeadPoolQuery:
        def __call__(self, dto):
            calls["list_user_ops_pool"] = dto
            return {"kind": "list_user_ops_pool"}

    class FakeListUserOpsHistoryQuery:
        def __call__(self, dto):
            calls["list_user_ops_history"] = dto
            return {"kind": "list_user_ops_history"}

    class FakeExportUserOpsPoolQuery:
        def __call__(self, dto):
            calls["export_user_ops_pool"] = dto
            return {"kind": "export_user_ops_pool"}

    class FakeUpsertLeadPoolMemberCommand:
        def __call__(self, dto):
            calls["upsert_user_ops_lead_pool_member"] = dto
            return {"kind": "upsert_user_ops_lead_pool_member"}

    class FakeWriteLeadPoolHistoryCommand:
        def __call__(self, dto):
            calls["write_user_ops_lead_pool_history"] = dto
            return None

    class FakeScheduleUserOpsAutoAssignClassTermJobCommand:
        def __call__(self, dto):
            calls["schedule_user_ops_auto_assign_class_term_job"] = dto
            return {"kind": "schedule_user_ops_auto_assign_class_term_job"}

    class FakeRunDueUserOpsDeferredJobsCommand:
        def __call__(self, dto):
            calls["run_due_user_ops_deferred_jobs"] = dto
            return {"kind": "run_due_user_ops_deferred_jobs"}

    class FakeImportExperienceLeadsCommand:
        def __call__(self, dto):
            calls["import_experience_leads"] = dto
            return {"kind": "import_experience_leads"}

    class FakeImportMobileClassTermCommand:
        def __call__(self, dto):
            calls["import_mobile_class_term_source"] = dto
            return {"kind": "import_mobile_class_term_source"}

    class FakeImportActivationStatusCommand:
        def __call__(self, dto):
            calls["import_activation_status_source"] = dto
            return {"kind": "import_activation_status_source"}

    class FakeBackfillOwnerClassTermsCommand:
        def __call__(self, dto):
            calls["backfill_owner_class_terms_into_lead_pool"] = dto
            return {"kind": "backfill_owner_class_terms_into_lead_pool"}

    class FakeRefreshUserOpsContactTagsCommand:
        def __call__(self, dto):
            key = (
                "refresh_user_ops_contact_tags_for_owner"
                if getattr(dto, "refresh_scope", "") == "owner"
                else "refresh_user_ops_contact_tags_for_external_userid"
            )
            calls[key] = dto
            return {"kind": key}

    monkeypatch.setattr(user_ops_queries, "GetUserOpsOverviewQuery", FakeGetUserOpsOverviewQuery)
    monkeypatch.setattr(user_ops_queries, "ListLeadPoolQuery", FakeListLeadPoolQuery)
    monkeypatch.setattr(user_ops_queries, "ListUserOpsHistoryQuery", FakeListUserOpsHistoryQuery)
    monkeypatch.setattr(user_ops_queries, "ExportUserOpsPoolQuery", FakeExportUserOpsPoolQuery)
    monkeypatch.setattr(user_ops_commands, "UpsertLeadPoolMemberCommand", FakeUpsertLeadPoolMemberCommand)
    monkeypatch.setattr(user_ops_commands, "WriteLeadPoolHistoryCommand", FakeWriteLeadPoolHistoryCommand)
    monkeypatch.setattr(
        user_ops_commands,
        "ScheduleUserOpsAutoAssignClassTermJobCommand",
        FakeScheduleUserOpsAutoAssignClassTermJobCommand,
    )
    monkeypatch.setattr(
        user_ops_commands,
        "RunDueUserOpsDeferredJobsCommand",
        FakeRunDueUserOpsDeferredJobsCommand,
    )
    monkeypatch.setattr(user_ops_commands, "ImportExperienceLeadsCommand", FakeImportExperienceLeadsCommand)
    monkeypatch.setattr(user_ops_commands, "ImportMobileClassTermCommand", FakeImportMobileClassTermCommand)
    monkeypatch.setattr(user_ops_commands, "ImportActivationStatusCommand", FakeImportActivationStatusCommand)
    monkeypatch.setattr(user_ops_commands, "BackfillOwnerClassTermsCommand", FakeBackfillOwnerClassTermsCommand)
    monkeypatch.setattr(user_ops_commands, "RefreshUserOpsContactTagsCommand", FakeRefreshUserOpsContactTagsCommand)

    assert services.get_user_ops_overview(query="客户A") == {"kind": "get_user_ops_overview"}
    assert services.list_user_ops_pool(query="客户A") == {"kind": "list_user_ops_pool"}
    assert services.list_user_ops_history(limit=12) == {"kind": "list_user_ops_history"}
    assert services.export_user_ops_pool(query="客户A") == {"kind": "export_user_ops_pool"}
    assert services.upsert_user_ops_lead_pool_member(
        mobile="13800138000",
        external_userid="wm_ext_001",
        entry_source="sidebar",
    ) == {"kind": "upsert_user_ops_lead_pool_member"}
    assert (
        services.write_user_ops_lead_pool_history(
            mobile="13800138000",
            external_userid="wm_ext_001",
            action_type="lead_pool_upsert",
            source_type="sidebar",
            operator="sales_01",
            before_payload={},
            after_payload={},
        )
        is None
    )
    assert services.schedule_user_ops_auto_assign_class_term_job(
        external_userid="wm_ext_001",
        owner_userid="sales_01",
        delay_seconds=30,
        operator="system",
    ) == {"kind": "schedule_user_ops_auto_assign_class_term_job"}
    assert services.run_due_user_ops_deferred_jobs(limit=9) == {"kind": "run_due_user_ops_deferred_jobs"}
    assert services.import_experience_leads(
        pasted_text="13800138000",
        created_by="admin",
    ) == {"kind": "import_experience_leads"}
    assert services.import_mobile_class_term_source(
        pasted_text="13800138000,3期",
        created_by="admin",
    ) == {"kind": "import_mobile_class_term_source"}
    assert services.import_activation_status_source(
        pasted_text="13800138000,已激活",
        created_by="admin",
    ) == {"kind": "import_activation_status_source"}
    assert services.backfill_owner_class_terms_into_lead_pool(
        owner_userid="sales_01",
        dry_run=False,
        operator="admin",
    ) == {"kind": "backfill_owner_class_terms_into_lead_pool"}
    assert services.refresh_user_ops_contact_tags_for_external_userid(
        external_userid="wm_ext_001",
        owner_userid="sales_01",
    ) == {"kind": "refresh_user_ops_contact_tags_for_external_userid"}
    assert services.refresh_user_ops_contact_tags_for_owner("sales_01") == {
        "kind": "refresh_user_ops_contact_tags_for_owner",
    }

    assert isinstance(calls["get_user_ops_overview"], GetUserOpsOverviewQueryDTO)
    assert isinstance(calls["get_user_ops_overview"].filters, LeadPoolFiltersDTO)
    assert isinstance(calls["list_user_ops_pool"], ListLeadPoolQueryDTO)
    assert isinstance(calls["list_user_ops_history"], ListUserOpsHistoryQueryDTO)
    assert isinstance(calls["export_user_ops_pool"], ExportUserOpsPoolQueryDTO)
    assert isinstance(calls["upsert_user_ops_lead_pool_member"], UpsertLeadPoolMemberCommandDTO)
    assert isinstance(calls["write_user_ops_lead_pool_history"], WriteLeadPoolHistoryCommandDTO)
    assert isinstance(
        calls["schedule_user_ops_auto_assign_class_term_job"],
        ScheduleUserOpsAutoAssignClassTermJobCommandDTO,
    )
    assert isinstance(calls["run_due_user_ops_deferred_jobs"], RunDueUserOpsDeferredJobsCommandDTO)
    assert isinstance(calls["import_experience_leads"], ImportExperienceLeadsCommandDTO)
    assert isinstance(calls["import_mobile_class_term_source"], ImportMobileClassTermCommandDTO)
    assert isinstance(calls["import_activation_status_source"], ImportActivationStatusCommandDTO)
    assert isinstance(calls["backfill_owner_class_terms_into_lead_pool"], BackfillOwnerClassTermsCommandDTO)
    assert isinstance(
        calls["refresh_user_ops_contact_tags_for_external_userid"],
        RefreshUserOpsContactTagsCommandDTO,
    )
    assert isinstance(calls["refresh_user_ops_contact_tags_for_owner"], RefreshUserOpsContactTagsCommandDTO)


