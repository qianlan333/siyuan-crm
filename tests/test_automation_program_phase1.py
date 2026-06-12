from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.repo import reset_automation_fixture_state
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_automation_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_program_list_and_setup_routes_are_next_owned(monkeypatch) -> None:
    client = _client(monkeypatch)

    programs = client.get("/api/admin/automation-conversion/programs")
    assert programs.status_code == 200
    assert programs.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert programs.headers["X-AICRM-Fallback-Used"] == "false"
    first = programs.json()["items"][0]["program"]

    setup = client.get(f"/admin/automation-conversion/programs/{first['id']}/setup")
    assert setup.status_code == 200
    assert setup.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert setup.headers.get("X-AICRM-Fallback-Used", "false") == "false"
    assert "automation" in setup.text.lower()


def test_program_operation_task_api_stays_next_native(monkeypatch) -> None:
    client = _client(monkeypatch)
    program = client.get("/api/admin/automation-conversion/programs").json()["items"][0]["program"]

    response = client.get(f"/api/admin/automation-conversion/programs/{program['id']}/setup/operation-tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["route_owner"] == "ai_crm_next"
    assert payload.get("fallback_used", False) is False
    assert isinstance(payload["tasks"], list)
