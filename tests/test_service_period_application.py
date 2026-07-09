from __future__ import annotations

import inspect
from datetime import datetime, timezone

from aicrm_next.commerce.repo import PostgresCommerceRepository, reset_commerce_fixture_state
from aicrm_next.service_period.application import (
    CreateServicePeriodProductCommand,
    ExpireDueEntitlementsCommand,
    GrantOrRenewEntitlementCommand,
)
from aicrm_next.service_period.dto import ServicePeriodProductCreateRequest
from aicrm_next.service_period.repo import build_service_period_repository, reset_service_period_fixture_state


def _reset() -> None:
    reset_commerce_fixture_state()
    reset_service_period_fixture_state()


def _payload(**overrides):
    payload = {
        "product_code": "sp_course_001",
        "title": "周期课服务",
        "description": "周期商品 fixture",
        "price_cents": 19900,
        "currency": "CNY",
        "status": "active",
        "duration_days": 30,
        "membership_config_id": "vip_30d",
        "membership_config_name": "30 天会员",
    }
    payload.update(overrides)
    return payload


def _paid_order(out_trade_no: str, *, product_code: str = "sp_course_001", unionid: str = "union_sp_001", paid_at: str = "2099-01-01T00:00:00+00:00") -> dict:
    return {
        "id": abs(hash(out_trade_no)) % 100000,
        "out_trade_no": out_trade_no,
        "product_code": product_code,
        "product_name": "周期课服务",
        "amount_total": 19900,
        "currency": "CNY",
        "unionid": unionid,
        "payer_name_snapshot": "服务期用户",
        "status": "paid",
        "trade_state": "SUCCESS",
        "paid_at": paid_at,
        "metadata_json": {"payer_identity": {"mobile": "13800138000", "external_userid": "wm_sp_001"}},
    }


