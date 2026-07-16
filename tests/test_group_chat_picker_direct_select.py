from __future__ import annotations

from pathlib import Path

import pytest

from aicrm_next.automation_engine.group_ops.picker_application import ListGroupChatPickerQuery, SyncGroupChatPickerCommand
from aicrm_next.automation_engine.group_ops.dto import GroupChatPickerSyncRequest
from aicrm_next.automation_engine.group_ops.material_resolver import GroupOpsMaterialResolveError, InMemoryGroupOpsMaterialResolver
from aicrm_next.automation_engine.group_ops.repo import InMemoryGroupOpsRepository
from aicrm_next.media_library.application import EnsureGroupInviteBindingCommand, UpdateGroupInviteBindingCommand
from aicrm_next.media_library.dto import GroupInviteBindingEnsureRequest, GroupInviteBindingUpdateRequest
from aicrm_next.media_library.repo import InMemoryMediaLibraryRepository, reset_media_library_fixture_state
from aicrm_next.send_content.application import assert_group_invite_bindings_ready, normalize_send_content_package
from aicrm_next.send_content.repo import InMemorySendContentRepository
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]
FORMAL_CHAT_ID = "wrbNXyCwAAm0Vx7_OVQ_-PkT6Exeg8pg"
EXPERIENCE_CHAT_ID = "wrbNXyCwAAnxf9Xlmdxcipk24E-dzAgw"


def _group(chat_id: str, name: str, member_count: int) -> dict:
    return {
        "chat_id": chat_id,
        "group_name": name,
        "owner_userid": "HuangYouCan",
        "owner_name": "HuangYouCan",
        "internal_member_count": 1,
        "external_member_count": member_count - 1,
        "status": "active",
    }


class PagedGroupAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_group_chats(self, *, owner_userid: str, limit: int = 100, cursor: str = "") -> dict:
        self.calls.append(cursor)
        if not cursor:
            return {
                "ok": True,
                "mode": "production",
                "groups": [_group(FORMAL_CHAT_ID, "老黄的AI+进化同行圈", 115)],
                "next_cursor": "page-2",
                "warnings": [],
            }
        return {
            "ok": True,
            "mode": "production",
            "groups": [_group(EXPERIENCE_CHAT_ID, "老黄的AI+进化同行圈体验版", 172)],
            "next_cursor": "",
            "warnings": [],
        }


