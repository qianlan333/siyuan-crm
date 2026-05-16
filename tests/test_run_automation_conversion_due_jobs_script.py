from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_automation_conversion_due_jobs.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_automation_conversion_due_jobs_script", SCRIPT_PATH)
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


def test_run_automation_conversion_due_jobs_posts_registered_endpoint(monkeypatch, capsys):
    module = _load_script_module()
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        captured.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "headers": {key.lower(): value for key, value in request.header_items()},
                "body": body,
            }
        )
        if body.get("jobs") == ["sop"]:
            return _FakeResponse(b'{"ok": true, "created_batch_count": 1, "batch_ids": [5]}')
        return _FakeResponse(b'{"ok": true, "total_success_count": 7, "batch_ids": [9]}')

    monkeypatch.setenv("APP_HOST", "automation.local")
    monkeypatch.setenv("APP_PORT", "5001")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "runner-token")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    body = module.run()

    assert [item["url"] for item in captured] == [
        "http://automation.local:5001/api/admin/automation-conversion/jobs/run-due",
        "http://automation.local:5001/api/admin/automation-conversion/jobs/run-due",
    ]
    assert [item["timeout"] for item in captured] == [180, 180]
    assert [item["headers"]["authorization"] for item in captured] == [
        "Bearer runner-token",
        "Bearer runner-token",
    ]
    assert [item["body"] for item in captured] == [
        {"operator": "automation_conversion_due_runner", "jobs": ["sop"]},
        {"operator": "automation_conversion_due_runner", "jobs": ["conversion_workflow"]},
    ]
    assert json.loads(body) == {
        "ok": True,
        "requested_job_codes": ["sop", "conversion_workflow"],
        "executed_job_count": 2,
        "failed_job_count": 0,
        "total_success_count": 7,
        "total_skipped_count": 0,
        "total_failed_count": 0,
        "batch_ids": [5, 9],
        "jobs": [
            {
                "job_code": "sop",
                "label": "自动化转化 SOP",
                "ok": True,
                "result": {"ok": True, "created_batch_count": 1, "batch_ids": [5]},
            },
            {
                "job_code": "conversion_workflow",
                "label": "自动化转化任务流",
                "ok": True,
                "result": {"ok": True, "total_success_count": 7, "batch_ids": [9]},
            },
        ],
    }
    assert json.loads(capsys.readouterr().out.strip())["total_success_count"] == 7


def test_run_automation_conversion_due_jobs_respects_job_filter(monkeypatch):
    module = _load_script_module()
    captured: list[str] = []

    def fake_urlopen(request, timeout):
        captured.append(request.full_url)
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setenv("AUTOMATION_CONVERSION_DUE_OPERATOR", "quarter-hour-runner")
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    module.run(jobs=["conversion_workflow"])

    assert captured == ["http://127.0.0.1:5000/api/admin/automation-conversion/jobs/run-due"]


def test_run_automation_conversion_due_jobs_rejects_unknown_job_code():
    module = _load_script_module()

    try:
        module.run(jobs=["unknown"])
    except ValueError as exc:
        assert str(exc) == "unsupported due jobs: unknown"
    else:
        raise AssertionError("expected ValueError")
