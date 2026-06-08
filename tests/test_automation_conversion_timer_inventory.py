from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/automation_conversion_timer_route_inventory.md"


def test_timer_inventory_contains_required_matrix_and_routes():
    text = INVENTORY.read_text(encoding="utf-8")

    assert "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix" in text
    for route in (
        "/api/admin/automation-conversion/reply-monitor/capture",
        "/api/admin/automation-conversion/reply-monitor/run-due",
        "/api/admin/automation-conversion/jobs/run-due/preview",
        "/api/admin/automation-conversion/jobs/run-due",
    ):
        assert route in text
    for status in (
        "next_reply_monitor_capture_plan",
        "next_reply_monitor_run_due_plan",
        "next_jobs_run_due_preview",
        "next_jobs_run_due_plan",
    ):
        assert status in text
    assert "legacy_fallback_allowed=false" in text
    assert "deletion_locked" in text
    assert "adapter_mode=real_blocked" in text
    assert "real_external_call_executed=false" in text
    assert "automation_runtime_executed=false" in text
    assert "wecom_send_executed=false" in text
    assert "/api/admin/automation-conversion/tasks/run-due" in text
    assert "send-via-bazhuayu" in text
