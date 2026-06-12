from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import reset_timer_fixture_state
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _joined(*parts: str) -> str:
    return "".join(parts)


def test_timer_routes_return_no_real_side_effect_flags(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    reset_timer_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    cases = (
        ("/api/admin/automation-conversion/reply-monitor/capture", {"limit": 1}, "reply_monitor_capture_executed"),
        ("/api/admin/automation-conversion/reply-monitor/run-due", {"limit": 1}, "reply_monitor_run_due_executed"),
        ("/api/admin/automation-conversion/jobs/run-due", {"jobs": ["job_a"]}, "jobs_run_due_executed"),
    )
    for path, payload, route_flag in cases:
        response = client.post(
            path,
            json=payload,
            headers={"Idempotency-Key": f"safe-{route_flag}", "Authorization": "Bearer timer-token"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["real_external_call_executed"] is False
        assert body["automation_runtime_executed"] is False
        assert body["wecom_send_executed"] is False
        assert body[route_flag] is False
        assert body["side_effect_plan"]["status"] == "blocked"
        assert body["external_call_attempt"]["status"] == "blocked"


def test_timer_source_does_not_reference_real_runtime_or_direct_clients():
    timer_source = (ROOT / "aicrm_next/automation_engine/timers.py").read_text(encoding="utf-8")
    api_source = (ROOT / "aicrm_next/automation_engine/api.py").read_text(encoding="utf-8")
    tree = ast.parse(api_source)
    timer_handler_sources = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            (
                "api_plan_automation_conversion_",
                "api_preview_automation_conversion_",
                "api_automation_conversion_",
            )
        ):
            timer_handler_sources.append(ast.get_source_segment(api_source, node) or "")
    combined = timer_source + "\n" + "\n".join(timer_handler_sources)

    forbidden = [
        _joined("run_", "reply_monitor_", "capture"),
        _joined("run_", "due_reply_", "monitor"),
        _joined("run_", "registered_due_", "jobs"),
        _joined("WeCom", "Client", ".from_app"),
        _joined("send", "_message"),
        _joined("Open", "Claw"),
        _joined("Bazhu", "ayu"),
        _joined("req", "uests"),
        _joined("htt", "px"),
        _joined("access", "_token"),
    ]
    for marker in forbidden:
        assert marker not in combined

    true_markers = [
        _joined("real_external_call_executed", "=True"),
        _joined("automation_runtime_executed", "=True"),
        _joined("reply_monitor_capture_executed", "=True"),
        _joined("reply_monitor_run_due_executed", "=True"),
        _joined("jobs_run_due_executed", "=True"),
        _joined("wecom_send_executed", "=True"),
        _joined("real_", "enabled def", "ault"),
        _joined("def", "ault real_", "enabled"),
    ]
    for marker in true_markers:
        assert marker not in combined
