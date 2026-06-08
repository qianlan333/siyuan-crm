from __future__ import annotations

from pathlib import Path

from starlette.routing import Match

from aicrm_next.main import create_app


def _first_match(app, *, method: str, path: str):
    scope = {"type": "http", "method": method, "path": path, "root_path": "", "headers": []}
    for route in app.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route
    raise AssertionError(f"no route matched {method} {path}")


def test_checkout_orders_routes_precede_production_compat_when_facade_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://route:route@127.0.0.1:1/aicrm_route")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "checkout-orders-route-precedence")
    app = create_app()

    for method, path in [
        ("POST", "/api/checkout/wechat"),
        ("POST", "/api/checkout/alipay"),
        ("OPTIONS", "/api/checkout/wechat"),
        ("OPTIONS", "/api/checkout/alipay"),
        ("GET", "/api/checkout/unknown-child"),
        ("GET", "/api/orders/order_masked_001"),
        ("GET", "/api/orders/order_masked_001/status"),
        ("OPTIONS", "/api/orders/order_masked_001"),
        ("OPTIONS", "/api/orders/order_masked_001/status"),
        ("GET", "/api/orders/smoke/legacy-child"),
    ]:
        route = _first_match(app, method=method, path=path)
        assert route.endpoint.__module__ == "aicrm_next.commerce.api"

    for path in ["/api/admin/wechat-pay/smoke", "/api/h5/wechat-pay/smoke"]:
        route = _first_match(app, method="GET", path=path)
        assert route.endpoint.__module__ == "aicrm_next.commerce.api"


def test_production_compat_source_has_no_checkout_order_wildcards() -> None:
    assert not (Path(__file__).resolve().parents[1] / "aicrm_next/production_compat/api.py").exists()
