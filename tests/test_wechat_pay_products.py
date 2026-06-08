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
from wecom_ability_service.infra.signed_context import build_sidebar_product_context_token
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
    del client, token
    payload = {
        "name": "AI 实战小课",
        "amount_total": 19900,
        "status": "active",
        "require_mobile": False,
        "cta_text": "立即报名",
        "lead_program_id": None,
        "slices": [],
    }
    payload.update(overrides)
    return product_service.create_admin_product(payload, operator="pytest")


def test_admin_product_management_routes_render_and_mutate(app, client):
    token = _login_admin(client)
    product = _create_product(client, token, name="私域成交动作拆解课", amount_total=39900)

    list_page = client.get("/admin/wechat-pay/products")
    assert list_page.status_code == 200
    list_html = list_page.get_data(as_text=True)
    assert "商品管理" in list_html
    assert "创建商品" in list_html

    new_page = client.get("/admin/wechat-pay/products/new")
    assert new_page.status_code == 200
    assert "保存商品" in new_page.get_data(as_text=True)
    assert "支付后引流渠道码" in new_page.get_data(as_text=True)
    assert "报名完成后跳转" in new_page.get_data(as_text=True)
    assert "开启完成后跳转" in new_page.get_data(as_text=True)
    assert "当前已开启完成后跳转" in new_page.get_data(as_text=True)
    assert "请填写跳转链接" in new_page.get_data(as_text=True)
    assert "跳转链接格式不合法" in new_page.get_data(as_text=True)
    assert "completionRedirectUrl" in new_page.get_data(as_text=True)
    assert "支付后引流计划" not in new_page.get_data(as_text=True)

    edit_page = client.get(f"/admin/wechat-pay/products/{product['id']}/edit")
    assert edit_page.status_code == 200
    assert "扫码预览" in edit_page.get_data(as_text=True)

    list_response = client.get("/api/admin/wechat-pay/products")
    assert list_response.status_code == 200
    assert list_response.json["ok"] is True
    assert any(item["id"] == product["id"] for item in list_response.json["items"])

    detail_response = client.get(f"/api/admin/wechat-pay/products/{product['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json["product"]["name"] == "私域成交动作拆解课"

    lead_channels_response = client.get("/api/admin/wechat-pay/products/lead-channels")
    assert lead_channels_response.status_code == 200
    assert lead_channels_response.json["ok"] is True

    share_response = client.get(f"/api/admin/wechat-pay/products/{product['id']}/share")
    assert share_response.status_code == 200
    assert f"/p/{product['product_code']}" in share_response.json["share"]["url"]
    assert share_response.json["share"]["qr_data_url"].startswith("data:image/svg+xml")

    update_response = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}",
        json={
            "admin_action_token": token,
            "name": "私域成交动作拆解课升级版",
            "amount_total": 49900,
            "status": "draft",
            "require_mobile": True,
            "cta_text": "立即报名",
            "slices": [],
        },
    )
    assert update_response.status_code == 200
    assert update_response.json["product"]["status"] == "draft"

    assert client.post(f"/api/admin/wechat-pay/products/{product['id']}/enable", json={"admin_action_token": token}).json["product"]["status"] == "active"
    assert client.post(f"/api/admin/wechat-pay/products/{product['id']}/disable", json={"admin_action_token": token}).json["product"]["status"] == "disabled"

    copy_response = client.post(f"/api/admin/wechat-pay/products/{product['id']}/copy", json={"admin_action_token": token})
    assert copy_response.status_code == 201
    copied_id = copy_response.json["product"]["id"]
    assert copied_id != product["id"]

    delete_response = client.delete(f"/api/admin/wechat-pay/products/{copied_id}", json={"admin_action_token": token})
    assert delete_response.status_code == 200
    assert delete_response.json["ok"] is True


