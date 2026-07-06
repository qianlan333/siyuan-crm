from __future__ import annotations

from pathlib import Path

from tools import check_autonomous_development_loop as checker


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs" / "development" / "phase_execution_state.yaml"


def test_autonomous_state_marks_old_member_actions_retired_not_remaining() -> None:
    state = STATE.read_text(encoding="utf-8")

    assert "automation_member_manual_send_focus_sop_retired" in state
    assert "    - automation_member_manual_send_focus_sop\n" not in state


def test_autonomous_checker_no_longer_expects_old_member_action_track() -> None:
    assert "automation_member_manual_send_focus_sop_retired" in checker.EXPECTED_COMPLETED_RUNTIME_TRACKS
    assert "automation_member_manual_send_focus_sop" not in checker.EXPECTED_REMAINING_RUNTIME_TRACKS
