from __future__ import annotations

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


READONLY_ROUTES = [
    "/api/sidebar/customer-context",
    "/api/sidebar/profile",
    "/api/sidebar/tags",
    "/api/sidebar/binding-status",
    "/api/sidebar/contact-binding-status",
    "/api/sidebar/lead-pool/status",
    "/api/sidebar/signup-tags/status",
    "/api/sidebar/marketing-status",
    "/api/sidebar/v2/workbench",
    "/api/sidebar/v2/questionnaires",
    "/api/sidebar/v2/materials",
    "/api/sidebar/v2/materials/image/{image_id}/thumbnail",
    "/api/sidebar/v2/other-staff-messages",
    "/api/sidebar/v2/products",
    "/api/sidebar/v2/orders",
]

WRITE_ROUTES = [
    "/api/sidebar/bind-mobile",
    "/api/sidebar/lead-pool/upsert-class-term",
    "/api/sidebar/signup-tags/mark",
    "/api/sidebar/marketing-status/set-followup-segment",
    "/api/sidebar/marketing-status/mark-enrolled",
    "/api/sidebar/marketing-status/unmark-enrolled",
    "/api/sidebar/v2/profile",
    "/api/sidebar/v2/materials/send",
]


def test_sidebar_readonly_routes_are_locked_next_native_in_registry() -> None:
    service = get_route_registry_service()

    for route in READONLY_ROUTES:
        entry = service.find_route(route, {"GET"})
        assert entry is not None, route
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.external_side_effect_risk == "none"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"


def test_sidebar_write_routes_are_locked_by_their_own_closeout() -> None:
    service = get_route_registry_service()

    for route in WRITE_ROUTES:
        entry = service.find_route(route, {"POST", "PUT", "OPTIONS"})
        assert entry is not None, route
        assert entry.legacy_fallback_allowed is False
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"
        assert "rollback" in entry.notes
        assert "removed" in entry.notes
