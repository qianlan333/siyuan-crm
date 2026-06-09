from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_autonomous_development_loop as checker


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"
DOC = ROOT / "docs/development/autonomous_development_loop.md"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_phase_execution_state_uses_compact_active_contract() -> None:
    data = checker.load_yaml(STATE)
    assert checker.REQUIRED_STATE_FIELDS <= set(data)
    assert data["current_phase"] == "post_phase7_cleanup_closeout"
    assert data["last_merged_pr"] == "#878"
    assert data["last_merged_cleanup_wave"] == "sidebar_customer_readonly_track3b"
    assert data["recommended_next_pr"] == "product_development_or_targeted_runtime_migration"
    assert data["owner_approval_required"] is False
    assert data["runtime_behavior_changed"] is False
    assert data["delete_ready"] is False
    assert data["cleanup_closeout"] == checker.EXPECTED_CLEANUP_CLOSEOUT
    assert "completed_steps" not in data
    assert "active_candidate" not in data
    assert "action_templates_readiness" not in data


def test_active_safety_gates_are_current() -> None:
    data = checker.load_yaml(STATE)
    assert set(data["active_safety_gates"]) == checker.EXPECTED_SAFETY_GATES
    assert "check_legacy_facade_growth_freeze" in data["active_safety_gates"]
    assert "generate_legacy_replacement_backlog" in data["active_safety_gates"]
    assert "check_production_route_resolution" in data["active_safety_gates"]
    assert "pr_smoke" in data["active_safety_gates"]


def test_protected_runtime_boundaries_are_retained() -> None:
    data = checker.load_yaml(STATE)
    assert set(data["protected_runtime_boundaries"]) == checker.EXPECTED_RUNTIME_BOUNDARIES
    assert "app.py Next-only startup entry" in data["protected_runtime_boundaries"]
    assert "legacy_flask_app.py" not in data["protected_runtime_boundaries"]
    assert "aicrm_next/production_compat/api.py high-risk and retained fallback entries only" in data["protected_runtime_boundaries"]
    assert "wecom_ability_service runtime" in data["protected_runtime_boundaries"]


def test_next_cleanup_candidates_close_global_runtime_fallback_track() -> None:
    data = checker.load_yaml(STATE)
    assert data["next_cleanup_candidates"] == checker.EXPECTED_NEXT_CANDIDATES
    assert data["next_cleanup_candidates"]["non_runtime_cleanup"] == "complete"
    assert data["next_cleanup_candidates"]["runtime_fallback_cleanup"] == "closed_as_global_task"
    assert data["next_cleanup_candidates"]["future_runtime_migration"] == "product_specific_only"
    assert data["next_cleanup_candidates"]["high_risk_external_cleanup"] == "separate_owner_approval_required"


def test_autopilot_settings_allow_targeted_runtime_migration_without_admin_override() -> None:
    data = checker.load_yaml(STATE)
    autopilot = data["autopilot"]
    assert autopilot["enabled"] is True
    assert autopilot["mode"] == "product_development_with_targeted_runtime_migration"
    assert autopilot["runtime_changes_allowed"] == "targeted_owner_approved_only"
    assert autopilot["admin_override_allowed"] is False


def test_completed_and_remaining_runtime_fallback_tracks_are_recorded() -> None:
    data = checker.load_yaml(STATE)
    assert set(data["completed_runtime_fallback_tracks"]) == checker.EXPECTED_COMPLETED_RUNTIME_TRACKS
    remaining = data["remaining_runtime_fallback_tracks"]
    assert set(remaining["product_specific_migration_required"]) == checker.EXPECTED_REMAINING_RUNTIME_TRACKS
    assert remaining["handling_rule"] == "migrate only when the related product capability is actively being developed"


def test_stop_conditions_complete() -> None:
    data = checker.load_yaml(STOP)
    ids = {item["id"] for item in data["high_risk_stop_conditions"]}
    assert checker.STOP_IDS <= ids


def test_docs_include_required_autopilot_contract_sections() -> None:
    text = DOC.read_text(encoding="utf-8")
    for section in ("Business value", "Business continuity", "Risk / rollback", "Next action"):
        assert section in text


def test_no_runtime_or_protected_files_changed_if_git_diff_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    if "app.py" in changed:
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        assert "wecom_ability_service" not in app_source
    if "legacy_flask_app.py" in changed:
        assert not (ROOT / "legacy_flask_app.py").exists()
    assert "aicrm_next/main.py" not in changed
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert not any(path.startswith("deploy/") for path in changed)
