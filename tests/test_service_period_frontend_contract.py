from __future__ import annotations

import json

from aicrm_next.commerce.repo import reset_commerce_fixture_state
from aicrm_next.public_product import h5_wechat_pay
from aicrm_next.service_period.application import GrantOrRenewEntitlementCommand
from aicrm_next.service_period.repo import reset_service_period_fixture_state


def _reset() -> None:
    reset_commerce_fixture_state()
    reset_service_period_fixture_state()


def _payload(**overrides) -> dict:
    payload = {
        "product_code": "sp_frontend_001",
        "title": "前端周期服务",
        "description": "周期商品前端契约",
        "price_cents": 99900,
        "currency": "CNY",
        "status": "active",
        "duration_days": 90,
        "membership_config_id": "frontend_vip_90d",
        "membership_config_name": "测试会员设置",
    }
    payload.update(overrides)
    return payload


def _create(next_client, **overrides) -> dict:
    response = next_client.post("/api/admin/service-period-products", json=_payload(**overrides))
    assert response.status_code == 201
    return response.json()["product"]


def _paid_order(out_trade_no: str, *, product_code: str, unionid: str, paid_at: str) -> dict:
    return {
        "id": abs(hash(out_trade_no)) % 100000,
        "out_trade_no": out_trade_no,
        "product_code": product_code,
        "product_name": "前端周期服务",
        "amount_total": 99900,
        "currency": "CNY",
        "unionid": unionid,
        "payer_name_snapshot": "前端用户",
        "status": "paid",
        "trade_state": "SUCCESS",
        "paid_at": paid_at,
    }


def test_service_period_admin_list_page_matches_table_contract(next_client) -> None:
    _reset()
    product = _create(next_client)

    response = next_client.get("/admin/service-period-products")
    assert response.status_code == 200
    text = response.text

    assert "周期商品管理" in text
    assert "创建、编辑和上下架周期商品。" in text
    assert "创建周期商品" in text
    for header in ("商品编码", "商品名称", "价格", "状态", "已售卖数量", "更新时间", "操作"):
        assert f"<th>{header}</th>" in text
    assert f"/admin/service-period-products/{product['id']}/data" in text
    assert "999.00 CNY / 90 天" in text
    operation_order = [">编辑<", ">数据<", ">分享<", ">复制<", ">下架<", ">删除<"]
    positions = [text.index(item) for item in operation_order]
    assert positions == sorted(positions)
    for forbidden in ("会员列表", "数据概览", "报名链接", "续费规则", "交易商品信息"):
        assert forbidden not in text


def test_service_period_edit_page_keeps_four_existing_dimensions_only(next_client) -> None:
    _reset()
    product = _create(next_client)

    response = next_client.get(f"/admin/service-period-products/{product['id']}/edit")
    assert response.status_code == 200
    text = response.text

    assert f"编辑周期商品 {product['product_code']}" in text
    for panel in ("sale", "media", "after", "push"):
        assert f'data-service-period-panel="{panel}"' in text
        assert f'data-service-period-panel-content="{panel}"' in text
    for label in ("售卖信息", "页面素材", "购买后动作", "外部推送"):
        assert label in text
    for field in ("商品名称", "商品编码", "价格", "有效期", "绑定会员设置", "商品状态", "商品描述"):
        assert field in text
    assert "保存售卖信息" in text
    assert "保存页面素材" in text
    assert "保存购买后动作" in text
    assert "保存外部推送" in text
    assert "/api/admin/service-period-products/membership-configs" in text
    assert "/api/admin/wechat-pay/products/${encodeURIComponent(tradeId)}/external-push" in text
    assert "image_upload_client.js" in text
    assert "prepareImageForUpload(file)" in text
    assert 'if (mode === "new") body.product_code = productCodeValue;' in text
    assert "formatApiError(payload.detail || payload.error)" in text
    assert "product_code: productCodeValue" not in text
    for forbidden in (
        "购买按钮文案",
        "周期设置",
        "会员设置</span>",
        "未过期续费规则",
        "已过期续费规则",
        "到期后处理",
        "礼包重发",
        "自动续费",
        "多规格",
        "用户端设置",
        "数据分析",
        "开通成功弹窗",
        "续费成功弹窗",
        "重新开通成功文案",
    ):
        assert forbidden not in text


