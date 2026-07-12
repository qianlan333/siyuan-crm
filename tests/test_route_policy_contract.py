from __future__ import annotations

from pathlib import Path

from fastapi.routing import APIRoute

from aicrm_next.main import create_app
from aicrm_next.shared.route_ownership import FASTAPI_BUILTIN_ROUTE_PATHS, collect_route_inventory, load_route_manifest
from aicrm_next.shared.route_policy import RoutePolicyIndex


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "architecture" / "route_ownership_manifest.yml"


def _entry(path: str, method: str) -> dict:
    for item in load_route_manifest(MANIFEST):
        if item["path"] == path and method in item["methods"]:
            return item
    raise AssertionError(f"missing route policy for {method} {path}")


def _assert_policy(path: str, method: str, expected: dict) -> None:
    actual = _entry(path, method)
    assert expected.items() <= actual.items()


def test_route_policy_inventory_covers_every_runtime_business_route() -> None:
    app = create_app()
    index = RoutePolicyIndex.from_manifest(MANIFEST)
    inventory = collect_route_inventory(app)

    assert len(index) == len(inventory) == 709
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in FASTAPI_BUILTIN_ROUTE_PATHS:
            continue
        assert index.get(path=route.path, methods=route.methods, route_name=route.name) is not None


def test_route_policy_inventory_uses_all_required_audiences() -> None:
    entries = load_route_manifest(MANIFEST)

    assert {entry["audience"] for entry in entries} == {
        "admin",
        "sidebar",
        "public_h5",
        "callback",
        "internal_worker",
        "external_integration",
    }


def test_known_unsafe_routes_have_explicit_deny_by_default_policies() -> None:
    _assert_policy("/mcp", "POST", {
        "audience": "external_integration",
        "auth_scheme": "internal_bearer",
        "capability": "external_write",
        "access_scope": "service",
        "pii_level": "sensitive",
        "csrf": False,
    })
    assert _entry("/api/identity/resolve", "GET")["auth_scheme"] == "internal_bearer"
    _assert_policy("/api/sidebar/bind-mobile", "POST", {
        "auth_scheme": "sidebar_signed_context",
        "capability": "sidebar_write",
        "access_scope": "owner",
    })
    _assert_policy("/api/automation/group-ops/plans", "POST", {
        "audience": "admin",
        "auth_scheme": "admin_session",
        "capability": "manage_group_ops",
        "csrf": True,
    })
    _assert_policy("/api/h5/questionnaires/{slug}/result/{submission_id}", "GET", {
        "auth_scheme": "path_token",
        "access_scope": "single_resource",
        "pii_level": "sensitive",
    })


def test_admin_session_writes_always_require_csrf() -> None:
    entries = load_route_manifest(MANIFEST)
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}

    violations = [
        f"{','.join(entry['methods'])} {entry['path']}"
        for entry in entries
        if entry["auth_scheme"] == "admin_session"
        and unsafe_methods.intersection(entry["methods"])
        and entry["csrf"] is not True
    ]

    assert violations == []
