from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


READ_ROUTES = {
    "/api/admin/wecom/tags",
    "/api/admin/wecom/tags/{tag_id}",
    "/api/admin/wecom/tag-groups",
    "/api/admin/wecom/tag-groups/{group_id}",
}

WRITE_FAMILIES = {
    "/api/admin/wecom/tags*",
    "/api/admin/wecom/tag-groups*",
}


def test_wecom_tag_read_registry_entries_are_deletion_locked_next_native() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route in READ_ROUTES:
        entry = service.find_route(route, {"GET"})
        assert entry is not None
        assert entry.capability_owner == "aicrm_next.customer_tags"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.external_side_effect_risk == "none"
        assert entry.adapter_mode == "none"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"


def test_wecom_tag_auxiliary_families_remain_out_of_scope_after_write_closeout() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route in WRITE_FAMILIES:
        entry = service.find_route(route, {"POST"})
        assert entry is not None
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.delete_status == "active"
        assert entry.replacement_status == "not_started"
        assert entry.adapter_mode == "real_blocked"


def test_wecom_tag_live_gate_is_group14_locked_boundary() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()
    entry = service.find_route("/api/admin/wecom/tags/live/gate", {"GET"})

    assert entry is not None
    assert entry.runtime_owner == "next_native"
    assert entry.legacy_fallback_allowed is False
    assert entry.adapter_mode == "real_blocked"
    assert entry.delete_status == "deletion_locked"
    assert entry.replacement_status == "locked"


def test_wecom_tag_read_route_registry_yaml_matches_lifecycle() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    by_route = {(record["path_pattern"], tuple(record["methods"])): record for record in registry["routes"]}

    for route in READ_ROUTES:
        record = by_route[(route, ("GET",))]
        assert record["runtime_owner"] == "next_native"
        assert record["legacy_fallback_allowed"] is False
        assert record["legacy_source"] == ""
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    for route in WRITE_FAMILIES:
        record = by_route[(route, ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"))]
        assert record["runtime_owner"] == "next_native"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "active"
        assert record["replacement_status"] == "not_started"


def test_wecom_tag_read_production_manifest_locks_read_routes_only() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {(record["route_pattern"], tuple(record["methods"])): record for record in manifest["routes"]}

    for route in READ_ROUTES:
        record = by_route[(route, ("GET",))]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_exact"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    for route in WRITE_FAMILIES:
        record = by_route[(route, ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"))]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "guarded_preview"
        assert record["legacy_fallback_allowed"] is False
        assert record["delete_status"] == "active"
        assert record["replacement_status"] == "not_started"
