from __future__ import annotations

from pathlib import Path

from wecom_ability_service import services
from wecom_ability_service.application.class_user import (
    ApplyClassUserStatusChangeCommand,
    ExportClassUserManagementRecordsQuery,
    GetClassUserStatusCurrentQuery,
    GetClassUserSnapshotQuery,
    GetClassUserStatusDefinitionQuery,
    ListClassUserManagementRecordsQuery,
    ListClassUserStatusHistoryQuery,
    MigrateClassUserStatusFromContactTagsCommand,
    UpdateClassUserStatusSyncResultCommand,
)
from wecom_ability_service.application.class_user import commands as class_user_commands
from wecom_ability_service.application.class_user import queries as class_user_queries
from wecom_ability_service.application.class_user.dto import (
    ApplyClassUserStatusChangeCommandDTO,
    ClearClassUserStatusCurrentCommandDTO,
    ExportClassUserManagementRecordsQueryDTO,
    GetClassUserSnapshotQueryDTO,
    GetClassUserStatusCurrentQueryDTO,
    GetClassUserStatusDefinitionQueryDTO,
    ListClassUserManagementRecordsQueryDTO,
    ListClassUserStatusHistoryQueryDTO,
    UpdateClassUserStatusSyncResultCommandDTO,
)


ROOT = Path(__file__).resolve().parents[1]


def test_class_user_application_api_is_importable():
    assert GetClassUserStatusDefinitionQuery
    assert GetClassUserStatusCurrentQuery
    assert GetClassUserSnapshotQuery
    assert ListClassUserStatusHistoryQuery
    assert ListClassUserManagementRecordsQuery
    assert ExportClassUserManagementRecordsQuery
    assert ApplyClassUserStatusChangeCommand
    assert class_user_commands.ClearClassUserStatusCurrentCommand
    assert UpdateClassUserStatusSyncResultCommand
    assert MigrateClassUserStatusFromContactTagsCommand
    assert class_user_queries.ListSignupScopeExternalUseridsQuery
    assert class_user_queries.ListClassUserLiveBaseRowsQuery


