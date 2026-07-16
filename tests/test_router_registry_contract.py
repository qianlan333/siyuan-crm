from __future__ import annotations

from pathlib import Path

from starlette.routing import Mount

from aicrm_next.main import create_app
from aicrm_next.router_registry import ROUTER_SPECS, router_registry_summary
from aicrm_next.shared.route_ownership import collect_route_inventory


def test_router_registry_specs_have_capability_owner_and_route_group() -> None:
    assert len(ROUTER_SPECS) == 62
    for spec in ROUTER_SPECS:
        assert spec.capability_owner
        assert spec.capability_owner != "unknown"
        assert spec.route_group
        assert spec.router.routes


def test_router_registry_summary_exposes_stable_metadata() -> None:
    summary = router_registry_summary()

    assert len(summary) == len(ROUTER_SPECS)
    assert summary[0]["capability_owner"] == "platform_foundation"
    assert summary[0]["route_group"] == "platform"
    assert summary[-1]["capability_owner"] == "platform_foundation"
    assert summary[-1]["route_group"] == "verification_files"


def test_router_registry_preserves_route_inventory_count_and_static_order() -> None:
    app = create_app()
    inventory = collect_route_inventory(app, include_static=True)
    static_mounts = [(route.path, route.name) for route in app.routes if isinstance(route, Mount)]

    assert len(inventory) == 746
    assert sum(1 for item in inventory if item.is_static) == 8
    assert static_mounts == [
        ("/static/group-ops", "group_ops_static"),
        ("/static/automation-engine", "automation_engine_static"),
        ("/static/customer-tags", "customer_tags_static"),
        ("/static/questionnaire", "questionnaire_static"),
        ("/static/navigation-target", "navigation_target_static"),
        ("/static/operation-cycles", "operation_cycles_static"),
        ("/static/service-period", "service_period_static"),
        ("/static", "static"),
    ]
    assert inventory[-1].path == "/{filename}"
    assert inventory[-1].route_name == "wechat_domain_verification_file"


def test_main_delegates_router_registration_to_registry() -> None:
    source = Path("aicrm_next/main.py").read_text(encoding="utf-8")

    assert "from .router_registry import register_routers" in source
    assert "register_routers(app)" in source
    assert "app.include_router(" not in source
