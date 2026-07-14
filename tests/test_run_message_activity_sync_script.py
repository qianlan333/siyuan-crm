from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pytest


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

    def fake_urlopen(request, *, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(b'{"ok": true, "synced_count": 3}')

    monkeypatch.setenv("APP_HOST", "automation.local")
    monkeypatch.setenv("APP_PORT", "5001")
    monkeypatch.setenv("AICRM_INTERNAL_API_BASE_URL", "https://automation.local")
    monkeypatch.setattr(module, "read_internal_access_token", lambda **_kwargs: "runner-oauth-access-token")
    monkeypatch.setattr(module, "read_internal_tls_context", lambda: None)
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    body = module.run()

    assert json.loads(body) == {"ok": True, "synced_count": 3}
    assert captured["url"] == "https://automation.local/api/admin/automation-conversion/message-activity-sync/run"
    assert captured["timeout"] == 180
    assert captured["headers"]["authorization"] == "Bearer runner-oauth-access-token"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["body"] == {
        "trigger_source": "scheduled",
        "operator": "cron_message_activity_sync",
    }
    assert json.loads(capsys.readouterr().out.strip()) == {"ok": True, "synced_count": 3}


def test_run_message_activity_sync_fails_closed_without_client_credentials(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(
        module,
        "read_internal_access_token",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("internal API client configuration is incomplete")),
    )

    with pytest.raises(RuntimeError, match="client configuration is incomplete"):
        module.run()
