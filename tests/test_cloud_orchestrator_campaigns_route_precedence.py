from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
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


def test_campaign_read_exact_routes_win_over_production_compat():
    result = checker.run_check()
    samples = result["resolution_samples"]

    paths = [
        "/api/admin/cloud-orchestrator/campaigns",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps",
    ]
    for path in paths:
        assert _owner_for(samples, "GET", path) == "next"
        assert _endpoint_for(samples, "GET", path) == "aicrm_next.cloud_orchestrator.api"

    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/batch-start") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/batch-start") == "aicrm_next.cloud_orchestrator.api"
    for method, path in [
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve"),
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/start"),
        ("PATCH", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps/0"),
    ]:
        assert _owner_for(samples, method, path) == "next"
        assert _endpoint_for(samples, method, path) == "aicrm_next.cloud_orchestrator.api"
    assert _owner_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "next"
    assert _endpoint_for(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due") == "aicrm_next.cloud_orchestrator.api"
    for item in samples:
        if item["method"] == "GET" and item["path"].startswith("/api/admin/cloud-orchestrator/campaigns"):
            assert item["manifest_production_behavior"] == "next_exact"
            assert item["manifest_current_runtime_owner"] == "next"
            assert item["route_owner"] == "next"


def test_campaign_read_requests_do_not_touch_legacy_forward(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_campaign_read_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    for path in [
        "/api/admin/cloud-orchestrator/campaigns",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/members",
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert response.headers["X-AICRM-Fallback-Used"] == "false"
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        body = response.json()
        assert body["source_status"] == "next_cloud_orchestrator_campaign_read"
        assert body["fallback_used"] is False
        assert body["route_owner"] == "ai_crm_next"
