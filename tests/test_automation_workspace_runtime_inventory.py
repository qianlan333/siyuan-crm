from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/automation_workspace_runtime_route_inventory.md"


def test_workspace_runtime_inventory_contains_required_matrix_and_boundaries():
    text = INVENTORY.read_text(encoding="utf-8")

    assert "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix" in text
    assert "/admin/automation-conversion" in text
    assert "/admin/automation-conversion/programs/{program_id}/setup" in text
    assert "/api/admin/automation-conversion/tasks/run-due" in text
    assert "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu" in text
    assert "api_admin_automation_conversion_tasks_run_due" in text
    assert "api_admin_automation_conversion_execution_item_send_via_bazhuayu" in text
    assert "PlanAutomationOperationTasksRunDueCommand" in text
    assert "PlanAutomationExecutionItemBazhuayuDispatchCommand" in text
    assert "next_automation_tasks_run_due_plan" in text
    assert "next_bazhuayu_dispatch_plan" in text
    assert "legacy_fallback_allowed=false" in text
    assert "deletion_locked" in text
    assert "adapter_mode=real_blocked" in text
    assert "no real operation task runtime" in text
    assert "No external dispatcher, WeCom, OpenClaw, or direct HTTP client is invoked" in text
    assert "member/manual/focus/SOP" in text
    assert "customer automation webhooks" in text
