from __future__ import annotations

from aicrm_next.channel_entry.application import process_channel_entry
from aicrm_next.channel_entry.schemas import ProcessChannelEntryCommand
from aicrm_next.channel_entry.wecom_adapter import set_wecom_adapter


def test_channel_entry_logs_real_call_disabled_without_fake_success(monkeypatch):
    channel = {
        "id": 10,
        "channel_code": "c",
        "channel_name": "C",
        "scene_value": "scene-a",
        "status": "active",
        "owner_staff_id": "owner-a",
        "welcome_message": "欢迎加入",
        "entry_tag_id": "tag-a",
        "entry_tag_name": "报名引流品",
    }
    effects: list[dict] = []
    contacts: list[dict] = []

    monkeypatch.delenv("AICRM_NEXT_WECOM_REAL_CALLS_ENABLED", raising=False)
    monkeypatch.setenv("WECOM_CORP_ID", "ww-test")
    monkeypatch.setenv("WECOM_CONTACT_SECRET", "secret")
    set_wecom_adapter(None)
    monkeypatch.setattr("aicrm_next.channel_entry.application.resolve_channel_for_scene", lambda **kwargs: (channel, {"match_type": "current_scene", "matched_scene": "scene-a", "channel_id": 10}))
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_contact", lambda **kwargs: contacts.append(kwargs) or {"id": 1, **kwargs})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.get_channel_entry_effect_log", lambda *args: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_entry_effect_log", lambda **kwargs: effects.append(kwargs) or kwargs)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.list_active_bindings_for_channel", lambda channel_id: [])
    monkeypatch.setattr("aicrm_next.channel_entry.repo.save_tag_snapshot", lambda *args, **kwargs: None)

    result = process_channel_entry(
        ProcessChannelEntryCommand(
            external_contact_id="wm-real-disabled",
            payload_json={"State": "scene-a", "WelcomeCode": "welcome-code", "corp_id": "ww-test"},
            follow_user_userid="owner-a",
            send_welcome_message=True,
            event_log_id=9001,
        )
    )

    assert result["handled"] is True
    assert result["baseline_effects"]["channel_contact"]["external_contact_id"] == "wm-real-disabled"
    assert result["welcome_message"]["sent"] is False
    assert result["welcome_message"]["reason"] == "wecom_real_calls_disabled"
    assert result["entry_tag"]["applied"] is False
    assert result["entry_tag"]["reason"] == "wecom_real_calls_disabled"
    assert result["mode"] == "standalone_channel"
    assert contacts
    assert any(row["effect_type"] == "welcome_message" and row["status"] == "failed" and row["reason"] == "wecom_real_calls_disabled" for row in effects)
    assert any(row["effect_type"] == "entry_tag" and row["status"] == "failed" and row["reason"] == "wecom_real_calls_disabled" for row in effects)
