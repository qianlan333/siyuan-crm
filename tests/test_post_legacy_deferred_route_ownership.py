from __future__ import annotations

from pathlib import Path

import yaml

from aicrm_next.main import create_app
from tests.post_legacy_baseline import baseline_env, first_matching_route

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/architecture/legacy_exit_route_registry.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"

EXPECTED = {
    "/api/admin/class-user-management/export": ("next_export", ("GET", "POST", "OPTIONS"), "aicrm_next.class_user_management.api"),
    "/api/admin/cloud-orchestrator/audit": ("next_cloud_observability", ("GET", "OPTIONS"), "aicrm_next.cloud_orchestrator.api"),
    "/api/admin/cloud-orchestrator/observability": ("next_cloud_observability", ("GET", "OPTIONS"), "aicrm_next.cloud_orchestrator.api"),
    "/api/admin/wecom-customer-acquisition-links": ("next_wecom_customer_acquisition", ("GET", "POST", "OPTIONS"), "aicrm_next.automation_engine.channels_api"),
    "/api/admin/wecom-customer-acquisition-links/{link_id}": ("next_wecom_customer_acquisition", ("GET", "PATCH", "DELETE", "OPTIONS"), "aicrm_next.automation_engine.channels_api"),
    "/api/admin/wecom-customer-acquisition-links/{link_id}/{action}": ("next_wecom_customer_acquisition", ("POST", "OPTIONS"), "aicrm_next.automation_engine.channels_api"),
}


def _manifest_records() -> dict[str, dict]:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    return {record["route_pattern"]: record for record in data["routes"]}


def _registry_records() -> dict[str, dict]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return {record["path_pattern"]: record for record in data["routes"]}


def test_deferred_closeout_routes_are_registered_in_manifest_and_registry() -> None:
    manifest = _manifest_records()
    registry = _registry_records()

    for route, (behavior, methods, _module) in EXPECTED.items():
        assert route in manifest
        assert route in registry
        manifest_record = manifest[route]
        registry_record = registry[route]
        assert manifest_record["production_behavior"] == behavior
        assert set(manifest_record["methods"]) == set(methods)
        assert manifest_record["legacy_fallback_allowed"] is False
        assert manifest_record["delete_status"] in {"deletion_locked", "post_legacy_locked"}
        assert manifest_record["replacement_status"] == "locked"
        assert registry_record["legacy_fallback_allowed"] is False
        assert registry_record["delete_status"] in {"deletion_locked", "post_legacy_locked"}
        assert registry_record["replacement_status"] == "locked"


def test_deferred_closeout_routes_resolve_outside_production_compat(monkeypatch) -> None:
    baseline_env(monkeypatch)
    app = create_app()
    samples = (
        ("GET", "/api/admin/class-user-management/export", "aicrm_next.class_user_management.api"),
        ("GET", "/api/admin/cloud-orchestrator/audit", "aicrm_next.cloud_orchestrator.api"),
        ("GET", "/api/admin/cloud-orchestrator/observability", "aicrm_next.cloud_orchestrator.api"),
        ("GET", "/api/admin/wecom-customer-acquisition-links", "aicrm_next.automation_engine.channels_api"),
        ("POST", "/api/admin/wecom-customer-acquisition-links", "aicrm_next.automation_engine.channels_api"),
        ("GET", "/api/admin/wecom-customer-acquisition-links/1", "aicrm_next.automation_engine.channels_api"),
        ("PATCH", "/api/admin/wecom-customer-acquisition-links/1", "aicrm_next.automation_engine.channels_api"),
        ("DELETE", "/api/admin/wecom-customer-acquisition-links/1", "aicrm_next.automation_engine.channels_api"),
        ("POST", "/api/admin/wecom-customer-acquisition-links/1/sync", "aicrm_next.automation_engine.channels_api"),
    )

    for method, path, expected_module in samples:
        route = first_matching_route(app, method, path)
        assert route is not None
        endpoint_module = getattr(getattr(route, "endpoint", None), "__module__", "")
        assert endpoint_module != "aicrm_next.production_compat.api"
        assert endpoint_module == expected_module
