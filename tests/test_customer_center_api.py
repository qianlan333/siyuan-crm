from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_customer_center_list_and_detail_are_next_read_model(monkeypatch):
    client = _client(monkeypatch)

    listing = client.get("/api/customers")
    detail = client.get("/api/customers/wx_ext_001")

    assert listing.status_code == 200
    assert detail.status_code == 200
    for payload in (listing.json(), detail.json()):
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
        assert payload["source_status"] == "local_contract_probe"
    assert listing.json()["items"][0]["external_userid"] == "wx_ext_001"
    assert detail.json()["customer"]["mobile"] == "13800138000"


def test_customer_center_admin_profile_and_identity_contract(monkeypatch):
    client = _client(monkeypatch)

    profile = client.get("/api/admin/customers/profile?external_userid=wx_ext_001").json()
    resolved = client.get("/api/admin/identity/resolve?external_userid=wx_ext_001").json()
    links = client.get("/api/admin/identity/links/13800138000").json()

    assert profile["profile"]["external_userid"] == "wx_ext_001"
    assert resolved["identity"]["person_id"] == "person_001"
    assert links["links"]["external_userid"] == "wx_ext_001"
    for payload in (profile, resolved, links):
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
