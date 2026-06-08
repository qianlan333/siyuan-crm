from __future__ import annotations

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


WRITE_ROUTES = {
    "/api/sidebar/bind-mobile": {"POST"},
    "/api/sidebar/lead-pool/upsert-class-term": {"POST"},
    "/api/sidebar/signup-tags/mark": {"POST"},
    "/api/sidebar/marketing-status/set-followup-segment": {"POST"},
    "/api/sidebar/marketing-status/mark-enrolled": {"POST"},
    "/api/sidebar/marketing-status/unmark-enrolled": {"POST"},
    "/api/sidebar/v2/profile": {"PUT"},
    "/api/sidebar/v2/materials/send": {"POST"},
}

HIGH_RISK_ROUTES = {
    "/api/sidebar/signup-tags/mark",
    "/api/sidebar/v2/profile",
    "/api/sidebar/v2/materials/send",
}

READONLY_LOCKED_ROUTES = [
    "/api/sidebar/customer-context",
    "/api/sidebar/profile",
    "/api/sidebar/tags",
    "/api/sidebar/binding-status",
    "/api/sidebar/contact-binding-status",
    "/api/sidebar/lead-pool/status",
    "/api/sidebar/signup-tags/status",
    "/api/sidebar/marketing-status",
]


def test_sidebar_write_routes_are_locked_next_commandbus_without_legacy_rollback() -> None:
    service = get_route_registry_service()

    for route, methods in WRITE_ROUTES.items():
        entry = service.find_route(route, methods)
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.sidebar_write"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.legacy_source == ""
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"
        assert entry.adapter_mode == "real_blocked"
        assert entry.external_side_effect_risk == ("high" if route in HIGH_RISK_ROUTES else "medium")
        assert "Next CommandBus" in entry.notes
        assert "rollback" in entry.notes
        assert "removed" in entry.notes
        assert "real_external_call_executed=false" in entry.notes


def test_sidebar_readonly_routes_stay_locked_and_jssdk_moves_to_group15_adapter() -> None:
    service = get_route_registry_service()

    for route in READONLY_LOCKED_ROUTES:
        entry = service.find_route(route, {"GET"})
        assert entry is not None, route
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"

    jssdk = service.find_route("/api/sidebar/jssdk-config", {"GET"})
    assert jssdk is not None
    assert jssdk.runtime_owner == "next_adapter"
    assert jssdk.legacy_fallback_allowed is False
    assert jssdk.delete_status == "deletion_locked"
    assert jssdk.replacement_status == "locked"
    assert jssdk.adapter_mode == "real_blocked"
    assert "JSSDK" in jssdk.notes or "jssdk" in jssdk.notes
