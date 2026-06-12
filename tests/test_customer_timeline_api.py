from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_customer_timeline_api_uses_next_read_model(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/customers/wx_ext_001/timeline?limit=10")
    payload = response.json()

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["source_status"] == "local_contract_probe"
    assert payload["timeline"]["items"]
