from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ops import manage_production_runtime_units as runtime_units


ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return runtime_units.load_manifest()


def test_runtime_units_manifest_classifies_every_deploy_timer() -> None:
    manifest = _manifest()
    active = {item["timer"] for item in manifest["active_autostart"]}
    approval_required = {item["timer"] for item in manifest["approval_required"]}
    retired_forbidden = set(manifest["retired_forbidden"])
    deploy_timers = {path.name for path in (ROOT / "deploy").glob("*.timer")}

    assert deploy_timers == active | approval_required
    assert active.isdisjoint(approval_required)
    assert active.isdisjoint(retired_forbidden)
    assert approval_required.isdisjoint(retired_forbidden)
    assert "aicrm-archive-sync.timer" in approval_required
    assert "aicrm-huangyoucan-usage-sync.timer" in approval_required
    assert "aicrm-wechat-shop-order-sync.timer" in approval_required
    assert "openclaw-external-effect-worker.timer" in active
    assert "openclaw-customer-read-model-refresh.timer" in active
    assert "openclaw-external-push-worker.timer" in retired_forbidden
    assert "openclaw-external-push-worker.service" in retired_forbidden
    assert "openclaw-external-push-worker.timer" not in deploy_timers
    assert "openclaw-wecom-callback-inbox-worker.timer" in retired_forbidden
    assert "openclaw-wecom-callback-inbox-worker.timer" not in deploy_timers
    assert "aicrm-automation-jobs-run-due.timer" in retired_forbidden
    assert "aicrm-web.service" in retired_forbidden
    assert "openclaw-automation-conversion-due-runner.timer" in retired_forbidden
    assert set(manifest["retired_unit_files"]) == retired_forbidden


def test_runtime_units_manifest_declares_primary_web_service() -> None:
    assert _manifest()["primary_web"] == {"service": "openclaw-wecom-postgres.service"}
    assert _manifest()["timer_service_drain_timeout_seconds"] == 600


def test_primary_web_has_a_persistent_systemd_transaction_guard() -> None:
    generic_guard = (ROOT / "deploy" / "systemd" / "00-aicrm-deploy-transaction-guard.conf").read_text(encoding="utf-8")
    primary_guard = (ROOT / "deploy" / "systemd" / "00-aicrm-primary-web-transaction-guard.conf").read_text(encoding="utf-8")

    assert generic_guard == (
        "[Unit]\nConditionPathExists=|!/home/ubuntu/.aicrm-production-deploy-in-progress\nConditionPathExists=|/run/aicrm-production-runtime-start-authorized\n"
    )
    assert primary_guard == (
        "[Unit]\n"
        "ConditionPathExists=|!/home/ubuntu/.aicrm-production-deploy-in-progress\n"
        "ConditionPathExists=|/run/aicrm-production-web-start-authorized\n"
        "ConditionPathExists=|/run/aicrm-production-runtime-start-authorized\n"
    )
    assert not (ROOT / "deploy" / "aicrm-web.service").exists()


def test_runtime_units_manifest_validates_units_and_calendar_persistence() -> None:
    runtime_units.validate_manifest(_manifest())


def test_runtime_units_manifest_rejects_managed_environment_service_without_user(monkeypatch) -> None:
    original_read_unit = runtime_units._read_unit

    def read_unit_without_user(unit: str) -> str:
        body = original_read_unit(unit)
        if unit == "aicrm-archive-sync.service":
            return body.replace("User=ubuntu\n", "")
        return body

    monkeypatch.setattr(runtime_units, "_read_unit", read_unit_without_user)

    with pytest.raises(ValueError, match="aicrm-archive-sync.service must declare User=ubuntu"):
        runtime_units.validate_manifest(_manifest())


