from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_cloud_orchestrator_observability_api_returns_empty_metrics_contract(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "cloud-observability-api-test")
    client = TestClient(create_app())

    response = client.get("/api/admin/cloud-orchestrator/observability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["source_status"] == "next_cloud_orchestrator_observability"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["health"]["status"] == "ok"
    assert payload["recent_runs"] == []


def test_cloud_orchestrator_audit_api_preserves_query_shape(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "cloud-audit-api-test")
    client = TestClient(create_app())

    response = client.get("/api/admin/cloud-orchestrator/audit?campaign_code=camp&limit=5&cursor=c1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["source_status"] == "next_cloud_orchestrator_audit"
    assert payload["campaign_code"] == "camp"
    assert payload["limit"] == 5
    assert payload["cursor"] == "c1"
    assert payload["items"] == []
