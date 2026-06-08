from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.platform_foundation.route_registry.checker import RuntimeRouteChecker, build_route_check_report
from aicrm_next.platform_foundation.route_registry.manifest_loader import load_route_registry
from aicrm_next.platform_foundation.route_registry.models import RouteRegistry, RouteRegistryEntry
from aicrm_next.platform_foundation.route_registry.service import RouteRegistryService


def test_route_registry_loader_merges_ownership_and_legacy_exit_manifest() -> None:
    registry = load_route_registry()
    patterns = {route.path_pattern for route in registry.routes}

    assert "/health" in patterns
    assert "/api/admin/system/routes" in patterns
    assert any(item.sample for item in registry.lifecycle_items)
    service = RouteRegistryService(registry)
    lifecycle = service.lifecycle_for_route("/api/h5/questionnaires/{slug}/submit")[0]
    assert lifecycle.sample is True
    assert lifecycle.production_decision == "excluded"
    assert "not used for deletion decision" in lifecycle.notes


def test_registered_route_passes_strict_when_registered() -> None:
    app = FastAPI()
    app.add_api_route("/api/registered", lambda: {"ok": True}, methods=["GET"])
    registry = RouteRegistry(
        routes=(
            RouteRegistryEntry(
                route_id="registered",
                path_pattern="/api/registered",
                methods=("GET",),
                capability_owner="tests",
                runtime_owner="next_native",
            ),
        )
    )

    report = build_route_check_report(app=app, service=RouteRegistryService(registry), strict=True)

    assert report["ok"] is True
    assert report["undocumented_routes"] == []


def test_undocumented_route_fails_strict_mode() -> None:
    app = FastAPI()
    app.add_api_route("/api/unregistered", lambda: {"ok": True}, methods=["GET"])

    report = build_route_check_report(app=app, service=RouteRegistryService(RouteRegistry()), strict=True)

    assert report["ok"] is False
    assert report["undocumented_routes"][0]["path"] == "/api/unregistered"


def test_new_production_compat_fallback_fails_strict_when_not_registered() -> None:
    app = FastAPI()

    async def fallback():
        return {"ok": True}

    fallback.__module__ = "aicrm_next.production_compat.api"
    app.add_api_route("/api/new-legacy/{path:path}", fallback, methods=["GET"])

    report = build_route_check_report(app=app, service=RouteRegistryService(RouteRegistry()), strict=True)

    assert report["ok"] is False
    assert report["undocumented_routes"][0]["path"] == "/api/new-legacy/{path:path}"
    assert report["wildcard_routes"][0]["path"] == "/api/new-legacy/{path:path}"


def test_wildcard_fallback_fails_strict_even_when_registered() -> None:
    app = FastAPI()

    async def fallback():
        return {"ok": True}

    fallback.__module__ = "aicrm_next.production_compat.api"
    app.add_api_route("/api/known/{path:path}", fallback, methods=["GET"])
    registry = RouteRegistry(
        routes=(
            RouteRegistryEntry(
                route_id="known_wildcard",
                path_pattern="/api/known*",
                methods=("GET",),
                capability_owner="tests",
                runtime_owner="production_compat",
                legacy_fallback_allowed=True,
            ),
        )
    )

    report = build_route_check_report(app=app, service=RouteRegistryService(registry), strict=True)

    assert report["ok"] is False
    assert report["wildcard_routes"][0]["path"] == "/api/known/{path:path}"
    assert report["legacy_fallback_routes"][0]["path"] == "/api/known/{path:path}"
    assert "legacy_fallback_route_registered:/api/known/{path:path}" in report["blockers"]


def test_path_wildcard_runtime_route_does_not_match_single_segment_placeholder() -> None:
    app = FastAPI()

    async def fallback():
        return {"ok": True}

    fallback.__module__ = "aicrm_next.production_compat.api"
    app.add_api_route("/api/messages/{path:path}", fallback, methods=["GET"])
    registry = RouteRegistry(
        routes=(
            RouteRegistryEntry(
                route_id="message_exact",
                path_pattern="/api/messages/{external_userid}",
                methods=("GET",),
                capability_owner="tests",
                runtime_owner="next_native",
                legacy_fallback_allowed=False,
            ),
            RouteRegistryEntry(
                route_id="message_wildcard",
                path_pattern="/api/messages*",
                methods=("GET",),
                capability_owner="tests",
                runtime_owner="production_compat",
                legacy_fallback_allowed=True,
            ),
        )
    )

    report = build_route_check_report(app=app, service=RouteRegistryService(registry), strict=True)

    assert report["ok"] is False
    assert report["legacy_fallback_routes"][0]["registry"]["route_id"] == "message_wildcard"
    assert "legacy_fallback_route_registered:/api/messages/{path:path}" in report["blockers"]


def test_deleted_route_still_registered_fails_strict_mode() -> None:
    app = FastAPI()
    app.add_api_route("/api/deleted", lambda: {"ok": True}, methods=["GET"])
    registry = RouteRegistry(
        routes=(
            RouteRegistryEntry(
                route_id="deleted",
                path_pattern="/api/deleted",
                methods=("GET",),
                capability_owner="tests",
                runtime_owner="next_native",
                delete_status="legacy_deleted",
            ),
        )
    )

    report = build_route_check_report(app=app, service=RouteRegistryService(registry), strict=True)

    assert report["ok"] is False
    assert report["deleted_but_still_registered_routes"][0]["path"] == "/api/deleted"


def test_admin_system_routes_api_reads_registry_service() -> None:
    client = TestClient(create_app())

    response = client.get("/api/admin/system/routes?runtime_owner=next_native")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["routes"]
    assert all(route["runtime_owner"] == "next_native" for route in payload["routes"])
    assert "registered_routes_count" in payload["checker"]


def test_runtime_route_checker_object_interface_matches_report() -> None:
    app = FastAPI()
    app.add_api_route("/api/registered", lambda: {"ok": True}, methods=["GET"])
    registry = RouteRegistry(
        routes=(
            RouteRegistryEntry(
                route_id="registered",
                path_pattern="/api/registered",
                methods=("GET",),
                capability_owner="tests",
                runtime_owner="next_native",
            ),
        )
    )

    result = RuntimeRouteChecker(RouteRegistryService(registry), app=app).check(strict=True)

    assert result.ok is True
    assert result.registered_routes_count == 1
    assert result.undocumented_routes == []
