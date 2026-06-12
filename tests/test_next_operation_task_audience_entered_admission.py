from __future__ import annotations

from aicrm_next.automation_engine.workspace_runtime import (
    PlanAutomationExecutionItemOutboundDispatchCommand,
    execute_workspace_runtime_command,
    reset_workspace_runtime_fixture_state,
)


def test_audience_entered_operation_task_outbound_dispatch_is_blocked_plan() -> None:
    reset_workspace_runtime_fixture_state()

    result = execute_workspace_runtime_command(
        PlanAutomationExecutionItemOutboundDispatchCommand(
            execution_item_id=42,
            source_route="/api/admin/automation-conversion/execution-items/42/send-via-bazhuayu",
        )
    )

    assert result["ok"] is True
    assert result["source_status"] == "next_bazhuayu_dispatch_plan"
    assert result["route_owner"] == "ai_crm_next"
    assert result["fallback_used"] is False
    assert result["execution_item_id"] == 42
    assert result["bazhuayu_send_executed"] is False
    assert result["real_external_call_executed"] is False
