from __future__ import annotations

from pathlib import Path

from aicrm_next.main import create_app as create_next_app
from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report
from wecom_ability_service import create_app as create_legacy_app


ROOT = Path(__file__).resolve().parents[1]
HTTP_INIT = ROOT / "wecom_ability_service/http/__init__.py"

CLOUD_HTTP_MODULES = [
    "cloud_orchestrator_endpoint",
    "cloud_orchestrator_campaigns",
    "cloud_orchestrator_campaign_details",
    "cloud_orchestrator_media",
    "cloud_orchestrator_pages",
    "cloud_orchestrator_plans",
    "cloud_orchestrator_segments",
]

REPRESENTATIVE_NEXT_ROUTES = {
    "/admin/cloud-orchestrator/campaigns": "aicrm_next.cloud_orchestrator.api",
    "/api/admin/cloud-orchestrator/campaigns": "aicrm_next.cloud_orchestrator.api",
    "/api/admin/cloud-orchestrator/campaigns/run-due/preview": "aicrm_next.cloud_orchestrator.api",
    "/api/admin/cloud-orchestrator/media/upload": "aicrm_next.cloud_orchestrator.api",
    "/api/admin/cloud-orchestrator/observability": "aicrm_next.post_legacy_deferred.api",
}


def test_cloud_orchestrator_legacy_handler_files_are_removed() -> None:
    for module in CLOUD_HTTP_MODULES:
        assert not (ROOT / "wecom_ability_service/http" / f"{module}.py").exists()


def test_cloud_orchestrator_legacy_handlers_are_not_registered_in_flask_http_registry() -> None:
    http_init = HTTP_INIT.read_text(encoding="utf-8")

    assert "register_cloud_orchestrator_routes" not in http_init
    for module in CLOUD_HTTP_MODULES:
        assert module not in http_init

    legacy_app = create_legacy_app({"TESTING": True})
    route_modules = {
        rule.rule: getattr(legacy_app.view_functions[rule.endpoint], "__module__", "")
        for rule in legacy_app.url_map.iter_rules()
    }
    retired_modules = {f"wecom_ability_service.http.{module}" for module in CLOUD_HTTP_MODULES}
    assert not retired_modules.intersection(route_modules.values())
    assert not any(route.startswith("/admin/cloud-orchestrator") for route in route_modules)
    assert not any(route.startswith("/api/admin/cloud-orchestrator") for route in route_modules)


def test_representative_cloud_orchestrator_routes_remain_next_owned() -> None:
    next_routes = {}
    for route in create_next_app().routes:
        route_path = getattr(route, "path", "")
        if route_path:
            next_routes.setdefault(route_path, getattr(getattr(route, "endpoint", None), "__module__", ""))

    for route_path, module_name in REPRESENTATIVE_NEXT_ROUTES.items():
        assert next_routes[route_path] == module_name


def test_cloud_orchestrator_prune_keeps_route_resolution_counters_zero() -> None:
    report = build_route_check_report(strict=True)

    assert report["production_compat_route_count"] == 0
    assert report["production_compat_catch_all_count"] == 0
    assert report["wildcard_legacy_forward_count"] == 0
    assert report["undocumented_routes_count"] == 0
    assert report["unknown_owner_routes_count"] == 0
    assert report["deleted_but_still_registered_count"] == 0
    assert report["legacy_fallback_routes_count"] == 0
