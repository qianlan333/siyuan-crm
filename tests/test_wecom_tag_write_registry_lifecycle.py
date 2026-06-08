from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


WRITE_ROUTES = {
    ("/api/admin/wecom/tags", "POST"),
    ("/api/admin/wecom/tags/{tag_id}", "PATCH"),
    ("/api/admin/wecom/tags/{tag_id}", "DELETE"),
    ("/api/admin/wecom/tag-groups", "POST"),
    ("/api/admin/wecom/tag-groups/{group_id}", "PATCH"),
    ("/api/admin/wecom/tag-groups/{group_id}", "DELETE"),
}

SYNC_ROUTES = {
    ("/api/admin/wecom/tags/sync", "POST"),
    ("/api/admin/wecom/tags/sync-due", "POST"),
}

ROLLBACK_FAMILIES = {
    "/api/admin/wecom/tags*",
    "/api/admin/wecom/tag-groups*",
}


def test_wecom_tag_write_registry_entries_are_deletion_locked_next_command() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route, method in WRITE_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None
        assert entry.capability_owner == "aicrm_next.customer_tags"
        assert entry.runtime_owner == "next_command"
        assert entry.legacy_fallback_allowed is False
        assert entry.legacy_source == ""
        assert entry.external_side_effect_risk == "high"
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"


def test_wecom_tag_auxiliary_families_are_next_owned_out_of_scope() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route in ROLLBACK_FAMILIES:
        entry = service.find_route(route, {"POST"})
        assert entry is not None
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.delete_status == "active"
        assert entry.replacement_status == "not_started"


def test_wecom_tag_sync_registry_entries_are_next_native_catalog_sync() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route, method in SYNC_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None
        assert entry.capability_owner == "aicrm_next.customer_tags"
        assert entry.runtime_owner == "next_native_sync"
        assert entry.legacy_fallback_allowed is False
        assert entry.legacy_source == ""
        assert entry.external_side_effect_risk == "medium"
        assert entry.adapter_mode == "live_catalog_sync"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"


def test_wecom_tag_write_yaml_registry_and_manifest_lifecycle() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    registry_by_route = {(record["path_pattern"], tuple(record["methods"])): record for record in registry["routes"]}
    manifest_by_route = {(record["route_pattern"], tuple(record["methods"])): record for record in manifest["routes"]}

    exact_routes = [
        ("/api/admin/wecom/tags", ("POST", "OPTIONS")),
        ("/api/admin/wecom/tags/{tag_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
        ("/api/admin/wecom/tag-groups", ("POST", "OPTIONS")),
        ("/api/admin/wecom/tag-groups/{group_id}", ("PUT", "PATCH", "DELETE", "OPTIONS")),
    ]
    sync_routes = [
        ("/api/admin/wecom/tags/sync", ("POST", "OPTIONS")),
        ("/api/admin/wecom/tags/sync-due", ("POST", "OPTIONS")),
    ]

    for route in exact_routes:
        registry_record = registry_by_route[route]
        manifest_record = manifest_by_route[route]
        assert registry_record["runtime_owner"] == "next_command"
        assert registry_record["legacy_fallback_allowed"] is False
        assert registry_record["legacy_source"] == ""
        assert registry_record["delete_status"] == "deletion_locked"
        assert registry_record["replacement_status"] == "locked"
        assert manifest_record["current_runtime_owner"] == "next"
        assert manifest_record["production_behavior"] == "next_command"
        assert manifest_record["legacy_fallback_allowed"] is False
        assert manifest_record["delete_ready"] is True
        assert manifest_record["delete_status"] == "deletion_locked"
        assert manifest_record["replacement_status"] == "locked"

    for route in sync_routes:
        registry_record = registry_by_route[route]
        manifest_record = manifest_by_route[route]
        assert registry_record["runtime_owner"] == "next_native_sync"
        assert registry_record["legacy_fallback_allowed"] is False
        assert registry_record["legacy_source"] == ""
        assert registry_record["external_side_effect_risk"] == "medium"
        assert registry_record["adapter_mode"] == "live_catalog_sync"
        assert registry_record["delete_status"] == "deletion_locked"
        assert registry_record["replacement_status"] == "locked"
        assert manifest_record["current_runtime_owner"] == "next_native_sync"
        assert manifest_record["production_behavior"] == "next_live_catalog_sync"
        assert manifest_record["legacy_fallback_allowed"] is False
        assert manifest_record["external_side_effect_risk"] == "medium"
        assert manifest_record["adapter_mode"] == "live_catalog_sync"
        assert manifest_record["delete_ready"] is True
        assert manifest_record["delete_status"] == "deletion_locked"
        assert manifest_record["replacement_status"] == "locked"
