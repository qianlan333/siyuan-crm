from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.workspace_runtime import get_workspace_runtime_side_effect_plans, reset_workspace_runtime_fixture_state
from aicrm_next.main import create_app


def test_workspace_runtime_idempotency_reuses_command_result(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_workspace_runtime_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)
    headers = {"Idempotency-Key": "same-workspace-runtime-key"}

    first = client.post("/api/admin/automation-conversion/tasks/run-due", json={"program_id": 1}, headers=headers)
    second = client.post("/api/admin/automation-conversion/tasks/run-due", json={"program_id": 2}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["command_id"] == second.json()["command_id"]
    assert first.json()["program_id"] == 1
    assert second.json()["program_id"] == 1
    assert len(get_workspace_runtime_side_effect_plans()) == 1
