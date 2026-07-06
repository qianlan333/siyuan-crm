from __future__ import annotations

from conftest import make_client


def test_product_list_and_detail_return_required_shape() -> None:
    client = make_client()
    payload = client.get("/api/admin/wechat-pay/products").json()
    assert payload["ok"] is True
    assert {"items", "total", "limit", "offset"} <= set(payload)
    item = payload["items"][0]
    for key in [
        "id",
        "product_code",
        "title",
        "description",
        "price_cents",
        "currency",
        "enabled",
        "page_slug",
        "cover_image_id",
        "detail_image_ids",
        "buy_button_text",
        "created_at",
        "updated_at",
    ]:
        assert key in item
    detail = client.get(f"/api/admin/wechat-pay/products/{item['id']}").json()
    assert detail["ok"] is True
    assert "detail_sections" in detail["product"]


def test_product_create_update_enable_disable_delete_and_validation() -> None:
    client = make_client()
    payload = {
        "product_code": "course_masked_new",
        "title": "新商品",
        "description": "fixture",
        "price_cents": 100,
        "page_slug": "course-masked-new",
    }
    created = client.post("/api/admin/wechat-pay/products", json=payload)
    assert created.status_code == 200
    product = created.json()["product"]
    assert client.post("/api/admin/wechat-pay/products", json=payload).status_code == 400
    assert client.post("/api/admin/wechat-pay/products", json={**payload, "product_code": "bad_price", "price_cents": -1}).status_code == 400
    updated = client.put(f"/api/admin/wechat-pay/products/{product['id']}", json={**payload, "title": "更新商品"}).json()
    assert updated["product"]["title"] == "更新商品"
    assert client.post(f"/api/admin/wechat-pay/products/{product['id']}/disable").json()["product"]["enabled"] is False
    assert client.post(f"/api/admin/wechat-pay/products/{product['id']}/enable").json()["product"]["enabled"] is True
    deleted = client.delete(f"/api/admin/wechat-pay/products/{product['id']}").json()
    assert deleted["soft_deleted"] is False
    assert client.get(f"/api/admin/wechat-pay/products/{product['id']}").status_code == 404
    assert all(item["id"] != product["id"] for item in client.get("/api/admin/wechat-pay/products").json()["items"])


def test_active_product_with_orders_must_be_disabled_before_delete() -> None:
    client = make_client()

    active_ordered = client.delete("/api/admin/wechat-pay/products/prod_001")
    assert active_ordered.status_code == 400
    assert "已有订单的商品不能删除" in active_ordered.json()["detail"]

    assert client.post("/api/admin/wechat-pay/products/prod_001/disable").json()["product"]["enabled"] is False
    disabled_ordered = client.delete("/api/admin/wechat-pay/products/prod_001")
    assert disabled_ordered.status_code == 200
    assert disabled_ordered.json()["soft_deleted"] is False
    assert client.get("/api/admin/wechat-pay/products/prod_001").status_code == 404


def test_product_completion_redirect_fields_flow_through_checkout_and_order_status() -> None:
    client = make_client()
    payload = {
        "product_code": "course_redirect_new",
        "title": "跳转商品",
        "description": "fixture",
        "price_cents": 100,
        "page_slug": "course-redirect-new",
        "completion_redirect_enabled": True,
        "completion_redirect_url": "https://example.com/after-paid",
    }
    created = client.post("/api/admin/wechat-pay/products", json=payload)
    assert created.status_code == 200
    product = created.json()["product"]
    assert product["completion_redirect_enabled"] is True
    assert product["completion_redirect_url"] == "https://example.com/after-paid"

    public_product = client.get("/api/products/course-redirect-new").json()["product"]
    assert public_product["completion_redirect"]["url"] == "https://example.com/after-paid"
    assert public_product["completion_action"] == {
        "type": "redirect",
        "redirect_url": "https://example.com/after-paid",
    }

    checkout = client.post("/api/checkout/wechat", json={"product_code": "course_redirect_new", "quantity": 1}).json()
    assert checkout["completion_redirect_url"] == "https://example.com/after-paid"
    assert checkout["completion_action"]["type"] == "redirect"
    status = client.get(f"/api/orders/{checkout['order_no']}/status").json()
    assert status["order"]["completion_redirect"]["url"] == "https://example.com/after-paid"
    assert status["order"]["completion_action"]["redirect_url"] == "https://example.com/after-paid"


