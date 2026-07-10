#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "deploy" / "production_runtime_units.json"
SYSTEMD_DIR = Path("/etc/systemd/system")


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
        services.append(ServiceUnit(service=str(item["service"]), health_url=item.get("health_url") or None))
    return services


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


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != 1:
        raise ValueError("production runtime units manifest schema_version must be 1")
    timers = active_timers(manifest)
    services = active_services(manifest)
    approval_required = [str(unit) for unit in manifest.get("approval_required") or []]
    retired_forbidden = [str(unit) for unit in manifest.get("retired_forbidden") or []]
    active_timer_names = [unit.timer for unit in timers]
    active_service_names = [unit.service for unit in timers] + [unit.service for unit in services]
    _unique(active_timer_names + approval_required + retired_forbidden, "timer classification")
    _unique(active_service_names, "active service")
    for service in services:
        if not _deploy_path(service.service).exists():
            raise FileNotFoundError(f"missing active service unit: {_deploy_path(service.service)}")
    for unit in timers:
        _validate_timer_unit(unit)
    for timer in approval_required:
        service = _timer_service(timer)
        if not service:
            raise ValueError(f"{timer} must declare Unit= before it can be approved")
        _validate_timer_unit(TimerUnit(timer=timer, service=service))


class Runner:
    def __init__(self, *, execute: bool) -> None:
        self.execute = execute

    def run(self, command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str] | None:
        print(_shell_join(command))
        if not self.execute:
            return None
        return subprocess.run(command, cwd=ROOT, text=True, check=check)

    def systemctl(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str] | None:
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


def phase_stop_for_migration(manifest: dict[str, Any], runner: Runner) -> None:
    for unit in active_timers(manifest):
        runner.systemctl("stop", unit.timer, check=False)
        runner.systemctl("stop", unit.service, check=False)


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


def phase_install_enable_after_web_health(manifest: dict[str, Any], runner: Runner) -> None:
    services = active_services(manifest)
    timers = active_timers(manifest)
    copied_services: set[str] = set()
    for service in services:
        _copy_unit(runner, service.service)
        copied_services.add(service.service)
    for unit in timers:
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
            proc = runner.systemctl("start", unit.service, check=unit.kick_failure_fatal)
            if runner.execute and proc is not None and proc.returncode != 0:
                runner.systemctl("status", unit.service, "--no-pager", check=False)
                runner.run(["sudo", "journalctl", "-u", unit.service, "-n", "80", "--no-pager"], check=False)
        runner.systemctl("status", unit.timer, "--no-pager")


def phase_verify(manifest: dict[str, Any], runner: Runner) -> None:
    for service in active_services(manifest):
        runner.systemctl("is-active", service.service)
    for unit in active_timers(manifest):
        runner.systemctl("is-active", unit.timer)
    approval_required = manifest.get("approval_required") or []
    if approval_required:
        print("approval_required_timers=" + ",".join(str(unit) for unit in approval_required))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage approved AI-CRM production systemd runtime units.")
    parser.add_argument(
        "--phase",
        required=True,
        choices=("stop-for-migration", "install-enable-after-web-health", "verify"),
    )
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument("--execute", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args(argv)

    manifest = load_manifest(Path(args.manifest))
    validate_manifest(manifest)
    runner = Runner(execute=bool(args.execute and not args.dry_run))
    if args.phase == "stop-for-migration":
        phase_stop_for_migration(manifest, runner)
    elif args.phase == "install-enable-after-web-health":
        phase_install_enable_after_web_health(manifest, runner)
    elif args.phase == "verify":
        phase_verify(manifest, runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
