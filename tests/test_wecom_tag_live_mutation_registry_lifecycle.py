from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


LIVE_ROUTES = {
    ("/api/admin/wecom/tags/live/gate", "GET"): "next_native",
    ("/api/admin/wecom/tags/live/mark", "POST"): "next_command",
    ("/api/admin/wecom/tags/live/unmark", "POST"): "next_command",
}


def test_wecom_tag_live_mutation_registry_entries_are_deletion_locked_real_blocked() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for (route, method), owner in LIVE_ROUTES.items():
        entry = service.find_route(route, {method})
        assert entry is not None
        assert entry.capability_owner == "aicrm_next.customer_tags"
        assert entry.runtime_owner == owner
        assert entry.legacy_fallback_allowed is False
        assert entry.external_side_effect_risk == "high"
        assert entry.adapter_mode == "real_blocked"
        assert entry.replacement_status == "locked"
        assert entry.delete_status == "deletion_locked"


def test_wecom_tag_live_mutation_manifest_matches_deletion_locked_lifecycle() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    registry_by_route = {(record["path_pattern"], tuple(record["methods"])): record for record in registry["routes"]}
    manifest_by_route = {(record["route_pattern"], tuple(record["methods"])): record for record in manifest["routes"]}

    expected = [
        ("/api/admin/wecom/tags/live/gate", ("GET",), "next_native", "next_exact"),
        ("/api/admin/wecom/tags/live/mark", ("POST", "OPTIONS"), "next_command", "next_command"),
        ("/api/admin/wecom/tags/live/unmark", ("POST", "OPTIONS"), "next_command", "next_command"),
    ]
    for route, methods, registry_owner, behavior in expected:
        registry_record = registry_by_route[(route, methods)]
        manifest_record = manifest_by_route[(route, methods)]
        assert registry_record["runtime_owner"] == registry_owner
        assert registry_record["legacy_fallback_allowed"] is False
        assert registry_record["delete_status"] == "deletion_locked"
        assert registry_record["replacement_status"] == "locked"
        assert registry_record["adapter_mode"] == "real_blocked"
        assert manifest_record["current_runtime_owner"] == "next"
        assert manifest_record["production_behavior"] == behavior
        assert manifest_record["legacy_fallback_allowed"] is False
        assert manifest_record["delete_ready"] is True
        assert manifest_record["delete_status"] == "deletion_locked"
        assert manifest_record["replacement_status"] == "locked"


def test_wecom_tag_crud_and_sync_remain_deletion_locked() -> None:
    get_route_registry_service.cache_clear()
    service = get_route_registry_service()

    for route, method in [
        ("/api/admin/wecom/tags", "POST"),
        ("/api/admin/wecom/tags/{tag_id}", "PATCH"),
        ("/api/admin/wecom/tag-groups", "POST"),
        ("/api/admin/wecom/tag-groups/{group_id}", "PATCH"),
    ]:
        entry = service.find_route(route, {method})
        assert entry is not None
        assert entry.runtime_owner == "next_command"
        assert entry.legacy_fallback_allowed is False
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"

    sync_entry = service.find_route("/api/admin/wecom/tags/sync", {"POST"})
    assert sync_entry is not None
    assert sync_entry.runtime_owner == "next_native_sync"
    assert sync_entry.adapter_mode == "live_catalog_sync"
    assert sync_entry.legacy_fallback_allowed is False
    assert sync_entry.delete_status == "deletion_locked"
    assert sync_entry.replacement_status == "locked"
