from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_customer_detail_frontend_wires_member_action_urls_to_next_exact_routes():
    template = (ROOT / "aicrm_next/frontend_compat/templates/admin_console/customer_detail.html").read_text(encoding="utf-8")
    routes = (ROOT / "aicrm_next/frontend_compat/legacy_routes.py").read_text(encoding="utf-8")
    script = (ROOT / "aicrm_next/frontend_compat/static/admin_console/customer_profile_automation.js").read_text(encoding="utf-8")

    assert "data-automation-member-url" in template
    assert "data-automation-put-in-pool-url" in template
    assert "data-automation-push-openclaw-url" in template
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
        assert route in routes
    for action in ("put_in_pool", "remove_from_pool", "set_focus", "set_normal", "mark_won", "unmark_won", "push_openclaw"):
        assert f"data-automation-action=\"{action}\"" in template
        assert action in script


def test_inventory_documents_out_of_scope_surfaces():
    text = (ROOT / "docs/architecture/automation_member_actions_route_inventory.md").read_text(encoding="utf-8")

    assert "stage manual-send" in text
    assert "focus-send-batches" in text
    assert "SOP" in text
    assert "customer automation webhook" in text
    assert "Out of scope; not marked locked by this group" in text
