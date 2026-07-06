from __future__ import annotations

from pathlib import Path

from tools import check_next_production_cutover_readiness as cutover


ROOT = Path(__file__).resolve().parents[1]


def test_retired_timer_route_readiness_tool_is_removed() -> None:
    assert not (ROOT / "tools" / "check_next_timer_route_readiness.py").exists()


def test_cutover_readiness_no_longer_depends_on_retired_timer_check(monkeypatch) -> None:
    monkeypatch.setattr(
        cutover,
        "run_gap_check",
        lambda: {
            "ok": True,
            "database_mode": "fixture",
            "route_404_blockers": [],
            "content_blockers": [],
            "oauth_blockers": [],
            "automation_production_data_ready": True,
            "production_config_modified": False,
        },
    )
    monkeypatch.setattr(
        cutover,
        "run_active_automation_guardrail_check",
        lambda: {"ok": True, "db_sentinel": {"ok": True}},
    )

    result = cutover.run_check()

    assert result["ok"] is True
    assert result["active_automation_guardrails_ok"] is True
    assert result["active_guardrail_db_sentinel_ok"] is True
    assert result["safe_to_enable_timers"] is False
    assert "timer_check" not in result
    assert "timer_routes_ready" not in result
    assert "dry_run_db_sentinel_ok" not in result
