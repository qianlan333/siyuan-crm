from __future__ import annotations

from aicrm_next.automation_engine.workspace_runtime import (
    PlanAutomationOperationTasksRunDueCommand,
    execute_workspace_runtime_command,
    reset_workspace_runtime_fixture_state,
)


def test_operation_task_run_due_is_next_plan_only() -> None:
    reset_workspace_runtime_fixture_state()

    result = execute_workspace_runtime_command(
        PlanAutomationOperationTasksRunDueCommand(
            program_id=1,
            source_route="/api/admin/automation-conversion/tasks/run-due",
        )
    )

    assert result["ok"] is True
    assert result["source_status"] == "next_automation_tasks_run_due_plan"
    assert result["route_owner"] == "ai_crm_next"
    assert result["fallback_used"] is False
    assert result["operation_tasks_executed"] is False
    assert result["real_external_call_executed"] is False
    assert result["side_effect_plan"]["status"] == "blocked"
