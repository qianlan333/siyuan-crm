from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.member_actions import reset_member_actions_fixture_state
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_member_actions_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_member_detail_returns_next_read_model(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/admin/automation-conversion/member?external_contact_id=wx_ext_001")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    body = response.json()
    assert body["ok"] is True
    assert body["source_status"] == "next_automation_member_read"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["detail"]["member"]["external_contact_id"] == "wx_ext_001"
    assert body["detail"]["actions"]["put_in_pool"]["enabled"] is True


def test_member_detail_missing_identity_is_controlled_400(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/admin/automation-conversion/member")

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["source_status"] == "next_automation_member_read"
    assert body["fallback_used"] is False
    assert "external_contact_id or phone" in body["error"]


def test_member_detail_head_is_next_owned(monkeypatch):
    client = _client(monkeypatch)

    response = client.head("/api/admin/automation-conversion/member?external_contact_id=wx_ext_001")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