def test_services_class_user_wrappers_route_through_application(monkeypatch):
    calls: dict[str, object] = {}

    class FakeGetClassUserStatusDefinitionQuery:
        def __call__(self, dto):
            calls["get_class_user_status_definition"] = dto
            return {"signup_status": "lead", "label": "报名引流品"}

    class FakeGetClassUserStatusCurrentQuery:
        def __call__(self, dto):
            calls["get_class_user_status_current"] = dto
            return {"external_userid": "wm_ext_001", "signup_status": "lead"}

    class FakeGetClassUserSnapshotQuery:
        def __call__(self, dto):
            calls["get_class_user_snapshot"] = dto
            return {
                "external_userid": "wm_ext_001",
                "customer_name_snapshot": "客户A",
                "owner_userid_snapshot": "sales_01",
                "mobile_snapshot": "13800138000",
            }

    class FakeListClassUserStatusHistoryQuery:
        def __call__(self, dto):
            calls["list_class_user_status_history"] = dto
            return {"items": [], "total": 0, "limit": 20}

    class FakeListClassUserManagementRecordsQuery:
        def __call__(self, dto):
            calls["list_class_user_management_records"] = dto
            return {"items": [], "total": 0, "stats": [], "meta": {}, "filter": "lead", "status_definitions": []}

    class FakeExportClassUserManagementRecordsQuery:
        def __call__(self, dto):
            calls["export_class_user_management_records"] = dto
            return {"headers": ["客户昵称"], "rows": [], "filename": "class-user.xls"}

    class FakeApplyClassUserStatusChangeCommand:
        def __call__(self, dto):
            calls["apply_class_user_status_change"] = dto
            return {"external_userid": "wm_ext_001", "signup_status": "signed_999"}

    class FakeUpdateClassUserStatusSyncResultCommand:
        def __call__(self, dto):
            calls["update_class_user_status_sync_result"] = dto
            return None

    class FakeMigrateClassUserStatusFromContactTagsCommand:
        def __call__(self, dto=None):
            calls["migrate_class_user_status_from_contact_tags"] = dto
            return {"migrated_count": 3}

    def fake_upsert_class_user_status_current_primitive(**kwargs):
        calls["upsert_class_user_status_current"] = kwargs
        return None

    def fake_append_class_user_status_history_primitive(**kwargs):
        calls["append_class_user_status_history"] = kwargs
        return None

    monkeypatch.setattr(
        class_user_queries,
        "GetClassUserStatusDefinitionQuery",
        FakeGetClassUserStatusDefinitionQuery,
    )
    monkeypatch.setattr(
        class_user_queries,
        "GetClassUserStatusCurrentQuery",
        FakeGetClassUserStatusCurrentQuery,
    )
    monkeypatch.setattr(
        class_user_queries,
        "GetClassUserSnapshotQuery",
        FakeGetClassUserSnapshotQuery,
    )
    monkeypatch.setattr(
        class_user_queries,
        "ListClassUserStatusHistoryQuery",
        FakeListClassUserStatusHistoryQuery,
    )
    monkeypatch.setattr(
        class_user_queries,
        "ListClassUserManagementRecordsQuery",
        FakeListClassUserManagementRecordsQuery,
    )
    monkeypatch.setattr(
        class_user_queries,
        "ExportClassUserManagementRecordsQuery",
        FakeExportClassUserManagementRecordsQuery,
    )
    monkeypatch.setattr(
        class_user_commands,
        "ApplyClassUserStatusChangeCommand",
        FakeApplyClassUserStatusChangeCommand,
    )
    monkeypatch.setattr(
        class_user_commands,
        "UpdateClassUserStatusSyncResultCommand",
        FakeUpdateClassUserStatusSyncResultCommand,
    )
    monkeypatch.setattr(
        class_user_commands,
        "MigrateClassUserStatusFromContactTagsCommand",
        FakeMigrateClassUserStatusFromContactTagsCommand,
    )
    monkeypatch.setattr(
        class_user_commands,
        "upsert_class_user_status_current_primitive",
        fake_upsert_class_user_status_current_primitive,
    )
    monkeypatch.setattr(
        class_user_commands,
        "append_class_user_status_history_primitive",
        fake_append_class_user_status_history_primitive,
    )

    assert services.get_class_user_status_definition("lead") == {
        "signup_status": "lead",
        "label": "报名引流品",
    }
    assert services.get_class_user_status_current("wm_ext_001") == {
        "external_userid": "wm_ext_001",
        "signup_status": "lead",
    }
    assert services.get_class_user_snapshot("wm_ext_001", "sales_01") == {
        "external_userid": "wm_ext_001",
        "customer_name_snapshot": "客户A",
        "owner_userid_snapshot": "sales_01",
        "mobile_snapshot": "13800138000",
    }
    assert services.list_class_user_status_history(limit=20) == {
        "items": [],
        "total": 0,
        "limit": 20,
    }
    assert services.list_class_user_management_records("lead") == {
        "items": [],
        "total": 0,
        "stats": [],
        "meta": {},
        "filter": "lead",
        "status_definitions": [],
    }
    assert services.export_class_user_management_records("lead") == {
        "headers": ["客户昵称"],
        "rows": [],
        "filename": "class-user.xls",
    }
    assert services.apply_class_user_status_change(
        external_userid="wm_ext_001",
        signup_status="signed_999",
        set_by_userid="sales_01",
        customer_name_snapshot="客户A",
        owner_userid_snapshot="sales_01",
        mobile_snapshot="13800138000",
    ) == {
        "external_userid": "wm_ext_001",
        "signup_status": "signed_999",
    }
    assert (
        services.update_class_user_status_sync_result(
            "wm_ext_001",
            wecom_tag_sync_status="success",
            wecom_tag_sync_error="",
        )
        is None
    )
    assert services.migrate_class_user_status_from_contact_tags() == {"migrated_count": 3}
    assert (
        services.upsert_class_user_status_current(
            external_userid="wm_ext_001",
            signup_status="lead",
        )
        is None
    )
    assert (
        services.append_class_user_status_history(
            external_userid="wm_ext_001",
            old_signup_status="",
            new_signup_status="lead",
        )
        is None
    )

    assert isinstance(calls["get_class_user_status_definition"], GetClassUserStatusDefinitionQueryDTO)
    assert isinstance(calls["get_class_user_status_current"], GetClassUserStatusCurrentQueryDTO)
    assert isinstance(calls["get_class_user_snapshot"], GetClassUserSnapshotQueryDTO)
    assert isinstance(calls["list_class_user_status_history"], ListClassUserStatusHistoryQueryDTO)
    assert isinstance(calls["list_class_user_management_records"], ListClassUserManagementRecordsQueryDTO)
    assert isinstance(calls["export_class_user_management_records"], ExportClassUserManagementRecordsQueryDTO)
    assert isinstance(calls["apply_class_user_status_change"], ApplyClassUserStatusChangeCommandDTO)
    assert isinstance(calls["update_class_user_status_sync_result"], UpdateClassUserStatusSyncResultCommandDTO)
    assert calls["migrate_class_user_status_from_contact_tags"] is None
    assert calls["upsert_class_user_status_current"] == {
        "external_userid": "wm_ext_001",
        "signup_status": "lead",
    }
    assert calls["append_class_user_status_history"] == {
        "external_userid": "wm_ext_001",
        "old_signup_status": "",
        "new_signup_status": "lead",
    }


