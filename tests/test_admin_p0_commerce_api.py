from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from aicrm_next.admin_config.api_docs_view_model import build_api_docs_view_model
from aicrm_next.commerce.admin_exports import reset_export_jobs_for_tests
from aicrm_next.commerce.repo import reset_commerce_fixture_state
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    reset_commerce_fixture_state()
    reset_export_jobs_for_tests()
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("SECRET_KEY", "admin-p0-commerce-api")
    return TestClient(create_app(), raise_server_exceptions=False)


def _paths(view_model: dict) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for group in view_model["endpoint_groups"]:
        for endpoint in group.get("endpoints") or []:
            result[(endpoint["method"], endpoint["path"])] = group["title"]
    return result


def test_admin_p0_routes_are_in_api_docs() -> None:
    view_model = build_api_docs_view_model()
    paths = _paths(view_model)
    assert view_model["endpoint_count"] > 80
    assert view_model["markdown_data"]["full"]
    expected = {
        ("GET", "/api/admin/orders"): "交易 / 商品",
        ("GET", "/api/admin/orders/{order_no}"): "交易 / 商品",
        ("GET", "/api/admin/orders/{order_no}/items"): "交易 / 商品",
        ("GET", "/api/admin/payments"): "交易 / 商品",
        ("GET", "/api/admin/refunds"): "交易 / 商品",
        ("POST", "/api/admin/refunds"): "交易 / 商品",
        ("GET", "/api/admin/customers/{external_userid}/orders"): "客户 / 身份 / 侧边栏",
        ("GET", "/api/admin/customers/{external_userid}/commerce-summary"): "客户 / 身份 / 侧边栏",
        ("GET", "/api/admin/customers/{external_userid}/business-profile"): "客户 / 身份 / 侧边栏",
        ("GET", "/api/admin/identity/resolve"): "客户 / 身份 / 侧边栏",
        ("GET", "/api/admin/identity/links/{identity_key}"): "客户 / 身份 / 侧边栏",
        ("GET", "/api/admin/webhooks/events"): "认证 / 回调",
        ("POST", "/api/admin/webhooks/replay"): "认证 / 回调",
        ("POST", "/api/admin/exports"): "系统 / MCP",
        ("GET", "/api/admin/exports/{job_id}"): "系统 / MCP",
    }
    for endpoint, group_title in expected.items():
        assert paths[endpoint] == group_title
        assert endpoint[1] in view_model["markdown_data"]["full"]


def test_unified_orders_list_detail_and_items(monkeypatch) -> None:
    client = _client(monkeypatch)
    wechat = client.get("/api/admin/orders?provider=wechat").json()
    alipay = client.get("/api/admin/orders?provider=alipay").json()
    merged = client.get("/api/admin/orders?provider=all").json()
    assert wechat["ok"] is True
    assert alipay["ok"] is True
    assert merged["ok"] is True
    assert merged["providers"] == ["wechat", "alipay", "wechat_shop"]
    assert {"id", "provider", "customer", "order_no", "amount_total", "can_refund"}.issubset(merged["items"][0])

    missing = client.get("/api/admin/orders/not_found_order")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "not_found"

    items = client.get("/api/admin/orders/order_masked_001/items?provider=wechat").json()
    assert items["ok"] is True
    assert items["total"] == 1
    assert items["items"][0]["quantity"] == 1
    assert items["items"][0]["order_no"] == "order_masked_001"


