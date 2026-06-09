from __future__ import annotations

from aicrm_next.channel_entry.application import process_channel_entry
from aicrm_next.channel_entry.schemas import ProcessChannelEntryCommand
from aicrm_next.channel_entry.wecom_adapter import get_wecom_adapter, set_wecom_adapter


def _base(monkeypatch, channel):
    sent = []
    monkeypatch.setattr("aicrm_next.channel_entry.application.resolve_channel_for_scene", lambda **kwargs: (channel, {"match_type": "current_scene", "matched_scene": "scene-a", "channel_id": 10}))
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_contact", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.get_channel_entry_effect_log", lambda *args: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_entry_effect_log", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.save_tag_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.list_active_bindings_for_channel", lambda channel_id: [])

    class Adapter:
        def send_welcome_msg(self, payload):
            sent.append(payload)
            return {"errcode": 0}

        def mark_external_contact_tags(self, **payload):
            return {"errcode": 0}

    previous = get_wecom_adapter()
    set_wecom_adapter(Adapter())
    return sent, previous


def test_welcome_supports_text_image_file_miniprogram(monkeypatch):
    channel = {"id": 10, "scene_value": "scene-a", "status": "active", "owner_staff_id": "sales", "welcome_message": "hello", "entry_tag_id": "", "welcome_image_library_ids": [1], "welcome_attachment_library_ids": [2], "welcome_miniprogram_library_ids": [3]}
    sent, previous = _base(monkeypatch, channel)
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["welcome_message"]["sent"] is True
    assert [item["msgtype"] for item in sent[0]["attachments"]] == ["image", "file", "miniprogram"]


def test_welcome_renders_customer_name_placeholder_from_identity_name(monkeypatch):
    channel = {"id": 10, "scene_value": "scene-a", "status": "active", "owner_staff_id": "sales", "welcome_message": "你好啊，{{客户名}}测试客户名", "entry_tag_id": ""}
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.resolve_external_contact_customer_name",
        lambda external_userid, **kwargs: "刘惠福",
    )
    sent, previous = _base(monkeypatch, channel)
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["welcome_message"]["sent"] is True
    assert sent[0]["text"]["content"] == "你好啊，刘惠福测试客户名"


def test_welcome_customer_name_placeholder_is_empty_when_identity_name_missing(monkeypatch):
    channel = {"id": 10, "scene_value": "scene-a", "status": "active", "owner_staff_id": "sales", "welcome_message": "你好啊，{{ 客户名 }}", "entry_tag_id": ""}
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.repo.resolve_external_contact_customer_name",
        lambda external_userid, **kwargs: "",
    )
    sent, previous = _base(monkeypatch, channel)
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm_external_id", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["welcome_message"]["sent"] is True
    assert sent[0]["text"]["content"] == "你好啊，"


def test_welcome_attachment_limit_failed(monkeypatch):
    channel = {"id": 10, "scene_value": "scene-a", "status": "active", "owner_staff_id": "sales", "welcome_message": "hello", "entry_tag_id": "", "welcome_image_library_ids": [1, 2, 3, 4], "welcome_attachment_library_ids": [5, 6, 7], "welcome_miniprogram_library_ids": [8, 9, 10]}
    sent, previous = _base(monkeypatch, channel)
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["welcome_message"]["sent"] is False
    assert result["welcome_message"]["reason"] == "attachment_limit_exceeded"
    assert sent == []
