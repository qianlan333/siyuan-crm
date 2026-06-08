from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.member_actions import reset_member_actions_fixture_state
from aicrm_next.main import create_app
from tools import check_production_route_resolution as checker


def test_member_action_exact_routes_resolve_before_production_compat(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_member_actions_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    detail = client.get("/api/admin/automation-conversion/member?external_contact_id=wx_ext_001")
    action = client.options("/api/admin/automation-conversion/member/put-in-pool")
    push = client.post("/api/admin/automation-conversion/member/push-openclaw", json={"external_contact_id": "wx_ext_001"})

    assert detail.status_code == 200
    assert detail.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert detail.json()["source_status"] == "next_automation_member_read"
    assert action.status_code == 200
    assert action.headers["X-AICRM-Fallback-Used"] == "false"
    assert push.status_code == 200
    assert push.json()["side_effect_plan"]["adapter_name"] == "openclaw"
    assert push.json()["openclaw_push_executed"] is False


def test_route_resolution_samples_show_member_actions_next_owned():
    result = checker.run_check()
    samples = result["resolution_samples"]

    def owner(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["route_owner"]

    def endpoint(method: str, path: str) -> str:
        return next(item for item in samples if item["method"] == method and item["path"] == path)["endpoint_module"]

    assert owner("GET", "/api/admin/automation-conversion/member") == "next"
    assert endpoint("GET", "/api/admin/automation-conversion/member") == "aicrm_next.automation_engine.api"
    assert owner("POST", "/api/admin/automation-conversion/member/put-in-pool") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/member/put-in-pool") == "aicrm_next.automation_engine.api"
    assert owner("POST", "/api/admin/automation-conversion/member/push-openclaw") == "next"
    assert endpoint("POST", "/api/admin/automation-conversion/member/push-openclaw") == "aicrm_next.automation_engine.api"
