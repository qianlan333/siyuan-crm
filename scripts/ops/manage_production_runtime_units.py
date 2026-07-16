#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "deploy" / "production_runtime_units.json"
SYSTEMD_DIR = Path("/etc/systemd/system")
DEPLOY_GUARD_FILE = Path("/home/ubuntu/.aicrm-production-deploy-in-progress")
WEB_START_AUTHORIZATION_FILE = Path("/run/aicrm-production-web-start-authorized")
RUNTIME_START_AUTHORIZATION_FILE = Path("/run/aicrm-production-runtime-start-authorized")
DEPLOY_GUARD_DROPIN = "00-aicrm-deploy-transaction-guard.conf"
DEPLOY_GUARD_SOURCE = ROOT / "deploy" / "systemd" / DEPLOY_GUARD_DROPIN
PRIMARY_WEB_GUARD_SOURCE = ROOT / "deploy" / "systemd" / "00-aicrm-primary-web-transaction-guard.conf"
DEFAULT_TIMER_SERVICE_DRAIN_TIMEOUT_SECONDS = 120
TIMER_SERVICE_DRAIN_POLL_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True)
class TimerUnit:
    timer: str
    service: str
    kick_after_timer_restart: bool = False
    kick_failure_fatal: bool = False


@dataclass(frozen=True)
class ServiceUnit:
    service: str
    health_url: str | None = None
    stop_for_migration: bool = False


@dataclass(frozen=True)
class RetiredDropIn:
    unit: str
    dropin: str


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def active_timers(manifest: dict[str, Any]) -> list[TimerUnit]:
    timers: list[TimerUnit] = []
    for item in manifest.get("active_autostart") or []:
        timers.append(
            TimerUnit(
                timer=str(item["timer"]),
                service=str(item["service"]),
                kick_after_timer_restart=bool(item.get("kick_after_timer_restart", False)),
                kick_failure_fatal=bool(item.get("kick_failure_fatal", False)),
            )
        )
    return timers


def active_services(manifest: dict[str, Any]) -> list[ServiceUnit]:
    services: list[ServiceUnit] = []
    for item in manifest.get("active_services") or []:
        services.append(
            ServiceUnit(
                service=str(item["service"]),
                health_url=item.get("health_url") or None,
                stop_for_migration=bool(item.get("stop_for_migration", False)),
            )
        )
    return services


def primary_web_service(manifest: dict[str, Any]) -> ServiceUnit:
    item = manifest.get("primary_web") or {}
    service = str(item.get("service") or "").strip()
    if not service:
        raise ValueError("production runtime units manifest must declare primary_web.service")
    return ServiceUnit(service=service, health_url=item.get("health_url") or None)


def retired_dropins(manifest: dict[str, Any]) -> list[RetiredDropIn]:
    return [RetiredDropIn(unit=str(item["unit"]), dropin=str(item["dropin"])) for item in manifest.get("retired_dropins") or []]


def _deploy_path(unit: str) -> Path:
    return ROOT / "deploy" / unit


def _read_unit(unit: str) -> str:
    return _deploy_path(unit).read_text(encoding="utf-8")


def _unique(items: list[str], label: str) -> None:
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label}: {duplicates}")


def _timer_service(timer: str) -> str | None:
    for line in _read_unit(timer).splitlines():
        if line.strip().startswith("Unit="):
            return line.split("=", 1)[1].strip()
    return None


def approval_timers(manifest: dict[str, Any]) -> list[TimerUnit]:
    timers: list[TimerUnit] = []
    for item in manifest.get("approval_required") or []:
        if not isinstance(item, dict):
            raise ValueError("approval_required entries must declare timer and service")
        timer_name = str(item.get("timer") or "").strip()
        service = str(item.get("service") or "").strip()
        if not timer_name or not service:
            raise ValueError("approval_required entries must declare timer and service")
        timers.append(TimerUnit(timer=timer_name, service=service))
    return timers


def retired_units(manifest: dict[str, Any]) -> list[str]:
    return [str(unit) for unit in manifest.get("retired_forbidden") or []]


def retired_unit_files(manifest: dict[str, Any]) -> list[str]:
    return [str(unit) for unit in manifest.get("retired_unit_files") or []]


