from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.timers import reset_timer_fixture_state
from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_reply_monitor_capture.py"
ROUTE = "/api/admin/automation-conversion/reply-monitor/capture"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    reset_timer_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_reply_monitor_capture_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def test_service_and_timer_lock_next_native_capture_script_contract() -> None:
    service = (ROOT / "deploy/aicrm-reply-monitor-capture.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/aicrm-reply-monitor-capture.timer").read_text(encoding="utf-8")
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "python scripts/run_reply_monitor_capture.py" in service
    assert "EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env" in service
    assert "Environment=APP_HOST=127.0.0.1" in service
    assert "Environment=APP_PORT=5001" in service
    assert "Unit=aicrm-reply-monitor-capture.service" in timer
    assert "OnCalendar=*-*-* *:00/3:00" in timer
    for source in (service, timer, script):
        assert "wecom_ability_service" not in source
        assert "legacy_flask_app" not in source
        assert "run-legacy" not in source


def test_deploy_workflow_installs_capture_timer_without_immediate_service_start() -> None:
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    copy_service_index = workflow.index("sudo cp deploy/aicrm-reply-monitor-capture.service /etc/systemd/system/")
    copy_timer_index = workflow.index("sudo cp deploy/aicrm-reply-monitor-capture.timer /etc/systemd/system/")
    daemon_reload_index = workflow.index("sudo systemctl daemon-reload")
    enable_index = workflow.index("sudo systemctl enable aicrm-reply-monitor-capture.timer")
    restart_index = workflow.index("sudo systemctl restart aicrm-reply-monitor-capture.timer")
    status_index = workflow.index("sudo systemctl status aicrm-reply-monitor-capture.timer --no-pager")
    run_due_enable_index = workflow.index("sudo systemctl enable aicrm-reply-monitor-run-due.timer")

    assert copy_service_index < copy_timer_index < daemon_reload_index
    assert daemon_reload_index < enable_index < restart_index < status_index < run_due_enable_index
    assert "sudo systemctl start aicrm-reply-monitor-capture.service" not in workflow


def test_reply_monitor_capture_requires_internal_token(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(ROUTE, json={"limit": 1})

    assert response.status_code in {401, 403}
    body = response.json()
    assert body["error_code"] == "internal_token_required"
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["side_effect_executed"] is False


def test_reply_monitor_capture_accepts_valid_timer_empty_body_without_400(monkeypatch) -> None:
    client = _client(monkeypatch)

    response = client.post(ROUTE, headers={"Authorization": "Bearer timer-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["route_owner"] == "ai_crm_next"
    assert body["source_status"] == "next_reply_monitor_capture_plan"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["automation_runtime_executed"] is False
    assert body["wecom_send_executed"] is False
    assert body["reply_monitor_capture_executed"] is False
    assert body["side_effect_plan"]["status"] == "blocked"
    assert "X-AICRM-Compatibility-Facade" not in response.headers


def test_reply_monitor_capture_timer_script_posts_structured_json_contract(monkeypatch, capsys) -> None:
    module = _load_script_module()
    captured: dict[str, object] = {}

    def fake_urlopen(request, *, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(b'{"ok": true, "real_external_call_executed": false}')

    monkeypatch.setenv("APP_HOST", "automation.local")
    monkeypatch.setenv("APP_PORT", "5001")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    body = module.run(limit=10, dry_run=True)

    assert json.loads(body) == {"ok": True, "real_external_call_executed": False}
    assert captured["url"] == f"http://automation.local:5001{ROUTE}"
    assert captured["timeout"] == 180
    assert captured["headers"]["authorization"] == "Bearer timer-token"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["body"] == {"operator": "reply_monitor_capture_timer", "limit": 10, "dry_run": True}
    assert json.loads(capsys.readouterr().out.strip())["real_external_call_executed"] is False


def test_reply_monitor_capture_timer_script_reports_missing_token_without_post(monkeypatch, capsys) -> None:
    module = _load_script_module()
    called = False

    def fake_urlopen(request, *, timeout):
        nonlocal called
        called = True
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.delenv("AUTOMATION_INTERNAL_API_TOKEN", raising=False)
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    body = module.run(limit=10, dry_run=True)
    payload = json.loads(body)

    assert called is False
    assert payload["ok"] is False
    assert payload["status"] == "skipped"
    assert payload["error_code"] == "automation_internal_token_not_configured"
    assert payload["source_status"] == "next_reply_monitor_capture_timer_config"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["reply_monitor_capture_executed"] is False
    assert json.loads(capsys.readouterr().out.strip())["error_code"] == "automation_internal_token_not_configured"


def test_reply_monitor_capture_timer_script_can_run_directly_without_package_import_error() -> None:
    env = os.environ.copy()
    env.pop("AUTOMATION_INTERNAL_API_TOKEN", None)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--limit", "1", "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "skipped"
    assert payload["error_code"] == "automation_internal_token_not_configured"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["reply_monitor_capture_executed"] is False
    assert "Traceback" not in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
