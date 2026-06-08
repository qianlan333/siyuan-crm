from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.sidebar_write import get_sidebar_write_audit_events


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app())


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_command", "expected_write_status"),
    [
        (
            "post",
            "/api/sidebar/bind-mobile",
            {"external_userid": "wx_ext_002", "mobile": "13800138123"},
            "sidebar.bind_mobile",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/lead-pool/upsert-class-term",
            {"external_userid": "wx_ext_001", "class_term": "term-2026-06", "status": "active"},
            "sidebar.upsert_lead_pool_class_term",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/signup-tags/mark",
            {"external_userid": "wx_ext_001", "tag_name": "trial-active", "marked": True},
            "sidebar.mark_signup_tag",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/marketing-status/set-followup-segment",
            {"external_userid": "wx_ext_001", "segment": "high_intent"},
            "sidebar.set_followup_segment",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/marketing-status/mark-enrolled",
            {"external_userid": "wx_ext_001"},
            "sidebar.mark_enrolled",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/marketing-status/unmark-enrolled",
            {"external_userid": "wx_ext_001"},
            "sidebar.unmark_enrolled",
            "updated",
        ),
        (
            "put",
            "/api/sidebar/v2/profile",
            {"external_userid": "wx_ext_001", "remark": "followup ready"},
            "sidebar.update_profile",
            "updated",
        ),
        (
            "post",
            "/api/sidebar/v2/materials/send",
            {"external_userid": "wx_ext_001", "material_id": "mat-001"},
            "sidebar.plan_material_send",
            "planned",
        ),
    ],
)
def test_sidebar_write_routes_execute_next_commandbus(
    client: TestClient,
    method: str,
    path: str,
    payload: dict,
    expected_command: str,
    expected_write_status: str,
) -> None:
    response = getattr(client, method)(path, json=payload, headers={"Idempotency-Key": f"test-{path}"})

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    body = response.json()
    assert body["ok"] is True
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["source_status"] == "next_command"
    assert body["command_name"] == expected_command
    assert body["write_model_status"] == expected_write_status
    assert body["audit_recorded"] is True
    assert body["real_external_call_executed"] is False
    assert body["command_id"]

    audit_events = get_sidebar_write_audit_events()
    assert any(event["command_id"] == body["command_id"] for event in audit_events)


def test_sidebar_write_routes_return_controlled_errors(client: TestClient) -> None:
    missing_external = client.post("/api/sidebar/bind-mobile", json={"mobile": "13800138123"})
    assert missing_external.status_code == 400
    assert missing_external.json()["source_status"] == "input_error"
    assert missing_external.json()["fallback_used"] is False

    missing_payload = client.post("/api/sidebar/bind-mobile", json={"external_userid": "wx_ext_001"})
    assert missing_payload.status_code == 400
    assert missing_payload.json()["source_status"] == "input_error"

    unknown_customer = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wx_ext_missing", "mobile": "13800138123"},
    )
    assert unknown_customer.status_code == 404
    assert unknown_customer.json()["source_status"] == "not_found"
    assert unknown_customer.json()["fallback_used"] is False


def test_sidebar_write_production_unavailable_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://sidebar-write:sidebar-write@127.0.0.1:1/aicrm_sidebar")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")

    client = TestClient(create_app())
    response = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wx_ext_001", "mobile": "13800138123"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["source_status"] == "production_unavailable"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
