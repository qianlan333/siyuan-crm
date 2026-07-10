from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ops import manage_production_runtime_units as runtime_units


ROOT = Path(__file__).resolve().parents[1]


pytestmark = pytest.mark.skipif(
    not (ROOT / "deploy" / "production_runtime_units.json").exists(),
    reason="siyuan-crm keeps its existing production deploy/systemd overlay",
)


def _manifest() -> dict:
    return runtime_units.load_manifest()


def test_runtime_units_manifest_classifies_every_deploy_timer() -> None:
    manifest = _manifest()
    active = {item["timer"] for item in manifest["active_autostart"]}
    approval_required = set(manifest["approval_required"])
    retired_forbidden = set(manifest["retired_forbidden"])
    deploy_timers = {path.name for path in (ROOT / "deploy").glob("*.timer")}

    assert deploy_timers == active | approval_required
    assert active.isdisjoint(approval_required)
    assert active.isdisjoint(retired_forbidden)
    assert approval_required.isdisjoint(retired_forbidden)
    assert "aicrm-archive-sync.timer" in approval_required
    assert "openclaw-external-effect-worker.timer" in active
    assert "aicrm-automation-jobs-run-due.timer" in retired_forbidden


def test_runtime_units_manifest_validates_units_and_calendar_persistence() -> None:
    runtime_units.validate_manifest(_manifest())


def test_runtime_units_install_dry_run_copies_and_enables_only_active_units(capsys) -> None:
    assert runtime_units.main(["--phase", "install-enable-after-web-health", "--dry-run"]) == 0
    output = capsys.readouterr().out

    assert "sudo cp deploy/openclaw-external-effect-worker.service /etc/systemd/system/" in output
    assert "sudo cp deploy/openclaw-external-effect-worker.timer /etc/systemd/system/" in output
    assert "sudo systemctl enable openclaw-external-effect-worker.timer" in output
    assert "sudo systemctl restart openclaw-external-effect-worker.timer" in output
    assert "sudo systemctl is-active openclaw-external-effect-worker.timer" not in output
    assert "sudo systemctl enable aicrm-archive-sync.timer" not in output
    assert "sudo cp deploy/aicrm-archive-sync.timer /etc/systemd/system/" not in output
    assert "curl -sSf http://127.0.0.1:5002/health" in output


def test_runtime_units_stop_and_verify_dry_runs_are_manifest_driven(capsys) -> None:
    assert runtime_units.main(["--phase", "stop-for-migration", "--dry-run"]) == 0
    stop_output = capsys.readouterr().out

    assert "sudo systemctl stop openclaw-external-effect-worker.timer" in stop_output
    assert "sudo systemctl stop openclaw-external-effect-worker.service" in stop_output
    assert "sudo systemctl stop aicrm-archive-sync.timer" not in stop_output

    assert runtime_units.main(["--phase", "verify", "--dry-run"]) == 0
    verify_output = capsys.readouterr().out

    assert "sudo systemctl is-active openclaw-external-effect-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-callback-ingress.service" in verify_output
    assert "approval_required_timers=aicrm-archive-sync.timer" in verify_output