def test_product_enable_disable_copy_and_delete(app, client):
    token = _login_admin(client)
    product = _create_product(client, token, status="draft")

    enabled = product_service.set_admin_product_status(product["id"], "active", operator="pytest")
    assert enabled["status"] == "active"

    disabled = product_service.set_admin_product_status(product["id"], "disabled", operator="pytest")
    assert disabled["status"] == "disabled"
    assert client.get(f"/p/{product['product_code']}").status_code == 404

    copied = product_service.copy_admin_product(product["id"], operator="pytest")
    assert copied["status"] == "draft"
    assert copied["product_code"] != product["product_code"]

    product_service.delete_admin_product(product["id"], operator="pytest")
    with pytest.raises(product_service.WeChatPayProductError, match="商品不存在"):
        product_service.get_admin_product(product["id"])


def test_delete_admin_product_rejects_product_with_orders(monkeypatch):
    deleted: list[int] = []
    monkeypatch.setattr(
        product_service.product_repo,
        "get_product_by_id",
        lambda product_id: {"id": int(product_id), "product_code": "prd_ordered", "status": "active"},
    )
    monkeypatch.setattr(product_service.product_repo, "count_orders_for_product_code", lambda product_code: 1)
    monkeypatch.setattr(product_service.product_repo, "delete_product", lambda product_id: deleted.append(int(product_id)))

    with pytest.raises(product_service.WeChatPayProductError, match="已有订单的商品不能删除"):
        product_service.delete_admin_product(8)

    assert deleted == []


def test_delete_admin_product_allows_disabled_product_with_orders(monkeypatch):
    deleted: list[int] = []
    commits: list[str] = []

    class FakeDb:
        def commit(self):
            commits.append("commit")

    monkeypatch.setattr(
        product_service.product_repo,
        "get_product_by_id",
        lambda product_id: {"id": int(product_id), "product_code": "prd_disabled_ordered", "status": "disabled"},
    )
    monkeypatch.setattr(product_service.product_repo, "count_orders_for_product_code", lambda product_code: 1)
    monkeypatch.setattr(product_service.product_repo, "delete_product", lambda product_id: deleted.append(int(product_id)))
    monkeypatch.setattr(product_service, "get_db", lambda: FakeDb())

    product_service.delete_admin_product(9)

    assert deleted == [9]
    assert commits == ["commit"]


def test_completion_redirect_payload_validation_is_effective_only_when_url_is_valid():
    normalized = product_service._normalize_completion_redirect_payload(
        {
            "completion_redirect_enabled": True,
            "completion_redirect_url": "https://example.com/after-paid",
        },
        {},
    )
    assert normalized == {
        "completion_redirect_enabled": True,
        "completion_redirect_url": "https://example.com/after-paid",
    }
    internal_path = product_service._normalize_completion_redirect_payload(
        {
            "completion_redirect_enabled": True,
            "completion_redirect_url": "/after-paid",
        },
        {},
    )
    assert internal_path == {
        "completion_redirect_enabled": True,
        "completion_redirect_url": "/after-paid",
    }

    empty_url = product_service._normalize_completion_redirect_payload(
        {
            "completion_redirect_enabled": True,
            "completion_redirect_url": "",
        },
        {},
    )
    assert empty_url == {"completion_redirect_enabled": True, "completion_redirect_url": ""}

    with pytest.raises(product_service.WeChatPayProductError, match="完成后跳转 URL"):
        product_service._normalize_completion_redirect_payload(
            {
                "completion_redirect_enabled": True,
                "completion_redirect_url": "javascript:alert(1)",
            },
            {},
        )
    with pytest.raises(product_service.WeChatPayProductError, match="完成后跳转 URL"):
        product_service._normalize_completion_redirect_payload(
            {
                "completion_redirect_enabled": True,
                "completion_redirect_url": "//evil.com",
            },
            {},
        )
    with pytest.raises(product_service.WeChatPayProductError, match="完成后跳转 URL"):
        product_service._normalize_completion_redirect_payload(
            {
                "completion_redirect_enabled": True,
                "completion_redirect_url": "data:text/html,evil",
            },
            {},
        )