def test_class_user_application_skeleton_delegates_to_legacy_module(monkeypatch):
    calls: dict[str, object] = {}

    def _record(name: str, result):
        def _inner(*args, **kwargs):
            calls[name] = args[0] if args else kwargs
            return result

        return _inner

    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.get_class_user_status_definition_legacy",
        _record("get_class_user_status_definition", {"signup_status": "lead"}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.get_class_user_status_current_legacy",
        _record("get_class_user_status_current", {"external_userid": "wm_ext_001"}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.get_class_user_snapshot_legacy",
        _record(
            "get_class_user_snapshot",
            {
                "external_userid": "wm_ext_001",
                "customer_name_snapshot": "客户A",
                "owner_userid_snapshot": "sales_01",
                "mobile_snapshot": "13800138000",
            },
        ),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.list_class_user_status_history_legacy",
        _record("list_class_user_status_history", {"items": [], "total": 0, "limit": 100}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.list_class_user_management_records_legacy",
        _record(
            "list_class_user_management_records",
            {"items": [], "total": 0, "stats": [], "meta": {}, "filter": "", "status_definitions": []},
        ),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.export_class_user_management_records_legacy",
        _record("export_class_user_management_records", {"headers": [], "rows": [], "filename": "class-user.xls"}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.apply_class_user_status_change_legacy",
        _record("apply_class_user_status_change", {"external_userid": "wm_ext_001", "signup_status": "lead"}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.update_class_user_status_sync_result_legacy",
        _record("update_class_user_status_sync_result", None),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.clear_class_user_status_current_legacy",
        _record("clear_class_user_status_current", None),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.migrate_class_user_status_from_contact_tags_legacy",
        _record("migrate_class_user_status_from_contact_tags", {"migrated_count": 2}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.list_signup_scope_external_userids_legacy",
        _record("list_signup_scope_external_userids", ["wm_ext_001"]),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.list_class_user_live_base_rows_legacy",
        _record("list_class_user_live_base_rows", [{"external_userid": "wm_ext_001"}]),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.upsert_class_user_status_current_legacy",
        _record("upsert_class_user_status_current", None),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.class_user._legacy_delegate.append_class_user_status_history_legacy",
        _record("append_class_user_status_history", None),
    )

    assert class_user_queries.GetClassUserStatusDefinitionQuery()(
        GetClassUserStatusDefinitionQueryDTO(signup_status="lead")
    ) == {"signup_status": "lead"}
    assert class_user_queries.GetClassUserStatusCurrentQuery()(
        GetClassUserStatusCurrentQueryDTO(external_userid="wm_ext_001")
    ) == {"external_userid": "wm_ext_001"}
    assert class_user_queries.GetClassUserSnapshotQuery()(
        GetClassUserSnapshotQueryDTO(external_userid="wm_ext_001", owner_userid="sales_01")
    ) == {
        "external_userid": "wm_ext_001",
        "customer_name_snapshot": "客户A",
        "owner_userid_snapshot": "sales_01",
        "mobile_snapshot": "13800138000",
    }
    assert class_user_queries.ListClassUserStatusHistoryQuery()(
        ListClassUserStatusHistoryQueryDTO(limit=100)
    ) == {"items": [], "total": 0, "limit": 100}
    assert class_user_queries.ListClassUserManagementRecordsQuery()(
        ListClassUserManagementRecordsQueryDTO(signup_status="lead")
    ) == {
        "items": [],
        "total": 0,
        "stats": [],
        "meta": {},
        "filter": "",
        "status_definitions": [],
    }
    assert class_user_queries.ExportClassUserManagementRecordsQuery()(
        ExportClassUserManagementRecordsQueryDTO(signup_status="lead")
    ) == {
        "headers": [],
        "rows": [],
        "filename": "class-user.xls",
    }
    assert class_user_commands.ApplyClassUserStatusChangeCommand()(
        ApplyClassUserStatusChangeCommandDTO(
            external_userid="wm_ext_001",
            signup_status="lead",
            set_by_userid="sales_01",
            customer_name_snapshot="客户A",
            owner_userid_snapshot="sales_01",
            mobile_snapshot="13800138000",
        )
    ) == {"external_userid": "wm_ext_001", "signup_status": "lead"}
    assert (
        class_user_commands.UpdateClassUserStatusSyncResultCommand()(
            UpdateClassUserStatusSyncResultCommandDTO(
                external_userid="wm_ext_001",
                wecom_tag_sync_status="success",
            )
        )
        is None
    )
    assert (
        class_user_commands.ClearClassUserStatusCurrentCommand()(
            ClearClassUserStatusCurrentCommandDTO(
                external_userid="wm_ext_001",
                set_by_userid="sales_01",
                customer_name_snapshot="客户A",
                owner_userid_snapshot="sales_01",
                mobile_snapshot="13800138000",
            )
        )
        is None
    )
    assert class_user_commands.MigrateClassUserStatusFromContactTagsCommand()() == {"migrated_count": 2}
    assert class_user_queries.ListSignupScopeExternalUseridsQuery()("ww-test") == ["wm_ext_001"]
    assert class_user_queries.ListClassUserLiveBaseRowsQuery()("ww-test") == [{"external_userid": "wm_ext_001"}]
    assert class_user_commands.upsert_class_user_status_current_primitive(
        external_userid="wm_ext_001",
        signup_status="lead",
    ) is None
    assert class_user_commands.append_class_user_status_history_primitive(
        external_userid="wm_ext_001",
        old_signup_status="",
        new_signup_status="lead",
    ) is None


def test_services_class_user_wrappers_do_not_alias_domain_service_directly():
    source = (ROOT / "wecom_ability_service" / "services.py").read_text(encoding="utf-8")

    required_fragments = [
        "GetClassUserStatusDefinitionQuery",
        "GetClassUserStatusCurrentQuery",
        "GetClassUserSnapshotQuery",
        "ListClassUserStatusHistoryQuery",
        "ListClassUserManagementRecordsQuery",
        "ExportClassUserManagementRecordsQuery",
        "ApplyClassUserStatusChangeCommand",
        "UpdateClassUserStatusSyncResultCommand",
        "MigrateClassUserStatusFromContactTagsCommand",
        "upsert_class_user_status_current_primitive",
        "append_class_user_status_history_primitive",
    ]
    for fragment in required_fragments:
        assert fragment in source, f"services.py must keep the Wave 2 class-user wrapper for {fragment}"

    forbidden_aliases = [
        "get_class_user_status_definition = class_user_domain_service.get_class_user_status_definition",
        "get_class_user_status_current = class_user_domain_service.get_class_user_status_current",
        "upsert_class_user_status_current = class_user_domain_service.upsert_class_user_status_current",
        "append_class_user_status_history = class_user_domain_service.append_class_user_status_history",
        "update_class_user_status_sync_result = class_user_domain_service.update_class_user_status_sync_result",
        "list_class_user_status_history = class_user_domain_service.list_class_user_status_history",
        "apply_class_user_status_change = class_user_domain_service.apply_class_user_status_change",
        "return class_user_domain_service.get_class_user_snapshot(",
        "return class_user_domain_service.list_class_user_management_records(",
        "return class_user_domain_service.export_class_user_management_records(",
        "return class_user_domain_service.migrate_class_user_status_from_contact_tags(",
    ]
    for fragment in forbidden_aliases:
        assert fragment not in source, f"services.py must not regress to direct class_user domain alias: {fragment}"
