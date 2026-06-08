from __future__ import annotations

import json
from pathlib import Path

import tools.check_automerge_eligibility as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/autonomous_development_loop.md"


def test_checker_current_repo_passes_and_reports_expected_eligibility() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    if any(path in checker.OWNER_DECISION_PACKAGE_PATHS for path in report["details"]["changed_files"]):
        assert report["eligible"] is False
        assert report["manual_merge_required"]
    else:
        assert report["eligible"] is True


def test_pr_body_sections_required() -> None:
    text = DOC.read_text(encoding="utf-8")
    for section in checker.REQUIRED_PR_BODY_SECTIONS:
        assert section in text


def test_low_risk_changed_files_are_docs_tools_tests_only() -> None:
    report = checker.build_report()
    for path in report["details"]["changed_files"]:
        assert checker._is_low_risk_path(path)


def test_protected_runtime_path_requires_owner_approval() -> None:
    assert checker._protected_path_reason("aicrm_next/production_compat/api.py") is None
    assert checker._protected_path_reason("aicrm_next/main.py")
    assert checker._protected_path_reason("wecom_ability_service/http/example.py")


def test_destructive_migration_detection() -> None:
    reason = checker._destructive_migration_reason("migrations/2026_drop.sql", "ALTER TABLE x DROP COLUMN y;")
    assert reason


def test_unauthorized_claim_patterns_detected() -> None:
    text = "route_switch_ready=true\ncanary_approved\nproduction_ready\ndelete_ready: true\ndelete_ready true\ncanary approved"
    for pattern in checker.UNAUTHORIZED_CLAIM_PATTERNS:
        assert __import__("re").search(pattern, text)


def test_stop_condition_terms_are_not_allowed_outside_policy_files(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Business value\nBusiness continuity\nRisk / rollback\nNext action\n", encoding="utf-8")
    report = checker.build_report(pr_body_file=str(body))
    assert report["overall"] == "PASS"


def test_import_boundary_runtime_paths_remain_explicit_autopilot_deliverables() -> None:
    expected = {
        "aicrm_next/automation_engine/group_ops/domain.py",
        "aicrm_next/integration_gateway/legacy_flask_facade.py",
        "aicrm_next/integration_gateway/wecom_group_adapter.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS


def test_owner_approval_does_not_make_protected_diff_automerge_eligible(tmp_path: Path) -> None:
    approval = tmp_path / "approval.md"
    approval.write_text("owner approval placeholder", encoding="utf-8")
    assert checker._has_owner_approval(str(approval)) is True


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production_ready",
        "canary_approved",
        "route_switch_ready=true",
        "delete_ready: true",
    ]
    for item in forbidden:
        assert item not in text
