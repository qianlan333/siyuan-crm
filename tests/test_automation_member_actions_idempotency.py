from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.member_actions import (
    get_member_actions_side_effect_plans,
    reset_member_actions_fixture_state,
)
from aicrm_next.main import create_app


def test_member_action_idempotency_reuses_first_command_result(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_member_actions_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    headers = {"Idempotency-Key": "automation-member-put-pool-idempotent"}
    first = client.post("/api/admin/automation-conversion/member/put-in-pool", json={"external_contact_id": "wx_ext_001"}, headers=headers)
    second = client.post("/api/admin/automation-conversion/member/put-in-pool", json={"external_contact_id": "wx_ext_001"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["command_id"] == second.json()["command_id"]
    assert first.json()["side_effect_plan"]["side_effect_plan_id"] == second.json()["side_effect_plan"]["side_effect_plan_id"]
    assert len(get_member_actions_side_effect_plans()) == 1
