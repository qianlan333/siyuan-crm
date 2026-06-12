from __future__ import annotations

from aicrm_next.automation_engine.member_actions import (
    GetAutomationMemberDetailQuery,
    PutAutomationMemberInPoolCommand,
    execute_member_action_command,
    read_automation_member_detail,
    reset_member_actions_fixture_state,
)


def test_member_state_read_model_returns_next_empty_state_without_external_calls() -> None:
    detail = read_automation_member_detail(GetAutomationMemberDetailQuery(external_contact_id="wm_state_001"))

    assert detail["ok"] is True
    assert detail["route_owner"] == "ai_crm_next"
    assert detail["fallback_used"] is False
    assert detail["real_external_call_executed"] is False
    assert detail["detail"]["member"]["external_contact_id"] == "wm_state_001"


def test_member_state_mutation_is_plan_only() -> None:
    reset_member_actions_fixture_state()

    result = execute_member_action_command(
        PutAutomationMemberInPoolCommand(
            external_contact_id="wm_state_002",
            source_route="/api/admin/automation-conversion/member/put-in-pool",
        )
    )

    assert result["ok"] is True
    assert result["status"] == "planned_blocked"
    assert result["route_owner"] == "ai_crm_next"
    assert result["real_external_call_executed"] is False
    assert result["automation_runtime_executed"] is False
    assert result["side_effect_plan"]["effect_type"] == "automation.member.put_in_pool"
