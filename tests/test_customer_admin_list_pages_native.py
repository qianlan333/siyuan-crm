from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _endpoint_module(path: str) -> str:
    app = create_app()
    for route in app.routes:
        if getattr(route, "path", "") == path and "GET" in getattr(route, "methods", set()):
            return route.endpoint.__module__
    raise AssertionError(f"missing route for {path}")


def test_customer_list_admin_page_renders_from_native_shell() -> None:
    client = TestClient(create_app())

    response = client.get("/admin/customers")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "客户激活 / 客户列表" in response.text
    assert "客户查找" in response.text
    assert "客户列表" in response.text
    assert 'name="keyword"' in response.text
    assert _endpoint_module("/admin/customers") == "aicrm_next.customer_read_model.admin_pages"


def test_customer_pages_and_user_ops_removed_from_frontend_compat_inventory() -> None:
    from aicrm_next.frontend_compat.legacy_routes import LEGACY_FRONTEND_ROUTES

    assert "/admin/customers" not in LEGACY_FRONTEND_ROUTES
    assert _endpoint_module("/admin/customers") == "aicrm_next.customer_read_model.admin_pages"
    assert _endpoint_module("/admin/customers/{external_userid}") == "aicrm_next.customer_read_model.admin_pages"


def test_customer_list_page_degrades_when_read_model_unavailable(monkeypatch) -> None:
    from aicrm_next.customer_read_model import admin_pages

    class FakeListCustomersQuery:
        def __call__(self, request):
            return {
                "ok": False,
                "source_status": "production_unavailable",
                "customers": [{"external_userid": "wx_ext_should_not_render"}],
                "total": 1,
            }

    monkeypatch.setattr(admin_pages, "ListCustomersQuery", FakeListCustomersQuery)
    client = TestClient(create_app())

    response = client.get("/admin/customers")

    assert response.status_code == 200
    assert admin_pages.ADMIN_CUSTOMERS_UNAVAILABLE_MESSAGE in response.text
    assert "wx_ext_should_not_render" not in response.text
