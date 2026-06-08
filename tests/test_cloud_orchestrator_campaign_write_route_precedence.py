from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from aicrm_next.cloud_orchestrator.campaigns_write import reset_campaign_write_fixture_state
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


def _assert_next_resolution(samples: list[dict], method: str, path: str) -> None:
    assert _owner_for(samples, method, path) == "next"
    assert _endpoint_for(samples, method, path) == "aicrm_next.cloud_orchestrator.api"


def _assert_next_command_response(response) -> dict:
    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    body = response.json()
    assert body["source_status"] == "next_command"
    assert body["fallback_used"] is False
    assert body["route_owner"] == "ai_crm_next"
    return body


def test_campaign_write_exact_routes_win_over_production_compat_wildcard():
    result = checker.run_check()
    samples = result["resolution_samples"]

    for method, path in [
        ("POST", "/api/admin/cloud-orchestrator/campaigns/batch-start"),
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve"),
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/start"),
        ("PATCH", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps/0"),
    ]:
        _assert_next_resolution(samples, method, path)

    _assert_next_resolution(samples, "POST", "/api/admin/cloud-orchestrator/campaigns/run-due")


def test_campaign_write_requests_use_next_exact_route_without_legacy_forward(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_campaign_read_fixture_state()
    reset_campaign_write_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve",
        json={},
        headers={"Idempotency-Key": "write-precedence-approve"},
    )
    _assert_next_command_response(response)

    samples = checker.run_check()["resolution_samples"]
    for method, path in [
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve"),
        ("POST", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/start"),
        ("PATCH", "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps/0"),
    ]:
        _assert_next_resolution(samples, method, path)


def test_cloud_orchestrator_campaign_routes_have_no_compatibility_facade_headers(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    reset_campaign_read_fixture_state()
    reset_campaign_write_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    requests = [
        client.post(
            "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/approve",
            json={},
            headers={"Idempotency-Key": "write-no-compat-approve"},
        ),
        client.post(
            "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/start",
            json={},
            headers={"Idempotency-Key": "write-no-compat-start"},
        ),
        client.patch(
            "/api/admin/cloud-orchestrator/campaigns/camp_next_read_fixture/steps/0",
            json={"send_time": "10:30"},
            headers={"Idempotency-Key": "write-no-compat-step"},
        ),
    ]

    for response in requests:
        _assert_next_command_response(response)
