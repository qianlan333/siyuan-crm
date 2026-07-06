from __future__ import annotations

from pathlib import Path

from conftest import make_client


def test_admin_dashboard_route_returns_legacy_shell() -> None:
    response = make_client().get("/admin")
    assert response.status_code == 200
    assert "客户管理后台" in response.text
    assert "系统概况" in response.text


def test_admin_user_ops_ui_returns_current_admin_shell() -> None:
    response = make_client().get("/admin/user-ops/ui")
    assert response.status_code == 200
    text = response.text
    for expected in ["客户激活 / 客户列表", "客户列表", "群运营计划", "admin-shell", "admin-nav"]:
        assert expected in text
    for forbidden in ["New UI", "redesign", "TODO replace old frontend"]:
        assert forbidden not in text


def test_admin_customers_route_returns_current_admin_shell() -> None:
    response = make_client().get("/admin/customers")
    assert response.status_code == 200
    assert "客户列表" in response.text
    assert "客户激活 / 客户列表" in response.text
    assert "admin-shell" in response.text
    assert "admin-nav" in response.text
    for forbidden in ["New UI", "redesign", "TODO replace old frontend", "partial shell", "new dashboard placeholder"]:
        assert forbidden not in response.text


def test_legacy_static_admin_console_css_is_served() -> None:
    response = make_client().get("/static/admin_console/admin_console.css")
    assert response.status_code == 200
    assert "admin-shell" in response.text


def test_commerce_and_media_admin_routes_return_legacy_shells() -> None:
    client = make_client()
    for path, expected in [
        ("/admin/wechat-pay/products", "商品管理"),
        ("/admin/wechat-pay/transactions", "微信支付交易管理"),
        ("/admin/alipay/transactions", "支付宝交易管理"),
        ("/admin/image-library", "图片素材库"),
        ("/admin/attachment-library", "附件素材库"),
        ("/admin/miniprogram-library", "小程序素材库"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert expected in response.text
        for forbidden in ["New UI", "redesign", "TODO replace old frontend", "experimental replacement UI"]:
            assert forbidden not in response.text


def test_wechat_transaction_admin_is_next_native_surface() -> None:
    response = make_client().get("/admin/wechat-pay/transactions")
    assert response.status_code == 200
    text = response.text
    assert 'data-next-commerce-admin="wechat-transactions"' in text
    assert "admin-shell" in text
    assert "admin-nav" in text
    assert "群运营计划" in text
    assert "微信支付交易管理" in text
    assert "导出筛选结果" in text
    assert "/api/admin/wechat-pay/orders" in text
    assert 'class="layout"' not in text
    assert 'class="sidebar"' not in text
    assert "心流商业客户管理" not in text
    assert "生产 wechat_pay_orders 只读列表" not in text
    assert "production_postgres" not in text
    detail = make_client().get("/admin/wechat-pay/transactions/order_masked_001")
    assert detail.status_code == 200
    assert "admin-shell" in detail.text
    assert "申请退款" in detail.text
    assert "再次完整输入微信单号" in detail.text
    assert "群运营计划" in detail.text


def test_media_library_routes_return_restored_card_templates() -> None:
    client = make_client()

    image_response = client.get("/admin/image-library")
    assert image_response.status_code == 200
    assert 'id="il-open-upload"' in image_response.text
    assert "图片素材列表" not in image_response.text
    assert "real-data-table" not in image_response.text

    miniprogram_response = client.get("/admin/miniprogram-library")
    assert miniprogram_response.status_code == 200
    assert 'id="mp-open-create"' in miniprogram_response.text
    assert "小程序素材列表" not in miniprogram_response.text
    assert "real-data-table" not in miniprogram_response.text

    attachment_response = client.get("/admin/attachment-library")
    assert attachment_response.status_code == 200
    assert 'id="al-open-upload"' in attachment_response.text
    assert "上传附件" in attachment_response.text
    assert "real-data-table" not in attachment_response.text


def test_admin_channels_route_returns_first_level_channel_center() -> None:
    response = make_client().get("/admin/channels")
    assert response.status_code == 200
    text = response.text
    assert "渠道码中心" in text
    assert "普通二维码" in text
    assert "企微获客助手链接" in text
    for forbidden in ["New UI", "redesign", "TODO replace old frontend", "experimental replacement UI"]:
        assert forbidden not in text


def test_user_ops_frontend_adapter_stubs_exist() -> None:
    client = make_client()
    assert client.get("/api/admin/miniprogram-library").json()["ok"] is True
    record_payload = client.get("/api/admin/user-ops/send-records").json()
    record_id = record_payload["items"][0]["record_id"]
    assert client.get(f"/api/admin/user-ops/send-records/{record_id}").json()["ok"] is True
    assert client.post(f"/api/admin/user-ops/send-records/{record_id}/refresh").json()["ok"] is True
    assert client.get("/api/admin/user-ops/export").json()["status"] == "stubbed"


def test_api_contracts_do_not_mark_do_not_disturb_implemented() -> None:
    text = Path("docs/api_contracts.md").read_text(encoding="utf-8")
    marker = "POST /api/admin/user-ops/do-not-disturb"
    assert marker in text
    section = text[text.index(marker) : text.index("### `POST /api/admin/user-ops/batch-send/preview`")]
    assert "implemented" not in section.lower()
    assert any(status in section.lower() for status in ["stubbed", "contract_ready", "partial"])
