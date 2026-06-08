from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import reset_timer_fixture_state
from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def test_timer_exact_routes_resolve_before_production_compat(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_timer_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.options("/api/admin/automation-conversion/jobs/run-due")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    body = response.json()
    assert body["source_status"] == "next_jobs_run_due_plan"
    assert body["fallback_used"] is False


def test_route_resolution_samples_show_timer_next_and_workspace_fallback():
    result = checker.run_check()
    samples = result["resolution_samples"]

    def owner(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["route_owner"]

    def endpoint(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["endpoint_module"]

    assert owner("POST", "/api/admin/automation-conversion/reply-monitor/capture") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/reply-monitor/capture") == "aicrm_next.automation_engine.api"
    assert owner("POST", "/api/admin/automation-conversion/reply-monitor/run-due") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/reply-monitor/run-due") == "aicrm_next.automation_engine.api"
    assert owner("POST", "/api/admin/automation-conversion/jobs/run-due/preview") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/jobs/run-due/preview") == "aicrm_next.automation_engine.api"
    assert owner("POST", "/api/admin/automation-conversion/jobs/run-due") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/jobs/run-due") == "aicrm_next.automation_engine.api"
    assert owner("POST", "/api/admin/automation-conversion/tasks/run-due") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/tasks/run-due") == "aicrm_next.automation_engine.api"
