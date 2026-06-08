from __future__ import annotations

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


def test_messages_routes_have_exact_registry_entries_and_wildcard_is_deleted() -> None:
    service = get_route_registry_service()

    recent = service.find_route("/api/messages/wx_ext_001/recent", {"GET"})
    assert recent is not None
    assert recent.capability_owner == "aicrm_next.customer_read_model"
    assert recent.legacy_fallback_allowed is False

    list_route = service.find_route("/api/messages/wx_ext_001", {"GET"})
    search_route = service.find_route("/api/messages/search", {"GET"})
    send_route = service.find_route("/api/messages/send", {"POST"})
    wildcard = next(route for route in service.list_routes() if route.path_pattern == "/api/messages*")

    assert list_route is not None
    assert list_route.capability_owner == "aicrm_next.message_archive"
    assert list_route.legacy_fallback_allowed is False
    assert list_route.delete_status == "next_shadow"

    assert search_route is not None
    assert search_route.capability_owner == "aicrm_next.message_archive"
    assert search_route.legacy_fallback_allowed is False

    assert send_route is not None
    assert send_route.adapter_mode == "real_blocked"
    assert send_route.legacy_fallback_allowed is False

    assert wildcard.runtime_owner == "next_native"
    assert wildcard.legacy_fallback_allowed is False
    assert wildcard.delete_status == "legacy_deleted"
    assert wildcard.replacement_status == "deleted"
    assert "Broad wildcard removed from production_compat" in wildcard.notes
    assert "no real external calls enabled" in wildcard.notes
