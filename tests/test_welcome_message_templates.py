from __future__ import annotations

from wecom_ability_service.domains.automation_conversion import member_state_service


def test_channel_welcome_message_renders_customer_name_from_profile(monkeypatch):
    captured: dict[str, object] = {}

    class _StubClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            captured["payload"] = payload
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(
        member_state_service.service_seams,
        "_build_live_context",
        lambda external_contact_id, phone: {"profile": {"customer_name": "思媛老师"}},
    )
    monkeypatch.setattr(
        member_state_service.service_seams,
        "get_contact_runtime_client",
        lambda: _StubClient(),
    )

    result = member_state_service._send_channel_welcome_message_for_contact(
        channel={"welcome_message": "哈喽，{{ 客户名 }}请填写问卷"},
        payload_json={"WelcomeCode": "welcome-name-001"},
        external_contact_id="wm_customer_001",
    )

    assert result["sent"] is True
    assert captured["payload"] == {
        "welcome_code": "welcome-name-001",
        "text": {"content": "哈喽，思媛老师请填写问卷"},
    }


def test_channel_welcome_message_uses_empty_value_when_customer_name_missing(monkeypatch):
    captured: dict[str, object] = {}

    class _StubClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            captured["payload"] = payload
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(
        member_state_service.service_seams,
        "_build_live_context",
        lambda external_contact_id, phone: {"profile": {"customer_name": ""}},
    )
    monkeypatch.setattr(
        member_state_service.service_seams,
        "get_contact_runtime_client",
        lambda: _StubClient(),
    )

    result = member_state_service._send_channel_welcome_message_for_contact(
        channel={"welcome_message": "哈喽，{{客户名}}"},
        payload_json={"welcome_code": "welcome-name-002"},
        external_contact_id="wm_customer_002",
    )

    assert result["sent"] is True
    assert captured["payload"] == {
        "welcome_code": "welcome-name-002",
        "text": {"content": "哈喽，"},
    }
