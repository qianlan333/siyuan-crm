from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains import image_library
from wecom_ability_service.domains.wechat_pay import product_service
from wecom_ability_service.domains.wechat_pay import repo as wechat_pay_repo
from wecom_ability_service.domains.wechat_pay import service as wechat_pay_service
from wecom_ability_service.domains.admin_auth.auth_runtime import (
    ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY,
    ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY,
    ADMIN_SESSION_LOGIN_TYPE_KEY,
    ADMIN_SESSION_ROLE_LIST_KEY,
    ADMIN_SESSION_USER_ID_KEY,
)


PNG_A = b"\x89PNG\r\n\x1a\n" + b"a" * 32
PNG_B = b"\x89PNG\r\n\x1a\n" + b"b" * 32
REPO_ROOT = Path(__file__).resolve().parents[1]


def _wechat_headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 MicroMessenger/8.0.50"}


def _login_admin(client, *, token: str = "test-admin-action-token") -> str:
    with client.session_transaction() as sess:
        sess[ADMIN_SESSION_USER_ID_KEY] = 0
        sess[ADMIN_SESSION_LOGIN_TYPE_KEY] = "break_glass"
        sess[ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY] = "tester"
        sess[ADMIN_SESSION_ROLE_LIST_KEY] = ["super_admin"]
        sess[ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY] = token
    return token


