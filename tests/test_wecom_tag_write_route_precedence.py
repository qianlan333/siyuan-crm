from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def test_wecom_tag_write_routes_resolve_before_production_compat_when_facade_exists(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-write-route-precedence")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    app = create_app()
    routes = [
        {
            "path": getattr(route, "path", ""),
            "methods": sorted((getattr(route, "methods", None) or set()) - {"HEAD"}),
            "endpoint_module": getattr(getattr(route, "endpoint", None), "__module__", ""),
            "is_production_compat": getattr(getattr(route, "endpoint", None), "__module__", "") == "aicrm_next.production_compat.api",
            "_route": route,
        }
        for route in app.routes
    ]

    production_compat_wecom_routes = [
        route
        for route in routes
        if route["is_production_compat"]
        and (route["path"].startswith("/api/admin/wecom/tags") or route["path"].startswith("/api/admin/wecom/tag-groups"))
    ]
    assert production_compat_wecom_routes == []

    for method, path in [
        ("POST", "/api/admin/wecom/tags"),
        ("PATCH", "/api/admin/wecom/tags/tag_fixture_active"),
        ("DELETE", "/api/admin/wecom/tags/tag_fixture_active"),
        ("POST", "/api/admin/wecom/tags/sync"),
        ("POST", "/api/admin/wecom/tag-groups"),
        ("PATCH", "/api/admin/wecom/tag-groups/group_fixture_lifecycle"),
        ("DELETE", "/api/admin/wecom/tag-groups/group_fixture_lifecycle"),
    ]:
        first = checker.first_matching_route(routes, method=method, path=path)
        assert first is not None
        assert first["endpoint_module"] == "aicrm_next.customer_tags.api"
        assert first["is_production_compat"] is False


def test_wecom_tag_write_requests_do_not_hit_compat_facade_header(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-write-route-precedence-request")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/admin/wecom/tags",
        json={"group_id": "group_fixture_lifecycle", "tag_name": "优先级标签"},
    )

    assert response.status_code == 200
    assert response.json()["source_status"] == "next_command"
    assert response.json()["fallback_used"] is False
    assert "X-AICRM-Compatibility-Facade" not in response.headers
