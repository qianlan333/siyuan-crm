from __future__ import annotations

from pathlib import Path

from starlette.routing import Match

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _first_match(app, *, method: str, path: str):
    scope = {"type": "http", "method": method, "path": path, "root_path": "", "headers": []}
    for route in app.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route
    raise AssertionError(f"no route matched {method} {path}")


def test_payment_final_routes_precede_empty_production_compat_when_facade_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://route:route@127.0.0.1:1/aicrm_route")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "payment-wildcard-final-route-precedence")
    app = create_app()

    for method, path in [
        ("GET", "/api/admin/wechat-pay/products"),
        ("GET", "/api/admin/wechat-pay/orders"),
        ("GET", "/api/admin/wechat-pay/transactions"),
        ("GET", "/api/admin/wechat-pay/unknown-child"),
        ("OPTIONS", "/api/admin/wechat-pay/products"),
        ("GET", "/api/admin/alipay/transactions"),
        ("GET", "/api/admin/alipay/unknown-child"),
        ("OPTIONS", "/api/admin/alipay/transactions"),
        ("GET", "/api/h5/wechat-pay/unknown-child"),
        ("GET", "/api/h5/alipay/unknown-child"),
        ("OPTIONS", "/api/h5/wechat-pay/unknown-child"),
    ]:
        route = _first_match(app, method=method, path=path)
        assert route.endpoint.__module__ == "aicrm_next.commerce.api"


def test_production_compat_source_has_no_payment_wildcards_or_facade() -> None:
    assert not (ROOT / "aicrm_next/production_compat/api.py").exists()
