from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.member_actions import (
    get_member_actions_audit_events,
    get_member_actions_external_call_attempts,
    get_member_actions_side_effect_plans,
    reset_member_actions_fixture_state,
)
from aicrm_next.main import create_app


ACTION_CASES = {
    "put-in-pool": "automation.member.put_in_pool",
    "remove-from-pool": "automation.member.remove_from_pool",
    "set-focus": "automation.member.set_focus",
    "set-normal": "automation.member.set_normal",
    "mark-won": "automation.member.mark_won",
    "unmark-won": "automation.member.unmark_won",
}


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_member_actions_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_action_contract(body: dict, effect_type: str) -> None:
    assert body["ok"] is True
    assert body["source_status"] == "next_command"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["status"] == "planned_blocked"
    assert body["adapter_mode"] == "real_blocked"
    assert body["real_external_call_executed"] is False
    assert body["automation_runtime_executed"] is False
    assert body["openclaw_push_executed"] is False
    assert body["wecom_send_executed"] is False
    assert body["processed_count"] == 0
    assert body["sent_count"] == 0
    assert body["failed_count"] == 0
    assert body["side_effect_plan"]["effect_type"] == effect_type
    assert body["side_effect_plan"]["status"] == "blocked"
    assert body["external_call_attempt"]["status"] == "blocked"
    assert body["audit_event"]["command_id"] == body["command_id"]


def test_member_actions_return_next_command_plans(monkeypatch):
    client = _client(monkeypatch)

    for action, effect_type in ACTION_CASES.items():
        response = client.post(
            f"/api/admin/automation-conversion/member/{action}",
            json={"external_contact_id": "wx_ext_001"},
            headers={"Idempotency-Key": f"member-action-{action}"},
        )
        assert response.status_code == 200
        _assert_action_contract(response.json(), effect_type)

    assert len(get_member_actions_side_effect_plans()) == len(ACTION_CASES)
    assert len(get_member_actions_external_call_attempts()) == len(ACTION_CASES)
    assert len(get_member_actions_audit_events()) == len(ACTION_CASES)


def test_push_openclaw_returns_blocked_side_effect_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/member/push-openclaw",
        json={"external_contact_id": "wx_ext_001"},
        headers={"Idempotency-Key": "member-action-openclaw"},
    )

    assert response.status_code == 200
    body = response.json()
    _assert_action_contract(body, "automation.member.push_openclaw")
    assert body["accepted"] is False
    assert body["side_effect_plan"]["adapter_name"] == "openclaw"
    assert body["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert body["side_effect_plan"]["requires_approval"] is True
    assert body["side_effect_plan"]["risk_level"] == "high"


def test_member_action_options_and_missing_identity(monkeypatch):
    client = _client(monkeypatch)

    options = client.options("/api/admin/automation-conversion/member/put-in-pool")
    assert options.status_code == 200
    options_body = options.json()
    assert options_body["allowed_methods"] == ["POST", "OPTIONS"]
    assert options_body["fallback_used"] is False
    assert options_body["openclaw_push_executed"] is False

    missing = client.post("/api/admin/automation-conversion/member/put-in-pool", json={})
    assert missing.status_code == 400
    missing_body = missing.json()
    assert missing_body["ok"] is False
    assert missing_body["source_status"] == "next_command"
    assert missing_body["fallback_used"] is False
    assert "external_contact_id or phone" in missing_body["error"]
