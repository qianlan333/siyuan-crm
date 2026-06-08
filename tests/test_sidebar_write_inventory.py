from __future__ import annotations

from pathlib import Path


INVENTORY = Path("docs/architecture/sidebar_write_route_inventory.md")

WRITE_ROUTES = {
    "/api/sidebar/bind-mobile": "BindMobileCommand",
    "/api/sidebar/lead-pool/upsert-class-term": "UpsertLeadPoolClassTermCommand",
    "/api/sidebar/signup-tags/mark": "MarkSignupTagCommand",
    "/api/sidebar/marketing-status/set-followup-segment": "SetFollowupSegmentCommand",
    "/api/sidebar/marketing-status/mark-enrolled": "MarkEnrolledCommand",
    "/api/sidebar/marketing-status/unmark-enrolled": "UnmarkEnrolledCommand",
    "/api/sidebar/v2/profile": "UpdateSidebarProfileCommand",
    "/api/sidebar/v2/materials/send": "PlanMaterialSendCommand",
}


def test_sidebar_write_inventory_documents_exact_routes_and_commands() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    for route, command in WRITE_ROUTES.items():
        assert route in text
        assert command in text

    assert "Next CommandBus" in text
    assert "AuditLedger" in text
    assert "SideEffectPlan" in text
    assert "legacy production_compat rollback removed" in text


def test_sidebar_write_inventory_marks_jssdk_out_of_scope_and_no_real_external_calls() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    assert "/api/sidebar/jssdk-config" in text
    assert "JSSDK real signature" in text
    assert "out of scope" in text
    assert "no real WeCom sends" in text
    assert "real_external_call_executed: false" in text