def _configure_pay(app, tmp_path) -> None:
    private_key = tmp_path / "wechat_pay_apiclient_key.pem"
    platform_key = tmp_path / "wechat_pay_platform_public_key.pem"
    private_key.write_text("fake-private-key", encoding="utf-8")
    platform_key.write_text("fake-public-key", encoding="utf-8")
    app.config.update(
        WECHAT_MP_APP_ID="wx-mp-app",
        WECHAT_MP_APP_SECRET="mp-secret",
        WECHAT_PAY_ENABLED="true",
        WECHAT_PAY_APP_ID="wx-pay-app",
        WECHAT_PAY_MCH_ID="1900000001",
        WECHAT_PAY_API_V3_KEY="12345678901234567890123456789012",
        WECHAT_PAY_PRIVATE_KEY_PATH=str(private_key),
        WECHAT_PAY_CERT_SERIAL_NO="merchant-serial",
        WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH=str(platform_key),
        WECHAT_PAY_PRODUCT_CATALOG_JSON=json.dumps(
            {
                "products": [
                    {
                        "product_code": "legacy_report_v1",
                        "name": "历史支付商品",
                        "description": "历史支付商品",
                        "amount_total": 9900,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )


def _create_image(file_bytes: bytes, name: str) -> dict:
    return image_library.create_image_from_upload(
        file_bytes=file_bytes,
        file_name=f"{name}.png",
        mime_type="image/png",
        name=name,
    )


def _create_product(client, token: str, **overrides):
    payload = {
        "admin_action_token": token,
        "name": "AI 实战小课",
        "amount_total": 19900,
        "status": "active",
        "require_mobile": False,
        "cta_text": "立即报名",
        "lead_program_id": None,
        "slices": [],
    }
    payload.update(overrides)
    response = client.post("/api/admin/wechat-pay/products", json=payload)
    assert response.status_code == 200
    return response.get_json()["product"]


def test_admin_product_create_generates_code_and_list_shape(app, client):
    token = _login_admin(client)

    product = _create_product(client, token, name="私域成交动作拆解课", amount_total=39900)

    assert product["product_code"].startswith("prd_")
    assert product["name"] == "私域成交动作拆解课"
    assert product["amount_total"] == 39900
    assert product["status"] == "active"
    assert product["slice_count"] == 0

    page = client.get("/admin/wechat-pay/products")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "商品管理" in html
    assert "创建商品" in html
    assert "分享商品" in html
    assert "/share" in html
    assert "wp-preview-slice" not in html
    assert "wp-preview-img" not in html
    assert "wp-phone" not in html
    assert "wp-thumb" not in html
    assert "全景贴图数量" not in html
    assert "商品编码" not in html
    assert "商品简介" not in html
    assert "介绍页路径" not in html

    items = client.get("/api/admin/wechat-pay/products").get_json()["items"]
    assert items[0]["name"] == "私域成交动作拆解课"
    assert {"name", "amount_total", "status", "updated_at"}.issubset(items[0])

    edit_page = client.get(f"/admin/wechat-pay/products/{product['id']}/edit")
    assert edit_page.status_code == 200
    edit_html = edit_page.get_data(as_text=True)
    assert 'id="editorLoading"' in edit_html
    assert 'id="editorShell" hidden' in edit_html
    assert "扫码预览" in edit_html
    assert 'id="editorSharePreview"' in edit_html
    assert 'id="copyEditorShareUrl"' in edit_html
    assert "加载中" in edit_html
    assert "最多 10 张" in edit_html
    assert "最多 20 张" not in edit_html
    assert "image_upload_client.js" in edit_html
    assert "ImageUploadClient.prepareImageForUpload" in edit_html
    assert "ImageUploadClient.requestJson" in edit_html
    assert "response.json()" not in edit_html
    assert "确认删除这个商品吗？已有订单的商品请下架保留。" in edit_html
    assert "手机端预览" not in edit_html
    assert "引流计划列表加载失败" not in edit_html


def test_product_enable_disable_copy_and_delete(app, client):
    token = _login_admin(client)
    product = _create_product(client, token, status="draft")

    enabled = client.post(
        f"/api/admin/wechat-pay/products/{product['id']}/enable",
        json={"admin_action_token": token},
    )
    assert enabled.status_code == 200
    assert enabled.get_json()["product"]["status"] == "active"

    disabled = client.post(
        f"/api/admin/wechat-pay/products/{product['id']}/disable",
        json={"admin_action_token": token},
    )
    assert disabled.status_code == 200
    assert disabled.get_json()["product"]["status"] == "disabled"
    assert client.get(f"/p/{product['product_code']}").status_code == 404

    copied = client.post(
        f"/api/admin/wechat-pay/products/{product['id']}/copy",
        json={"admin_action_token": token},
    )
    assert copied.status_code == 200
    assert copied.get_json()["product"]["status"] == "draft"
    assert copied.get_json()["product"]["product_code"] != product["product_code"]

    deleted = client.delete(
        f"/api/admin/wechat-pay/products/{product['id']}",
        json={"admin_action_token": token},
    )
    assert deleted.status_code == 200


def test_delete_admin_product_rejects_product_with_orders(monkeypatch):
    deleted: list[int] = []
    monkeypatch.setattr(
        product_service.product_repo,
        "get_product_by_id",
        lambda product_id: {"id": int(product_id), "product_code": "prd_ordered"},
    )
    monkeypatch.setattr(product_service.product_repo, "count_orders_for_product_code", lambda product_code: 1)
    monkeypatch.setattr(product_service.product_repo, "delete_product", lambda product_id: deleted.append(int(product_id)))

    with pytest.raises(product_service.WeChatPayProductError, match="已有订单的商品不能删除"):
        product_service.delete_admin_product(8)

    assert deleted == []


def test_create_jsapi_order_success_path_commits_with_fake_client(monkeypatch):
    commits: list[str] = []
    inserted_payloads: list[dict[str, object]] = []
    payment_updates: list[dict[str, object]] = []

    class FakeDb:
        def commit(self):
            commits.append("commit")

    class FakeClient:
        def create_jsapi_transaction(self, payload):
            return {"prepay_id": "wx-prepay-id"}

        def build_jsapi_pay_params(self, prepay_id):
            return {"package": f"prepay_id={prepay_id}"}

    product = {
        "product_code": "prd_active_commit",
        "name": "支付链路回归商品",
        "description": "支付链路回归商品",
        "amount_total": 9900,
        "currency": "CNY",
        "success_url": "",
        "metadata": {},
        "require_mobile": False,
        "enabled": True,
        "status": "active",
    }

    monkeypatch.setattr(wechat_pay_service, "get_db", lambda: FakeDb())
    monkeypatch.setattr(
        wechat_pay_service,
        "_require_ready_for_order",
        lambda: SimpleNamespace(app_id="wx-pay-app", mch_id="1900000001"),
    )
    monkeypatch.setattr(wechat_pay_service, "get_product", lambda product_code: product)
    monkeypatch.setattr(
        wechat_pay_service.repo,
        "get_paid_order_for_product_identity",
        lambda **kwargs: None,
    )

    def fake_insert_order(payload):
        inserted_payloads.append(payload)
        return {
            **payload,
            "out_trade_no": payload["out_trade_no"],
            "status": "created",
            "trade_state": "",
            "refund_status": "",
            "refunded_amount_total": 0,
        }

    def fake_update_order_payment_request(out_trade_no, *, prepay_id, request_payload, response_payload):
        payment_updates.append(
            {
                "out_trade_no": out_trade_no,
                "prepay_id": prepay_id,
                "request_payload": request_payload,
                "response_payload": response_payload,
            }
        )
        return {
            **inserted_payloads[-1],
            "out_trade_no": out_trade_no,
            "status": "paying",
            "trade_state": "",
            "refund_status": "",
            "refunded_amount_total": 0,
            "prepay_id": prepay_id,
        }

    monkeypatch.setattr(wechat_pay_service.repo, "insert_order", fake_insert_order)
    monkeypatch.setattr(wechat_pay_service.repo, "update_order_payment_request", fake_update_order_payment_request)
    monkeypatch.setattr(wechat_pay_service.repo, "mark_order_failed", lambda *args, **kwargs: None)
    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())

    result = wechat_pay_service.create_jsapi_order(
        product_code="prd_active_commit",
        payer_openid="op_test",
        notify_url="https://example.test/wechat-pay/notify",
    )

    assert result["order"]["status"] == "paying"
    assert result["pay_params"]["package"] == "prepay_id=wx-prepay-id"
    assert inserted_payloads[0]["product_code"] == "prd_active_commit"
    assert payment_updates[0]["prepay_id"] == "wx-prepay-id"
    assert commits == ["commit"]


def test_admin_product_share_returns_public_link_and_qr(app, client):
    token = _login_admin(client)
    product = _create_product(client, token, name="可分享商品")

    response = client.get(
        f"/api/admin/wechat-pay/products/{product['id']}/share",
        base_url="https://crm.example.test",
    )

    assert response.status_code == 200
    share = response.get_json()["share"]
    assert share["url"] == f"https://crm.example.test/p/{product['product_code']}"
    assert share["product_name"] == "可分享商品"
    assert share["qr_data_url"].startswith("data:image/svg+xml;charset=UTF-8,")
    assert "%3Csvg" in share["qr_data_url"]
    assert 'xmlns="http://www.w3.org/2000/svg"' in unquote(share["qr_data_url"])


def test_lead_plan_options_skip_program_summary_dependency(app, client, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import program_service

    _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_plan_direct_options', '直接读取的引流计划', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_direct_options', '默认渠道', 'https://example.com/direct-qr.png', 'active')
        """,
        (program["id"],),
    )
    get_db().commit()

    def fail_summary_loader(**kwargs):
        raise AssertionError("lead plan options must not depend on program summaries")

    monkeypatch.setattr(program_service, "list_automation_programs", fail_summary_loader)

    response = client.get("/api/admin/wechat-pay/products/lead-plans")

    assert response.status_code == 200
    items = response.get_json()["items"]
    option = next(item for item in items if item["program_id"] == program["id"])
    assert option["program_name"] == "直接读取的引流计划"
    assert option["qr_url"] == "https://example.com/direct-qr.png"
    assert option["selectable"] is True


def test_product_slices_sort_and_public_page_render_order(app, client):
    token = _login_admin(client)
    first = _create_image(PNG_A, "slice-a")
    second = _create_image(PNG_B, "slice-b")
    product = _create_product(
        client,
        token,
        slices=[
            {"image_library_id": second["id"], "sort_order": 1},
            {"image_library_id": first["id"], "sort_order": 2},
        ],
    )

    detail = client.get(f"/api/admin/wechat-pay/products/{product['id']}").get_json()["product"]
    assert [item["image_library_id"] for item in detail["slices"]] == [second["id"], first["id"]]
    assert all("image_url" not in item for item in detail["slices"])

    reordered = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}/slices/reorder",
        json={
            "admin_action_token": token,
            "slice_ids": [detail["slices"][1]["id"], detail["slices"][0]["id"]],
        },
    )
    assert reordered.status_code == 200
    assert [item["image_library_id"] for item in reordered.get_json()["product"]["slices"]] == [first["id"], second["id"]]

    public_html = client.get(f"/p/{product['product_code']}").get_data(as_text=True)
    assert public_html.index("YWFhYWFh") < public_html.index("YmJiYmJi")


def test_product_slices_limit_is_ten(app, client):
    token = _login_admin(client)
    images = [_create_image(PNG_A, f"slice-limit-{index}") for index in range(11)]
    too_many = client.post(
        "/api/admin/wechat-pay/products",
        json={
            "admin_action_token": token,
            "name": "超过切片限制商品",
            "amount_total": 19900,
            "status": "active",
            "require_mobile": False,
            "cta_text": "立即报名",
            "slices": [
                {"image_library_id": item["id"], "sort_order": index + 1}
                for index, item in enumerate(images)
            ],
        },
    )
    assert too_many.status_code == 400
    assert "最多 10 张" in too_many.get_json()["error"]

    product = _create_product(
        client,
        token,
        slices=[
            {"image_library_id": item["id"], "sort_order": index + 1}
            for index, item in enumerate(images[:10])
        ],
    )

    detail = client.get(f"/api/admin/wechat-pay/products/{product['id']}").get_json()["product"]
    assert len(detail["slices"]) == 10

    update_too_many = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}",
        json={
            "admin_action_token": token,
            "name": product["name"],
            "amount_total": product["amount_total"],
            "status": product["status"],
            "require_mobile": product["require_mobile"],
            "cta_text": product["cta_text"],
            "slices": [
                {"image_library_id": item["id"], "sort_order": index + 1}
                for index, item in enumerate(images)
            ],
        },
    )
    assert update_too_many.status_code == 400
    assert "最多 10 张" in update_too_many.get_json()["error"]

    response = client.post(
        f"/api/admin/wechat-pay/products/{product['id']}/slices",
        json={"admin_action_token": token, "image_library_id": images[-1]["id"]},
    )
    assert response.status_code == 400
    assert "最多 10 张" in response.get_json()["error"]


def test_normalize_product_slices_rejects_more_than_ten():
    with pytest.raises(product_service.WeChatPayProductError, match="最多 10 张"):
        product_service._normalize_slices_payload([{"image_library_id": index + 1} for index in range(11)])


def test_product_editor_rejects_batch_upload_over_slice_limit():
    template = (
        REPO_ROOT
        / "wecom_ability_service"
        / "templates"
        / "admin_console"
        / "wechat_pay_products.html"
    ).read_text(encoding="utf-8")

    assert "selectedFiles.length > available" in template
    assert "Array.from(files || []).slice(0, available)" not in template


def test_product_intro_redirects_to_payment_oauth_before_rendering_in_wechat(app, client, tmp_path):
    _configure_pay(app, tmp_path)
    app.config["SECRET_KEY"] = "wechat-pay-product-intro-secret"
    token = _login_admin(client)
    product = _create_product(client, token)

    response = client.get(f"/p/{product['product_code']}", headers=_wechat_headers())

    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/api/h5/wechat-pay/oauth/start" in location
    assert f"return_url=%2Fp%2F{product['product_code']}" in location


def test_image_library_upload_limits_are_reused(app, client):
    token = _login_admin(client)
    _create_product(client, token)
    response = client.post(
        "/api/admin/image-library/upload",
        data={"image": (BytesIO(b"not-image"), "slice.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "JPG/PNG" in response.get_json()["error"] or "supported" in response.get_json()["error"]


def test_checkout_page_mobile_field_depends_on_product(app, client):
    token = _login_admin(client)
    require_mobile = _create_product(client, token, require_mobile=True)
    no_mobile = _create_product(client, token, name="无需手机号商品", require_mobile=False)
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_test", "payer_name": "微信昵称"}

    html = client.get(f"/pay/{require_mobile['product_code']}", headers=_wechat_headers()).get_data(as_text=True)
    assert 'id="mobileInput"' in html
    assert 'fetch(state.create_order_url' in html
    assert 'order_source: "product_checkout"' in html
    assert 'WeixinJSBridge.invoke("getBrandWCPayRequest"' in html
    assert "waitForPaid(activeOrderNo)" in html

    html = client.get(f"/pay/{no_mobile['product_code']}", headers=_wechat_headers()).get_data(as_text=True)
    assert 'id="mobileInput"' not in html


def test_require_mobile_order_validation_and_mobile_snapshot(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    token = _login_admin(client)
    product = _create_product(client, token, require_mobile=True)
    calls: dict[str, object] = {}

    class FakeClient:
        def create_jsapi_transaction(self, payload):
            calls["transaction_payload"] = payload
            return {"prepay_id": "wx-prepay-id"}

        def build_jsapi_pay_params(self, prepay_id):
            return {"package": f"prepay_id={prepay_id}"}

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_test", "unionid": "un_test", "payer_name": "微信昵称"}

    missing_mobile = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={"product_code": product["product_code"], "order_source": "product_checkout"},
        headers=_wechat_headers(),
    )
    assert missing_mobile.status_code == 400
    assert missing_mobile.get_json()["error"] == "mobile_required"
    assert get_db().execute("SELECT COUNT(*) AS c FROM wechat_pay_orders").fetchone()["c"] == 0

    created = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={
            "product_code": product["product_code"],
            "order_source": "product_checkout",
            "mobile": "13800138000",
        },
        headers=_wechat_headers(),
    )
    assert created.status_code == 200
    payload = created.get_json()
    row = get_db().execute(
        "SELECT mobile_snapshot, request_meta_json FROM wechat_pay_orders WHERE out_trade_no = ?",
        (payload["order"]["out_trade_no"],),
    ).fetchone()
    assert row["mobile_snapshot"] == "13800138000"
    assert row["request_meta_json"]["mobile_binding"]["mobile"] == "13800138000"
    assert calls["transaction_payload"]["amount"]["total"] == 19900


def test_created_jsapi_order_can_refresh_paid_status_with_lead_qr(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    token = _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_plan_paid_refresh', '0元引流用户', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    channel = get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_paid_refresh', '默认渠道', 'https://example.com/paid-refresh-qr.png', 'active')
        RETURNING *
        """,
        (program["id"],),
    ).fetchone()
    get_db().commit()
    product = _create_product(client, token, lead_program_id=program["id"])
    assert product["lead_channel_id"] == channel["id"]

    class FakeClient:
        def create_jsapi_transaction(self, payload):
            return {"prepay_id": "wx-prepay-id"}

        def build_jsapi_pay_params(self, prepay_id):
            return {"package": f"prepay_id={prepay_id}"}

        def query_order_by_out_trade_no(self, out_trade_no):
            return {
                "out_trade_no": out_trade_no,
                "transaction_id": "420000000020260518",
                "trade_state": "SUCCESS",
                "bank_type": "OTHERS",
                "success_time": "2026-05-18T19:06:00+08:00",
                "amount": {"total": product["amount_total"], "payer_total": product["amount_total"]},
                "payer": {"openid": "op_test"},
            }

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_test", "unionid": "un_test", "payer_name": "微信昵称"}

    created = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={"product_code": product["product_code"], "order_source": "product_checkout"},
        headers=_wechat_headers(),
    )
    assert created.status_code == 200
    out_trade_no = created.get_json()["order"]["out_trade_no"]

    paid = client.get(f"/api/h5/wechat-pay/orders/{out_trade_no}?refresh=1").get_json()["order"]
    assert paid["status"] == "paid"
    assert paid["lead_qr"]["qr_url"] == "https://example.com/paid-refresh-qr.png"


def test_checkout_page_reopens_paid_order_and_duplicate_order_is_blocked(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    token = _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_plan_reopen_paid', '0元引流用户', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_reopen_paid', '默认渠道', 'https://example.com/reopen-qr.png', 'active')
        """,
        (program["id"],),
    )
    get_db().commit()
    product = _create_product(client, token, lead_program_id=program["id"], require_mobile=True)
    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": "WXP_ALREADY_PAID",
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["name"],
            "amount_total": product["amount_total"],
            "payer_openid": "op_paid",
            "unionid": "un_paid",
            "status": "paid",
            "metadata": {},
            "request_meta": {},
        }
    )
    get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET trade_state = 'SUCCESS'
        WHERE out_trade_no = ?
        """,
        (order["out_trade_no"],),
    )
    get_db().commit()

    class FakeClient:
        def create_jsapi_transaction(self, payload):
            raise AssertionError("duplicate paid users must not create a new WeChat order")

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_paid", "unionid": "un_paid", "payer_name": "已报名用户"}

    intro_html = client.get(f"/p/{product['product_code']}", headers=_wechat_headers()).get_data(as_text=True)
    assert "支付成功" in intro_html
    assert '"paid_order":' in intro_html
    assert 'id="showLeadQrButton"' in intro_html
    assert "showPaid(state.paid_order, { autoShowQr: false })" in intro_html

    html = client.get(f"/pay/{product['product_code']}", headers=_wechat_headers()).get_data(as_text=True)
    assert '"paid_order":' in html
    assert "WXP_ALREADY_PAID" in html
    assert 'id="showLeadQrButton"' in html
    assert "showPaid(state.paid_order, { autoShowQr: false })" in html

    duplicate = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={
            "product_code": product["product_code"],
            "order_source": "product_checkout",
            "mobile": "13800138000",
        },
        headers=_wechat_headers(),
    )
    assert duplicate.status_code == 400
    assert duplicate.get_json()["error"] == "already_paid"