def _validate_timer_unit(timer: TimerUnit) -> None:
    timer_path = _deploy_path(timer.timer)
    service_path = _deploy_path(timer.service)
    if not timer_path.exists():
        raise FileNotFoundError(f"missing timer unit: {timer_path}")
    if not service_path.exists():
        raise FileNotFoundError(f"missing service unit for {timer.timer}: {service_path}")
    timer_text = _read_unit(timer.timer)
    if _timer_service(timer.timer) != timer.service:
        raise ValueError(f"{timer.timer} Unit= must point to {timer.service}")
    if "WantedBy=timers.target" not in timer_text:
        raise ValueError(f"{timer.timer} must install into timers.target")
    if "OnCalendar=" in timer_text and "Persistent=true" not in timer_text:
        raise ValueError(f"{timer.timer} uses OnCalendar and must set Persistent=true")


def _directive_values(body: str, directive: str) -> list[str]:
    prefix = f"{directive}="
    return [line.strip().split("=", 1)[1].strip() for line in body.splitlines() if line.strip().startswith(prefix)]


def _entrypoint_path(exec_start: str) -> Path | None:
    module_match = re.search(r"\bpython(?:3(?:\.\d+)*)?\s+-m\s+([A-Za-z_][A-Za-z0-9_.]*)", exec_start)
    if module_match:
        module_path = Path(*module_match.group(1).split("."))
        module_file = ROOT / module_path.with_suffix(".py")
        if module_file.exists():
            return module_file
        return ROOT / module_path / "__main__.py"
    script_match = re.search(r"\bpython(?:3(?:\.\d+)*)?\s+([A-Za-z0-9_./-]+\.py)\b", exec_start)
    if not script_match:
        return None
    relative_path = Path(script_match.group(1))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    return ROOT / relative_path


def _validate_managed_service(service: str) -> None:
    path = _deploy_path(service)
    if not path.exists():
        raise FileNotFoundError(f"missing managed service unit: {path}")
    body = _read_unit(service)
    if not _directive_values(body, "EnvironmentFile"):
        raise ValueError(f"{service} must declare EnvironmentFile")
    if _directive_values(body, "User") != ["ubuntu"]:
        raise ValueError(f"{service} must declare User=ubuntu")
    if _directive_values(body, "WorkingDirectory") != ["/home/ubuntu/极简 crm"]:
        raise ValueError(f"{service} must declare WorkingDirectory=/home/ubuntu/极简 crm")
    exec_starts = _directive_values(body, "ExecStart")
    if len(exec_starts) != 1:
        raise ValueError(f"{service} must declare exactly one ExecStart")
    entrypoint = _entrypoint_path(exec_starts[0])
    if entrypoint is None:
        raise ValueError(f"{service} ExecStart must reference a repository Python entrypoint")
    if not entrypoint.exists():
        raise FileNotFoundError(f"managed service entrypoint does not exist: {service}: {entrypoint}")


def _guarded_units(manifest: dict[str, Any]) -> list[str]:
    units = [
        primary_web_service(manifest).service,
        *(service.service for service in active_services(manifest)),
        *(unit.timer for unit in active_timers(manifest)),
        *(unit.service for unit in active_timers(manifest)),
        *(unit.timer for unit in approval_timers(manifest)),
        *(unit.service for unit in approval_timers(manifest)),
        *retired_units(manifest),
    ]
    return list(dict.fromkeys(units))


def _deploy_guard_source(manifest: dict[str, Any], unit: str) -> Path:
    if unit == primary_web_service(manifest).service:
        return PRIMARY_WEB_GUARD_SOURCE
    return DEPLOY_GUARD_SOURCE


def _deploy_guard_destination(service: str) -> Path:
    return SYSTEMD_DIR / f"{service}.d" / DEPLOY_GUARD_DROPIN


def _validate_deploy_guards() -> None:
    for source in (DEPLOY_GUARD_SOURCE, PRIMARY_WEB_GUARD_SOURCE):
        if not source.exists():
            raise FileNotFoundError(f"missing production deploy guard: {source}")
    generic_values = _directive_values(DEPLOY_GUARD_SOURCE.read_text(encoding="utf-8"), "ConditionPathExists")
    if generic_values != [f"|!{DEPLOY_GUARD_FILE}", f"|{RUNTIME_START_AUTHORIZATION_FILE}"]:
        raise ValueError(f"production deploy guard must block starts while {DEPLOY_GUARD_FILE} exists")
    primary_values = _directive_values(
        PRIMARY_WEB_GUARD_SOURCE.read_text(encoding="utf-8"),
        "ConditionPathExists",
    )
    if primary_values != [
        f"|!{DEPLOY_GUARD_FILE}",
        f"|{WEB_START_AUTHORIZATION_FILE}",
        f"|{RUNTIME_START_AUTHORIZATION_FILE}",
    ]:
        raise ValueError("primary Web deploy guard must require an idle transaction or explicit canary authorization")


