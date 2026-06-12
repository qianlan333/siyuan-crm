from __future__ import annotations

from aicrm_next.main import create_app


REQUIRED_ROUTES = {
    "/api/external/orders",
    "/api/external/orders/{order_no}",
    "/api/external/users/resolve",
}


def test_pr2_external_orders_routes_are_next_native_commerce_owned() -> None:
    app = create_app()
    by_path: dict[str, list[str]] = {}
    for route in app.routes:
        path = str(getattr(route, "path", "") or "")
        endpoint = getattr(route, "endpoint", None)
        module = str(getattr(endpoint, "__module__", "") or "")
        if path in REQUIRED_ROUTES:
            by_path.setdefault(path, []).append(module)

    assert set(by_path) == REQUIRED_ROUTES
    for path, modules in by_path.items():
        assert "aicrm_next.commerce.external_orders" in modules, (path, modules)
        assert all("frontend_compat" not in module for module in modules), (path, modules)
        assert all("post_legacy_deferred" not in module for module in modules), (path, modules)
