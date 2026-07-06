from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/reports/p1_group_ops_workspace_production_validation_remediation_20260625.md"


def test_release_sha_prefers_deploy_marker_over_stale_env(monkeypatch, tmp_path) -> None:
    marker = tmp_path / "release-sha"
    marker.write_text("marker-sha\n", encoding="utf-8")
    monkeypatch.setenv("AICRM_NEXT_RELEASE_SHA_FILE", str(marker))
    monkeypatch.setenv("AICRM_NEXT_RELEASE_SHA", "stale-env-sha")

    from aicrm_next.shared.release import current_release_sha, reset_release_sha_cache

    reset_release_sha_cache()
    assert current_release_sha() == "marker-sha"
    reset_release_sha_cache()


def test_release_sha_falls_back_to_git_head_before_stale_env(monkeypatch, tmp_path) -> None:
    missing_marker = tmp_path / "missing-release-sha"
    monkeypatch.setenv("AICRM_NEXT_RELEASE_SHA_FILE", str(missing_marker))
    monkeypatch.setenv("AICRM_NEXT_RELEASE_SHA", "stale-env-sha")
    expected = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()

    from aicrm_next.shared.release import current_release_sha, reset_release_sha_cache

    reset_release_sha_cache()
    assert current_release_sha() == expected
    reset_release_sha_cache()


def test_health_release_header_uses_release_helper(monkeypatch, tmp_path) -> None:
    marker = tmp_path / "release-sha"
    marker.write_text("health-marker-sha\n", encoding="utf-8")
    monkeypatch.setenv("AICRM_NEXT_RELEASE_SHA_FILE", str(marker))
    monkeypatch.setenv("AICRM_NEXT_RELEASE_SHA", "stale-env-sha")

    from aicrm_next.main import create_app
    from aicrm_next.shared.release import reset_release_sha_cache

    reset_release_sha_cache()
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.headers["x-aicrm-release-sha"] == "health-marker-sha"
    reset_release_sha_cache()


def test_prod_sh_is_safe_stub_without_production_connection_details() -> None:
    source = (ROOT / "scripts/prod.sh").read_text(encoding="utf-8")

    assert "Production diagnostics are intentionally not exposed" in source
    assert "private ops handoff" in source
    assert "exec ssh" not in source
    assert "crm-prod" not in source
    assert "SSH_HOST" not in source
    assert "psql" not in source.lower()
    assert "diagnose-p1-bridge" not in source


def test_prod_sh_exits_before_any_remote_operation() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/prod.sh"), "health"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "private ops handoff" in result.stderr
    assert result.stdout == ""


def test_bridge_diagnostic_reports_dry_run_and_permission_limited_aggregate(monkeypatch) -> None:
    import scripts.diagnose_p1_group_ops_workspace_bridge_acceptance as diagnostic

    monkeypatch.setattr(diagnostic, "_route_manifest_check", lambda: {"ok": True})
    monkeypatch.setattr(diagnostic, "_registered_route_check", lambda: {"ok": True})
    monkeypatch.setattr(diagnostic, "_auth_fail_closed_check", lambda: {"ok": True})
    monkeypatch.setattr(diagnostic, "_migration_check", lambda: {"ok": True})
    monkeypatch.setattr(diagnostic, "_static_asset_check", lambda: {"ok": True})
    monkeypatch.setattr(diagnostic, "_source_inventory_check", lambda: {"ok": True})
    monkeypatch.setattr(diagnostic, "_business_closure_check", lambda: {"ok": True, "can_claim_90_plus": False})
    monkeypatch.setattr(
        diagnostic,
        "_aggregate_evidence_check",
        lambda window_minutes=30: {
            "ok": True,
            "dry_run_read_only": True,
            "status": "AGGREGATE_EVIDENCE_SAFE_SKIP",
            "window_minutes": window_minutes,
            "external_effect_job": {
                "status": "EXTERNAL_EFFECT_JOB_READ_SKIPPED_PERMISSION_LIMITED",
                "verified": False,
            },
            "external_effect_job_aggregate_verified": False,
            "sensitive_payload_exposed": False,
        },
    )

    payload = diagnostic.run(window_minutes=15)
    assert payload["ok"] is True
    assert payload["dry_run_read_only"] is True
    assert payload["write_validation_status"] == "SKIPPED_WRITE_VALIDATION_SAFE_MODE"
    assert payload["real_external_call_executed"] is False
    assert payload["can_claim_pass_90_plus"] is False
    aggregate = payload["checks"]["aggregate_evidence"]
    assert aggregate["external_effect_job"]["status"] == "EXTERNAL_EFFECT_JOB_READ_SKIPPED_PERMISSION_LIMITED"
    assert payload["summary"]["external_effect_job_aggregate_verified"] is False


def test_production_validation_remediation_report_contract() -> None:
    report = REPORT.read_text(encoding="utf-8")
    report_lower = report.lower()
    for expected in [
        "release sha mismatch",
        ".release-sha",
        "private ops handoff",
        "SKIPPED_WRITE_VALIDATION_SAFE_MODE",
        "EXTERNAL_EFFECT_JOB_READ_SKIPPED_PERMISSION_LIMITED",
        "dry_run_read_only=true",
        "real_external_call_executed=false",
        "can_claim_pass_90_plus=false",
        "no external effect execution",
        "PASS_90_PLUS_NOT_CLAIMED",
    ]:
        haystack = report if expected != expected.lower() else report_lower
        assert expected in haystack
