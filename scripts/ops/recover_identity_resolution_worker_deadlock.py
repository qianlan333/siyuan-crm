#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable

try:
    from scripts.script_runtime import print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_runtime import print_json


SERVICE = "openclaw-identity-resolution-worker.service"
DEPLOY_GUARD_FILE = Path("/home/ubuntu/.aicrm-production-deploy-in-progress")
DEFAULT_MINIMUM_AGE_SECONDS = 120
CommandRunner = Callable[[list[str]], str]


_LEGACY_SELF_DEADLOCK_SQL = """
WITH matching_pairs AS (
    SELECT DISTINCT blocked.pid AS blocked_pid,
                    blocker.pid AS blocker_pid,
                    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - blocker.xact_start))::BIGINT AS blocker_age_seconds
    FROM pg_stat_activity blocked
    CROSS JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) blocking_pid
    JOIN pg_stat_activity blocker ON blocker.pid = blocking_pid
    WHERE blocked.wait_event_type = 'Lock'
      AND blocked.state = 'active'
      AND POSITION('insert into crm_user_identity_resolution_queue' IN lower(blocked.query)) > 0
      AND blocker.state = 'idle in transaction'
      AND POSITION('update crm_user_identity_resolution_queue q' IN lower(blocker.query)) > 0
      AND POSITION('for update skip locked' IN lower(blocker.query)) > 0
      AND POSITION('set status = ''polling''' IN lower(blocker.query)) > 0
      AND blocker.xact_start <= CURRENT_TIMESTAMP - make_interval(secs => %s)
)
SELECT COUNT(*)::BIGINT AS matching_deadlock_count,
       COALESCE(MAX(blocker_age_seconds), 0)::BIGINT AS oldest_blocker_age_seconds
FROM matching_pairs
"""


def _database_url() -> str:
    value = str(os.getenv("DATABASE_URL") or "").strip()
    if value.startswith("postgresql+psycopg://"):
        value = "postgresql://" + value[len("postgresql+psycopg://") :]
    if not value.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must be PostgreSQL")
    return value


def _connect() -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_database_url(), row_factory=dict_row, autocommit=True)


def collect_deadlock_evidence(conn: Any, *, minimum_age_seconds: int) -> dict[str, int]:
    row = conn.execute(
        _LEGACY_SELF_DEADLOCK_SQL,
        (max(DEFAULT_MINIMUM_AGE_SECONDS, int(minimum_age_seconds or DEFAULT_MINIMUM_AGE_SECONDS)),),
    ).fetchone()
    return {
        "matching_deadlock_count": int((row or {}).get("matching_deadlock_count") or 0),
        "oldest_blocker_age_seconds": int((row or {}).get("oldest_blocker_age_seconds") or 0),
    }


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
    return completed.stdout


def service_state(runner: CommandRunner, *, service: str = SERVICE) -> dict[str, Any]:
    output = runner(
        [
            "systemctl",
            "show",
            service,
            "--property=ActiveState",
            "--property=SubState",
            "--property=MainPID",
            "--no-pager",
        ]
    )
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return {
        "active_state": values.get("ActiveState", "unknown"),
        "sub_state": values.get("SubState", "unknown"),
        "main_pid_present": int(values.get("MainPID") or 0) > 0,
    }


def recover_deadlock(
    conn: Any,
    *,
    execute: bool,
    minimum_age_seconds: int = DEFAULT_MINIMUM_AGE_SECONDS,
    guard_file: Path = DEPLOY_GUARD_FILE,
    runner: CommandRunner = _run_command,
    service: str = SERVICE,
) -> dict[str, Any]:
    before = collect_deadlock_evidence(conn, minimum_age_seconds=minimum_age_seconds)
    state_before = service_state(runner, service=service)
    recovery_required = before["matching_deadlock_count"] > 0
    report: dict[str, Any] = {
        "ok": True,
        "execute": bool(execute),
        "service": service,
        "recovery_required": recovery_required,
        "recovered": False,
        "matching_deadlock_count_before": before["matching_deadlock_count"],
        "oldest_blocker_age_seconds": before["oldest_blocker_age_seconds"],
        "service_state_before": state_before,
        "matching_deadlock_count_after": before["matching_deadlock_count"],
        "service_state_after": state_before,
        "pii_included": False,
    }
    if not execute or not recovery_required:
        return report
    if not guard_file.exists():
        return {**report, "ok": False, "reason": "deploy_transaction_guard_missing"}
    if state_before["active_state"] not in {"active", "activating"} or not state_before["main_pid_present"]:
        return {**report, "ok": False, "reason": "matching_deadlock_not_owned_by_active_worker"}

    runner(["sudo", "systemctl", "stop", service])
    runner(["sudo", "systemctl", "reset-failed", service])

    after = before
    state_after = state_before
    for _ in range(20):
        after = collect_deadlock_evidence(conn, minimum_age_seconds=minimum_age_seconds)
        state_after = service_state(runner, service=service)
        if after["matching_deadlock_count"] == 0 and state_after["active_state"] == "inactive":
            break
        time.sleep(0.25)
    recovered = after["matching_deadlock_count"] == 0 and state_after["active_state"] == "inactive"
    return {
        **report,
        "ok": recovered,
        "recovered": recovered,
        "matching_deadlock_count_after": after["matching_deadlock_count"],
        "service_state_after": state_after,
        "reason": "" if recovered else "deadlock_recovery_incomplete",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover only the proven legacy identity-resolution worker self-deadlock during a guarded deploy."
    )
    parser.add_argument("--execute", action="store_true", help="Stop the worker only when the exact legacy self-deadlock is present.")
    parser.add_argument("--minimum-age-seconds", type=int, default=DEFAULT_MINIMUM_AGE_SECONDS)
    parser.add_argument("--guard-file", type=Path, default=DEPLOY_GUARD_FILE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        with _connect() as conn:
            report = recover_deadlock(
                conn,
                execute=bool(args.execute),
                minimum_age_seconds=int(args.minimum_age_seconds),
                guard_file=Path(args.guard_file),
            )
    except Exception as exc:
        report = {
            "ok": False,
            "execute": bool(args.execute),
            "reason": "deadlock_recovery_check_failed",
            "error_type": type(exc).__name__,
            "pii_included": False,
        }
    print_json(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
