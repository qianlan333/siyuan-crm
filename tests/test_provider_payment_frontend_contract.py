from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "provider-payment-frontend")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_api_docs_surface_lists_provider_notify_return(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/api-docs")

    assert response.status_code == 200
    assert "/api/wechat-pay/notify" in response.text
    assert "/api/alipay/notify" in response.text
    assert "/api/alipay/return" in response.text
