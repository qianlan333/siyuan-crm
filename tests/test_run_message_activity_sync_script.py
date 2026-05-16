from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_message_activity_sync.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_message_activity_sync_script", SCRIPT_PATH)
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


def test_run_message_activity_sync_uses_internal_http_helper(monkeypatch, capsys):
    module = _load_script_module()
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(b'{"ok": true, "synced_count": 3}')

    monkeypatch.setenv("APP_HOST", "automation.local")
    monkeypatch.setenv("APP_PORT", "5001")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "runner-token")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    body = module.run()

    assert json.loads(body) == {"ok": True, "synced_count": 3}
    assert captured["url"] == "http://automation.local:5001/api/admin/automation-conversion/message-activity-sync/run"
    assert captured["timeout"] == 180
    assert captured["headers"]["authorization"] == "Bearer runner-token"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["body"] == {
        "trigger_source": "scheduled",
        "operator": "cron_message_activity_sync",
    }
    assert json.loads(capsys.readouterr().out.strip()) == {"ok": True, "synced_count": 3}


def test_run_message_activity_sync_omits_missing_token(monkeypatch):
    module = _load_script_module()
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.delenv("AUTOMATION_INTERNAL_API_TOKEN", raising=False)
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    module.run()

    assert "authorization" not in captured["headers"]