def test_order_public_payload_completion_redirect_suppresses_lead_qr(monkeypatch):
    monkeypatch.setattr(
        wechat_pay_service,
        "get_completion_redirect_for_product_code",
        lambda product_code: product_service.completion_redirect_projection(
            True,
            "https://example.com/after-paid",
        ),
    )
    monkeypatch.setattr(
        wechat_pay_service,
        "get_lead_qr_for_product_code",
        lambda product_code: pytest.fail("lead_qr must not be resolved when completion redirect is active"),
    )

    payload = wechat_pay_service._order_public_payload(
        {
            "out_trade_no": "WXP_REDIRECT_UNIT",
            "product_code": "prd_redirect_unit",
            "product_name": "跳转商品",
            "amount_total": 9900,
            "status": "paid",
            "trade_state": "SUCCESS",
        }
    )

    assert payload["completion_redirect_enabled"] is True
    assert payload["completion_redirect"]["enabled"] is True
    assert payload["completion_redirect"]["url"] == "https://example.com/after-paid"
    assert payload["completion_action"] == {
        "type": "redirect",
        "redirect_url": "https://example.com/after-paid",
    }
    assert "lead_qr" not in payload


def test_order_public_payload_empty_completion_redirect_keeps_lead_qr(monkeypatch):
    monkeypatch.setattr(
        wechat_pay_service,
        "get_completion_redirect_for_product_code",
        lambda product_code: product_service.completion_redirect_projection(True, ""),
    )
    monkeypatch.setattr(
        wechat_pay_service,
        "get_lead_qr_for_product_code",
        lambda product_code: {"qr_url": "https://example.com/lead-qr.png", "channel_id": 12},
    )

    payload = wechat_pay_service._order_public_payload(
        {
            "out_trade_no": "WXP_EMPTY_REDIRECT_UNIT",
            "product_code": "prd_empty_redirect_unit",
            "product_name": "空跳转商品",
            "amount_total": 9900,
            "status": "paid",
            "trade_state": "SUCCESS",
        }
    )

    assert payload["completion_redirect_enabled"] is True
    assert payload["completion_redirect_url"] == ""
    assert payload["completion_redirect"]["enabled"] is False
    assert payload["completion_action"] == {"type": "lead_qr", "redirect_url": ""}
    assert payload["lead_qr"]["qr_url"] == "https://example.com/lead-qr.png"


def test_order_public_payload_without_redirect_or_lead_qr_keeps_success_url(monkeypatch):
    monkeypatch.setattr(
        wechat_pay_service,
        "get_completion_redirect_for_product_code",
        lambda product_code: product_service.completion_redirect_projection(False, ""),
    )
    monkeypatch.setattr(
        wechat_pay_service,
        "get_lead_qr_for_product_code",
        lambda product_code: {},
    )

    payload = wechat_pay_service._order_public_payload(
        {
            "out_trade_no": "WXP_SUCCESS_URL_UNIT",
            "product_code": "prd_success_url_unit",
            "product_name": "成功页商品",
            "amount_total": 9900,
            "status": "paid",
            "trade_state": "SUCCESS",
            "success_url": "/paid",
        }
    )

    assert payload["completion_action"] == {"type": "default", "redirect_url": ""}
    assert "lead_qr" not in payload
    assert payload["success_url"] == "/paid"


def test_copy_admin_product_payload_preserves_completion_redirect(monkeypatch):
    captured: dict[str, object] = {}
    source = {
        "id": 8,
        "product_code": "prd_copy_source",
        "name": "可复制跳转商品",
        "amount_total": 9900,
        "currency": "CNY",
        "status": "active",
        "enabled": True,
        "cta_text": "立即报名",
        "require_mobile": False,
        "lead_program_id": None,
        "lead_channel_id": None,
        "completion_redirect_enabled": True,
        "completion_redirect_url": "https://example.com/copied-after-paid",
        "metadata_json": {},
    }

    class FakeDb:
        def commit(self):
            captured["committed"] = True

    def fake_insert_product(payload):
        captured["payload"] = payload
        return {**source, **payload, "id": 9, "product_code": "prd_copy_target"}

    monkeypatch.setattr(product_service.product_repo, "get_product_by_id", lambda product_id: source)
    monkeypatch.setattr(product_service.product_repo, "insert_product", fake_insert_product)
    monkeypatch.setattr(product_service.product_repo, "list_product_slices", lambda *args, **kwargs: [])
    monkeypatch.setattr(product_service.product_repo, "replace_product_slices", lambda *args, **kwargs: [])
    monkeypatch.setattr(product_service, "get_admin_product", lambda product_id: captured["payload"])
    monkeypatch.setattr(product_service, "get_db", lambda: FakeDb())

    copied = product_service.copy_admin_product(8, operator="pytest")

    assert copied["completion_redirect_enabled"] is True
    assert copied["completion_redirect_url"] == "https://example.com/copied-after-paid"
    assert captured["committed"] is True


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

    share = product_service.build_admin_product_share(
        product["id"],
        product_url=f"https://crm.example.test/p/{product['product_code']}",
    )

    assert share["url"] == f"https://crm.example.test/p/{product['product_code']}"
    assert share["product_name"] == "可分享商品"
    assert share["qr_data_url"].startswith("data:image/svg+xml;charset=UTF-8,")
    assert "%3Csvg" in share["qr_data_url"]
    assert 'xmlns="http://www.w3.org/2000/svg"' in unquote(share["qr_data_url"])


