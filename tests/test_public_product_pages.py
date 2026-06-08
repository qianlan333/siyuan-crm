from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "public-product-pages-test")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_public_product_page_renders_next_display_contract(monkeypatch) -> None:
    response = _client(monkeypatch).get("/p/test-product")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert "测试商品" in response.text
    assert "/pay/test-product" in response.text
    assert "不创建订单" not in response.text
    assert "商品编码" not in response.text
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_public_product_page_unknown_path_is_controlled_404(monkeypatch) -> None:
    response = _client(monkeypatch).get("/p/unknown-path-for-smoke")

    assert response.status_code == 404
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert "商品不存在" in response.text


def test_public_product_page_options_is_next_owned(monkeypatch) -> None:
    response = _client(monkeypatch).options("/p/test-product")

    assert response.status_code == 200
    assert response.json()["allowed_methods"] == ["GET", "HEAD", "OPTIONS"]
    assert response.json()["fallback_used"] is False