def test_create_update_copy_disable_delete_facade(next_client) -> None:
    _reset()

    created = next_client.post("/api/admin/service-period-products", json=_payload())
    assert created.status_code == 201
    product = created.json()["product"]
    assert product["product_code"] == "sp_course_001"
    assert product["duration_days"] == 30
    assert product["membership_config_id"] == "vip_30d"
    assert product["trade_product"]["buy_button_text"] == "立即报名"

    listed = next_client.get("/api/admin/service-period-products")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == product["id"]

    updated = next_client.put(
        f"/api/admin/service-period-products/{product['id']}",
        json={"title": "周期课服务升级版", "price_cents": 29900, "duration_days": 60, "membership_config_name": "60 天会员"},
    )
    assert updated.status_code == 200
    updated_product = updated.json()["product"]
    assert updated_product["title"] == "周期课服务升级版"
    assert updated_product["price_cents"] == 29900
    assert updated_product["duration_days"] == 60

    copied = next_client.post(f"/api/admin/service-period-products/{product['id']}/copy")
    assert copied.status_code == 201
    copied_product = copied.json()["product"]
    assert copied_product["status"] == "draft"
    assert copied_product["enabled"] is False
    assert copied_product["duration_days"] == 60
    assert copied_product["membership_config_name"] == "60 天会员"

    disabled = next_client.post(f"/api/admin/service-period-products/{product['id']}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["product"]["enabled"] is False

    stats = next_client.get(f"/api/admin/service-period-products/{product['id']}/stats")
    assert stats.status_code == 200
    assert stats.json()["active_user_count"] == 0

    members = next_client.get(f"/api/admin/service-period-products/{product['id']}/members")
    assert members.status_code == 200
    assert members.json()["items"] == []

    share = next_client.get(f"/api/admin/service-period-products/{product['id']}/share")
    assert share.status_code == 200
    assert "/s/sp_course_001" in share.json()["share"]["url"]


def test_service_period_trade_product_is_hidden_from_regular_product_management(next_client) -> None:
    _reset()

    regular = next_client.post(
        "/api/admin/wechat-pay/products",
        json={
            "product_code": "regular_visible_001",
            "title": "普通商品可见",
            "description": "普通商品管理可见 fixture",
            "price_cents": 9900,
            "currency": "CNY",
            "status": "active",
            "enabled": True,
            "page_slug": "regular-visible-001",
        },
    )
    assert regular.status_code == 200

    created = next_client.post(
        "/api/admin/service-period-products",
        json=_payload(product_code="sp_hidden_regular", title="周期商品不进入普通管理"),
    )
    assert created.status_code == 201
    service_product = created.json()["product"]

    regular_list = next_client.get("/api/admin/wechat-pay/products?limit=100")
    assert regular_list.status_code == 200
    regular_codes = [item["product_code"] for item in regular_list.json()["items"]]
    assert "regular_visible_001" in regular_codes
    assert "sp_hidden_regular" not in regular_codes

    regular_page = next_client.get("/admin/wechat-pay/products")
    assert regular_page.status_code == 200
    assert "regular_visible_001" in regular_page.text
    assert "sp_hidden_regular" not in regular_page.text

    service_list = next_client.get("/api/admin/service-period-products?limit=100")
    assert service_list.status_code == 200
    service_codes = [item["product_code"] for item in service_list.json()["items"]]
    assert "sp_hidden_regular" in service_codes

    trade_detail = next_client.get(f"/api/admin/wechat-pay/products/{service_product['trade_product_id']}")
    assert trade_detail.status_code == 200
    assert trade_detail.json()["product"]["product_code"] == "sp_hidden_regular"


def test_postgres_regular_product_list_filters_service_period_trade_products() -> None:
    source = inspect.getsource(PostgresCommerceRepository.list_products)
    assert "service_period_products sp" in source
    assert "sp.trade_product_id = p.id" in source
    assert "NOT EXISTS" in source


def test_update_service_period_product_persists_page_slices(next_client) -> None:
    _reset()
    created = next_client.post("/api/admin/service-period-products", json=_payload(product_code="sp_course_slices"))
    assert created.status_code == 201
    product = created.json()["product"]
    image_id = 11

    updated = next_client.put(
        f"/api/admin/service-period-products/{product['id']}",
        json={
            "title": product["title"],
            "duration_days": product["duration_days"],
            "membership_config_id": product["membership_config_id"],
            "membership_config_name": product["membership_config_name"],
            "slices": [{"image_library_id": image_id, "sort_order": 1}],
        },
    )

    assert updated.status_code == 200, updated.text
    slices = updated.json()["product"]["trade_product"]["slices"]
    assert [item["image_library_id"] for item in slices] == [image_id]

    detail = next_client.get(f"/api/admin/service-period-products/{product['id']}")
    assert detail.status_code == 200
    assert [item["image_library_id"] for item in detail.json()["product"]["trade_product"]["slices"]] == [image_id]


def test_public_state_and_page_use_service_period_slug(next_client) -> None:
    _reset()
    CreateServicePeriodProductCommand()(ServicePeriodProductCreateRequest(**_payload(product_code="sp_public_001")))

    state = next_client.get("/api/h5/service-period-products/sp_public_001")
    assert state.status_code == 200
    payload = state.json()
    assert payload["product"]["duration_days"] == 30
    assert payload["entitlement"]["status"] == "none"
    assert payload["cta_text"] == "立即报名"
    assert payload["create_order_url"] == "/api/h5/service-period-products/sp_public_001/wechat-pay/jsapi/orders"

    page = next_client.get("/s/sp_public_001")
    assert page.status_code == 200
    assert 'data-route-owner="ai_crm_next"' in page.text
    assert "周期课服务" in page.text


def test_draft_service_period_slug_renders_owned_preview_without_payment(next_client) -> None:
    _reset()
    CreateServicePeriodProductCommand()(ServicePeriodProductCreateRequest(**_payload(product_code="sp_public_draft", status="draft")))

    state = next_client.get("/api/h5/service-period-products/sp_public_draft")
    assert state.status_code == 404

    page = next_client.get("/s/sp_public_draft")
    assert page.status_code == 200
    assert 'data-route-owner="ai_crm_next"' in page.text
    assert "周期课服务" in page.text
    assert "暂未开放" in page.text
    assert "questionnaire not found" not in page.text

    order = next_client.post("/api/h5/service-period-products/sp_public_draft/wechat-pay/jsapi/orders", json={})
    assert order.status_code == 404


def test_grant_or_renew_entitlement_rules_are_idempotent() -> None:
    _reset()
    product = CreateServicePeriodProductCommand()(ServicePeriodProductCreateRequest(**_payload()))["product"]
    grant = GrantOrRenewEntitlementCommand()

    first = grant(order=_paid_order("SP_ORDER_1"))
    assert first["event_type"] == "activated"
    assert first["entitlement"]["start_at"].startswith("2099-01-01T00:00:00")
    assert first["entitlement"]["end_at"].startswith("2099-01-31T00:00:00")
    assert first["entitlement"]["renewal_count"] == 0

    renewed = grant(order=_paid_order("SP_ORDER_2", paid_at="2099-01-02T00:00:00+00:00"))
    assert renewed["event_type"] == "renewed"
    assert renewed["entitlement"]["end_at"].startswith("2099-03-02T00:00:00")
    assert renewed["entitlement"]["renewal_count"] == 1

    idempotent = grant(order=_paid_order("SP_ORDER_2", paid_at="2099-01-02T00:00:00+00:00"))
    assert idempotent["idempotent"] is True
    entitlement = build_service_period_repository().entitlement_for_unionid(product["id"], "union_sp_001")
    assert entitlement["end_at"].startswith("2099-03-02T00:00:00")


def test_expired_reactivation_missing_unionid_and_due_expiry() -> None:
    _reset()
    product = CreateServicePeriodProductCommand()(ServicePeriodProductCreateRequest(**_payload(product_code="sp_expire_001")))["product"]
    grant = GrantOrRenewEntitlementCommand()

    old = grant(order=_paid_order("SP_OLD", product_code="sp_expire_001", paid_at="2000-01-01T00:00:00+00:00"))
    assert old["event_type"] == "activated"
    expired = ExpireDueEntitlementsCommand()(now=datetime(2000, 2, 1, tzinfo=timezone.utc))
    assert expired["expired_count"] == 1

    reopened = grant(order=_paid_order("SP_REOPEN", product_code="sp_expire_001", paid_at="2099-04-01T00:00:00+00:00"))
    assert reopened["event_type"] == "activated"
    assert reopened["entitlement"]["start_at"].startswith("2099-04-01T00:00:00")
    assert reopened["entitlement"]["renewal_count"] == 1

    missing = grant(order=_paid_order("SP_MISSING_UNION", product_code="sp_expire_001", unionid=""))
    assert missing["reason"] == "missing_unionid"
    assert missing["event"]["event_type"] == "grant_failed_missing_unionid"