def test_lead_channel_options_skip_program_summary_dependency(app, client, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import program_service

    _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_channel_direct_options', '渠道所属计划', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    channel = get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_direct_options', '已付费引流渠道码', 'https://example.com/direct-qr.png', 'active')
        RETURNING *
        """,
        (program["id"],),
    ).fetchone()
    get_db().commit()

    def fail_summary_loader(**kwargs):
        raise AssertionError("lead channel options must not depend on program summaries")

    monkeypatch.setattr(program_service, "list_automation_programs", fail_summary_loader)

    items = product_service.list_lead_channel_options()
    option = next(item for item in items if item["channel_id"] == channel["id"])
    assert option["channel_name"] == "已付费引流渠道码"
    assert option["program_name"] == "渠道所属计划"
    assert option["qr_url"] == "https://example.com/direct-qr.png"
    assert option["selectable"] is True


def test_product_can_bind_direct_lead_channel(app, client):
    token = _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_channel_product_bind', '渠道码所属计划', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    channel = get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'product_bind_channel', '支付后渠道码', 'https://example.com/product-bind-qr.png', 'configured')
        RETURNING *
        """,
        (program["id"],),
    ).fetchone()
    get_db().commit()

    product = _create_product(client, token, lead_channel_id=channel["id"])

    assert product["lead_channel_id"] == channel["id"]
    assert product["lead_program_id"] == program["id"]
    assert product_service.get_lead_qr_for_product_code(product["product_code"])["qr_url"] == "https://example.com/product-bind-qr.png"

    cleared = product_service.update_admin_product(product["id"], {"lead_channel_id": None}, operator="pytest")

    assert cleared["lead_channel_id"] is None
    assert cleared["lead_program_id"] is None
    assert product_service.get_lead_qr_for_product_code(product["product_code"]) == {}


def test_product_completion_redirect_create_update_copy_and_validation(app, client):
    token = _login_admin(client)
    product = _create_product(
        client,
        token,
        completion_redirect_enabled=True,
        completion_redirect_url="https://example.com/after-paid",
    )

    detail = product_service.get_admin_product(product["id"])
    assert detail["completion_redirect_enabled"] is True
    assert detail["completion_redirect_url"] == "https://example.com/after-paid"

    updated = product_service.update_admin_product(
        product["id"],
        {
            "name": product["name"],
            "amount_total": product["amount_total"],
            "status": "active",
            "require_mobile": False,
            "cta_text": "立即报名",
            "completion_redirect_enabled": False,
            "completion_redirect_url": "https://example.com/welcome",
            "slices": [],
        },
        operator="pytest",
    )
    assert updated["completion_redirect_enabled"] is False
    assert updated["completion_redirect_url"] == "https://example.com/welcome"
    assert updated["completion_redirect"]["enabled"] is False
    assert updated["completion_action"] == {"type": "default", "redirect_url": ""}

    copied = product_service.copy_admin_product(product["id"], operator="pytest")
    assert copied["completion_redirect_enabled"] is False
    assert copied["completion_redirect_url"] == "https://example.com/welcome"

    with pytest.raises(product_service.WeChatPayProductError, match="完成后跳转 URL"):
        product_service.update_admin_product(
            product["id"],
            {
                "name": product["name"],
                "amount_total": product["amount_total"],
                "status": "active",
                "completion_redirect_enabled": True,
                "completion_redirect_url": "javascript:alert(1)",
            },
            operator="pytest",
        )


