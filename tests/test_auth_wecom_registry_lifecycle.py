from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


EXACT_NEXT_ROUTES = {
    "/auth/wecom/start": "deletion_locked",
    "/auth/wecom/callback": "deletion_locked",
    "/auth/wecom/unknown": "deletion_locked",
    "/api/h5/wechat/oauth/unknown": "deletion_locked",
}


def test_auth_wecom_exact_routes_are_next_deletion_locked_without_rollback() -> None:
    service = get_route_registry_service()

    for route, delete_status in EXACT_NEXT_ROUTES.items():
        entry = service.find_route(route, {"GET"})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.legacy_source == ""
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == delete_status
        assert entry.replacement_status == "locked"
        assert "fallback_used=false" in entry.notes
        assert "real_external_call_executed=false" in entry.notes
        assert "wildcard rollback removed" in entry.notes


def test_auth_wecom_manifest_records_exact_routes_and_deleted_wildcards() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route, delete_status in EXACT_NEXT_ROUTES.items():
        record = by_route[route]
        assert record["current_runtime_owner"] == "next"
        assert record["production_behavior"] == "next_exact"
        assert record["legacy_fallback_allowed"] is False
        assert record["adapter_mode"] == "real_blocked"
        assert record["delete_status"] == delete_status
        assert record["replacement_status"] == "locked"
        assert "fallback_used=false" in record["notes"]
        assert "real_external_call_executed=false" in record["notes"]
        assert "wildcard rollback removed" in record["notes"]

    assert by_route["/api/h5/wechat/oauth/start"]["delete_status"] == "deletion_locked"
    assert by_route["/api/h5/wechat/oauth/start"]["legacy_fallback_allowed"] is False
    assert by_route["/api/h5/wechat/oauth/callback"]["delete_status"] == "deletion_locked"
    assert by_route["/api/h5/wechat/oauth/callback"]["legacy_fallback_allowed"] is False

    assert by_route["/api/h5/wechat/oauth*"]["current_runtime_owner"] == "next"
    assert by_route["/api/h5/wechat/oauth*"]["production_behavior"] != "legacy_forward"
    assert by_route["/api/h5/wechat/oauth*"]["delete_status"] == "legacy_deleted"
    assert by_route["/api/h5/wechat/oauth*"]["legacy_fallback_allowed"] is False
    assert by_route["/api/h5/wechat/oauth*"]["replacement_status"] == "deleted"
    assert by_route["/auth/wecom*"]["current_runtime_owner"] == "next"
    assert by_route["/auth/wecom*"]["production_behavior"] != "legacy_forward"
    assert by_route["/auth/wecom*"]["delete_status"] == "legacy_deleted"
    assert by_route["/auth/wecom*"]["legacy_fallback_allowed"] is False
    assert by_route["/auth/wecom*"]["replacement_status"] == "deleted"
