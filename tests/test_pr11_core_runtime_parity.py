from __future__ import annotations

import importlib
from pathlib import Path

from aicrm_next.main import app


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_MAIN_MARKERS = {
    "frontend_compat_router",
    "post_legacy_deferred_router",
    "reset_post_legacy_deferred_fixture_state",
    "production_compat_router",
    "production_compat_wildcard_router",
    "legacy_flask_facade",
    "forward_to_legacy_flask",
    "X-AICRM-Compatibility-Facade",
}

CORE_ROUTES = {
    "/health",
    "/admin",
    "/admin/channels",
    "/admin/customers",
    "/admin/config",
    "/admin/api-docs",
    "/api/admin/user-ops/overview",
    "/api/external/orders",
}

NEXT_HANDOFF_ROUTES = {
    "/admin/api-docs": "aicrm_next.admin_config.api",
    "/api/admin/cloud-orchestrator/audit": "aicrm_next.cloud_orchestrator.api",
    "/api/admin/cloud-orchestrator/observability": "aicrm_next.cloud_orchestrator.api",
    "/api/admin/wecom-customer-acquisition-links": "aicrm_next.automation_engine.channels_api",
}


def _route_modules(path: str) -> list[str]:
    return [
        getattr(getattr(route, "endpoint", None), "__module__", "")
        for route in app.routes
        if getattr(route, "path", "") == path
    ]


def test_pr11_main_removes_runtime_compat_router_mounts() -> None:
    source = (ROOT / "aicrm_next/main.py").read_text(encoding="utf-8")
    for marker in FORBIDDEN_MAIN_MARKERS:
        assert marker not in source


def test_pr11_core_routes_remain_registered() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    missing = sorted(CORE_ROUTES - paths)
    assert not missing


def test_pr11_legacy_handoff_routes_are_next_owned() -> None:
    for path, expected_module in NEXT_HANDOFF_ROUTES.items():
        modules = _route_modules(path)
        assert modules, path
        assert expected_module in modules, (path, modules)
        assert all("frontend_compat.legacy_routes" not in module for module in modules), (path, modules)
        assert all("post_legacy_deferred" not in module for module in modules), (path, modules)


def test_pr11_background_jobs_and_external_push_are_importable() -> None:
    for module in (
        "aicrm_next.background_jobs",
        "aicrm_next.background_jobs.automation_ops_scheduler",
        "aicrm_next.background_jobs.broadcast_queue_worker",
        "aicrm_next.background_jobs.external_contact_sync",
        "aicrm_next.external_push",
        "aicrm_next.external_push.service",
        "aicrm_next.external_push.security",
    ):
        importlib.import_module(module)


def test_pr11_no_real_external_call_headers_on_handoff_routes() -> None:
    for path in NEXT_HANDOFF_ROUTES:
        for route in app.routes:
            if getattr(route, "path", "") != path:
                continue
            endpoint_module = getattr(getattr(route, "endpoint", None), "__module__", "")
            assert endpoint_module.startswith("aicrm_next.")
