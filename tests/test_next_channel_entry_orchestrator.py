from __future__ import annotations

from aicrm_next.channel_entry.application import process_channel_entry
from aicrm_next.channel_entry.schemas import ProcessChannelEntryCommand
from aicrm_next.channel_entry.wecom_adapter import get_wecom_adapter, set_wecom_adapter


def _patch_repo(monkeypatch, *, channel_status="active", bindings=None):
    channel = {"id": 10, "channel_code": "c", "channel_name": "C", "scene_value": "scene-a", "status": channel_status, "owner_staff_id": "sales", "welcome_message": "hello", "entry_tag_id": "tag-a"}
    calls: list[str] = []
    monkeypatch.setattr("aicrm_next.channel_entry.application.resolve_channel_for_scene", lambda **kwargs: (channel, {"match_type": "current_scene", "matched_scene": "scene-a", "channel_id": 10}))
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_contact", lambda **kwargs: calls.append("contact") or {"ok": True})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.get_channel_entry_effect_log", lambda *args: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_channel_entry_effect_log", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.save_tag_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr("aicrm_next.channel_entry.repo.list_active_bindings_for_channel", lambda channel_id: list(bindings or []))
    def fake_runtime_event(**kwargs):
        calls.append("member")
        return {
            "processed": [
                {
                    "membership": {"program_id": 30, "current_stage": "operating"},
                    "legacy_projection": {"id": 99, "audience_entry_id": 299},
                    "stage_entry": {"entry_reason": "audience_entry_rule_passed"},
                    "counts": {"planned": 1, "enqueued": 1},
                }
            ],
            "reason": "processed",
        }

    monkeypatch.setattr("aicrm_next.automation_runtime_v2.bridge.process_channel_entry_event", fake_runtime_event)
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application._admit_program_binding",
        lambda **kwargs: calls.append("member")
        or {
            "admission_status": "accepted",
            "accepted": True,
            "reason": "audience_entry_rule_passed",
            "program_member": {"id": 99},
            "legacy_member": {"id": 199},
            "audience_entry_id": 299,
            "audience_code": "operating",
            "entry_reason": "audience_entry_rule_passed",
            "realtime_task_hook": {"ok": True},
            "realtime_operation_tasks_ran": 1,
            "realtime_operation_tasks_enqueued_count": 1,
        },
    )
    monkeypatch.setattr("aicrm_next.channel_entry.repo.upsert_program_member", lambda **kwargs: calls.append("legacy_member") or {"id": 99})
    monkeypatch.setattr("aicrm_next.channel_entry.repo.insert_program_admission_attempt", lambda **kwargs: {"id": 88, "admission_status": kwargs["admission_status"]})

    class Adapter:
        def send_welcome_msg(self, payload):
            calls.append("welcome")
            return {"errcode": 0}

        def mark_external_contact_tags(self, **payload):
            calls.append("tag")
            return {"errcode": 0}

    previous = get_wecom_adapter()
    set_wecom_adapter(Adapter())
    return calls, previous


def test_active_channel_baseline_before_program_admission(monkeypatch):
    calls, previous = _patch_repo(monkeypatch, bindings=[{"id": 20, "program_id": 30, "program_status": "active"}])
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm-a", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["handled"] is True
    assert result["mode"] == "program_admission"
    assert calls[:3] == ["contact", "welcome", "tag"]
    assert "member" in calls


def test_archived_program_keeps_baseline_and_rejects_admission(monkeypatch):
    calls, previous = _patch_repo(monkeypatch, bindings=[{"id": 20, "program_id": 30, "program_status": "archived"}])
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm-a", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["mode"] == "channel_baseline_only"
    assert result["reason"] == "program_archived"
    assert result["program_member_written"] is False
    assert result["admission_results"][0]["reason"] == "program_archived"
    assert calls[:3] == ["contact", "welcome", "tag"]
    assert "member" not in calls


def test_channel_disabled_has_no_baseline_side_effects(monkeypatch):
    calls, previous = _patch_repo(monkeypatch, channel_status="inactive")
    try:
        result = process_channel_entry(ProcessChannelEntryCommand(external_contact_id="wm-a", payload_json={"State": "scene-a", "WelcomeCode": "wc"}, send_welcome_message=True))
    finally:
        set_wecom_adapter(previous)

    assert result["handled"] is False
    assert result["mode"] == "channel_disabled"
    assert calls == []
