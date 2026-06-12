from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_admin_customer_profile_console_uses_next_profile_routes(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    profile = client.get("/api/admin/customers/profile?external_userid=wx_ext_001")
    tags = client.get("/api/admin/customers/profile/tags?external_userid=wx_ext_001")
    answers = client.get("/api/admin/customers/profile/questionnaire-answers?external_userid=wx_ext_001")
    messages = client.get("/api/admin/customers/profile/messages?external_userid=wx_ext_001")

    for response in (profile, tags, answers, messages):
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        payload = response.json()
        assert payload["route_owner"] == "ai_crm_next"
        assert payload.get("fallback_used", False) is False

    assert profile.json()["profile"]["external_userid"] == "wx_ext_001"
    assert tags.json()["tags"]
