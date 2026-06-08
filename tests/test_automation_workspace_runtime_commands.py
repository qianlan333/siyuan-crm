from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.workspace_runtime import (
    get_workspace_runtime_audit_events,
    get_workspace_runtime_external_call_attempts,
    get_workspace_runtime_side_effect_plans,
    reset_workspace_runtime_fixture_state,
)
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_workspace_runtime_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_safe_contract(body: dict) -> None:
    assert body["ok"] is True
    assert body["status"] == "planned_blocked"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["adapter_mode"] == "real_blocked"
    assert body["real_external_call_executed"] is False
    assert body["automation_runtime_executed"] is False
    assert body["operation_tasks_executed"] is False
    assert body["bazhuayu_send_executed"] is False
    assert body["wecom_send_executed"] is False
    assert body["processed_count"] == 0
    assert body["sent_count"] == 0
    assert body["failed_count"] == 0
    assert body["side_effect_plan"]["status"] == "blocked"
    assert body["side_effect_plan"]["adapter_mode"] == "real_blocked"
    assert body["external_call_attempt"]["status"] == "blocked"


def test_tasks_run_due_returns_next_safe_mode_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/tasks/run-due",
        json={"program_id": 1},
        headers={"Idempotency-Key": "workspace-tasks-run-due-command"},
    )

    assert response.status_code == 200
    body = response.json()
    _assert_safe_contract(body)
    assert body["source_status"] == "next_automation_tasks_run_due_plan"
    assert body["program_id"] == 1
    assert body["planned_count"] == 1
    assert body["skipped_count"] == 1
    assert body["side_effect_plan"]["effect_type"] == "automation.operation_tasks.run_due"
    assert len(get_workspace_runtime_side_effect_plans()) == 1
    assert len(get_workspace_runtime_external_call_attempts()) == 1
    assert get_workspace_runtime_audit_events()


def test_send_via_bazhuayu_returns_next_safe_mode_plan(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/execution-items/1/send-via-bazhuayu",
        json={},
        headers={"Idempotency-Key": "workspace-send-via-command"},
    )

    assert response.status_code == 200
    body = response.json()
    _assert_safe_contract(body)
    assert body["source_status"] == "next_bazhuayu_dispatch_plan"
    assert body["execution_item_id"] == 1
    assert body["planned_count"] == 1
    assert body["side_effect_plan"]["effect_type"] == "automation.execution_item.send_via_bazhuayu"
    assert body["side_effect_plan"]["requires_approval"] is True


def test_options_and_invalid_program_id_are_controlled(monkeypatch):
    client = _client(monkeypatch)

    tasks_options = client.options("/api/admin/automation-conversion/tasks/run-due")
    assert tasks_options.status_code == 200
    body = tasks_options.json()
    assert body["source_status"] == "next_automation_tasks_run_due_plan"
    assert body["allowed_methods"] == ["POST", "OPTIONS"]
    assert body["fallback_used"] is False
    assert body["operation_tasks_executed"] is False

    outbound_options = client.options("/api/admin/automation-conversion/execution-items/1/send-via-bazhuayu")
    assert outbound_options.status_code == 200
    outbound_body = outbound_options.json()
    assert outbound_body["source_status"] == "next_bazhuayu_dispatch_plan"
    assert outbound_body["execution_item_id"] == 1
    assert outbound_body["bazhuayu_send_executed"] is False

    invalid = client.post("/api/admin/automation-conversion/tasks/run-due", json={"program_id": -1})
    assert invalid.status_code == 400
    invalid_body = invalid.json()
    assert invalid_body["ok"] is False
    assert invalid_body["source_status"] == "next_automation_tasks_run_due_plan"
    assert invalid_body["status"] == "input_error"
    assert "program_id" in invalid_body["error"]
