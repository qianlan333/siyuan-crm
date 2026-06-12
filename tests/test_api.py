from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_questionnaire_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_next_response(response) -> dict:
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    payload = response.json()
    assert payload["route_owner"] == "ai_crm_next"
    assert payload.get("fallback_used", False) is False
    return payload


def test_questionnaire_sidebar_customer_api_contracts_are_next_owned(monkeypatch):
    client = _client(monkeypatch)

    questionnaire = _assert_next_response(client.get("/api/admin/questionnaires/1"))
    h5 = _assert_next_response(client.get("/api/h5/questionnaires/hxc-activation-v1"))
    sidebar = _assert_next_response(client.get("/api/sidebar/customer-context?external_userid=wx_ext_001"))
    customers = _assert_next_response(client.get("/api/customers?limit=5"))
    detail = _assert_next_response(client.get("/api/customers/wx_ext_001"))

    assert questionnaire["questionnaire"]["slug"] == "hxc-activation-v1"
    assert h5["questionnaire"]["slug"] == "hxc-activation-v1"
    assert sidebar["context"]["customer"]["external_userid"] == "wx_ext_001"
    assert customers["customers"]
    assert detail["customer"]["external_userid"] == "wx_ext_001"


def test_identity_and_sidebar_binding_contracts_are_next_owned(monkeypatch):
    client = _client(monkeypatch)

    identity = _assert_next_response(client.get("/api/admin/identity/resolve?external_userid=wx_ext_001"))
    binding = _assert_next_response(client.get("/api/sidebar/contact-binding-status?external_userid=wx_ext_001"))

    assert identity["identity"]["external_userid"] == "wx_ext_001"
    assert binding["is_bound"] is True
    assert binding["mobile"] == "13800138000"