def validate_manifest(manifest: dict[str, Any], *, validate_unit_files: bool = True) -> None:
    if manifest.get("schema_version") != 2:
        raise ValueError("production runtime units manifest schema_version must be 2")
    drain_timeout = int(manifest.get("timer_service_drain_timeout_seconds") or DEFAULT_TIMER_SERVICE_DRAIN_TIMEOUT_SECONDS)
    if drain_timeout < 1 or drain_timeout > 900:
        raise ValueError("timer_service_drain_timeout_seconds must be between 1 and 900")
    primary_web = primary_web_service(manifest)
    timers = active_timers(manifest)
    services = active_services(manifest)
    approval = approval_timers(manifest)
    approval_required = [unit.timer for unit in approval]
    retired_forbidden = retired_units(manifest)
    retired_files = retired_unit_files(manifest)
    retired_overlay_dropins = retired_dropins(manifest)
    active_timer_names = [unit.timer for unit in timers]
    active_service_names = [unit.service for unit in timers] + [unit.service for unit in services]
    _unique(active_timer_names + approval_required + retired_forbidden, "timer classification")
    _unique(active_service_names, "active service")
    _unique(retired_files, "retired unit file")
    _unique([f"{item.unit}.d/{item.dropin}" for item in retired_overlay_dropins], "retired drop-in")
    for item in retired_overlay_dropins:
        if not item.unit.endswith(".service"):
            raise ValueError(f"retired drop-in unit must be a service: {item.unit}")
        if not item.dropin.endswith(".conf") or Path(item.dropin).name != item.dropin:
            raise ValueError(f"retired drop-in must be a .conf basename: {item.dropin}")
    managed_service_names = [
        primary_web.service,
        *(service.service for service in services),
        *(unit.service for unit in timers),
        *(unit.service for unit in approval),
    ]
    _unique(managed_service_names, "managed service")
    overlaps = sorted(set(managed_service_names + active_timer_names + approval_required) & set(retired_forbidden))
    if overlaps:
        raise ValueError(f"retired units must not be managed: {overlaps}")
    invalid_retired_files = sorted(set(retired_files) - set(retired_forbidden))
    if invalid_retired_files:
        raise ValueError(f"retired unit files must also be retired_forbidden: {invalid_retired_files}")
    for unit in retired_files:
        if Path(unit).name != unit or not unit.endswith((".service", ".timer")):
            raise ValueError(f"retired unit file must be a systemd basename: {unit}")
    if validate_unit_files:
        _validate_deploy_guards()
        for unit in timers:
            _validate_timer_unit(unit)
        for unit in approval:
            _validate_timer_unit(unit)
        for service in managed_service_names:
            _validate_managed_service(service)


class Runner:
    def __init__(self, *, execute: bool) -> None:
        self.execute = execute

    def run(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str] | None:
        print(_shell_join(command))
        if not self.execute:
            return None
        return subprocess.run(command, cwd=ROOT, text=True, check=check)

    def systemctl(
        self,
        *args: str,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str] | None:
        if capture_output:
            command = ["sudo", "systemctl", *args]
            print(_shell_join(command))
            if not self.execute:
                return None
            return subprocess.run(command, cwd=ROOT, text=True, check=check, capture_output=True)
        return self.run(["sudo", "systemctl", *args], check=check)


def _shell_join(command: list[str]) -> str:
    return " ".join(_quote(part) for part in command)