def test_product_completion_redirect_allows_safe_internal_path() -> None:
    client = make_client()
    response = client.post(
        "/api/admin/wechat-pay/products",
        json={
            "product_code": "course_internal_redirect",
            "title": "站内跳转商品",
            "price_cents": 100,
            "completion_redirect_enabled": True,
            "completion_redirect_url": "/welcome",
        },
    )
    assert response.status_code == 200
    product = response.json()["product"]
    assert product["completion_action"] == {"type": "redirect", "redirect_url": "/welcome"}


def test_product_completion_redirect_rejects_invalid_url_when_enabled() -> None:
    client = make_client()
    response = client.post(
        "/api/admin/wechat-pay/products",
        json={
            "product_code": "course_bad_redirect",
            "title": "坏跳转商品",
            "price_cents": 100,
            "completion_redirect_enabled": True,
            "completion_redirect_url": "javascript:alert(1)",
        },
    )
    assert response.status_code == 400


def test_product_create_accepts_product_code_aliases_in_next_native_contract() -> None:
    client = make_client()
    payload = {
        "product": {"code": "custom_course_2026"},
        "title": "自定义编码商品",
        "description": "fixture",
        "price_cents": 29900,
    }

    created = client.post("/api/admin/wechat-pay/products", json=payload)
    assert created.status_code == 200
    product = created.json()["product"]
    assert product["product_code"] == "custom_course_2026"
    assert product["page_slug"] == "custom_course_2026"

    public_payload = client.get("/api/products/custom_course_2026").json()
    assert public_payload["product"]["product_code"] == "custom_course_2026"

    duplicate = client.post("/api/admin/wechat-pay/products", json=payload)
    assert duplicate.status_code == 400
    assert "product_code must be unique" in duplicate.json()["detail"]

    invalid = client.post(
        "/api/admin/wechat-pay/products",
        json={**payload, "product": {"code": "bad code"}},
    )
    assert invalid.status_code == 400
    assert "product_code must be 3-80 characters" in invalid.json()["detail"]


def test_product_admin_pages_are_next_native_and_submit_product_code_alias() -> None:
    client = make_client()

    list_page = client.get("/admin/wechat-pay/products")
    assert list_page.status_code == 200
    assert "course_masked_001" in list_page.text
    assert "/admin/wechat-pay/products/new" in list_page.text

    new_page = client.get("/admin/wechat-pay/products/new")
    assert new_page.status_code == 200
    assert "创建微信支付商品" in new_page.text
    assert "admin-shell" in new_page.text
    assert "admin-nav" in new_page.text
    assert 'id="productCode"' in new_page.text
    assert "product: { code:" in new_page.text
    assert "外部推送" in new_page.text
    assert 'mode === "edit" ? "PUT" : "POST"' in new_page.text

    created = client.post(
        "/api/admin/wechat-pay/products",
        json={
            "product": {"code": "admin_page_code_2026"},
            "title": "后台创建商品",
            "price_cents": 12800,
            "status": "draft",
            "require_mobile": True,
            "buy_button_text": "立即报名",
            "slices": [{"image_library_id": 1, "sort_order": 1}],
        },
    ).json()["product"]
    assert created["status"] == "draft"
    assert created["require_mobile"] is True
    assert created["slice_count"] == 1
    edit_page = client.get(f"/admin/wechat-pay/products/{created['id']}/edit")
    assert edit_page.status_code == 200
    assert "admin_page_code_2026" in edit_page.text
    assert "readonly" in edit_page.text