def test_service_period_admin_payloads_omit_inline_slice_image_data(next_client) -> None:
    _reset()
    product = _create(
        next_client,
        product_code="sp_light_slices",
        slices=[
            {"image_library_id": 21, "image_url": "data:image/png;base64,YQ==", "sort_order": 1},
            {"image_library_id": 22, "data_url": "data:image/png;base64,Yg==", "sort_order": 2},
        ],
    )

    listed = next_client.get("/api/admin/service-period-products?limit=100")
    assert listed.status_code == 200
    listed_payload = listed.json()
    listed_text = json.dumps(listed_payload, ensure_ascii=False)
    assert "data:image" not in listed_text
    assert "data_base64" not in listed_text
    listed_product = next(item for item in listed_payload["items"] if item["id"] == product["id"])
    assert "slices" not in (listed_product.get("trade_product") or {})

    detail = next_client.get(f"/api/admin/service-period-products/{product['id']}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    detail_text = json.dumps(detail_payload, ensure_ascii=False)
    assert "data:image" not in detail_text
    assert "data_base64" not in detail_text
    slices = detail_payload["product"]["trade_product"]["slices"]
    assert [item["image_library_id"] for item in slices] == [21, 22]
    assert [item["sort_order"] for item in slices] == [1, 2]
    assert all(not str(item.get("image_url") or "").startswith("data:") for item in slices)

    edit_page = next_client.get(f"/admin/service-period-products/{product['id']}/edit")
    assert edit_page.status_code == 200
    assert "data:image" not in edit_page.text
    assert "data_base64" not in edit_page.text


def test_service_period_data_page_has_only_data_contract(next_client) -> None:
    _reset()
    product = _create(next_client)

    response = next_client.get(f"/admin/service-period-products/{product['id']}/data")
    assert response.status_code == 200
    text = response.text

    assert "前端周期服务数据" in text
    assert "查看有效用户、到期用户和续费订单。" in text
    assert "导出数据" in text
    for label in ("有效用户", "7 天内到期", "续费订单", "累计金额", "会员列表"):
        assert label in text
    for header in ("会员", "状态", "剩余有效期", "到期日", "最近订单", "操作"):
        assert f"<th>{header}</th>" in text
    assert ">查看<" in text
    for forbidden in ("报名链接", "续费规则", "交易商品卡片", "交易商品信息", ">编辑<", "用户报名页", "用户续费页", "管理配置页", "管理详情页"):
        assert forbidden not in text


def test_service_period_public_page_renders_none_active_and_expired_ctas(next_client) -> None:
    _reset()
    _create(next_client, product_code="sp_public_none")

    none_page = next_client.get("/s/sp_public_none")
    assert none_page.status_code == 200
    assert "立即报名" in none_page.text
    assert "开通后获得" in none_page.text
    assert "商品编码" not in none_page.text
    assert "webhook" not in none_page.text.lower()

    _create(next_client, product_code="sp_public_active")
    GrantOrRenewEntitlementCommand()(
        order=_paid_order("SP_PUBLIC_ACTIVE", product_code="sp_public_active", unionid="union_public_active", paid_at="2099-01-01T00:00:00+00:00")
    )
    next_client.cookies.set(h5_wechat_pay.COOKIE_NAME, h5_wechat_pay._signed_blob({"openid": "op_active", "unionid": "union_public_active"}))
    active_page = next_client.get("/s/sp_public_active")
    assert active_page.status_code == 200
    assert "立即续费" in active_page.text
    assert "续费后有效期将继续顺延" in active_page.text

    _create(next_client, product_code="sp_public_expired")
    GrantOrRenewEntitlementCommand()(
        order=_paid_order("SP_PUBLIC_EXPIRED", product_code="sp_public_expired", unionid="union_public_expired", paid_at="2000-01-01T00:00:00+00:00")
    )
    next_client.cookies.set(h5_wechat_pay.COOKIE_NAME, h5_wechat_pay._signed_blob({"openid": "op_expired", "unionid": "union_public_expired"}))
    expired_page = next_client.get("/s/sp_public_expired")
    assert expired_page.status_code == 200
    assert "重新开通" in expired_page.text
    assert "上次到期日" in expired_page.text


def test_service_period_public_page_keeps_draft_slug_in_service_period_context(next_client) -> None:
    _reset()
    _create(next_client, product_code="sp_public_draft", status="draft")

    page = next_client.get("/s/sp_public_draft")
    assert page.status_code == 200
    assert "暂未开放" in page.text
    assert 'button.disabled = true;' in page.text
    assert "payload && payload.ok !== false" in page.text
    assert "questionnaire not found" not in page.text


def test_service_period_membership_configs_contract(next_client) -> None:
    _reset()

    response = next_client.get("/api/admin/service-period-products/membership-configs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["items"] == []
