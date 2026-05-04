from __future__ import annotations

from wecom_ability_service import services
from wecom_ability_service.application.identity_contact import (
    BindExternalContactIdentityCommand,
    CountExternalContactIdentityMapsQuery,
    GetContactBindingStatusQuery,
    GetPrimaryFollowUserUseridQuery,
    MarkExternalContactFollowUserStatusCommand,
    MarkExternalContactIdentityStatusCommand,
    RefreshExternalContactIdentityOwnerCommand,
    ReplaceFollowUsersCommand,
    ResolveExternalContactIdentityQuery,
    ResolvePersonIdentityQuery,
    UpsertExternalContactIdentityCommand,
)
from wecom_ability_service.application.identity_contact import commands as identity_commands
from wecom_ability_service.application.identity_contact import queries as identity_queries
from wecom_ability_service.application.identity_contact.dto import (
    BindExternalContactIdentityCommandDTO,
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


def test_identity_application_api_is_importable():
    assert ResolvePersonIdentityQuery
    assert GetContactBindingStatusQuery
    assert ResolveExternalContactIdentityQuery
    assert CountExternalContactIdentityMapsQuery
    assert GetPrimaryFollowUserUseridQuery
    assert BindExternalContactIdentityCommand
    assert UpsertExternalContactIdentityCommand
    assert ReplaceFollowUsersCommand
    assert RefreshExternalContactIdentityOwnerCommand
    assert MarkExternalContactIdentityStatusCommand
    assert MarkExternalContactFollowUserStatusCommand


def test_services_identity_wrappers_route_through_application(monkeypatch):
    calls: dict[str, object] = {}

    class FakeResolvePersonIdentityQuery:
        def __call__(self, dto):
            calls["resolve_person_identity"] = dto
            return {"kind": "resolve_person_identity"}

    class FakeGetContactBindingStatusQuery:
        def __call__(self, dto):
            calls["get_contact_binding_status"] = dto
            return {"kind": "get_contact_binding_status"}

    class FakeResolveExternalContactIdentityQuery:
        def __call__(self, dto):
            calls["resolve_external_contact_identity"] = dto
            return {"kind": "resolve_external_contact_identity"}

    class FakeCountExternalContactIdentityMapsQuery:
        def __call__(self, dto=None):
            calls["count_external_contact_identity_maps"] = dto
            return 17

    class FakeGetPrimaryFollowUserUseridQuery:
        def __call__(self, dto):
            calls["get_primary_follow_user_userid"] = dto
            return "sales_01"

    class FakeBindExternalContactIdentityCommand:
        def __call__(self, dto):
            key = "bind_mobile_to_external_contact" if getattr(dto, "mobile", "") else "bind_openid_to_external_contact"
            calls[key] = dto
            return {"kind": key}

    class FakeUpsertExternalContactIdentityCommand:
        def __call__(self, dto):
            calls["upsert_external_contact_identity"] = dto
            return 9

    class FakeReplaceFollowUsersCommand:
        def __call__(self, dto):
            calls["replace_external_contact_follow_users"] = dto
            return None

    class FakeRefreshExternalContactIdentityOwnerCommand:
        def __call__(self, dto):
            calls["refresh_external_contact_identity_owner"] = dto
            return None

    class FakeMarkExternalContactFollowUserStatusCommand:
        def __call__(self, dto):
            calls["mark_external_contact_follow_user_status"] = dto
            return None

    class FakeMarkExternalContactIdentityStatusCommand:
        def __call__(self, dto):
            calls["mark_external_contact_identity_status"] = dto
            return None

    monkeypatch.setattr(identity_queries, "ResolvePersonIdentityQuery", FakeResolvePersonIdentityQuery)
    monkeypatch.setattr(identity_queries, "GetContactBindingStatusQuery", FakeGetContactBindingStatusQuery)
    monkeypatch.setattr(identity_queries, "ResolveExternalContactIdentityQuery", FakeResolveExternalContactIdentityQuery)
    monkeypatch.setattr(identity_queries, "CountExternalContactIdentityMapsQuery", FakeCountExternalContactIdentityMapsQuery)
    monkeypatch.setattr(identity_queries, "GetPrimaryFollowUserUseridQuery", FakeGetPrimaryFollowUserUseridQuery)
    monkeypatch.setattr(identity_commands, "BindExternalContactIdentityCommand", FakeBindExternalContactIdentityCommand)
    monkeypatch.setattr(identity_commands, "UpsertExternalContactIdentityCommand", FakeUpsertExternalContactIdentityCommand)
    monkeypatch.setattr(identity_commands, "ReplaceFollowUsersCommand", FakeReplaceFollowUsersCommand)
    monkeypatch.setattr(
        identity_commands,
        "RefreshExternalContactIdentityOwnerCommand",
        FakeRefreshExternalContactIdentityOwnerCommand,
    )
    monkeypatch.setattr(
        identity_commands,
        "MarkExternalContactFollowUserStatusCommand",
        FakeMarkExternalContactFollowUserStatusCommand,
    )
    monkeypatch.setattr(
        identity_commands,
        "MarkExternalContactIdentityStatusCommand",
        FakeMarkExternalContactIdentityStatusCommand,
    )

    assert services.resolve_person_identity(external_userid="wm_ext_001") == {"kind": "resolve_person_identity"}
    assert services.get_contact_binding_status("wm_ext_001", "sales_01") == {"kind": "get_contact_binding_status"}
    assert services.resolve_external_contact_identity("ww-test", external_userid="wm_ext_001") == {
        "kind": "resolve_external_contact_identity"
    }
    assert services.count_external_contact_identity_maps() == 17
    assert services.get_primary_follow_user_userid("wm_ext_001") == "sales_01"
    assert services.bind_mobile_to_external_contact(
        external_userid="wm_ext_001",
        owner_userid="sales_01",
        bind_by_userid="sidebar_bind",
        mobile="13800138000",
        force_rebind=True,
    ) == {"kind": "bind_mobile_to_external_contact"}
    assert services.bind_openid_to_external_contact(
        "ww-test",
        "wm_ext_001",
        "openid-001",
        unionid="union-001",
    ) == {"kind": "bind_openid_to_external_contact"}
    assert services.upsert_external_contact_identity({"corp_id": "ww-test", "external_userid": "wm_ext_001"}) == 9
    assert services.replace_external_contact_follow_users(
        "ww-test",
        "wm_ext_001",
        [{"userid": "sales_01"}],
        preferred_userid="sales_01",
    ) is None
    assert services.refresh_external_contact_identity_owner("ww-test", "wm_ext_001") is None
    assert services.mark_external_contact_follow_user_status(
        "ww-test",
        "wm_ext_001",
        user_id="sales_01",
        status="inactive",
    ) is None
    assert services.mark_external_contact_identity_status(
        "ww-test",
        "wm_ext_001",
        status="inactive",
        follow_user_userid="sales_01",
    ) is None

    assert isinstance(calls["resolve_person_identity"], ResolvePersonIdentityQueryDTO)
    assert isinstance(calls["get_contact_binding_status"], GetContactBindingStatusQueryDTO)
    assert isinstance(calls["resolve_external_contact_identity"], ResolveExternalContactIdentityQueryDTO)
    assert isinstance(calls["get_primary_follow_user_userid"], GetPrimaryFollowUserUseridQueryDTO)
    assert isinstance(calls["bind_mobile_to_external_contact"], BindExternalContactIdentityCommandDTO)
    assert isinstance(calls["bind_openid_to_external_contact"], BindExternalContactIdentityCommandDTO)
    assert isinstance(calls["upsert_external_contact_identity"], UpsertExternalContactIdentityCommandDTO)
    assert isinstance(calls["replace_external_contact_follow_users"], ReplaceFollowUsersCommandDTO)
    assert isinstance(calls["refresh_external_contact_identity_owner"], RefreshExternalContactIdentityOwnerCommandDTO)
    assert isinstance(calls["mark_external_contact_follow_user_status"], MarkExternalContactFollowUserStatusCommandDTO)
    assert isinstance(calls["mark_external_contact_identity_status"], MarkExternalContactIdentityStatusCommandDTO)


def test_identity_application_skeleton_delegates_to_legacy_module(monkeypatch):
    calls: dict[str, object] = {}

    def _record(name: str, result):
        def _inner(dto):
            calls[name] = dto
            return result

        return _inner

    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.resolve_person_identity_legacy",
        _record("resolve_person_identity", {"ok": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.get_contact_binding_status_legacy",
        _record("get_contact_binding_status", {"ok": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.resolve_external_contact_identity_legacy",
        _record("resolve_external_contact_identity", {"ok": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.count_external_contact_identity_maps_legacy",
        _record("count_external_contact_identity_maps", 3),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.get_primary_follow_user_userid_legacy",
        _record("get_primary_follow_user_userid", "sales_09"),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.bind_external_contact_identity_legacy",
        _record("bind_external_contact_identity", {"ok": True}),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.upsert_external_contact_identity_legacy",
        _record("upsert_external_contact_identity", 11),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.replace_follow_users_legacy",
        _record("replace_follow_users", None),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.refresh_external_contact_identity_owner_legacy",
        _record("refresh_external_contact_identity_owner", None),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.mark_external_contact_identity_status_legacy",
        _record("mark_external_contact_identity_status", None),
    )
    monkeypatch.setattr(
        "wecom_ability_service.application.identity_contact._legacy_delegate.mark_external_contact_follow_user_status_legacy",
        _record("mark_external_contact_follow_user_status", None),
    )

    assert identity_queries.ResolvePersonIdentityQuery()(ResolvePersonIdentityQueryDTO(external_userid="wm_ext_001")) == {
        "ok": True
    }
    assert identity_queries.GetContactBindingStatusQuery()(
        GetContactBindingStatusQueryDTO(external_userid="wm_ext_001")
    ) == {"ok": True}
    assert identity_queries.ResolveExternalContactIdentityQuery()(
        ResolveExternalContactIdentityQueryDTO(corp_id="ww-test", external_userid="wm_ext_001")
    ) == {"ok": True}
    assert identity_queries.CountExternalContactIdentityMapsQuery()() == 3
    assert identity_queries.GetPrimaryFollowUserUseridQuery()(
        GetPrimaryFollowUserUseridQueryDTO(external_userid="wm_ext_001")
    ) == "sales_09"
    assert identity_commands.BindExternalContactIdentityCommand()(
        BindExternalContactIdentityCommandDTO(external_userid="wm_ext_001", mobile="13800138000")
    ) == {"ok": True}
    assert identity_commands.UpsertExternalContactIdentityCommand()(
        UpsertExternalContactIdentityCommandDTO(record={"external_userid": "wm_ext_001"})
    ) == 11
    assert identity_commands.ReplaceFollowUsersCommand()(
        ReplaceFollowUsersCommandDTO(corp_id="ww-test", external_userid="wm_ext_001")
    ) is None
    assert identity_commands.RefreshExternalContactIdentityOwnerCommand()(
        RefreshExternalContactIdentityOwnerCommandDTO(corp_id="ww-test", external_userid="wm_ext_001")
    ) is None
    assert identity_commands.MarkExternalContactIdentityStatusCommand()(
        MarkExternalContactIdentityStatusCommandDTO(
            corp_id="ww-test",
            external_userid="wm_ext_001",
            status="inactive",
        )
    ) is None
    assert identity_commands.MarkExternalContactFollowUserStatusCommand()(
        MarkExternalContactFollowUserStatusCommandDTO(
            corp_id="ww-test",
            external_userid="wm_ext_001",
            status="inactive",
        )
    ) is None
