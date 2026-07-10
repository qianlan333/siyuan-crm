from __future__ import annotations

from pathlib import Path

import pytest

from tools.check_next_production_runtime_gaps import run_check


ROOT = Path(__file__).resolve().parents[1]


pytestmark = pytest.mark.skipif(
    not (ROOT / "deploy" / "production_runtime_units.json").exists(),
    reason="siyuan-crm keeps its existing production deploy/systemd overlay",
)


def test_runtime_gap_report_keeps_retired_automation_timers_out_of_disabled_todo_list(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")

    result = run_check()

    retired_timers = {
        "aicrm-reply-monitor-run-due.timer",
        "aicrm-reply-monitor-capture.timer",
        "aicrm-automation-jobs-run-due.timer",
    }
    assert retired_timers.isdisjoint(set(result["timers_currently_disabled"]))
    assert retired_timers.isdisjoint(set(result["retired_timers_currently_disabled"]))
    assert retired_timers.issubset(set(result["forbidden_retired_timer_units"]))


def test_runtime_gap_report_tracks_ai_audience_scheduler_as_active_timer(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")

    result = run_check()

    assert "openclaw-ai-audience-scheduler.timer" in result["active_timer_units"]
    assert "openclaw-external-effect-worker.timer" in result["active_timer_units"]
    assert "aicrm-archive-sync.timer" in result["approval_required_timer_units"]
