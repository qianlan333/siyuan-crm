from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


READONLY_ROUTES = {
    "/api/admin/user-ops/overview",
    "/api/admin/user-ops/cards",
    "/api/admin/user-ops/customers",
    "/api/admin/user-ops/customers/{external_userid}",
    "/api/admin/user-ops/customers/{external_userid}/timeline",
    "/api/admin/user-ops/filters",
    "/api/admin/user-ops/send-records",
}

PREVIEW_ROUTES = {
    "/api/admin/user-ops/broadcast/preview",
    "/api/admin/user-ops/export/preview",
}


def test_user_ops_readonly_routes_are_deletion_locked_next_native_without_handler_fallback() -> None:
    service = get_route_registry_service()

    for route in READONLY_ROUTES:
        entry = service.find_route(route, {"GET"})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.ops_enrollment"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"
        assert "readonly" in entry.notes


def test_user_ops_admin_page_is_locked_without_hxc_redirect_fallback() -> None:
    service = get_route_registry_service()
    entry = service.find_route("/admin/user-ops", {"GET"})

    assert entry is not None
    assert entry.capability_owner == "aicrm_next.ops_enrollment"
    assert entry.runtime_owner == "frontend_compat"
    assert entry.legacy_fallback_allowed is False
    assert entry.delete_status == "deletion_locked"
    assert entry.replacement_status == "locked"
    assert "must not redirect to the HXC dashboard" in entry.notes


def test_user_ops_preview_routes_are_next_command_deletion_locked() -> None:
    service = get_route_registry_service()

    for route in PREVIEW_ROUTES:
        entry = service.find_route(route, {"POST"})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.ops_enrollment"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"
        assert "CommandBus" in entry.notes
        assert "real_external_call_executed=false" in entry.notes
        assert "controlled default preview" in entry.notes


def test_user_ops_manifest_distinguishes_readonly_and_preview_routes() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    readonly = by_route["/api/admin/user-ops*"]
    assert readonly["current_runtime_owner"] == "next"
    assert readonly["production_behavior"] == "next_read_model_only"
    assert readonly["legacy_fallback_allowed"] is False
    assert readonly["delete_ready"] is False

    admin_page = by_route["/admin/user-ops"]
    assert admin_page["current_runtime_owner"] == "frontend_compat"
    assert admin_page["legacy_fallback_allowed"] is False
    assert admin_page["delete_status"] == "deletion_locked"
    assert admin_page["replacement_status"] == "locked"

    for route in READONLY_ROUTES:
        record = by_route[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_read_model_only"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    for route in PREVIEW_ROUTES:
        record = by_route[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is False
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
