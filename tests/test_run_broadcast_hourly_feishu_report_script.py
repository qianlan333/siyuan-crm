from __future__ import annotations

import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_broadcast_hourly_feishu_report as runner  # type: ignore[import-not-found]


def test_hourly_feishu_report_script_returns_zero_for_non_failed_status(monkeypatch, capsys):
    monkeypatch.setattr(
        runner,
        "run",
        lambda: {"status": "skipped_no_jobs", "summary": {"totalJobs": 0, "successJobs": 0, "failedJobs": 0}},
    )

    assert runner.main() == 0
    output = capsys.readouterr().out
    assert '"status": "skipped_no_jobs"' in output


def test_hourly_feishu_report_script_returns_nonzero_for_failed_status(monkeypatch, capsys):
    monkeypatch.setattr(
        runner,
        "run",
        lambda: {"status": "failed", "summary": {"totalJobs": 1, "successJobs": 0, "failedJobs": 1}},
    )

    assert runner.main() == 1
    output = capsys.readouterr().out
    assert '"status": "failed"' in output
