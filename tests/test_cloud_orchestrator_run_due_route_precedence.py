from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from aicrm_next.cloud_orchestrator.run_due import reset_run_due_fixture_state
from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def _owner_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["route_owner"])
    raise AssertionError(f"missing sample {method} {path}")


def _endpoint_for(samples: list[dict], method: str, path: str) -> str:
    for item in samples:
        if item["method"] == method and item["path"] == path:
            return str(item["endpoint_module"])
    raise AssertionError(f"missing sample {method} {path}")


def test_run_due_exact_routes_win_over_production_compat():
    result = checker.run_check()
    samples = result["resolution_samples"]

    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/automation-conversion/jobs/run-due") == "aicrm_next.automation_engine.api"


def test_options_routes_are_next_diagnostics(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_campaign_read_fixture_state()
    reset_run_due_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    for path, source_status in [
        ("/api/admin/cloud-orchestrator/campaigns/run-due", "next_run_due_plan"),
        ("/api/admin/cloud-orchestrator/campaigns/run-due/preview", "next_run_due_preview"),
    ]:
        response = client.options(path)
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        body = response.json()
        assert body["source_status"] == source_status
        assert body["fallback_used"] is False
        assert body["allowed_methods"] == ["POST", "OPTIONS"]
