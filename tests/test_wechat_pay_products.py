from __future__ import annotations

import pytest

import aicrm_next.commerce.application as commerce_application
import aicrm_next.public_product.service as public_product_service
from aicrm_next.commerce.application import (
    DeleteProductCommand,
    GetProductQuery,
    SetProductEnabledCommand,
    UpsertProductCommand,
)
from aicrm_next.commerce.dto import ProductUpsertRequest
from aicrm_next.commerce.repo import InMemoryCommerceRepository, reset_commerce_fixture_state
from aicrm_next.shared.errors import ContractError


def _product_payload(**overrides) -> dict:
    payload = {
        "product_code": "next_course_001",
        "title": "Next 私域成交课",
        "description": "Next commerce product fixture",
        "price_cents": 19900,
        "enabled": True,
        "status": "active",
        "page_slug": "next-course-001",
        "buy_button_text": "立即报名",
        "completion_redirect_enabled": False,
        "completion_redirect_url": "",
    }
    payload.update(overrides)
    return payload


def _assert_next_payment_contract(response) -> dict:
    payload = response.json()
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "x-aicrm-compatibility-facade" not in response.headers
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["payment_request_executed"] is False
    return payload


def test_admin_product_api_uses_next_fixture_routes(next_client):
    reset_commerce_fixture_state()

    created = next_client.post("/api/admin/wechat-pay/products", json=_product_payload())
    assert created.status_code == 200
    created_payload = _assert_next_payment_contract(created)
    product = created_payload["product"]
    assert product["product_code"] == "next_course_001"
    assert product["enabled"] is True

    listed = next_client.get("/api/admin/wechat-pay/products")
    assert listed.status_code == 200
    payload = _assert_next_payment_contract(listed)
    assert payload["ok"] is True
    assert "next_course_001" in [item["product_code"] for item in payload["items"]]

    detail = next_client.get(f"/api/admin/wechat-pay/products/{product['id']}")
    assert detail.status_code == 200
    assert _assert_next_payment_contract(detail)["product"]["title"] == "Next 私域成交课"

    updated = next_client.put(
        f"/api/admin/wechat-pay/products/{product['id']}",
        json=_product_payload(title="Next 私域成交课升级版", completion_redirect_enabled=True, completion_redirect_url="/paid"),
    )
    assert updated.status_code == 200
    updated_product = _assert_next_payment_contract(updated)["product"]
    assert updated_product["title"] == "Next 私域成交课升级版"
    assert updated_product["completion_redirect"]["enabled"] is True
    assert updated_product["completion_action"] == {"type": "redirect", "redirect_url": "/paid"}

    disabled = next_client.post(f"/api/admin/wechat-pay/products/{product['id']}/disable")
    assert disabled.status_code == 200
    assert _assert_next_payment_contract(disabled)["product"]["enabled"] is False

    enabled = next_client.post(f"/api/admin/wechat-pay/products/{product['id']}/enable")
    assert enabled.status_code == 200
    assert _assert_next_payment_contract(enabled)["product"]["enabled"] is True

    copied = next_client.post(f"/api/admin/wechat-pay/products/{product['id']}/copy")
    assert copied.status_code == 201
    copied_product = _assert_next_payment_contract(copied)["product"]
    assert copied_product["id"] != product["id"]
    assert copied_product["status"] == "draft"
    assert copied_product["completion_redirect_url"] == "/paid"

    deleted = next_client.delete(f"/api/admin/wechat-pay/products/{copied_product['id']}")
    assert deleted.status_code == 200
    assert _assert_next_payment_contract(deleted)["deleted"] is True


def test_next_product_commands_preserve_delete_and_redirect_contracts():
    repo = InMemoryCommerceRepository()
    created = UpsertProductCommand(repo)(ProductUpsertRequest(**_product_payload(completion_redirect_enabled=True, completion_redirect_url="https://example.com/paid")))["product"]

    assert GetProductQuery(repo)(created["id"])["product"]["completion_redirect"]["url"] == "https://example.com/paid"

    disabled = SetProductEnabledCommand(repo)(created["id"], enabled=False)["product"]
    assert disabled["status"] == "disabled"

    copied = repo.copy_product(created["id"])
    assert copied["status"] == "draft"
    assert copied["completion_redirect_url"] == "https://example.com/paid"

    with pytest.raises(ContractError, match="已有订单"):
        DeleteProductCommand(repo)("prod_000")

    assert DeleteProductCommand(repo)(created["id"])["deleted"] is True


def test_completion_redirect_validation_blocks_unsafe_url():
    repo = InMemoryCommerceRepository()

    with pytest.raises(ContractError, match="completion_redirect_url"):
        UpsertProductCommand(repo)(
            ProductUpsertRequest(
                **_product_payload(
                    product_code="bad_redirect_001",
                    completion_redirect_enabled=True,
                    completion_redirect_url="javascript:alert(1)",
                )
            )
        )


def test_public_product_and_checkout_routes_are_next_owned_and_no_real_payment(next_client, monkeypatch):
    reset_commerce_fixture_state()

    checkout_repo = InMemoryCommerceRepository()
    UpsertProductCommand(checkout_repo)(
        ProductUpsertRequest(
            **_product_payload(
                product_code="test-product-next-fixture",
                title="测试商品",
                description="测试商品",
                price_cents=12900,
                page_slug="test-product-next-fixture",
            )
        )
    )
    monkeypatch.setattr(commerce_application, "build_commerce_repository", lambda: checkout_repo)
    monkeypatch.setattr(public_product_service, "build_commerce_repository", lambda: checkout_repo)

    product = next_client.get("/api/products/test-product")
    assert product.status_code == 200
    assert product.json()["product"]["product_code"] == "test-product"

    page = next_client.get("/p/test-product")
    assert page.status_code == 200
    assert "测试商品" in page.text

    checkout = next_client.post(
        "/api/checkout/wechat",
        json={
            "product_code": "test-product-next-fixture",
            "quantity": 1,
            "buyer_identity": {"mobile": "13800138000", "external_userid": "wx_ext_001", "openid": "op_fixture"},
            "return_url": "/pay/test-product-next-fixture",
        },
    )
    assert checkout.status_code == 200
    payload = checkout.json()
    assert checkout.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert checkout.headers["X-AICRM-Real-External-Call-Executed"] == "false"
    assert checkout.headers["X-AICRM-Payment-Request-Executed"] == "false"
    assert payload["payment_provider"] == "wechat"
    assert payload["amount_cents"] == 12900
    assert payload["fake_payment"] is True
    assert payload["fallback_used"] is False
    assert payload["payment_request_executed"] is False
    assert payload["side_effect_safety"]["real_wechat_pay_executed"] is False
