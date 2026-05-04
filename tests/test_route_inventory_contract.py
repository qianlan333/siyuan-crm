from __future__ import annotations

from collections.abc import Iterable

from wecom_ability_service import create_app
from wecom_ability_service.http.admin_api_docs import _api_endpoint_groups

from scripts.export_flask_routes import export_routes


EXCLUDED_METHODS = {"HEAD", "OPTIONS"}


def _route_methods(app) -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(set(rule.methods) - EXCLUDED_METHODS)
    return routes


def _endpoint_docs() -> list[dict]:
    endpoints = []
    for group in _api_endpoint_groups():
        endpoints.extend(group.get("endpoints") or [])
    return endpoints


def _walk_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def test_core_routes_are_registered_in_url_map():
    app = create_app({"TESTING": True})
    routes = _route_methods(app)

    required_routes = {
        ("/health", "GET"),
        ("/login", "GET"),
        ("/logout", "GET"),
        ("/auth/wecom/start", "GET"),
        ("/auth/wecom/callback", "GET"),
        ("/api/customers", "GET"),
        ("/api/customers/<external_userid>", "GET"),
        ("/api/customers/<external_userid>/timeline", "GET"),
        ("/api/h5/questionnaires/<slug>", "GET"),
        ("/api/h5/questionnaires/<slug>/submit", "POST"),
    }
    for rule, method in required_routes:
        assert method in routes.get(rule, set()), f"{method} {rule} is not registered"

    assert "/mcp" in routes
    assert routes["/mcp"] & {"GET", "POST"}


def test_exported_route_inventory_has_no_duplicate_method_rule_endpoint_rows():
    app = create_app({"TESTING": True})
    rows = export_routes(app)

    seen = set()
    duplicates = []
    for row in rows:
        for method in row["methods"]:
            key = (method, row["rule"], row["endpoint"])
            if key in seen:
                duplicates.append(key)
            seen.add(key)

    assert not duplicates


def test_admin_api_docs_questionnaire_and_logout_paths_are_current():
    endpoints = _endpoint_docs()
    paths = {endpoint.get("path") for endpoint in endpoints}

    assert "/api/questionnaires/<slug>" not in paths
    assert "/api/questionnaires/<slug>/submit" not in paths
    assert "/api/h5/questionnaires/<slug>" in paths
    assert "/api/h5/questionnaires/<slug>/submit" in paths

    all_doc_strings = "\n".join(_walk_strings(_api_endpoint_groups()))
    assert "/api/questionnaires/intent-survey" not in all_doc_strings
    assert "/api/questionnaires/<slug>" not in all_doc_strings

    logout_docs = [endpoint for endpoint in endpoints if endpoint.get("path") == "/logout"]
    assert logout_docs
    assert {endpoint.get("method") for endpoint in logout_docs} == {"GET"}
    assert "/admin/logout" not in paths