@pytest.mark.parametrize(
    ("removed_directive", "expected_error"),
    [
        ("EnvironmentFile=/home/ubuntu/.openclaw-wecom-pg.env\n", "must declare EnvironmentFile"),
        ("WorkingDirectory=/home/ubuntu/极简 crm\n", "must declare WorkingDirectory"),
    ],
)
def test_runtime_units_manifest_rejects_incomplete_managed_service_contract(monkeypatch, removed_directive: str, expected_error: str) -> None:
    original_read_unit = runtime_units._read_unit

    def read_incomplete_unit(unit: str) -> str:
        body = original_read_unit(unit)
        if unit == "aicrm-archive-sync.service":
            return body.replace(removed_directive, "")
        return body

    monkeypatch.setattr(runtime_units, "_read_unit", read_incomplete_unit)

    with pytest.raises(ValueError, match=expected_error):
        runtime_units.validate_manifest(_manifest())


def test_runtime_units_manifest_rejects_missing_managed_service_entrypoint(monkeypatch) -> None:
    original_read_unit = runtime_units._read_unit

    def read_unit_with_missing_entrypoint(unit: str) -> str:
        body = original_read_unit(unit)
        if unit == "aicrm-archive-sync.service":
            return body.replace("scripts.run_incremental_archive_sync", "scripts.does_not_exist")
        return body

    monkeypatch.setattr(runtime_units, "_read_unit", read_unit_with_missing_entrypoint)

    with pytest.raises(FileNotFoundError, match="managed service entrypoint does not exist"):
        runtime_units.validate_manifest(_manifest())


def test_archive_sync_service_runs_as_secret_store_owner() -> None:
    service = (ROOT / "deploy" / "aicrm-archive-sync.service").read_text(encoding="utf-8")

    assert "User=ubuntu" in service
    assert "WorkingDirectory=/home/ubuntu/极简 crm" in service


def test_runtime_units_manifest_retires_legacy_overlay_dropins() -> None:
    retired = {(item["unit"], item["dropin"]) for item in _manifest()["retired_dropins"]}

    assert retired == {
        ("openclaw-wecom-postgres.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-wecom-callback-ingress.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-wecom-callback-inbox-worker.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-internal-event-worker.service", "p0-2-payment-shadow.conf"),
        ("openclaw-internal-event-worker.service", "zz-service-period-payment-consumer.conf"),
    }


def test_runtime_units_retire_legacy_overlays_is_idempotent_and_verified(capsys) -> None:
    assert runtime_units.main(["--phase", "retire-legacy-overlays", "--dry-run"]) == 0
    output = capsys.readouterr().out

    for unit, dropin in (
        ("openclaw-wecom-postgres.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-wecom-callback-ingress.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-wecom-callback-inbox-worker.service", "10-aicrm-callback-hotfix-runtime.conf"),
        ("openclaw-internal-event-worker.service", "p0-2-payment-shadow.conf"),
        ("openclaw-internal-event-worker.service", "zz-service-period-payment-consumer.conf"),
    ):
        path = f"/etc/systemd/system/{unit}.d/{dropin}"
        assert f"sudo rm -f {path}" in output
        assert f"sudo test '!' -e {path}" in output
    assert output.index("sudo rm -f") < output.index("sudo systemctl daemon-reload") < output.index("sudo test '!' -e")


def test_runtime_units_install_dry_run_copies_and_enables_only_active_units(capsys) -> None:
    assert runtime_units.main(["--phase", "install-enable-after-web-health", "--dry-run"]) == 0
    output = capsys.readouterr().out

    assert "sudo cp deploy/openclaw-external-effect-worker.service /etc/systemd/system/" in output
    assert "sudo cp deploy/openclaw-external-effect-worker.timer /etc/systemd/system/" in output
    assert "sudo systemctl enable openclaw-external-effect-worker.timer" in output
    assert "sudo systemctl restart openclaw-external-effect-worker.timer" in output
    assert "sudo systemctl is-active openclaw-external-effect-worker.timer" not in output
    assert "sudo systemctl is-enabled aicrm-archive-sync.timer" in output
    assert "sudo systemctl enable aicrm-archive-sync.timer" not in output
    assert "sudo systemctl restart aicrm-archive-sync.timer" not in output
    assert "sudo cp deploy/aicrm-archive-sync.service /etc/systemd/system/" in output
    assert "sudo cp deploy/aicrm-archive-sync.timer /etc/systemd/system/" in output
    assert "curl -sSf http://127.0.0.1:5002/health" in output
    assert "sudo cp deploy/openclaw-wecom-callback-inbox-worker.service /etc/systemd/system/" in output
    assert "sudo systemctl enable openclaw-wecom-callback-inbox-worker.service" in output
    assert "sudo systemctl restart openclaw-wecom-callback-inbox-worker.service" in output


