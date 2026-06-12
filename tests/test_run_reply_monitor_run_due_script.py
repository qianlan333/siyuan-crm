from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_reply_monitor_run_due.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_reply_monitor_run_due_script_only", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_reply_monitor_run_due_script_reports_http_error_without_raising(monkeypatch, capsys) -> None:
    module = _load_script_module()

    def fake_urlopen(request, *, timeout):
        raise urllib.error.HTTPError(request.full_url, 409, "Conflict", hdrs={}, fp=None)

    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    body = module.run(limit=10, dry_run=True)
    payload = json.loads(body)

    assert payload["ok"] is False
    assert payload["status"] == "skipped"
    assert payload["error_code"] == "reply_monitor_run_due_http_error"
    assert payload["http_status"] == 409
    assert payload["real_external_call_executed"] is False
    assert payload["reply_monitor_run_due_executed"] is False
    assert json.loads(capsys.readouterr().out.strip())["http_status"] == 409


def test_reply_monitor_run_due_script_reports_connection_error_without_raising(monkeypatch) -> None:
    module = _load_script_module()

    def fake_urlopen(request, *, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    body = module.run(limit=10, dry_run=True)
    payload = json.loads(body)

    assert payload["ok"] is False
    assert payload["status"] == "skipped"
    assert payload["error_code"] == "reply_monitor_run_due_connection_error"
    assert payload["error"] == "connection refused"
    assert payload["real_external_call_executed"] is False
    assert payload["reply_monitor_run_due_executed"] is False
