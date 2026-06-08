from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


WRITE_ROUTES = {
    ("/api/admin/questionnaires", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}", "PUT"),
    ("/api/admin/questionnaires/{questionnaire_id}", "PATCH"),
    ("/api/admin/questionnaires/{questionnaire_id}", "DELETE"),
    ("/api/admin/questionnaires/{questionnaire_id}/duplicate", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/publish", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/enable", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/disable", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/export/preview", "POST"),
    ("/api/admin/questionnaires/{questionnaire_id}/export", "GET"),
}


def test_questionnaire_admin_write_routes_are_next_native_without_production_legacy_fallback() -> None:
    service = get_route_registry_service()

    for route, method in WRITE_ROUTES:
        entry = service.find_route(route, {method})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_command"
        assert entry.legacy_fallback_allowed is False
        assert entry.legacy_source == ""
        assert entry.external_side_effect_risk in {"guarded", "medium"}
        assert entry.adapter_mode == "real_blocked"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"
        assert "CommandBus" in entry.notes
        assert "legacy rollback removed" in entry.notes


def test_questionnaire_admin_write_manifest_documents_next_native_lifecycle() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    write_family = by_route["/api/admin/questionnaires*"]
    assert write_family["current_runtime_owner"] == "next_command"
    assert write_family["production_behavior"] == "next_command"
    assert write_family["legacy_fallback_allowed"] is False
    assert write_family["fixture_allowed_in_production"] is False
    assert write_family["delete_ready"] is True
    assert write_family["delete_status"] == "deletion_locked"
    assert write_family["replacement_status"] == "locked"
    assert write_family["adapter_mode"] == "real_blocked"
    assert "legacy rollback removed" in write_family["notes"]

    export_record = by_route["/api/admin/questionnaires/{questionnaire_id}/export"]
    assert export_record["current_runtime_owner"] == "next_command"
    assert export_record["production_behavior"] == "next_command"
    assert export_record["legacy_fallback_allowed"] is False
    assert export_record["delete_status"] == "deletion_locked"
    assert export_record["replacement_status"] == "locked"


def test_questionnaire_h5_group9_locked_and_oauth_wildcard_deleted() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    assert by_route["/api/h5/questionnaires/{slug}/submit"]["delete_ready"] is True
    assert by_route["/api/h5/questionnaires/{slug}/submit"]["replacement_status"] == "locked"
    assert by_route["/api/h5/questionnaires/{slug}/client-diagnostics"]["delete_ready"] is True
    assert by_route["/api/h5/questionnaires/{slug}/client-diagnostics"]["replacement_status"] == "locked"
    assert by_route["/api/h5/wechat/oauth*"]["delete_ready"] is True
    assert by_route["/api/h5/wechat/oauth*"]["delete_status"] == "legacy_deleted"
    assert by_route["/api/h5/wechat/oauth*"]["legacy_fallback_allowed"] is False