def test_product_admin_restores_lead_external_push_copy_and_slice_contracts() -> None:
    client = make_client()
    created = client.post(
        "/api/admin/wechat-pay/products",
        json={
            "product": {"code": "capability_course_2026"},
            "title": "能力回归商品",
            "price_cents": 16800,
            "status": "active",
            "cta_text": "马上加入",
            "require_mobile": True,
            "slices": [{"image_library_id": 1, "sort_order": 1}],
        },
    ).json()["product"]

    detail = client.get(f"/api/admin/wechat-pay/products/{created['id']}").json()["product"]
    assert detail["name"] == "能力回归商品"
    assert detail["amount_total"] == 16800
    assert detail["status"] == "active"
    assert detail["cta_text"] == "马上加入"
    assert detail["require_mobile"] is True
    assert [item["image_library_id"] for item in detail["slices"]] == [1]

    channels = client.get("/api/admin/wechat-pay/products/lead-channels").json()
    assert channels["ok"] is True
    assert channels["items"][0]["channel_id"] == 0

    config = client.put(
        f"/api/admin/wechat-pay/products/{created['id']}/external-push",
        json={
            "enabled": True,
            "webhook_url": "https://hooks.example.test/product",
            "push_type": "paid_notify",
            "expires_at_ts": 1999999999,
            "day": 7,
            "frequency": 1,
            "remark": "支付后通知",
            "custom_params": {"source": "product"},
        },
    ).json()["config"]
    assert config["enabled"] is True
    assert config["custom_params"] == {"source": "product"}
    assert client.get(f"/api/admin/wechat-pay/products/{created['id']}/external-push").json()["config"]["push_type"] == "paid_notify"

    test_push = client.post(f"/api/admin/wechat-pay/products/{created['id']}/external-push/test").json()
    assert test_push["real_external_call_executed"] is False
    assert test_push["route_owner"] == "ai_crm_next"
    if test_push["ok"] is True:
        assert test_push["result"]["delivery"]["status"] in {"preview", "retrying"}
    else:
        assert test_push["error"]

    copied = client.post(f"/api/admin/wechat-pay/products/{created['id']}/copy")
    assert copied.status_code == 201
    copied_product = copied.json()["product"]
    assert copied_product["product_code"] != created["product_code"]
    assert copied_product["status"] == "draft"
    assert copied_product["slice_count"] == 1


def test_postgres_lead_channels_use_qrcode_assets_and_program_name() -> None:
    from aicrm_next.commerce.repo import PostgresCommerceRepository

    captured_sql: list[str] = []

    class FakeResult:
        def fetchall(self) -> list[dict[str, object]]:
            return [
                {
                    "channel_id": 11,
                    "channel_name": "二维码资产渠道",
                    "program_id": 7,
                    "program_name": "9.9已付费引流方案",
                    "qr_url": "https://example.com/asset-qr.png",
                    "status": "active",
                },
                {
                    "channel_id": 12,
                    "channel_name": "未生成二维码渠道",
                    "program_id": None,
                    "program_name": None,
                    "qr_url": "",
                    "status": "active",
                },
            ]

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def execute(self, sql: str, params: object | None = None) -> FakeResult:
            captured_sql.append(sql)
            return FakeResult()

    repository = PostgresCommerceRepository("postgres://fixture")
    repository._connect = lambda: FakeConnection()  # type: ignore[method-assign]

    items = repository.list_lead_channels()

    assert items[0]["channel_id"] == 0
    assert items[0]["channel_name"] == "不配置引流渠道码"
    assert items[0]["qr_url"] == ""
    assert items[0]["selectable"] is True
    assert items[1]["channel_name"] == "二维码资产渠道"
    assert items[1]["qr_url"] == "https://example.com/asset-qr.png"
    assert items[1]["selectable"] is True
    assert items[2]["channel_name"] == "未生成二维码渠道"
    assert items[2]["selectable"] is False
    assert "automation_channel_qrcode_asset" in captured_sql[0]


def test_product_share_route_is_next_native() -> None:
    client = make_client()
    item = client.get("/api/admin/wechat-pay/products").json()["items"][0]

    payload = client.get(f"/api/admin/wechat-pay/products/{item['id']}/share").json()

    assert payload["ok"] is True
    assert f"/p/{item['product_code']}" in payload["share"]["url"]
    assert payload["share"]["qr_data_url"].startswith("data:image/svg+xml")


