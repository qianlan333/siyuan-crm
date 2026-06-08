from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.commerce.repo import reset_commerce_fixture_state
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _client(monkeypatch) -> TestClient:
    reset_commerce_fixture_state()
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("SECRET_KEY", "payment-wildcard-final-no-real")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_payment_final_closeout_responses_do_not_mark_real_execution(monkeypatch) -> None:
    client = _client(monkeypatch)

    responses = [
        client.get("/api/admin/wechat-pay/products"),
        client.get("/api/admin/wechat-pay/unknown-child"),
        client.get("/api/admin/alipay/transactions"),
        client.get("/api/h5/wechat-pay/unknown-child"),
        client.get("/api/h5/alipay/unknown-child"),
    ]

    for response in responses:
        payload = response.json()
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
        assert payload["real_external_call_executed"] is False
        assert payload["payment_request_executed"] is False
        assert payload["provider_signature_verified"] is False
        assert payload["real_refund_executed"] is False


def test_payment_final_source_does_not_enable_real_payment_defaults() -> None:
    source = "\n".join(
        [
            (ROOT / "aicrm_next/commerce/api.py").read_text(encoding="utf-8"),
            (ROOT / "aicrm_next/commerce/application.py").read_text(encoding="utf-8"),
        ]
    )

    for forbidden in (
        "forward_to_legacy_flask",
        "legacy_flask_facade",
        '"real_external_call_executed": True',
        "'real_external_call_executed': True",
        "real_external_call_executed=True",
        '"payment_request_executed": True',
        "'payment_request_executed': True",
        "payment_request_executed=True",
        '"real_wechat_pay_executed": True',
        "'real_wechat_pay_executed': True",
        '"real_alipay_executed": True',
        "'real_alipay_executed': True",
        '"provider_signature_verified": True',
        "'provider_signature_verified': True",
        '"real_refund_executed": True',
        "'real_refund_executed': True",
        "real_enabled default",
        "default real_enabled",
    ):
        assert forbidden not in source
