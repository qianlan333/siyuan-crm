from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tests.post_legacy_baseline import assert_no_compatibility_facade, assert_no_legacy_flags, baseline_env


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    baseline_env(monkeypatch)
    return TestClient(create_app())


def _assert_next_json(response, *, source_status: str | None = None) -> dict:
    assert response.status_code < 500
    assert_no_compatibility_facade(response)
    body = response.json()
    assert_no_legacy_flags(body)
    if source_status:
        assert body["source_status"] == source_status
    return body


def test_class_user_management_export_returns_controlled_local_csv(client: TestClient) -> None:
    response = client.get("/api/admin/class-user-management/export?signup_status=signed")

    assert response.status_code == 200
    assert_no_compatibility_facade(response)
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert response.headers["X-AICRM-Real-External-Call-Executed"] == "false"
    assert response.headers["X-AICRM-External-Storage-Executed"] == "false"
    assert "route_owner,fallback_used,real_external_call_executed,export_generated" in response.text
    assert "ai_crm_next,false,false,local_only" in response.text
    assert "Post Legacy Local" in response.text


@pytest.mark.parametrize("method", ("GET", "POST", "OPTIONS"))
def test_class_user_management_export_methods_do_not_500(client: TestClient, method: str) -> None:
    response = client.request(method, "/api/admin/class-user-management/export", json={"signup_status": "lead"})

    assert response.status_code in {200, 204}
    assert response.status_code != 500
    assert_no_compatibility_facade(response)


def test_cloud_orchestrator_audit_returns_empty_read_contract(client: TestClient) -> None:
    response = client.get("/api/admin/cloud-orchestrator/audit?campaign_code=camp&limit=5&cursor=c1")
    body = _assert_next_json(response, source_status="next_cloud_orchestrator_audit")

    assert body["items"] == []
    assert body["count"] == 0
    assert body["limit"] == 5
    assert body["campaign_code"] == "camp"
    assert body["degraded"] is False
    assert body["warnings"] == []


def test_cloud_orchestrator_observability_returns_local_contract(client: TestClient) -> None:
    response = client.get("/api/admin/cloud-orchestrator/observability")
    body = _assert_next_json(response, source_status="next_cloud_orchestrator_observability")

    assert body["health"]["status"] == "ok"
    assert body["metrics"] == {}
    assert body["recent_runs"] == []
    assert body["degraded"] is False


def test_wecom_customer_acquisition_links_read_create_detail_and_sync_are_safe_mode(client: TestClient) -> None:
    read = _assert_next_json(client.get("/api/admin/wecom-customer-acquisition-links"), source_status="next_wecom_customer_acquisition_links")
    assert read["count"] >= 1
    assert read["adapter_mode"] == "real_blocked"
    assert read["wecom_api_called"] is False

    created = _assert_next_json(
        client.post(
            "/api/admin/wecom-customer-acquisition-links",
            json={"name": "Post Legacy Smoke", "description": "safe-mode only"},
            headers={"Idempotency-Key": "post-legacy-wecom-ca-link-create-001"},
        ),
        source_status="next_command",
    )
    assert created["adapter_mode"] == "real_blocked"
    assert created["wecom_api_called"] is False
    assert created["side_effect_plan"]["status"] == "blocked"
    link_id = created["link"]["id"]

    detail = _assert_next_json(client.get(f"/api/admin/wecom-customer-acquisition-links/{link_id}"), source_status="next_wecom_customer_acquisition_links")
    assert detail["link"]["id"] == link_id
    assert detail["wecom_api_called"] is False

    patched = _assert_next_json(
        client.patch(f"/api/admin/wecom-customer-acquisition-links/{link_id}", json={"description": "updated"}),
        source_status="next_command",
    )
    assert patched["link"]["description"] == "updated"
    assert patched["wecom_api_called"] is False

    synced = _assert_next_json(client.post(f"/api/admin/wecom-customer-acquisition-links/{link_id}/sync"), source_status="next_command")
    assert synced["sync_executed"] is False
    assert synced["wecom_api_called"] is False
    assert synced["side_effect_plan"]["status"] == "blocked"


def test_wecom_customer_acquisition_links_unknown_action_is_controlled_410(client: TestClient) -> None:
    response = client.post("/api/admin/wecom-customer-acquisition-links/1/unknown")
    body = response.json()

    assert response.status_code == 410
    assert body["error_code"] == "wecom_customer_acquisition_action_deprecated"
    assert_no_legacy_flags(body)
    assert_no_compatibility_facade(response)
