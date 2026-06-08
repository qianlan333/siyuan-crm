from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_public_product_alias_redirects_to_current_product(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "public-product-alias-redirect-test")

    response = TestClient(create_app(), raise_server_exceptions=False).get(
        "/p/prd_20260518095708_9f77db?utm=qr",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/p/subscription_trial_month?utm=qr"
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert response.headers["X-AICRM-Compatibility-Facade"] == "product_code_alias_redirect"
