from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.commerce.repo import reset_commerce_fixture_state
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    reset_commerce_fixture_state()
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AICRM_NEXT_WECHAT_PAY_MODE", "fake")
    monkeypatch.setenv("AICRM_NEXT_ALIPAY_MODE", "fake")
    monkeypatch.setenv("SECRET_KEY", "checkout-api-contract")
    return TestClient(create_app(), raise_server_exceptions=False)


def _checkout_payload() -> dict:
    return {
        "product_code": "test-product",
        "quantity": 1,
        "buyer_identity": {"mobile": "13800138000", "external_userid": "wx_ext_001"},
        "return_url": "/pay/test-product",
    }


def _assert_checkout_contract(response) -> dict:
    payload = response.json()

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert payload["ok"] is True
    assert payload["order_no"].startswith("order_fake_")
    assert payload["amount_cents"] == 12900
    assert payload["fake_payment"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["source_status"] == "next_checkout"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["payment_request_executed"] is False
    assert payload["order_create_executed"] == "local_only"
    assert payload["side_effect_safety"]["payment_request_executed"] is False
    assert payload["side_effect_safety"]["real_external_call_executed"] is False
    assert payload["side_effect_safety"]["order_create_executed"] == "local_only"
    return payload


def test_checkout_wechat_returns_next_fake_payment_contract(monkeypatch) -> None:
    response = _client(monkeypatch).post("/api/checkout/wechat", json=_checkout_payload())
    payload = _assert_checkout_contract(response)

    assert payload["payment_provider"] == "wechat"
    assert payload["adapter_mode"] == "fake"
    assert payload["provider_payload"]["provider"] == "wechat"


def test_checkout_alipay_returns_next_fake_payment_contract(monkeypatch) -> None:
    response = _client(monkeypatch).post("/api/checkout/alipay", json=_checkout_payload())
    payload = _assert_checkout_contract(response)

    assert payload["payment_provider"] == "alipay"
    assert payload["adapter_mode"] == "fake"
    assert payload["provider_payload"]["provider"] == "alipay"


def test_checkout_options_are_next_diagnostics(monkeypatch) -> None:
    client = _client(monkeypatch)

    for path in ["/api/checkout/wechat", "/api/checkout/alipay"]:
        response = client.options(path)
        payload = response.json()
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
        assert payload["side_effect_safety"]["payment_request_executed"] is False
