from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_questionnaire_admin_read_does_not_use_fixture_when_production_data_ready(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://questionnaire:questionnaire@127.0.0.1:1/aicrm_questionnaire")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    response = TestClient(create_app()).get("/api/admin/questionnaires")

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["source_status"] == "production_unavailable"
    assert payload["read_model_status"] == "unavailable"
    assert payload["degraded"] is True
    assert "local_contract_probe" not in str(payload)
    assert "compatibility_facade" not in payload


def test_questionnaire_admin_page_shows_controlled_production_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://questionnaire:questionnaire@127.0.0.1:1/aicrm_questionnaire")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    response = TestClient(create_app()).get("/admin/questionnaires/1")

    assert response.status_code == 503
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "production_unavailable" in response.text
    assert "fallback_used=false" in response.text
