from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.shared.runtime import require_signing_secret, runtime_health_state


def test_create_app_requires_secret_key_in_production(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("WECHAT_SHOP_CALLBACK_TOKEN", "wechat-shop-token")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_missing_wechat_shop_callback_token_does_not_block_app_startup_but_rejects_callback(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "runtime-production-secret")
    monkeypatch.delenv("WECHAT_SHOP_CALLBACK_TOKEN", raising=False)

    client = TestClient(create_app(), raise_server_exceptions=False)

    health = client.get("/health")
    response = client.post(
        "/api/wechat-shop/notify?signature=bad&timestamp=1777777777&nonce=nonce",
        json={"order_info": {"order_id": "3705115058471208928"}},
    )

    assert health.status_code == 200
    assert health.json()["wechat_shop_callback_token_present"] is False
    assert response.status_code == 403
    assert "token is not configured" in response.text


def test_local_signing_secret_fallback_is_non_production_only(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    assert require_signing_secret("SECRET_KEY", local_fallback="local-secret") == b"local-secret"
    assert runtime_health_state()["secret_key_present"] is False