class _RecordingRunner:
    def __init__(
        self,
        *,
        enabled_units: set[str],
        active_units: set[str] | None = None,
        failed_units: set[str] | None = None,
        static_units: set[str] | None = None,
        failed_starts: set[str] | None = None,
    ) -> None:
        self.execute = True
        self.enabled_units = enabled_units
        self.active_units = active_units or set()
        self.failed_units = failed_units or set()
        self.static_units = static_units or set()
        self.failed_starts = failed_starts or set()
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        self.commands.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def systemctl(
        self,
        *args: str,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = ("sudo", "systemctl", *args)
        self.commands.append(command)
        if args and args[0] == "is-enabled":
            if args[1] in self.static_units:
                return subprocess.CompletedProcess(command, 0, stdout="static\n", stderr="")
            enabled = args[1] in self.enabled_units
            return subprocess.CompletedProcess(command, 0 if enabled else 1, stdout="enabled\n" if enabled else "disabled\n", stderr="")
        if args and args[0] == "is-active":
            active = args[1] in self.active_units
            return subprocess.CompletedProcess(command, 0 if active else 3, stdout="active\n" if active else "inactive\n", stderr="")
        if args and args[0] == "is-failed":
            failed = args[1] in self.failed_units
            return subprocess.CompletedProcess(command, 0 if failed else 1, stdout="failed\n" if failed else "inactive\n", stderr="")
        if args and args[0] == "show" and "--property=ActiveState" in args:
            state = "activating" if args[1] in self.active_units else "inactive"
            return subprocess.CompletedProcess(command, 0, stdout=f"{state}\n", stderr="")
        if args and args[0] == "start" and args[1] in self.failed_starts:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def test_runtime_units_install_restores_only_previously_enabled_approval_timer() -> None:
    manifest = {
        "active_services": [],
        "active_autostart": [],
        "approval_required": [
            {"timer": "aicrm-archive-sync.timer", "service": "aicrm-archive-sync.service"},
            {
                "timer": "openclaw-automation-ops-scheduler.timer",
                "service": "openclaw-automation-ops-scheduler.service",
            },
        ],
    }
    runner = _RecordingRunner(enabled_units={"aicrm-archive-sync.timer"})

    runtime_units.phase_install_enable_after_web_health(manifest, runner)

    assert ("sudo", "cp", "deploy/aicrm-archive-sync.service", "/etc/systemd/system/") in runner.commands
    assert ("sudo", "cp", "deploy/aicrm-archive-sync.timer", "/etc/systemd/system/") in runner.commands
    assert ("sudo", "cp", "deploy/openclaw-automation-ops-scheduler.service", "/etc/systemd/system/") in runner.commands
    assert ("sudo", "cp", "deploy/openclaw-automation-ops-scheduler.timer", "/etc/systemd/system/") in runner.commands
    assert ("sudo", "systemctl", "restart", "aicrm-archive-sync.timer") in runner.commands
    assert ("sudo", "systemctl", "restart", "openclaw-automation-ops-scheduler.timer") not in runner.commands


def test_runtime_units_fatal_kick_logs_diagnostics_before_failing() -> None:
    service = "openclaw-customer-read-model-refresh.service"
    manifest = {
        "active_services": [],
        "active_autostart": [
            {
                "timer": "openclaw-customer-read-model-refresh.timer",
                "service": service,
                "kick_after_timer_restart": True,
                "kick_failure_fatal": True,
            }
        ],
        "approval_required": [],
    }
    runner = _RecordingRunner(enabled_units=set(), failed_starts={service})

    with pytest.raises(RuntimeError, match=f"fatal runtime kick failed: {service}"):
        runtime_units.phase_install_enable_after_web_health(manifest, runner)

    assert ("sudo", "systemctl", "start", service) in runner.commands
    assert ("sudo", "systemctl", "status", service, "--no-pager") in runner.commands
    assert ("sudo", "journalctl", "-u", service, "-n", "80", "--no-pager") in runner.commands


def test_runtime_units_install_primary_web_dry_run_copies_before_start(capsys) -> None:
    assert runtime_units.main(["--phase", "install-primary-web", "--dry-run"]) == 0
    output = capsys.readouterr().out

    assert "sudo rm -f /etc/systemd/system/aicrm-web.service" in output
    assert "sudo cp deploy/openclaw-wecom-postgres.service /etc/systemd/system/" in output
    assert "sudo install -m 0644 deploy/systemd/00-aicrm-primary-web-transaction-guard.conf" in output
    assert "sudo install -m 0644 deploy/systemd/00-aicrm-deploy-transaction-guard.conf" in output
    assert "sudo systemctl daemon-reload" in output
    assert "sudo systemctl enable openclaw-wecom-postgres.service" in output
    assert "sudo systemctl start openclaw-wecom-postgres.service" not in output


def test_runtime_units_transaction_guard_authorizes_only_web_before_release(capsys) -> None:
    assert runtime_units.main(["--phase", "begin-transaction", "--dry-run"]) == 0
    begin_output = capsys.readouterr().out

    guard_file = "/home/ubuntu/.aicrm-production-deploy-in-progress"
    guard_dropin = "/etc/systemd/system/openclaw-wecom-postgres.service.d/00-aicrm-deploy-transaction-guard.conf"
    assert f"sudo touch {guard_file}" in begin_output
    assert f"sudo test -e {guard_file}" in begin_output
    assert f"sudo test -f {guard_dropin}" in begin_output
    for guarded_unit in (
        "openclaw-external-effect-worker.timer",
        "aicrm-archive-sync.timer",
        "aicrm-web.service",
    ):
        assert f"/etc/systemd/system/{guarded_unit}.d/00-aicrm-deploy-transaction-guard.conf" in begin_output
    assert "sudo systemctl daemon-reload" in begin_output

    web_authorization = "/run/aicrm-production-web-start-authorized"
    assert runtime_units.main(["--phase", "authorize-web-start", "--dry-run"]) == 0
    authorize_output = capsys.readouterr().out

    assert f"sudo test -e {guard_file}" in authorize_output
    assert f"sudo touch {web_authorization}" in authorize_output
    assert f"sudo test -e {web_authorization}" in authorize_output
    assert f"sudo rm -f {guard_file}" not in authorize_output

    runtime_authorization = "/run/aicrm-production-runtime-start-authorized"
    assert runtime_units.main(["--phase", "authorize-runtime-start", "--dry-run"]) == 0
    runtime_authorize_output = capsys.readouterr().out

    assert f"sudo test -e {guard_file}" in runtime_authorize_output
    assert f"sudo touch {runtime_authorization}" in runtime_authorize_output
    assert f"sudo rm -f {web_authorization}" in runtime_authorize_output
    assert f"sudo test -e {runtime_authorization}" in runtime_authorize_output
    assert f"sudo rm -f {guard_file}" not in runtime_authorize_output

    assert runtime_units.main(["--phase", "release-runtime-guard", "--dry-run"]) == 0
    release_output = capsys.readouterr().out

    assert f"sudo rm -f {runtime_authorization}" in release_output
    assert f"sudo rm -f {guard_file}" in release_output
    assert f"sudo test '!' -e {web_authorization}" in release_output
    assert f"sudo test '!' -e {runtime_authorization}" in release_output
    assert f"sudo test '!' -e {guard_file}" in release_output
    assert f"sudo test -f {guard_dropin}" in release_output


def test_runtime_units_stop_and_verify_dry_runs_are_manifest_driven(capsys) -> None:
    assert runtime_units.main(["--phase", "stop-for-migration", "--dry-run"]) == 0
    stop_output = capsys.readouterr().out

    assert "sudo test -e /home/ubuntu/.aicrm-production-deploy-in-progress" in stop_output
    assert "sudo systemctl stop openclaw-external-effect-worker.timer" in stop_output
    assert "sudo systemctl stop openclaw-external-effect-worker.service" in stop_output
    assert "sudo systemctl stop openclaw-wecom-callback-inbox-worker.service" in stop_output
    assert "sudo systemctl stop aicrm-archive-sync.timer" in stop_output
    assert "sudo systemctl stop aicrm-archive-sync.service" in stop_output
    assert "sudo systemctl stop openclaw-automation-ops-scheduler.timer" in stop_output
    assert "sudo systemctl stop openclaw-automation-ops-scheduler.service" in stop_output
    drain_probe = "sudo systemctl show openclaw-broadcast-queue-worker.service --property=ActiveState --value"
    assert drain_probe in stop_output
    assert stop_output.index(drain_probe) < stop_output.index("sudo systemctl stop openclaw-broadcast-queue-worker.service")
    for unit in _manifest()["retired_forbidden"]:
        assert f"sudo systemctl disable --now {unit}" in stop_output
        assert f"sudo systemctl stop {unit}" in stop_output
        assert f"sudo systemctl reset-failed {unit}" in stop_output

    assert runtime_units.main(["--phase", "verify", "--dry-run"]) == 0
    verify_output = capsys.readouterr().out

    assert "sudo test '!' -e /run/aicrm-production-web-start-authorized" in verify_output
    assert "sudo test '!' -e /run/aicrm-production-runtime-start-authorized" in verify_output
    assert "sudo test '!' -e /home/ubuntu/.aicrm-production-deploy-in-progress" in verify_output
    assert "sudo systemctl is-enabled openclaw-wecom-postgres.service" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-postgres.service" in verify_output
    assert "sudo systemctl is-enabled openclaw-external-effect-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-external-effect-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-callback-ingress.service" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-callback-inbox-worker.service" in verify_output
    assert "sudo systemctl is-active openclaw-wecom-callback-inbox-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-external-push-worker.timer" in verify_output
    assert "sudo systemctl is-active openclaw-external-push-worker.service" in verify_output
    assert "sudo systemctl is-enabled aicrm-archive-sync.timer" in verify_output
    assert "sudo systemctl is-active aicrm-archive-sync.timer" in verify_output
    for unit in _manifest()["retired_forbidden"]:
        assert f"sudo systemctl is-enabled {unit}" in verify_output
        assert f"sudo systemctl is-active {unit}" in verify_output
        assert f"sudo systemctl is-failed {unit}" in verify_output
    assert "sudo test '!' -e /etc/systemd/system/openclaw-wecom-callback-ingress.service.d/10-aicrm-callback-hotfix-runtime.conf" in verify_output
    expected_approval = "approval_required_timers=" + ",".join(item["timer"] for item in _manifest()["approval_required"])
    assert expected_approval in verify_output


def test_runtime_units_verify_requires_primary_active_and_enabled_approval_timer_active() -> None:
    manifest = {
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [{"service": "openclaw-wecom-callback-ingress.service"}],
        "active_autostart": [
            {
                "timer": "openclaw-external-effect-worker.timer",
                "service": "openclaw-external-effect-worker.service",
            }
        ],
        "approval_required": [{"timer": "aicrm-archive-sync.timer", "service": "aicrm-archive-sync.service"}],
        "retired_forbidden": ["aicrm-reply-monitor-run-due.timer"],
        "retired_unit_files": [],
        "retired_dropins": [],
    }
    runner = _RecordingRunner(
        enabled_units={
            "openclaw-wecom-postgres.service",
            "openclaw-wecom-callback-ingress.service",
            "openclaw-external-effect-worker.timer",
            "aicrm-archive-sync.timer",
        },
        active_units={
            "openclaw-wecom-postgres.service",
            "openclaw-wecom-callback-ingress.service",
            "openclaw-external-effect-worker.timer",
            "aicrm-archive-sync.timer",
        },
    )

    runtime_units.phase_verify(manifest, runner)

    assert ("sudo", "systemctl", "is-active", "openclaw-wecom-postgres.service") in runner.commands
    assert ("sudo", "systemctl", "is-enabled", "aicrm-archive-sync.timer") in runner.commands
    assert ("sudo", "systemctl", "is-active", "aicrm-archive-sync.timer") in runner.commands
    assert ("sudo", "systemctl", "is-enabled", "aicrm-reply-monitor-run-due.timer") in runner.commands
    assert ("sudo", "systemctl", "is-active", "aicrm-reply-monitor-run-due.timer") in runner.commands
    assert ("sudo", "systemctl", "is-failed", "aicrm-reply-monitor-run-due.timer") in runner.commands


def test_runtime_units_stop_accepts_inactive_static_retired_guard_only_unit() -> None:
    retired_unit = "aicrm-reply-monitor-run-due.service"
    manifest = {
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [],
        "active_autostart": [],
        "approval_required": [],
        "retired_forbidden": [retired_unit],
        "retired_unit_files": [],
        "retired_dropins": [],
    }
    runner = _RecordingRunner(
        enabled_units={"openclaw-wecom-postgres.service"},
        static_units={retired_unit},
    )

    runtime_units.phase_stop_for_migration(manifest, runner)

    assert ("sudo", "systemctl", "is-enabled", retired_unit) in runner.commands
    assert ("sudo", "systemctl", "is-active", retired_unit) in runner.commands
    assert ("sudo", "systemctl", "is-failed", retired_unit) in runner.commands


def test_runtime_units_steady_state_rejects_static_retired_unit() -> None:
    retired_unit = "aicrm-reply-monitor-run-due.service"
    manifest = {
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [],
        "active_autostart": [],
        "approval_required": [],
        "retired_forbidden": [retired_unit],
        "retired_unit_files": [],
        "retired_dropins": [],
    }
    runner = _RecordingRunner(
        enabled_units={"openclaw-wecom-postgres.service"},
        active_units={"openclaw-wecom-postgres.service"},
        static_units={retired_unit},
    )

    with pytest.raises(RuntimeError, match=f"retired runtime unit is still enabled: {retired_unit}"):
        runtime_units.phase_verify(manifest, runner)


@pytest.mark.parametrize(
    ("enabled_units", "active_units", "failed_units", "expected_error"),
    [
        (set(), set(), set(), "required runtime unit is not enabled: openclaw-wecom-postgres.service"),
        (
            {"openclaw-wecom-postgres.service"},
            set(),
            set(),
            "required runtime unit is not active: openclaw-wecom-postgres.service",
        ),
        (
            {"openclaw-wecom-postgres.service", "aicrm-archive-sync.timer"},
            {"openclaw-wecom-postgres.service"},
            set(),
            "enabled approval timer is not active: aicrm-archive-sync.timer",
        ),
        (
            {"openclaw-wecom-postgres.service", "aicrm-reply-monitor-run-due.timer"},
            {"openclaw-wecom-postgres.service"},
            set(),
            "retired runtime unit is still enabled: aicrm-reply-monitor-run-due.timer",
        ),
        (
            {"openclaw-wecom-postgres.service"},
            {"openclaw-wecom-postgres.service", "aicrm-reply-monitor-run-due.timer"},
            set(),
            "retired runtime unit is still active: aicrm-reply-monitor-run-due.timer",
        ),
        (
            {"openclaw-wecom-postgres.service"},
            {"openclaw-wecom-postgres.service"},
            {"aicrm-reply-monitor-run-due.timer"},
            "retired runtime unit remains failed: aicrm-reply-monitor-run-due.timer",
        ),
    ],
)
def test_runtime_units_verify_fails_closed_on_invalid_desired_state(
    enabled_units: set[str],
    active_units: set[str],
    failed_units: set[str],
    expected_error: str,
) -> None:
    manifest = {
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [],
        "active_autostart": [],
        "approval_required": [{"timer": "aicrm-archive-sync.timer", "service": "aicrm-archive-sync.service"}],
        "retired_forbidden": ["aicrm-reply-monitor-run-due.timer"],
        "retired_unit_files": [],
        "retired_dropins": [],
    }
    runner = _RecordingRunner(
        enabled_units=enabled_units,
        active_units=active_units,
        failed_units=failed_units,
    )

    with pytest.raises(RuntimeError, match=expected_error):
        runtime_units.phase_verify(manifest, runner)


def test_runtime_units_stop_fails_when_a_timer_remains_active() -> None:
    manifest = {
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [],
        "active_autostart": [
            {
                "timer": "openclaw-external-effect-worker.timer",
                "service": "openclaw-external-effect-worker.service",
            }
        ],
        "approval_required": [],
        "retired_forbidden": [],
    }
    runner = _RecordingRunner(
        enabled_units=set(),
        active_units={"openclaw-external-effect-worker.timer"},
    )

    with pytest.raises(RuntimeError, match="runtime timer did not stop: openclaw-external-effect-worker.timer"):
        runtime_units.phase_stop_for_migration(manifest, runner)


def test_runtime_units_stop_never_signals_an_active_oneshot_before_drain_timeout(monkeypatch) -> None:
    service = "openclaw-broadcast-queue-worker.service"
    manifest = {
        "timer_service_drain_timeout_seconds": 1,
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [],
        "active_autostart": [
            {
                "timer": "openclaw-broadcast-queue-worker.timer",
                "service": service,
            }
        ],
        "approval_required": [],
        "retired_forbidden": [],
    }
    runner = _RecordingRunner(enabled_units=set(), active_units={service})
    monotonic_values = iter((0.0, 2.0))
    monkeypatch.setattr(runtime_units.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(runtime_units.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="timer services did not drain within 1s"):
        runtime_units.phase_stop_for_migration(manifest, runner)

    assert ("sudo", "systemctl", "stop", "openclaw-broadcast-queue-worker.timer") in runner.commands
    assert ("sudo", "systemctl", "show", service, "--property=ActiveState", "--value") in runner.commands
    assert ("sudo", "systemctl", "stop", service) not in runner.commands
    assert ("sudo", "systemctl", "stop", "openclaw-wecom-postgres.service") not in runner.commands


def test_runtime_restore_authorization_does_not_require_web_restart(capsys) -> None:
    assert runtime_units.main(["--phase", "authorize-runtime-restore", "--dry-run"]) == 0
    output = capsys.readouterr().out

    assert "sudo test -e /home/ubuntu/.aicrm-production-deploy-in-progress" in output
    assert "sudo systemctl is-active openclaw-wecom-postgres.service" in output
    assert "sudo touch /run/aicrm-production-runtime-start-authorized" in output
    assert "sudo test -e /run/aicrm-production-web-start-authorized" not in output


def test_runtime_guard_cannot_authorize_an_already_running_web() -> None:
    manifest = {
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [],
        "active_autostart": [],
        "approval_required": [],
        "retired_forbidden": [],
    }
    runner = _RecordingRunner(
        enabled_units={"openclaw-wecom-postgres.service"},
        active_units={"openclaw-wecom-postgres.service"},
    )

    with pytest.raises(RuntimeError, match="primary Web must be stopped before canary authorization"):
        runtime_units.phase_authorize_web_start(manifest, runner)


def test_runtime_guard_cannot_release_before_web_is_active() -> None:
    manifest = {
        "primary_web": {"service": "openclaw-wecom-postgres.service"},
        "active_services": [],
        "active_autostart": [],
        "approval_required": [],
        "retired_forbidden": [],
    }
    runner = _RecordingRunner(
        enabled_units={"openclaw-wecom-postgres.service"},
        active_units=set(),
    )

    with pytest.raises(RuntimeError, match="primary Web must be active before runtime guard release"):
        runtime_units.phase_release_runtime_guard(manifest, runner)
