from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _assert_readonly_ok(payload: dict) -> None:
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["source_status"] in {"local_contract_probe", "identity_contact", "next_read_model"}
    assert payload["read_model_status"] in {"fixture", "identity_contact", "primary", "local_contract_probe", "next_read_model"}


def test_sidebar_readonly_routes_return_next_native_diagnostics() -> None:
    client = _client()

    responses = {
        "customer-context": client.get("/api/sidebar/customer-context?external_userid=wx_ext_001"),
        "profile": client.get("/api/sidebar/profile?external_userid=wx_ext_001"),
        "tags": client.get("/api/sidebar/tags?external_userid=wx_ext_001"),
        "binding-status": client.get("/api/sidebar/binding-status?external_userid=wx_ext_001"),
        "lead-pool": client.get("/api/sidebar/lead-pool/status?external_userid=wx_ext_001"),
        "signup-tags": client.get("/api/sidebar/signup-tags/status?external_userid=wx_ext_001"),
        "marketing-status": client.get("/api/sidebar/marketing-status?external_userid=wx_ext_001"),
    }

    assert {name: response.status_code for name, response in responses.items()} == {
        name: 200 for name in responses
    }
    for response in responses.values():
        _assert_readonly_ok(response.json())
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert "X-AICRM-Compatibility-Facade" not in response.headers

    assert responses["customer-context"].json()["context"]["customer"]["external_userid"] == "wx_ext_001"
    assert responses["profile"].json()["profile"]["external_userid"] == "wx_ext_001"
    assert "付费意向" in responses["tags"].json()["tags"]
    assert responses["binding-status"].json()["is_bound"] is True
    assert responses["lead-pool"].json()["is_wecom_added"] is True
    assert responses["signup-tags"].json()["current_signup_status"] == "trial_9_9"
    assert responses["marketing-status"].json()["marketing_status"]["external_userid"] == "wx_ext_001"


def test_sidebar_readonly_routes_handle_missing_and_unknown_customers() -> None:
    client = _client()

    missing = client.get("/api/sidebar/marketing-status")
    unknown = client.get("/api/sidebar/marketing-status?external_userid=wx_missing_sidebar")

    assert missing.status_code == 400
    assert missing.json()["source_status"] == "input_error"
    assert missing.json()["fallback_used"] is False
    assert unknown.status_code == 404
    assert unknown.json()["source_status"] == "not_found"
    assert unknown.json()["fallback_used"] is False


def test_sidebar_readonly_production_unavailable_is_controlled(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://sidebar-readonly:sidebar-readonly@127.0.0.1:1/aicrm_sidebar")
    client = _client()

    response = client.get("/api/sidebar/customer-context?external_userid=wx_ext_001")

    assert response.status_code == 503
    payload = response.json()
    assert payload["source_status"] == "production_unavailable"
    assert payload["fallback_used"] is False
    assert payload["degraded"] is True