def test_full_refunded_order_allows_repurchase(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    token = _login_admin(client)
    product = _create_product(client, token)
    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": "WXP_FULL_REFUNDED",
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["name"],
            "amount_total": product["amount_total"],
            "payer_openid": "op_refunded",
            "status": "paid",
            "metadata": {},
            "request_meta": {},
        }
    )
    get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET trade_state = 'SUCCESS',
            refunded_amount_total = amount_total,
            refund_status = 'full_refunded'
        WHERE out_trade_no = ?
        """,
        (order["out_trade_no"],),
    )
    get_db().commit()

    class FakeClient:
        def create_jsapi_transaction(self, payload):
            return {"prepay_id": "wx-prepay-id"}

        def build_jsapi_pay_params(self, prepay_id):
            return {"package": f"prepay_id={prepay_id}"}

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_refunded", "payer_name": "退款用户"}

    html = client.get(f"/pay/{product['product_code']}", headers=_wechat_headers()).get_data(as_text=True)
    assert '"paid_order": null' in html
    created = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={"product_code": product["product_code"], "order_source": "product_checkout"},
        headers=_wechat_headers(),
    )
    assert created.status_code == 200
    assert created.get_json()["order"]["status"] == "paying"


def test_public_order_payload_does_not_show_lead_qr_after_full_refund(monkeypatch):
    product_lookups: list[str] = []
    monkeypatch.setattr(
        wechat_pay_service,
        "get_lead_qr_for_product_code",
        lambda product_code: product_lookups.append(product_code) or {"qr_url": "https://example.test/qr.png"},
    )

    payload = wechat_pay_service._order_public_payload(
        {
            "out_trade_no": "WXP_REFUNDED_PUBLIC",
            "product_code": "prd_refunded",
            "product_name": "退款商品",
            "amount_total": 9900,
            "refunded_amount_total": 9900,
            "refund_status": "full_refunded",
            "status": "paid",
            "trade_state": "SUCCESS",
        }
    )

    assert payload["status"] == "full_refunded"
    assert payload["refund_status"] == "full_refunded"
    assert "lead_qr" not in payload
    assert product_lookups == []


def test_checkout_template_uses_normalized_paid_status_only():
    source = (REPO_ROOT / "wecom_ability_service/templates/wechat_pay_h5_checkout.html").read_text(encoding="utf-8")

    assert 'order.status === "paid"' in source
    assert 'order.trade_state === "SUCCESS"' not in source
    assert 'order.status !== "paid" && order.trade_state !== "SUCCESS"' not in source


def test_paid_order_status_returns_lead_qr_only_after_paid(app, client):
    token = _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_plan_v1', '引流计划', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    channel = get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_lead_plan_v1', '默认渠道', 'https://example.com/qr.png', 'active')
        RETURNING *
        """,
        (program["id"],),
    ).fetchone()
    get_db().commit()
    product = _create_product(client, token, lead_program_id=program["id"])
    assert product["lead_channel_id"] == channel["id"]

    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": "WXP_LEAD_QR",
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["name"],
            "amount_total": product["amount_total"],
            "payer_openid": "op_test",
            "status": "paying",
            "metadata": {},
            "request_meta": {},
        }
    )
    unpaid = client.get(f"/api/h5/wechat-pay/orders/{order['out_trade_no']}").get_json()["order"]
    assert "lead_qr" not in unpaid

    get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET status = 'paid', trade_state = 'SUCCESS'
        WHERE out_trade_no = ?
        """,
        (order["out_trade_no"],),
    )
    get_db().commit()
    paid = client.get(f"/api/h5/wechat-pay/orders/{order['out_trade_no']}").get_json()["order"]
    assert paid["lead_qr"]["qr_url"] == "https://example.com/qr.png"


def test_legacy_catalog_product_api_still_works(app, client, tmp_path):
    _configure_pay(app, tmp_path)

    payload = client.get("/api/h5/wechat-pay/products/legacy_report_v1").get_json()

    assert payload["ok"] is True
    assert payload["product"]["product_code"] == "legacy_report_v1"
    assert payload["product"]["amount_total"] == 9900
    assert payload["product"]["slices"] == []