def test_picker_syncs_all_cursor_pages_and_preserves_plus_in_search(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_MEDIA_LIBRARY_REPO_BACKEND", "memory")
    reset_media_library_fixture_state()
    repo = InMemoryGroupOpsRepository(seed_groups=False)
    adapter = PagedGroupAdapter()

    result = SyncGroupChatPickerCommand(repo=repo, sync_adapter=adapter)(
        GroupChatPickerSyncRequest(owner_userid="HuangYouCan", limit=100)
    )

    assert result["ok"] is True
    assert adapter.calls == ["", "page-2"]
    by_name = {item["group_name"]: item for item in result["items"]}
    assert by_name["老黄的AI+进化同行圈"]["member_count"] == 115
    assert "老黄的AI+进化同行圈体验版" in by_name
    exact = ListGroupChatPickerQuery(repo)(owner_userid="HuangYouCan", keyword="老黄的AI+进化同行圈")
    assert [item["group_name"] for item in exact["items"]] == ["老黄的AI+进化同行圈", "老黄的AI+进化同行圈体验版"]
    partial = ListGroupChatPickerQuery(repo)(owner_userid="HuangYouCan", keyword="同行圈")
    assert len(partial["items"]) == 2


def test_pending_binding_keeps_stable_id_and_becomes_ready_without_reselection() -> None:
    repo = InMemoryMediaLibraryRepository()
    ensured = EnsureGroupInviteBindingCommand(repo)(
        GroupInviteBindingEnsureRequest(
            chat_id=FORMAL_CHAT_ID,
            group_name="老黄的AI+进化同行圈",
            owner_userid="HuangYouCan",
            owner_name="HuangYouCan",
            member_count=115,
        )
    )
    ensured_again = EnsureGroupInviteBindingCommand(repo)(
        GroupInviteBindingEnsureRequest(chat_id=FORMAL_CHAT_ID, group_name="老黄的AI+进化同行圈")
    )
    binding_id = int(ensured["binding_id"])

    assert binding_id == int(ensured_again["binding_id"])
    assert ensured["item"]["binding_status"] == "pending"
    assert ensured["item"]["join_url"] == ""
    package = normalize_send_content_package(
        {"content_text": "欢迎进群", "group_invite_library_ids": [binding_id]},
        require_body=True,
    )
    assert package["group_invite_library_ids"] == [binding_id]

    pending_item = repo.get_item("group_invite", str(binding_id)) or {}
    pending_send_repo = InMemorySendContentRepository(
        {
            "image": [],
            "miniprogram": [],
            "attachment": [],
            "group_invite": [
                {
                    "type": "group_invite",
                    "library_id": binding_id,
                    "title": pending_item["title"],
                    "subtitle": "邀请卡片准备中",
                    "thumbnail_url": "",
                    "enabled": True,
                    "metadata": {"join_url": "", "binding_status": "pending"},
                }
            ],
        }
    )
    with pytest.raises(ContractError, match="group_invite_not_ready"):
        assert_group_invite_bindings_ready(package, repo=pending_send_repo)
    resolver = InMemoryGroupOpsMaterialResolver(items={"group_invite": {binding_id: pending_item}})
    with pytest.raises(GroupOpsMaterialResolveError, match="group_invite_not_ready"):
        resolver.resolve_content_package_materials(package)

    updated = UpdateGroupInviteBindingCommand(repo)(
        str(binding_id),
        GroupInviteBindingUpdateRequest(join_url="https://work.weixin.qq.com/gm/ready-formal-group"),
    )
    assert updated["binding_id"] == binding_id
    assert updated["item"]["binding_status"] == "ready"
    ready_send_repo = InMemorySendContentRepository(
        {
            "image": [],
            "miniprogram": [],
            "attachment": [],
            "group_invite": [
                {
                    "type": "group_invite",
                    "library_id": binding_id,
                    "title": updated["item"]["title"],
                    "subtitle": "点击卡片直接加入群聊",
                    "thumbnail_url": "",
                    "enabled": True,
                    "metadata": {"join_url": updated["item"]["join_url"], "binding_status": "ready"},
                }
            ],
        }
    )
    assert_group_invite_bindings_ready(package, repo=ready_send_repo)
    ready_resolver = InMemoryGroupOpsMaterialResolver(items={"group_invite": {binding_id: updated["item"]}})
    attachments, media_ids = ready_resolver.resolve_content_package_materials(package)
    assert media_ids == []
    assert attachments == [
        {
            "msgtype": "link",
            "link": {
                "title": "加入「老黄的AI+进化同行圈」",
                "url": "https://work.weixin.qq.com/gm/ready-formal-group",
                "desc": "点击卡片直接加入群聊",
            },
        }
    ]


def test_group_dissolution_hides_group_and_invalidates_existing_binding(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_MEDIA_LIBRARY_REPO_BACKEND", "memory")
    reset_media_library_fixture_state()
    group_repo = InMemoryGroupOpsRepository(seed_groups=False)
    first = PagedGroupAdapter()
    SyncGroupChatPickerCommand(repo=group_repo, sync_adapter=first)(
        GroupChatPickerSyncRequest(owner_userid="HuangYouCan")
    )

    from aicrm_next.media_library.repo import build_media_library_repository

    media_repo = build_media_library_repository()
    binding = EnsureGroupInviteBindingCommand(media_repo)(
        GroupInviteBindingEnsureRequest(chat_id=FORMAL_CHAT_ID, group_name="老黄的AI+进化同行圈")
    )["item"]
    UpdateGroupInviteBindingCommand(media_repo)(
        str(binding["id"]),
        GroupInviteBindingUpdateRequest(join_url="https://work.weixin.qq.com/gm/formal-before-dissolution"),
    )

    class ExperienceOnlyAdapter:
        def list_group_chats(self, *, owner_userid: str, limit: int = 100, cursor: str = "") -> dict:
            return {"ok": True, "mode": "production", "groups": [_group(EXPERIENCE_CHAT_ID, "老黄的AI+进化同行圈体验版", 172)], "next_cursor": "", "warnings": []}

    after = SyncGroupChatPickerCommand(repo=group_repo, sync_adapter=ExperienceOnlyAdapter())(
        GroupChatPickerSyncRequest(owner_userid="HuangYouCan")
    )
    assert after["sync"]["inactive_count"] == 1
    assert [item["chat_id"] for item in after["items"]] == [EXPERIENCE_CHAT_ID]
    invalid = media_repo.get_item("group_invite", str(binding["id"])) or {}
    assert invalid["binding_status"] == "invalid"


def test_shared_picker_is_a_pure_searchable_list_and_all_surfaces_load_it() -> None:
    picker = (ROOT / "aicrm_next/frontend_compat/static/admin_console/group_chat_picker.js").read_text(encoding="utf-8")
    material_picker = (ROOT / "aicrm_next/frontend_compat/static/admin_console/material_picker.js").read_text(encoding="utf-8")
    templates = [
        ROOT / "aicrm_next/automation_engine/templates/admin_console/channel_code_form.html",
        ROOT / "aicrm_next/frontend_compat/templates/admin_console/cloud_campaigns_workspace.html",
        ROOT / "aicrm_next/frontend_compat/templates/admin_console/hxc_dashboard.html",
        ROOT / "aicrm_next/automation_agents/templates/admin_console/automation_agent_edit.html",
        ROOT / "aicrm_next/automation_engine/group_ops/templates/admin_console/group_ops.html",
    ]

    assert "AICRMGroupChatPicker" in material_picker
    assert "window.AdminApi.requestJson" in picker
    assert "aicrm-group-chat-picker__list" in picker
    assert "aicrm-group-chat-picker__row" in picker
    assert "member_count" in picker
    assert "thumbnail" not in picker.lower()
    assert "客户群</span>" not in picker
    assert "管理群邀请设置" not in picker
    for template in templates:
        source = template.read_text(encoding="utf-8")
        assert "group_chat_picker.js" in source
        assert source.index("group_chat_picker.js") < source.index("material_picker.js")
