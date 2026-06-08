from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


H5_COMMAND_ROUTES = {
    ("/api/h5/questionnaires/{slug}/submit", "POST"),
    ("/api/h5/questionnaires/{slug}/client-diagnostics", "POST"),
}


def test_questionnaire_h5_submit_routes_are_next_command_deletion_locked() -> None:
    service = get_route_registry_service()

    for route, method in H5_COMMAND_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_command"
        assert entry.legacy_fallback_allowed is False
        assert entry.legacy_source == "none"
        assert entry.external_side_effect_risk == "medium"
        expected_adapter_mode = "real_enabled" if route == "/api/h5/questionnaires/{slug}/submit" else "real_blocked"
        assert entry.adapter_mode == expected_adapter_mode
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"
        assert "CommandBus" in entry.notes
        assert "legacy rollback removed" in entry.notes
        if route == "/api/h5/questionnaires/{slug}/submit":
            assert "configured questionnaire external push executes" in entry.notes
        else:
            assert "real_external_call_executed=false" in entry.notes


def test_questionnaire_h5_submit_manifest_is_next_command_deletion_locked() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route in ["/api/h5/questionnaires/{slug}/submit", "/api/h5/questionnaires/{slug}/client-diagnostics"]:
        record = by_route[route]
        assert record["current_runtime_owner"] == "next_command"
        assert record["production_behavior"] == "next_command"
        assert record["legacy_fallback_allowed"] is False
        assert record["fixture_allowed_in_production"] is False
        assert record["delete_ready"] is True
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"
        expected_adapter_mode = "real_enabled" if route == "/api/h5/questionnaires/{slug}/submit" else "real_blocked"
        assert record["adapter_mode"] == expected_adapter_mode
        assert "legacy rollback removed" in record["notes"]
        if route == "/api/h5/questionnaires/{slug}/submit":
            assert "configured questionnaire external push executes" in record["notes"]
        else:
            assert "real_external_call_executed=false" in record["notes"]


def test_questionnaire_oauth_and_admin_read_write_lifecycle_boundaries_remain_intact() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    by_path = {record["path_pattern"]: record for record in registry["routes"]}

    assert by_path["/api/h5/wechat/oauth/start"]["delete_status"] == "deletion_locked"
    assert by_path["/api/h5/wechat/oauth/start"]["replacement_status"] == "locked"
    assert by_path["/api/h5/wechat/oauth/start"]["legacy_fallback_allowed"] is False
    assert by_path["/api/h5/wechat/oauth/callback"]["delete_status"] == "deletion_locked"
    assert by_path["/api/h5/wechat/oauth/callback"]["legacy_fallback_allowed"] is False
    assert by_path["/api/h5/wechat/oauth*"]["delete_status"] == "legacy_deleted"
    assert by_path["/api/h5/wechat/oauth*"]["replacement_status"] == "deleted"
    assert by_path["/api/h5/wechat/oauth*"]["legacy_fallback_allowed"] is False

    for route in ["/api/admin/questionnaires", "/api/admin/questionnaires*"]:
        assert by_path[route]["delete_status"] == "deletion_locked"
        assert by_path[route]["replacement_status"] == "locked"