def test_product_copy_preserves_enabled_completion_redirect(app, client):
    token = _login_admin(client)
    product = _create_product(
        client,
        token,
        completion_redirect_enabled=True,
        completion_redirect_url="https://example.com/copy-after-paid",
    )

    copied = product_service.copy_admin_product(product["id"], operator="pytest")

    assert copied["completion_redirect_enabled"] is True
    assert copied["completion_redirect_url"] == "https://example.com/copy-after-paid"


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

    detail = product_service.get_admin_product(product["id"])
    assert [item["image_library_id"] for item in detail["slices"]] == [second["id"], first["id"]]
    assert all("image_url" not in item for item in detail["slices"])

    reordered = product_service.reorder_admin_product_slices(
        product["id"],
        {"slice_ids": [detail["slices"][1]["id"], detail["slices"][0]["id"]]},
    )
    assert [item["image_library_id"] for item in reordered["slices"]] == [first["id"], second["id"]]

    public_html = client.get(f"/p/{product['product_code']}").get_data(as_text=True)
    assert public_html.index("YWFhYWFh") < public_html.index("YmJiYmJi")


def test_public_product_and_checkout_preserve_signed_sidebar_context(app, client):
    app.config["AICRM_NEXT_ACTION_TOKEN_SECRET"] = "test-sidebar-product-context-secret"
    token = _login_admin(client)
    product = _create_product(client, token, name="带上下文商品")
    with app.app_context():
        context_token = build_sidebar_product_context_token(
            external_userid="wm_pay_ctx",
            owner_userid="sales_01",
            bind_by_userid="sales_01",
        )

    product_html = client.get(f"/p/{product['product_code']}?ctx={context_token}").get_data(as_text=True)
    checkout_html = client.get(f"/pay/{product['product_code']}?ctx={context_token}", headers=_wechat_headers()).get_data(as_text=True)

    assert f"/pay/{product['product_code']}?ctx=" in product_html
    assert "wm_pay_ctx" not in product_html
    assert context_token in checkout_html
    assert "context_status" in checkout_html
    assert "/api/h5/wechat-pay/oauth/start" in checkout_html


def test_h5_create_order_uses_signed_sidebar_context_not_raw_external_userid(app, client, monkeypatch):
    app.config["AICRM_NEXT_ACTION_TOKEN_SECRET"] = "test-sidebar-product-context-secret"
    captured: dict[str, object] = {}
    with app.app_context():
        context_token = build_sidebar_product_context_token(
            external_userid="wm_signed_pay_ctx",
            owner_userid="sales_01",
            bind_by_userid="sales_02",
        )

    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {
            "openid": "openid_pay_ctx",
            "unionid": "union_pay_ctx",
            "payer_name": "付款用户",
        }

    def fake_create_jsapi_order(**kwargs):
        captured.update(kwargs)
        return {
            "order": {
                "out_trade_no": "WXP_CTX_UNIT",
                "status": "paying",
            },
            "pay_params": {"package": "prepay_id=ctx"},
        }

    monkeypatch.setattr("wecom_ability_service.http.wechat_pay.create_jsapi_order", fake_create_jsapi_order)

    response = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        headers=_wechat_headers(),
        json={
            "product_code": "prd_ctx_unit",
            "ctx": context_token,
            "external_userid": "wm_forged_raw_query",
            "mobile": "138 0013 8000",
            "order_source": "product_checkout",
        },
    )

    assert response.status_code == 200
    assert captured["external_userid"] == "wm_signed_pay_ctx"
    assert captured["owner_userid"] == "sales_01"
    assert captured["bind_by_userid"] == "sales_02"
    assert captured["mobile"] == "13800138000"
    assert captured["context_source"] == "signed_sidebar_product_link"
    assert captured["mobile_source"] == "payload"
    assert captured["request_meta"]["sidebar_product_context"] == {
        "context_status": "valid",
        "context_source": "signed_sidebar_product_link",
        "external_userid_present": True,
        "owner_userid_present": True,
        "mobile_source": "payload",
    }