def _quote(value: str) -> str:
    if not value:
        return "''"
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:=+-"
    if all(char in safe for char in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _copy_unit(runner: Runner, unit: str) -> None:
    runner.run(["sudo", "cp", f"deploy/{unit}", str(SYSTEMD_DIR) + "/"])


def _install_deploy_guard(manifest: dict[str, Any], runner: Runner) -> None:
    for unit in _guarded_units(manifest):
        destination = _deploy_guard_destination(unit)
        source = _deploy_guard_source(manifest, unit).relative_to(ROOT)
        runner.run(["sudo", "install", "-d", "-m", "0755", str(destination.parent)])
        runner.run(["sudo", "install", "-m", "0644", str(source), str(destination)])


def _verify_deploy_guard_installed(manifest: dict[str, Any], runner: Runner) -> None:
    for unit in _guarded_units(manifest):
        source = _deploy_guard_source(manifest, unit).relative_to(ROOT)
        destination = _deploy_guard_destination(unit)
        runner.run(["sudo", "test", "-f", str(destination)])
        runner.run(["sudo", "cmp", "-s", str(source), str(destination)])


def phase_begin_transaction(manifest: dict[str, Any], runner: Runner) -> None:
    _install_deploy_guard(manifest, runner)
    runner.run(["sudo", "rm", "-f", str(WEB_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "rm", "-f", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "touch", str(DEPLOY_GUARD_FILE)])
    runner.run(["sudo", "chmod", "0644", str(DEPLOY_GUARD_FILE)])
    runner.systemctl("daemon-reload")
    runner.run(["sudo", "test", "-e", str(DEPLOY_GUARD_FILE)])
    _verify_deploy_guard_installed(manifest, runner)


def phase_authorize_web_start(manifest: dict[str, Any], runner: Runner) -> None:
    runner.run(["sudo", "test", "-e", str(DEPLOY_GUARD_FILE)])
    _require_inactive(
        runner,
        primary_web_service(manifest).service,
        error_prefix="primary Web must be stopped before canary authorization",
    )
    runner.run(["sudo", "touch", str(WEB_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "chmod", "0644", str(WEB_START_AUTHORIZATION_FILE)])
    runner.systemctl("daemon-reload")
    runner.run(["sudo", "test", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    _verify_deploy_guard_installed(manifest, runner)


def phase_authorize_runtime_start(manifest: dict[str, Any], runner: Runner) -> None:
    runner.run(["sudo", "test", "-e", str(DEPLOY_GUARD_FILE)])
    runner.run(["sudo", "test", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    _require_active(
        runner,
        primary_web_service(manifest).service,
        error_prefix="primary Web must be active before runtime authorization",
    )
    runner.run(["sudo", "touch", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "chmod", "0644", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "rm", "-f", str(WEB_START_AUTHORIZATION_FILE)])
    runner.systemctl("daemon-reload")
    runner.run(["sudo", "test", "-e", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    _verify_deploy_guard_installed(manifest, runner)


def phase_authorize_runtime_restore(manifest: dict[str, Any], runner: Runner) -> None:
    """Resume timers after a stop transaction aborts before Web is stopped."""

    runner.run(["sudo", "test", "-e", str(DEPLOY_GUARD_FILE)])
    _require_active(
        runner,
        primary_web_service(manifest).service,
        error_prefix="primary Web must remain active for partial runtime restore",
    )
    runner.run(["sudo", "touch", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "chmod", "0644", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "rm", "-f", str(WEB_START_AUTHORIZATION_FILE)])
    runner.systemctl("daemon-reload")
    runner.run(["sudo", "test", "-e", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    _verify_deploy_guard_installed(manifest, runner)


def phase_release_runtime_guard(manifest: dict[str, Any], runner: Runner) -> None:
    runner.run(["sudo", "test", "-e", str(DEPLOY_GUARD_FILE)])
    runner.run(["sudo", "test", "-e", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    _require_active(
        runner,
        primary_web_service(manifest).service,
        error_prefix="primary Web must be active before runtime guard release",
    )
    _verify_desired_runtime_state(manifest, runner)
    runner.run(["sudo", "rm", "-f", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "rm", "-f", str(DEPLOY_GUARD_FILE)])
    runner.systemctl("daemon-reload")
    runner.run(["sudo", "test", "!", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(DEPLOY_GUARD_FILE)])
    _verify_deploy_guard_installed(manifest, runner)


def _retired_dropin_path(item: RetiredDropIn) -> Path:
    return SYSTEMD_DIR / f"{item.unit}.d" / item.dropin


def _verify_retired_dropins_absent(manifest: dict[str, Any], runner: Runner) -> None:
    for item in retired_dropins(manifest):
        runner.run(["sudo", "test", "!", "-e", str(_retired_dropin_path(item))])


def phase_retire_legacy_overlays(manifest: dict[str, Any], runner: Runner) -> None:
    for item in retired_dropins(manifest):
        runner.run(["sudo", "rm", "-f", str(_retired_dropin_path(item))])
    runner.systemctl("daemon-reload")
    _verify_retired_dropins_absent(manifest, runner)


def _timer_service_active_state(runner: Runner, service: str) -> str:
    proc = runner.systemctl(
        "show",
        service,
        "--property=ActiveState",
        "--value",
        check=False,
        capture_output=True,
    )
    if not runner.execute or proc is None:
        return "inactive"
    return (proc.stdout or "").strip().lower() or "unknown"


def _wait_for_timer_services_to_drain(manifest: dict[str, Any], runner: Runner, services: list[str]) -> None:
    unique_services = list(dict.fromkeys(services))
    timeout_seconds = int(manifest.get("timer_service_drain_timeout_seconds") or DEFAULT_TIMER_SERVICE_DRAIN_TIMEOUT_SECONDS)
    deadline = time.monotonic() + timeout_seconds
    while True:
        pending = {service: state for service in unique_services if (state := _timer_service_active_state(runner, service)) not in {"inactive", "failed"}}
        if not runner.execute or not pending:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            detail = ", ".join(f"{service}={state}" for service, state in sorted(pending.items()))
            raise RuntimeError(f"timer services did not drain within {timeout_seconds}s: {detail}")
        time.sleep(min(TIMER_SERVICE_DRAIN_POLL_INTERVAL_SECONDS, remaining))


def phase_stop_for_migration(manifest: dict[str, Any], runner: Runner) -> None:
    runner.run(["sudo", "test", "-e", str(DEPLOY_GUARD_FILE)])
    timers = [*active_timers(manifest), *approval_timers(manifest)]
    for unit in timers:
        runner.systemctl("stop", unit.timer, check=False)
    _wait_for_timer_services_to_drain(manifest, runner, [unit.service for unit in timers])
    for unit in timers:
        runner.systemctl("stop", unit.service, check=False)
    for unit in timers:
        runner.systemctl("reset-failed", unit.timer, check=False)
        runner.systemctl("reset-failed", unit.service, check=False)
        _require_inactive(runner, unit.timer, error_prefix="runtime timer did not stop")
        _require_inactive(runner, unit.service, error_prefix="runtime service did not stop")
        _require_not_failed(runner, unit.timer, error_prefix="runtime timer remains failed")
        _require_not_failed(runner, unit.service, error_prefix="runtime service remains failed")
    for service in active_services(manifest):
        runner.systemctl("stop", service.service, check=False)
        runner.systemctl("reset-failed", service.service, check=False)
        _require_inactive(runner, service.service, error_prefix="runtime service did not stop")
        _require_not_failed(runner, service.service, error_prefix="runtime service remains failed")
    for unit in retired_units(manifest):
        runner.systemctl("disable", "--now", unit, check=False)
        runner.systemctl("stop", unit, check=False)
        runner.systemctl("reset-failed", unit, check=False)
        _verify_retired_unit_state(runner, unit, allow_static=True)
    primary_web = primary_web_service(manifest).service
    runner.systemctl("stop", primary_web, check=False)
    runner.systemctl("reset-failed", primary_web, check=False)
    _require_inactive(runner, primary_web, error_prefix="primary Web did not stop")
    _require_not_failed(runner, primary_web, error_prefix="primary Web remains failed")


def _wait_for_health(url: str, *, execute: bool, attempts: int = 20, interval: float = 0.5) -> None:
    print(f"curl -sSf {url}")
    if not execute:
        return
    last_error = ""
    for _ in range(attempts):
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= int(response.status) < 300:
                    return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(interval)
    raise RuntimeError(f"health check failed for {url}: {last_error}")


def _is_enabled(runner: Runner, unit: str) -> bool:
    proc = runner.systemctl("is-enabled", unit, check=False)
    return bool(runner.execute and proc is not None and proc.returncode == 0)


def _require_active(runner: Runner, unit: str, *, error_prefix: str) -> None:
    proc = runner.systemctl("is-active", unit, check=False)
    if runner.execute and (proc is None or proc.returncode != 0):
        raise RuntimeError(f"{error_prefix}: {unit}")


def _require_inactive(runner: Runner, unit: str, *, error_prefix: str) -> None:
    proc = runner.systemctl("is-active", unit, check=False)
    if runner.execute and proc is not None and proc.returncode == 0:
        raise RuntimeError(f"{error_prefix}: {unit}")


def _require_enabled(runner: Runner, unit: str, *, error_prefix: str) -> None:
    proc = runner.systemctl("is-enabled", unit, check=False)
    if runner.execute and (proc is None or proc.returncode != 0):
        raise RuntimeError(f"{error_prefix}: {unit}")


def _require_not_failed(runner: Runner, unit: str, *, error_prefix: str) -> None:
    proc = runner.systemctl("is-failed", unit, check=False)
    if runner.execute and proc is not None and proc.returncode == 0:
        raise RuntimeError(f"{error_prefix}: {unit}")


def _verify_approval_timer_state(runner: Runner, unit: str) -> None:
    proc = runner.systemctl("is-enabled", unit, check=False)
    if not runner.execute:
        _require_active(runner, unit, error_prefix="enabled approval timer is not active")
        return
    if proc is not None and proc.returncode == 0:
        _require_active(runner, unit, error_prefix="enabled approval timer is not active")
    else:
        _require_inactive(runner, unit, error_prefix="disabled approval timer is still active")


def _verify_retired_unit_state(runner: Runner, unit: str, *, allow_static: bool = False) -> None:
    enabled = runner.systemctl("is-enabled", unit, check=False, capture_output=True)
    enabled_state = (enabled.stdout or "").strip() if enabled is not None else ""
    static_guard_only = allow_static and enabled_state == "static"
    if runner.execute and enabled is not None and enabled.returncode == 0 and not static_guard_only:
        raise RuntimeError(f"retired runtime unit is still enabled: {unit}")

    checks = (
        ("is-active", "retired runtime unit is still active"),
        ("is-failed", "retired runtime unit remains failed"),
    )
    for action, error_prefix in checks:
        proc = runner.systemctl(action, unit, check=False)
        if runner.execute and proc is not None and proc.returncode == 0:
            raise RuntimeError(f"{error_prefix}: {unit}")


def phase_install_primary_web(manifest: dict[str, Any], runner: Runner) -> None:
    service = primary_web_service(manifest).service
    for retired_file in retired_unit_files(manifest):
        runner.run(["sudo", "rm", "-f", str(SYSTEMD_DIR / retired_file)])
    _copy_unit(runner, service)
    _install_deploy_guard(manifest, runner)
    runner.systemctl("daemon-reload")
    runner.systemctl("enable", service)


def phase_install_enable_after_web_health(manifest: dict[str, Any], runner: Runner) -> None:
    services = active_services(manifest)
    timers = active_timers(manifest)
    approval = approval_timers(manifest)
    enabled_approval_timers = {unit.timer for unit in approval if _is_enabled(runner, unit.timer)}
    copied_services: set[str] = set()
    for service in services:
        _copy_unit(runner, service.service)
        copied_services.add(service.service)
    for unit in timers:
        if unit.service not in copied_services:
            _copy_unit(runner, unit.service)
            copied_services.add(unit.service)
        _copy_unit(runner, unit.timer)
    for unit in approval:
        if unit.service not in copied_services:
            _copy_unit(runner, unit.service)
            copied_services.add(unit.service)
        _copy_unit(runner, unit.timer)
    runner.systemctl("daemon-reload")
    for service in services:
        runner.systemctl("enable", service.service)
        runner.systemctl("restart", service.service)
        if service.health_url:
            _wait_for_health(service.health_url, execute=runner.execute)
        runner.systemctl("status", service.service, "--no-pager")
    for unit in timers:
        runner.systemctl("enable", unit.timer)
        runner.systemctl("restart", unit.timer)
        if unit.kick_after_timer_restart:
            proc = runner.systemctl("start", unit.service, check=False)
            if runner.execute and proc is not None and proc.returncode != 0:
                runner.systemctl("status", unit.service, "--no-pager", check=False)
                runner.run(["sudo", "journalctl", "-u", unit.service, "-n", "80", "--no-pager"], check=False)
                if unit.kick_failure_fatal:
                    raise RuntimeError(f"fatal runtime kick failed: {unit.service}")
        runner.systemctl("status", unit.timer, "--no-pager")
    for unit in approval:
        if unit.timer not in enabled_approval_timers:
            continue
        runner.systemctl("restart", unit.timer)
        runner.systemctl("status", unit.timer, "--no-pager")


def _verify_desired_runtime_state(manifest: dict[str, Any], runner: Runner) -> None:
    primary_web = primary_web_service(manifest).service
    _require_enabled(runner, primary_web, error_prefix="required runtime unit is not enabled")
    _require_active(
        runner,
        primary_web,
        error_prefix="required runtime unit is not active",
    )
    for service in active_services(manifest):
        _require_enabled(runner, service.service, error_prefix="required runtime unit is not enabled")
        _require_active(runner, service.service, error_prefix="required runtime unit is not active")
    for unit in active_timers(manifest):
        _require_enabled(runner, unit.timer, error_prefix="required runtime unit is not enabled")
        _require_active(runner, unit.timer, error_prefix="required runtime unit is not active")
    for unit in approval_timers(manifest):
        _verify_approval_timer_state(runner, unit.timer)
    for unit in retired_units(manifest):
        _verify_retired_unit_state(runner, unit)
    for unit in retired_unit_files(manifest):
        runner.run(["sudo", "test", "!", "-e", str(SYSTEMD_DIR / unit)])
    _verify_retired_dropins_absent(manifest, runner)
    approval_required = [unit.timer for unit in approval_timers(manifest)]
    if approval_required:
        print("approval_required_timers=" + ",".join(str(unit) for unit in approval_required))


def phase_verify_staged_runtime(manifest: dict[str, Any], runner: Runner) -> None:
    runner.run(["sudo", "test", "-e", str(DEPLOY_GUARD_FILE)])
    runner.run(["sudo", "test", "-e", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    _verify_deploy_guard_installed(manifest, runner)
    _verify_desired_runtime_state(manifest, runner)


def phase_verify(manifest: dict[str, Any], runner: Runner) -> None:
    runner.run(["sudo", "test", "!", "-e", str(WEB_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(RUNTIME_START_AUTHORIZATION_FILE)])
    runner.run(["sudo", "test", "!", "-e", str(DEPLOY_GUARD_FILE)])
    _verify_deploy_guard_installed(manifest, runner)
    _verify_desired_runtime_state(manifest, runner)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage approved AI-CRM production systemd runtime units.")
    parser.add_argument(
        "--phase",
        required=True,
        choices=(
            "authorize-runtime-start",
            "authorize-runtime-restore",
            "authorize-web-start",
            "begin-transaction",
            "retire-legacy-overlays",
            "stop-for-migration",
            "install-primary-web",
            "release-runtime-guard",
            "install-enable-after-web-health",
            "verify",
            "verify-staged-runtime",
        ),
    )
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args(argv)

    manifest = load_manifest(Path(args.manifest))
    validate_manifest(
        manifest,
        validate_unit_files=args.phase
        not in {
            "authorize-runtime-start",
            "authorize-runtime-restore",
            "authorize-web-start",
            "begin-transaction",
            "stop-for-migration",
            "release-runtime-guard",
        },
    )
    runner = Runner(execute=bool(args.execute and not args.dry_run))
    if args.phase == "authorize-runtime-start":
        phase_authorize_runtime_start(manifest, runner)
    elif args.phase == "authorize-runtime-restore":
        phase_authorize_runtime_restore(manifest, runner)
    elif args.phase == "authorize-web-start":
        phase_authorize_web_start(manifest, runner)
    elif args.phase == "begin-transaction":
        phase_begin_transaction(manifest, runner)
    elif args.phase == "retire-legacy-overlays":
        phase_retire_legacy_overlays(manifest, runner)
    elif args.phase == "stop-for-migration":
        phase_stop_for_migration(manifest, runner)
    elif args.phase == "install-primary-web":
        phase_install_primary_web(manifest, runner)
    elif args.phase == "release-runtime-guard":
        phase_release_runtime_guard(manifest, runner)
    elif args.phase == "install-enable-after-web-health":
        phase_install_enable_after_web_health(manifest, runner)
    elif args.phase == "verify":
        phase_verify(manifest, runner)
    elif args.phase == "verify-staged-runtime":
        phase_verify_staged_runtime(manifest, runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
