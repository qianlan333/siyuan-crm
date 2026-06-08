from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.workspace_runtime import reset_workspace_runtime_fixture_state
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _joined(*parts: str) -> str:
    return "".join(parts)


def test_workspace_runtime_routes_return_no_real_side_effect_flags(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_workspace_runtime_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    cases = (
        ("/api/admin/automation-conversion/tasks/run-due", {"program_id": 1}, "operation_tasks_executed"),
        ("/api/admin/automation-conversion/execution-items/1/send-via-bazhuayu", {}, "bazhuayu_send_executed"),
    )
    for path, payload, route_flag in cases:
        response = client.post(path, json=payload, headers={"Idempotency-Key": f"workspace-safe-{route_flag}"})
        assert response.status_code == 200
        body = response.json()
        assert body["real_external_call_executed"] is False
        assert body["automation_runtime_executed"] is False
        assert body["operation_tasks_executed"] is False
        assert body["bazhuayu_send_executed"] is False
        assert body["wecom_send_executed"] is False
        assert body[route_flag] is False
        assert body["side_effect_plan"]["status"] == "blocked"
        assert body["external_call_attempt"]["status"] == "blocked"


def test_workspace_runtime_source_does_not_reference_legacy_runtime_or_direct_clients():
    runtime_source = (ROOT / "aicrm_next/automation_engine/workspace_runtime.py").read_text(encoding="utf-8")
    api_source = (ROOT / "aicrm_next/automation_engine/api.py").read_text(encoding="utf-8")
    tree = ast.parse(api_source)
    handler_sources = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("api_automation_workspace"):
            handler_sources.append(ast.get_source_segment(api_source, node) or "")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("api_plan_automation_workspace"):
            handler_sources.append(ast.get_source_segment(api_source, node) or "")
    combined = runtime_source + "\n" + "\n".join(handler_sources)

    forbidden = [
        _joined("run_due_", "operation_tasks"),
        _joined("send_conversion_execution_item_", "via_bazhuayu"),
        _joined("AutomationConversion", "DispatchError"),
        _joined("WeCom", "Client", ".from_app"),
        _joined("Open", "Claw"),
        _joined("Baz", "huayu"),
        _joined("req", "uests"),
        _joined("htt", "px"),
        _joined("access", "_token"),
    ]
    for marker in forbidden:
        assert marker not in combined

    true_markers = [
        _joined("real_external_call_executed", "=True"),
        _joined("automation_runtime_executed", "=True"),
        _joined("operation_tasks_executed", "=True"),
        _joined("bazhuayu_send_executed", "=True"),
        _joined("wecom_send_executed", "=True"),
        _joined("real_", "enabled def", "ault"),
        _joined("def", "ault real_", "enabled"),
    ]
    for marker in true_markers:
        assert marker not in combined