def test_product_slices_limit_is_ten(app, client):
    token = _login_admin(client)
    images = [_create_image(PNG_A, f"slice-limit-{index}") for index in range(11)]
    with pytest.raises(product_service.WeChatPayProductError, match="最多 10 张"):
        product_service.create_admin_product(
            {
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
            operator="pytest",
        )

    product = _create_product(
        client,
        token,
        slices=[
            {"image_library_id": item["id"], "sort_order": index + 1}
            for index, item in enumerate(images[:10])
        ],
    )

    detail = product_service.get_admin_product(product["id"])
    assert len(detail["slices"]) == 10

    with pytest.raises(product_service.WeChatPayProductError, match="最多 10 张"):
        product_service.update_admin_product(
            product["id"],
            {
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
            operator="pytest",
        )

    with pytest.raises(product_service.WeChatPayProductError, match="最多 10 张"):
        product_service.add_admin_product_slice(product["id"], {"image_library_id": images[-1]["id"]})


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


def test_next_product_admin_share_modal_renders_link_qr_and_download():
    template = (
        REPO_ROOT
        / "aicrm_next"
        / "commerce"
        / "templates"
        / "wechat_products.html"
    ).read_text(encoding="utf-8")

    assert 'id="product-share-modal"' in template
    assert "商品链接" in template
    assert "商品二维码" in template
    assert "保存二维码" in template
    assert "openShareModal(payload.share || {})" in template
    assert 'window.prompt("商品链接"' not in template


def test_next_product_editor_uses_v5_collapsed_modules_and_real_actions():
    template = (
        REPO_ROOT
        / "aicrm_next"
        / "commerce"
        / "templates"
        / "wechat_products.html"
    ).read_text(encoding="utf-8")

    module_titles = ["售卖信息", "页面素材", "购买后动作", "外部推送"]
    positions = [template.index(f"<h2>{title}</h2>") for title in module_titles]
    assert positions == sorted(positions)

    assert 'id="afterActionPanel" hidden' in template
    assert 'id="externalPushPanel" hidden' in template
    assert 'id="afterActionExpand"' in template
    assert 'id="externalPushExpand"' in template
    assert 'id="externalPushEnabled" type="button" role="switch"' not in template
    assert "支付成功外推" not in template
    assert "enabled: Boolean(externalPush.enabled)," in template
    assert "配置购买后动作" not in template
    assert "配置外部推送" not in template
    assert "completionRedirectEnabled" not in template
    assert "completionRedirectLeadHint" not in template
    assert "product_code: productCode" in template
    assert "product: { code: productCode }" in template
    assert 'copyShareLinkBtn' in template
    assert 'openSharePreviewBtn' in template
    assert template.count('id="productToast"') == 1
    assert "商品已保存，外部推送保存失败" in template
    assert "loadShareInfo().catch(() => {})" in template
    assert 'loadShareInfo()' in template
    assert "/api/admin/wechat-pay/products/${encodeURIComponent(product.id)}/share" in template


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


def test_image_library_upload_route_creates_item_for_product_editor(app, client):
    token = _login_admin(client)
    _create_product(client, token)
    response = client.post(
        "/api/admin/image-library/upload",
        data={
            "image": (BytesIO(PNG_A), "slice.png"),
            "name": "商品切片",
            "category": "商品详情",
            "tags": "商品,切片",
        },
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["item"]["id"]
    assert payload["item"]["name"] == "商品切片"
    assert payload["item"]["file_name"] == "slice.png"
    assert payload["item"]["mime_type"] == "image/png"
    assert payload["item"]["category"] == "商品详情"
    assert payload["item"]["tags"] == ["商品", "切片"]


def test_image_library_upload_route_rejects_invalid_file(app, client):
    token = _login_admin(client)
    _create_product(client, token)
    response = client.post(
        "/api/admin/image-library/upload",
        data={"image": (BytesIO(b"not-image"), "slice.txt")},
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert "only JPG/PNG" in payload["error"]


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
    assert row["request_meta_json"]["mobile_binding"]["mobile_masked"] == "138****8000"
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
    assert 'page_state.completion_action.type != "redirect"' in source
    assert "page_state.completion_redirect.enabled" not in source


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


def test_paid_order_completion_redirect_takes_priority_over_lead_qr(app, client):
    token = _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_plan_redirect_priority', '跳转优先计划', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    channel = get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_redirect_priority', '默认渠道', 'https://example.com/redirect-priority-qr.png', 'active')
        RETURNING *
        """,
        (program["id"],),
    ).fetchone()
    get_db().commit()
    product = _create_product(
        client,
        token,
        lead_program_id=program["id"],
        completion_redirect_enabled=True,
        completion_redirect_url="https://example.com/after-paid-priority",
    )
    assert product["lead_channel_id"] == channel["id"]

    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": "WXP_REDIRECT_PRIORITY",
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["name"],
            "amount_total": product["amount_total"],
            "payer_openid": "op_redirect",
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

    paid = client.get(f"/api/h5/wechat-pay/orders/{order['out_trade_no']}").get_json()["order"]
    assert paid["completion_redirect_enabled"] is True
    assert paid["completion_redirect_url"] == "https://example.com/after-paid-priority"
    assert paid["completion_redirect"]["url"] == "https://example.com/after-paid-priority"
    assert paid["completion_action"] == {
        "type": "redirect",
        "redirect_url": "https://example.com/after-paid-priority",
    }
    assert "lead_qr" not in paid

    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_redirect", "payer_name": "已报名用户"}
    html = client.get(f"/pay/{product['product_code']}", headers=_wechat_headers()).get_data(as_text=True)
    assert "completionActionFromOrder" in html
    assert 'setState("报名成功，正在跳转...", "success")' in html
    assert 'id="showLeadQrButton"' not in html


def test_completion_redirect_empty_url_keeps_existing_lead_qr_logic(app, client):
    token = _login_admin(client)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('lead_plan_empty_redirect', '空跳转计划', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    channel = get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_empty_redirect', '默认渠道', 'https://example.com/empty-redirect-qr.png', 'active')
        RETURNING *
        """,
        (program["id"],),
    ).fetchone()
    get_db().commit()
    product = _create_product(
        client,
        token,
        lead_program_id=program["id"],
        completion_redirect_enabled=True,
        completion_redirect_url="",
    )
    assert product["lead_channel_id"] == channel["id"]
    assert product["completion_redirect_enabled"] is True

    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": "WXP_EMPTY_REDIRECT",
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["name"],
            "amount_total": product["amount_total"],
            "payer_openid": "op_empty_redirect",
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

    paid = client.get(f"/api/h5/wechat-pay/orders/{order['out_trade_no']}").get_json()["order"]
    assert paid["completion_redirect"]["enabled"] is False
    assert paid["completion_redirect_url"] == ""
    assert paid["completion_action"] == {"type": "lead_qr", "redirect_url": ""}
    assert paid["lead_qr"]["qr_url"] == "https://example.com/empty-redirect-qr.png"


def test_legacy_catalog_product_api_still_works(app, client, tmp_path):
    _configure_pay(app, tmp_path)

    payload = client.get("/api/h5/wechat-pay/products/legacy_report_v1").get_json()

    assert payload["ok"] is True
    assert payload["product"]["product_code"] == "legacy_report_v1"
    assert payload["product"]["amount_total"] == 9900
    assert payload["product"]["slices"] == []


def test_next_style_public_product_api_alias_is_readonly(app, client, tmp_path):
    _configure_pay(app, tmp_path)

    response = client.get("/api/products/legacy_report_v1")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["product"]["product_code"] == "legacy_report_v1"
    assert payload["product"]["name"] == "历史支付商品"
    assert payload["product"]["amount_total"] == 9900
    assert payload["product"]["slices"] == []


def test_next_style_public_product_api_alias_returns_404_for_missing_product(client):
    response = client.get("/api/products/missing_product")

    assert response.status_code == 404
    assert response.get_json() == {"ok": False, "error": "product_not_configured"}