def test_checkout_orders_notify_and_transactions_are_fake_and_idempotent() -> None:
    client = make_client()
    seeded_detail = client.get("/admin/wechat-pay/transactions/order_masked_001")
    assert seeded_detail.status_code == 200
    assert "申请退款" in seeded_detail.text
    assert "可退款" in seeded_detail.text
    mismatch = client.post(
        "/api/admin/wechat-pay/orders/order_masked_001/refunds",
        json={
            "refund_amount_total": 100,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "wrong_transaction",
            "checked": True,
        },
    )
    assert mismatch.status_code == 400
    assert "微信单号二次确认不匹配" in mismatch.json()["error"]
    refund = client.post(
        "/api/admin/wechat-pay/orders/order_masked_001/refunds",
        json={
            "refund_amount_total": 100,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "transaction_masked_001",
            "checked": True,
        },
    ).json()
    assert refund["ok"] is True
    assert refund["refund"]["provider_refund_executed"] is False
    assert refund["order"]["status"] == "refund_processing"
    assert refund["order"]["active_refund_amount_total"] == 100

    wechat = client.post(
        "/api/checkout/wechat",
        json={"product_code": "course_masked_001", "buyer_identity": {"mobile": "mobile_masked_001"}, "quantity": 2},
    ).json()
    assert wechat["ok"] is True
    assert wechat["payment_provider"] == "wechat"
    assert wechat["payment_status"] == "pending"
    assert wechat["fake_payment"] is True
    assert client.post("/api/checkout/wechat", json={"product_code": "course_masked_001", "quantity": 0}).status_code == 400
    assert client.post("/api/checkout/wechat", json={"product_code": "missing", "quantity": 1}).status_code == 404
    assert client.post("/api/checkout/wechat", json={"product_code": "course_disabled_001", "quantity": 1}).status_code == 400

    status = client.get(f"/api/orders/{wechat['order_no']}/status").json()
    assert status["payment_status"] == "pending"
    paid = client.post(
        "/api/wechat-pay/notify",
        json={"order_no": wechat["order_no"], "payment_status": "paid", "transaction_id": "transaction_masked_new"},
    ).json()
    paid_again = client.post(
        "/api/wechat-pay/notify",
        json={"order_no": wechat["order_no"], "payment_status": "paid", "transaction_id": "transaction_masked_new"},
    ).json()
    assert paid["payment_status"] == "paid"
    assert paid_again["transaction_id"] == "transaction_masked_new"
    assert client.post("/api/wechat-pay/notify", json={"order_no": wechat["order_no"], "payment_status": "failed"}).json()["payment_status"] == "failed"

    alipay = client.post(
        "/api/checkout/alipay",
        json={"product_code": "course_masked_001", "buyer_identity": {"openid": "openid_masked_001"}, "quantity": 1},
    ).json()
    assert alipay["payment_provider"] == "alipay"
    assert client.get(f"/api/alipay/return?order_no={alipay['order_no']}&status=paid").json()["payment_status"] == "paid"

    wx_tx = client.get("/api/admin/wechat-pay/transactions?payment_status=failed&product_code=course_masked_001&mobile=mobile_masked").json()
    assert wx_tx["ok"] is True
    assert wx_tx["items"][0]["out_trade_no"] == wechat["order_no"]
    assert wx_tx["items"][0]["merchant_order_no"] == wechat["order_no"]
    wx_admin_orders = client.get("/api/admin/wechat-pay/orders?status=failed&product_code=course_masked_001&mobile=mobile_masked").json()
    assert wx_admin_orders["ok"] is True
    assert wx_admin_orders["items"][0]["transaction_id"] == "transaction_masked_new"
    assert wx_admin_orders["items"][0]["status_label"] == "支付失败"
    assert client.get(f"/api/admin/wechat-pay/transactions/{wechat['order_no']}").json()["transaction"]["status"] == "failed"
    detail_page = client.get(f"/admin/wechat-pay/transactions/{wechat['order_no']}")
    assert detail_page.status_code == 200
    assert "微信支付订单详情" in detail_page.text
    assert "transaction_masked_new" in detail_page.text
    assert client.get("/api/admin/alipay/transactions?payment_status=paid").json()["ok"] is True

    export_response = client.post("/api/admin/wechat-pay/order-exports", json={"filters": {"product_code": "course_masked_001"}})
    assert export_response.status_code == 200
    assert "text/csv" in export_response.headers["content-type"]
    assert "微信单号" in export_response.text


def test_public_product_page_and_unknown_product_contracts() -> None:
    client = make_client()
    assert client.get("/p/course-masked-001").status_code == 200
    product = client.get("/api/products/course-masked-001").json()["product"]
    assert product["product_code"] == "course_masked_001"
    assert client.get("/api/products/missing-product").status_code == 404
