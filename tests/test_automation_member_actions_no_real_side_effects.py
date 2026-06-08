from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.member_actions import reset_member_actions_fixture_state
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]


def _joined(*parts: str) -> str:
    return "".join(parts)


def test_member_action_routes_return_no_real_side_effect_flags(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_FORCE_PRODUCTION_DATA", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_member_actions_fixture_state()
    client = TestClient(create_app(), raise_server_exceptions=False)

    for path in (
        "/api/admin/automation-conversion/member/put-in-pool",
        "/api/admin/automation-conversion/member/set-focus",
        "/api/admin/automation-conversion/member/mark-won",
        "/api/admin/automation-conversion/member/push-openclaw",
    ):
        response = client.post(path, json={"external_contact_id": "wx_ext_001"}, headers={"Idempotency-Key": f"safe-{path.rsplit('/', 1)[-1]}"})
        assert response.status_code == 200
        body = response.json()
        assert body["real_external_call_executed"] is False
        assert body["automation_runtime_executed"] is False
        assert body["openclaw_push_executed"] is False
        assert body["wecom_send_executed"] is False
        assert body["side_effect_plan"]["status"] == "blocked"
        assert body["external_call_attempt"]["status"] == "blocked"


def test_member_action_source_does_not_reference_legacy_services_or_direct_clients():
    module_source = (ROOT / "aicrm_next/automation_engine/member_actions.py").read_text(encoding="utf-8")
    api_source = (ROOT / "aicrm_next/automation_engine/api.py").read_text(encoding="utf-8")
    tree = ast.parse(api_source)
    handler_sources = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("api_automation_member"):
            handler_sources.append(ast.get_source_segment(api_source, node) or "")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("api_plan_automation_member"):
            handler_sources.append(ast.get_source_segment(api_source, node) or "")
    combined = module_source + "\n" + "\n".join(handler_sources)

    forbidden = [
        _joined("wecom_", "ability_service"),
        _joined("legacy_", "automation_facade"),
        _joined("get_automation_member_detail_", "from_legacy"),
        _joined("send_outbound_", "webhook"),
        _joined("PushMemberContextTo", "Open", "Claw", "Command"),
        _joined("req", "uests"),
        _joined("htt", "px"),
        _joined("access", "_token"),
    ]
    for marker in forbidden:
        assert marker not in combined

    true_markers = [
        _joined("real_external_call_executed", "=True"),
        _joined("openclaw_push_executed", "=True"),
        _joined("automation_runtime_executed", "=True"),
        _joined("real_", "enabled def", "ault"),
        _joined("def", "ault real_", "enabled"),
    ]
    for marker in true_markers:
        assert marker not in combined
