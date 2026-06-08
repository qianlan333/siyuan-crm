from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/automation_member_actions_route_inventory.md"


def test_member_actions_inventory_contains_required_matrix_and_boundaries():
    text = INVENTORY.read_text(encoding="utf-8")

    assert "Frontend ↔ API ↔ Backend Contract Matrix" in text
    assert "/admin/automation-conversion" in text
    assert "/admin/automation-conversion/programs/{program_id}/setup" in text
    assert "customer_profile_automation.js" in text
    assert "customer_detail.html" in text
    for route in (
        "/api/admin/automation-conversion/member",
        "/api/admin/automation-conversion/member/put-in-pool",
        "/api/admin/automation-conversion/member/remove-from-pool",
        "/api/admin/automation-conversion/member/set-focus",
        "/api/admin/automation-conversion/member/set-normal",
        "/api/admin/automation-conversion/member/mark-won",
        "/api/admin/automation-conversion/member/unmark-won",
        "/api/admin/automation-conversion/member/push-openclaw",
    ):
        assert route in text
    for marker in (
        "GetAutomationMemberDetailQuery",
        "PutAutomationMemberInPoolCommand",
        "RemoveAutomationMemberFromPoolCommand",
        "SetAutomationMemberFocusCommand",
        "SetAutomationMemberNormalCommand",
        "MarkAutomationMemberWonCommand",
        "UnmarkAutomationMemberWonCommand",
        "PlanAutomationMemberOpenClawPushCommand",
        "legacy_fallback_allowed=false",
        "deletion_locked",
        "adapter_mode=real_blocked",
        "real_external_call_executed=false",
        "automation_runtime_executed=false",
        "openclaw_push_executed=false",
        "stage manual-send",
        "focus-send-batches",
        "SOP",
        "customer automation webhook",
    ):
        assert marker in text