def test_payments_and_refunds(monkeypatch) -> None:
    client = _client(monkeypatch)
    payments = client.get("/api/admin/payments").json()
    assert payments["ok"] is True
    assert "payments" in payments
    assert {"provider", "order_no", "transaction_id", "payment_status", "customer"}.issubset(payments["payments"][0])

    refunds = client.get("/api/admin/refunds").json()
    assert refunds["ok"] is True
    assert refunds["refunds"] == []

    alipay_refund = client.post("/api/admin/refunds", json={"provider": "alipay", "order_no": "order_fake_0003"})
    assert alipay_refund.status_code == 400
    assert alipay_refund.json()["error_code"] == "provider_refund_not_supported"

    wechat_refund = client.post(
        "/api/admin/refunds",
        json={
            "provider": "wechat",
            "order_no": "order_masked_001",
            "refund_amount_total": 100,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "transaction_masked_001",
            "checked": True,
            "operator": "tester",
        },
    )
    assert wechat_refund.status_code == 200
    payload = wechat_refund.json()
    assert payload["ok"] is True
    assert payload["refund"]["status"] == "requested"
    assert payload["source_status"] == "next_admin_refund_request"


def test_product_share_uses_real_qr_svg(monkeypatch) -> None:
    client = _client(monkeypatch)
    products = client.get("/api/admin/wechat-pay/products").json()
    product = products["items"][0]

    payload = client.get(f"/api/admin/wechat-pay/products/{product['id']}/share").json()

    share = payload["share"]
    assert share["url"].endswith(f"/p/{product['product_code']}")
    assert share["qr_data_url"].startswith("data:image/svg+xml;base64,")
    svg = base64.b64decode(share["qr_data_url"].split(",", 1)[1]).decode("utf-8")
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert "<path" in svg
    assert "PRODUCT" not in svg
    assert product["product_code"] not in svg


def test_customer_business_profile_orders_and_summary(monkeypatch) -> None:
    client = _client(monkeypatch)
    profile = client.get("/api/admin/customers/wx_ext_001/business-profile").json()
    assert profile["ok"] is True
    assert set(profile["business_profile"]) == {"tags", "recent_messages", "questionnaire_answers"}
    assert profile["counts"]["recent_messages"] <= 20
    assert isinstance(profile["business_profile"]["tags"], list)
    assert profile["business_profile"]["questionnaire_answers"][0]["question"]
    assert profile["business_profile"]["questionnaire_answers"][0]["answer"]
    for forbidden in ("orders", "commerce_summary", "tasks", "coupons", "entitlements"):
        assert forbidden not in profile["business_profile"]

    orders = client.get("/api/admin/customers/wx_ext_001/orders").json()
    assert orders["ok"] is True
    assert "orders" in orders

    summary = client.get("/api/admin/customers/wx_ext_001/commerce-summary").json()
    assert summary["ok"] is True
    assert "summary" in summary
    assert {"order_count", "paid_order_count", "total_paid_amount", "providers"}.issubset(summary["summary"])


def test_identity_admin_resolve_and_links(monkeypatch) -> None:
    client = _client(monkeypatch)
    resolved = client.get("/api/admin/identity/resolve?external_userid=wx_ext_001&transaction_id=tx_ignored").json()
    assert resolved["ok"] is True
    assert resolved["identity"]["person_id"] == "person_001"
    assert resolved["warnings"]

    links = client.get("/api/admin/identity/links/13800138000").json()
    assert links["ok"] is True
    assert links["links"]["mobile"] == "13800138000"

    missing = client.get("/api/admin/identity/links/not_found_identity")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "not_found"


def test_webhooks_and_exports(monkeypatch) -> None:
    client = _client(monkeypatch)
    events = client.get("/api/admin/webhooks/events").json()
    assert events["ok"] is True
    assert "events" in events

    replay = client.post("/api/admin/webhooks/replay", json={"source": "wechat-pay", "event_id": "evt_fixture", "operator": "tester"}).json()
    assert replay["ok"] is True
    assert replay["dry_run"] is True

    export = client.post("/api/admin/exports", json={"resource": "orders", "format": "csv", "filters": {}, "operator": "tester"}).json()
    assert export["ok"] is True
    assert export["job"]["status"] == "completed"
    result = client.get(export["job"]["download_url"]).json()
    assert result["ok"] is True
    assert result["content_text"]
    assert result["content_type"] == "text/csv; charset=utf-8"

    missing = client.get("/api/admin/exports/exp_missing")
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "not_found"
