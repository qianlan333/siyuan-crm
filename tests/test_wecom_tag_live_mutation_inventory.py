from __future__ import annotations

from pathlib import Path


def test_live_mutation_inventory_covers_callers_and_plan_matrix() -> None:
    inventory = Path("docs/archive/route_inventory/wecom_tag_live_mutation_route_inventory.md").read_text(encoding="utf-8")

    for marker in [
        "Caller ↔ API ↔ CommandBus ↔ SideEffectPlan Matrix",
        "/api/admin/wecom/tags/live/gate",
        "/api/admin/wecom/tags/live/mark",
        "/api/admin/wecom/tags/live/unmark",
        "/api/sidebar/signup-tags/mark",
        "/api/h5/questionnaires/{slug}/submit",
        "/api/admin/customers/profile/tags",
        "PlanWeComTagMarkCommand",
        "PlanWeComTagUnmarkCommand",
        "PlanCustomerTagAssignmentCommand",
        "wecom.tag.mark",
        "wecom.tag.unmark",
        "wecom.tag.assignment.apply",
        "questionnaire.tag.apply",
        "queued_external_effect",
        "real_mark_tag",
        "ProductionWeComAdapter.mark_external_contact_tags()",
        "synchronous WeCom mark_tag",
        "requires_approval=false",
        "real_external_call_executed=false",
        "wecom_api_called=false",
    ]:
        assert marker in inventory
