from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.workspace_runtime import reset_workspace_runtime_fixture_state
from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def test_workspace_runtime_exact_routes_resolve_before_production_compat(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_workspace_runtime_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    tasks = client.options("/api/admin/automation-conversion/tasks/run-due")
    outbound = client.options("/api/admin/automation-conversion/execution-items/1/send-via-bazhuayu")

    assert tasks.status_code == 200
    assert tasks.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert tasks.headers["X-AICRM-Fallback-Used"] == "false"
    assert tasks.json()["source_status"] == "next_automation_tasks_run_due_plan"
    assert outbound.status_code == 200
    assert outbound.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert outbound.json()["source_status"] == "next_bazhuayu_dispatch_plan"


def test_route_resolution_samples_show_workspace_runtime_next_owned():
    result = checker.run_check()
    samples = result["resolution_samples"]

    def owner(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["route_owner"]

    def endpoint(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["endpoint_module"]

    assert owner("POST", "/api/admin/automation-conversion/tasks/run-due") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/tasks/run-due") == "aicrm_next.automation_engine.api"
    assert owner("POST", "/api/admin/automation-conversion/execution-items/123/send-via-bazhuayu") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/execution-items/123/send-via-bazhuayu") == "aicrm_next.automation_engine.api"
