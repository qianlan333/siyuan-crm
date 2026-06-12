from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts import run_external_push_worker


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts/run_external_push_worker.py"


def test_worker_script_uses_next_native_service_without_legacy_imports() -> None:
    source = WORKER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")

    assert all(not module.startswith("wecom_ability" + "_service") for module in imported_modules)
    assert "from " + "wecom_ability" + "_service" not in source
    assert "import " + "wecom_ability" + "_service" not in source
    assert "create_app" not in source
    assert "app_context" not in source
    assert "aicrm_next.external_push" in source


def test_worker_default_runs_events_and_retries(monkeypatch, capsys) -> None:
    calls: list[tuple[str, int]] = []

    def fake_events(*, limit: int):
        calls.append(("events", limit))
        return {"ok": True, "scanned_count": 1}

    def fake_retries(*, limit: int):
        calls.append(("retries", limit))
        return {"ok": True, "retried_count": 2}

    monkeypatch.setattr(run_external_push_worker.external_push_service, "run_due_external_push_events", fake_events)
    monkeypatch.setattr(run_external_push_worker.external_push_service, "run_due_external_push_retries", fake_retries)

    assert run_external_push_worker.main([]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert calls == [("events", 50), ("retries", 50)]
    assert payload["ok"] is True
    assert payload["events"]["scanned_count"] == 1
    assert payload["retries"]["retried_count"] == 2


def test_worker_limit_and_skip_flags(monkeypatch, capsys) -> None:
    calls: list[tuple[str, int]] = []

    def fake_events(*, limit: int):
        calls.append(("events", limit))
        return {"ok": True}

    def fake_retries(*, limit: int):
        calls.append(("retries", limit))
        return {"ok": True}

    monkeypatch.setattr(run_external_push_worker.external_push_service, "run_due_external_push_events", fake_events)
    monkeypatch.setattr(run_external_push_worker.external_push_service, "run_due_external_push_retries", fake_retries)

    assert run_external_push_worker.main(["--limit", "7", "--skip-events"]) == 0
    retry_payload = json.loads(capsys.readouterr().out)
    assert calls == [("retries", 7)]
    assert "events" not in retry_payload
    assert "retries" in retry_payload

    calls.clear()
    assert run_external_push_worker.main(["--limit", "9", "--skip-retries"]) == 0
    event_payload = json.loads(capsys.readouterr().out)
    assert calls == [("events", 9)]
    assert "events" in event_payload
    assert "retries" not in event_payload


def test_deploy_service_still_runs_same_worker_script() -> None:
    service = (ROOT / "deploy/openclaw-external-push-worker.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/openclaw-external-push-worker.timer").read_text(encoding="utf-8")

    assert "python scripts/run_external_push_worker.py" in service
    assert "openclaw-external-push-worker.service" in timer
