from __future__ import annotations

import yaml

from aicrm_next.platform_foundation.route_registry.service import get_route_registry_service


ADMIN_PAGE_ROUTES = {
    "/admin/questionnaires": "next_native",
    "/admin/questionnaires/new": "next_native",
    "/admin/questionnaires/{questionnaire_id}": "next_native",
}

ADMIN_READ_API_ROUTES = {
    "/api/admin/questionnaires",
    "/api/admin/questionnaires/{questionnaire_id}",
    "/api/admin/questionnaires/{questionnaire_id}/questions",
    "/api/admin/questionnaires/{questionnaire_id}/results",
    "/api/admin/questionnaires/{questionnaire_id}/submissions",
}

OUT_OF_SCOPE_PATTERNS = {
    "/api/h5/wechat/oauth*",
}


def test_questionnaire_admin_read_routes_are_deletion_locked_after_rollback_removal() -> None:
    service = get_route_registry_service()

    for route, owner in ADMIN_PAGE_ROUTES.items():
        entry = service.find_route(route, {"GET"})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == owner
        assert entry.legacy_fallback_allowed is False
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"

    for route in ADMIN_READ_API_ROUTES:
        entry = service.find_route(route, {"GET"})
        assert entry is not None, route
        assert entry.capability_owner == "aicrm_next.questionnaire"
        assert entry.runtime_owner == "next_native"
        assert entry.legacy_fallback_allowed is False
        assert entry.external_side_effect_risk == "none"
        assert entry.delete_status == "deletion_locked"
        assert entry.replacement_status == "locked"


def test_questionnaire_oauth_wildcard_is_deleted_without_admin_read_regression() -> None:
    registry = yaml.safe_load(open("docs/architecture/legacy_exit_route_registry.yaml", encoding="utf-8"))
    by_path = {record["path_pattern"]: record for record in registry["routes"]}

    for route in OUT_OF_SCOPE_PATTERNS:
        record = by_path[route]
        assert record["delete_status"] == "legacy_deleted"
        assert record["replacement_status"] == "deleted"
        assert record["legacy_fallback_allowed"] is False
        assert "wildcard removed" in record["notes"]


def test_questionnaire_manifest_documents_read_primary_and_out_of_scope_families() -> None:
    manifest = yaml.safe_load(open("docs/route_ownership/production_route_ownership_manifest.yaml", encoding="utf-8"))
    by_route = {record["route_pattern"]: record for record in manifest["routes"]}

    for route in ADMIN_PAGE_ROUTES | {route: "next" for route in ADMIN_READ_API_ROUTES}:
        record = by_route[route]
        assert record["legacy_fallback_allowed"] is False
        assert record["production_behavior"] == "next_read_model_only"
        assert record["delete_status"] == "deletion_locked"
        assert record["replacement_status"] == "locked"

    assert by_route["/api/h5/questionnaires/{slug}/submit"]["delete_ready"] is True
    assert by_route["/api/h5/questionnaires/{slug}/submit"]["production_behavior"] == "next_command"
    assert by_route["/api/h5/questionnaires/{slug}/submit"]["replacement_status"] == "locked"
    assert by_route["/api/h5/questionnaires/{slug}/client-diagnostics"]["delete_ready"] is True
    assert by_route["/api/h5/questionnaires/{slug}/client-diagnostics"]["replacement_status"] == "locked"
    assert by_route["/api/h5/wechat/oauth*"]["delete_ready"] is True
    assert by_route["/api/h5/wechat/oauth*"]["delete_status"] == "legacy_deleted"
    assert by_route["/api/h5/wechat/oauth*"]["legacy_fallback_allowed"] is False
