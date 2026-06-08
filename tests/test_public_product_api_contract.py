from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "public-product-api-test")
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_no_side_effects(payload: dict) -> None:
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["payment_request_executed"] is False
    assert payload["order_create_executed"] is False


def test_public_product_api_known_detail_contract(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/products/test-product")
    payload = response.json()

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert payload["ok"] is True
    assert payload["product"]["product_code"] == "test-product"
    assert payload["checkout"]["status"] == "blocked"
    _assert_no_side_effects(payload)


def test_public_product_api_list_contract(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/products/list")
    payload = response.json()

    assert response.status_code == 200
    assert any(item["product_code"] == "test-product" for item in payload["items"])
    _assert_no_side_effects(payload)


def test_public_product_api_unknown_path_is_controlled_404(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/products/unknown-path-for-smoke")
    payload = response.json()

    assert response.status_code == 404
    assert payload["error_code"] == "product_not_found"
    _assert_no_side_effects(payload)


def test_public_product_api_checkout_like_get_is_blocked(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/products/test-product/checkout")
    payload = response.json()

    assert response.status_code == 410
    assert payload["error_code"] == "public_product_payment_action_blocked"
    _assert_no_side_effects(payload)


def test_public_product_api_write_method_is_blocked(monkeypatch) -> None:
    response = _client(monkeypatch).post("/api/products/test-product", json={})
    payload = response.json()

    assert response.status_code == 410
    assert payload["method"] == "POST"
    assert payload["error_code"] == "public_product_payment_action_blocked"
    _assert_no_side_effects(payload)
