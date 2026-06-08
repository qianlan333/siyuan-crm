from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.platform_foundation.route_registry.checker import build_route_check_report


def test_final_runtime_has_no_production_compat_routes(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    app = create_app()

    compat_routes = [
        route
        for route in app.routes
        if getattr(getattr(route, "endpoint", None), "__module__", "") == "aicrm_next.production_compat.api"
    ]

    assert compat_routes == []


def test_final_route_registry_counters_are_zero(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    report = build_route_check_report(strict=True)

    assert report["ok"] is True
    assert report["undocumented_routes"] == []
    assert report["legacy_fallback_routes"] == []
    assert report["unknown_owner_routes"] == []
    assert report["deleted_but_still_registered_routes"] == []
    assert report["undocumented_routes_count"] == 0
    assert report["unknown_owner_count"] == 0
    assert report["deleted_but_still_registered_count"] == 0
    assert report["production_compat_route_count"] == 0
    assert report["production_compat_catch_all_count"] == 0
    assert report["legacy_fallback_routes_count"] == 0
    assert report["wildcard_legacy_forward_count"] == 0


def test_representative_next_routes_do_not_emit_compatibility_facade(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "final-cleanup-test")
    client = TestClient(create_app())

    for path in (
        "/login",
        "/admin/hxc-dashboard",
        "/p/test-product",
        "/pay/test-product",
        "/api/products/test-product",
        "/api/admin/wechat-pay/unknown-child",
        "/api/h5/wechat-pay/unknown-child",
    ):
        response = client.get(path)
        assert response.status_code < 500
        assert "X-AICRM-Compatibility-Facade" not in response.headers
