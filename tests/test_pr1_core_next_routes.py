from __future__ import annotations

from aicrm_next.main import app


def _route_modules(path: str) -> list[str]:
    return [
        route.endpoint.__module__
        for route in app.routes
        if getattr(route, "path", "") == path
    ]


def _first_route_module(path: str) -> str:
    modules = _route_modules(path)
    if not modules:
        raise AssertionError(f"missing route: {path}")
    return modules[0]


def test_pr1_main_imports_and_required_native_admin_routes_exist() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/admin/customers" in paths
    assert "/admin/customers/{external_userid}" in paths
    assert "/admin/user-ops" in paths
    assert "/admin/user-ops/ui" in paths


def test_pr1_automation_runtime_v2_and_class_user_routes_are_mounted() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/automation-runtime/v2/webhooks/{webhook_key}" in paths
    assert "/api/automation-runtime/v2/scheduled/run-due" in paths
    assert "/api/admin/class-user-management/export" in paths
    assert _first_route_module("/api/admin/class-user-management/export") == "aicrm_next.class_user_management.api"


def test_pr1_frontend_compat_does_not_preempt_native_exact_routes() -> None:
    from aicrm_next.frontend_compat.legacy_routes import LEGACY_FRONTEND_ROUTES

    assert "/admin/customers" not in LEGACY_FRONTEND_ROUTES
    assert "/admin/user-ops" not in LEGACY_FRONTEND_ROUTES
    assert "/admin/user-ops/ui" not in LEGACY_FRONTEND_ROUTES
    assert _first_route_module("/admin/customers") == "aicrm_next.customer_read_model.admin_pages"
    assert _first_route_module("/admin/customers/{external_userid}") == "aicrm_next.customer_read_model.admin_pages"
    assert _first_route_module("/admin/user-ops") == "aicrm_next.ops_enrollment.admin_pages"
    assert _first_route_module("/admin/user-ops/ui") == "aicrm_next.ops_enrollment.admin_pages"
