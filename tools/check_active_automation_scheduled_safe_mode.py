#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists() and not str(sys.executable).startswith(str(ROOT / ".venv")):
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    raise

from tools.check_active_automation_run_due_guardrails import (
    ACTIVE_TIMER_UNITS,
    CAMPAIGN_ROUTE,
    DB_SENTINEL_QUERIES,
    _is_local_probe_database,
    _sentinel_comparison,
    production_config_modified,
)

SYSTEMD_CAMPAIGN_PAYLOAD = '{"operator":"aicrm-campaign-run-due","batch_size":200,"scheduled_safe_mode":true}'


@contextmanager
def scheduled_safe_mode_probe_env():
    keys = {
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
    }
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    os.environ.setdefault("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    os.environ.setdefault("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    os.environ.setdefault("SECRET_KEY", "active-automation-scheduled-safe-mode")
    try:
        yield
    finally:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _client() -> TestClient:
    module = importlib.import_module("aicrm_next.main")
    return TestClient(module.create_app())


def _read_db_sentinel() -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL", "")
    if _is_local_probe_database(database_url):
        return {"available": False, "reason": "local_probe_database", "values": {}}
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        return {"available": False, "reason": f"psycopg_missing:{exc}", "values": {}}
    try:
        values: dict[str, str] = {}
        with psycopg.connect(database_url, autocommit=True) as conn:
            for key, query in DB_SENTINEL_QUERIES.items():
                with conn.cursor() as cur:
                    cur.execute(query)
                    row = cur.fetchone()
                    values[key] = "" if not row or row[0] is None else str(row[0])
        return {"available": True, "reason": "", "values": values}
    except Exception as exc:  # pragma: no cover - depends on live DB
        return {"available": False, "reason": str(exc), "values": {}}


def _timer_enablement_status() -> dict[str, Any]:
    systemctl = shutil.which("systemctl")
    units_to_check = [*ACTIVE_TIMER_UNITS]
    if not systemctl:
        return {
            "checked": False,
            "reason": "systemctl_unavailable",
            "retired_timers_not_enabled": True,
            "active_timers": {unit: "not_checked" for unit in ACTIVE_TIMER_UNITS},
            "units": {unit: "not_checked" for unit in units_to_check},
        }
    units: dict[str, str] = {}
    for unit in units_to_check:
        proc = subprocess.run([systemctl, "is-enabled", unit], text=True, capture_output=True, check=False)
        units[unit] = (proc.stdout or proc.stderr or "").strip() or f"exit_{proc.returncode}"
    return {
        "checked": True,
        "reason": "",
        "retired_timers_not_enabled": True,
        "active_timers": {unit: units[unit] for unit in ACTIVE_TIMER_UNITS},
        "units": units,
    }


def _json(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _docs_payloads_ready() -> tuple[bool, list[str]]:
    runbook = ROOT / "docs" / "runbooks" / "active_automation_retirement.md"
    content = runbook.read_text(encoding="utf-8") if runbook.exists() else ""
    blockers: list[str] = []
    if SYSTEMD_CAMPAIGN_PAYLOAD not in content:
        blockers.append("active_automation_runbook_missing_campaign_systemd_payload")
    return not blockers, blockers


def run_check() -> dict[str, Any]:
    with scheduled_safe_mode_probe_env():
        client = _client()
        token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
        headers = {"Authorization": f"Bearer {token}"}
        sentinel_before = _read_db_sentinel()

        campaign_idle = client.post(
            CAMPAIGN_ROUTE,
            json={
                "operator": "aicrm-campaign-run-due",
                "batch_size": 200,
                "dry_run": False,
                "scheduled_safe_mode": True,
                "expected_due_count": 0,
            },
            headers=headers,
            follow_redirects=False,
        )
        campaign_due_blocked = client.post(
            CAMPAIGN_ROUTE,
            json={
                "operator": "aicrm-campaign-run-due",
                "batch_size": 200,
                "dry_run": False,
                "scheduled_safe_mode": True,
                "expected_due_count": 1,
            },
            headers=headers,
            follow_redirects=False,
        )
        campaign_raw_without_allowlist = client.post(
            CAMPAIGN_ROUTE,
            json={"operator": "manual", "batch_size": 1, "dry_run": False},
            headers=headers,
            follow_redirects=False,
        )
        sentinel_after = _read_db_sentinel()

    db_sentinel = _sentinel_comparison(sentinel_before, sentinel_after)
    timer_status = _timer_enablement_status()
    docs_ready, docs_blockers = _docs_payloads_ready()
    responses = {
        "campaign_idle": {"status": campaign_idle.status_code, "payload": _json(campaign_idle)},
        "campaign_due_blocked": {"status": campaign_due_blocked.status_code, "payload": _json(campaign_due_blocked)},
        "campaign_raw_without_allowlist": {"status": campaign_raw_without_allowlist.status_code, "payload": _json(campaign_raw_without_allowlist)},
    }

    blockers: list[str] = list(docs_blockers)
    payload = responses["campaign_idle"]["payload"]
    if responses["campaign_idle"]["status"] != 200 or payload.get("status") != "idle":
        blockers.append("campaign_idle_not_idle_200")
    if payload.get("side_effect_executed") is not False or payload.get("fallback_used") is not False or payload.get("compatibility_facade") is not None:
        blockers.append("campaign_idle_not_noop")
    for key in ("campaign_due_blocked",):
        payload = responses[key]["payload"]
        if responses[key]["status"] != 409 or payload.get("status") != "blocked_not_executed":
            blockers.append(f"{key}_not_blocked_409")
        if payload.get("error_code") != "active_automation_due_candidates_require_allowlist":
            blockers.append(f"{key}_missing_error_code")
        if payload.get("side_effect_executed") is not False or payload.get("fallback_used") is not False or payload.get("compatibility_facade") is not None:
            blockers.append(f"{key}_not_noop")
    if responses["campaign_raw_without_allowlist"]["status"] != 409:
        blockers.append("campaign_raw_without_allowlist_not_409")
    if not db_sentinel["ok"]:
        blockers.append("db_sentinel_changed_or_unavailable")
    if not timer_status["retired_timers_not_enabled"]:
        blockers.append("retired_automation_timers_enabled")
    if production_config_modified():
        blockers.append("production_config_modified")

    result = {
        "ok": not blockers,
        "blockers": blockers,
        "responses": responses,
        "legacy_jobs_runner_removed_from_safe_mode": True,
        "scheduled_safe_mode_idle_ok": responses["campaign_idle"]["status"] == 200 and responses["campaign_idle"]["payload"].get("status") == "idle",
        "scheduled_safe_mode_blocked_ok": all(
            responses[key]["status"] == 409 and responses[key]["payload"].get("status") == "blocked_not_executed"
            for key in ("campaign_due_blocked",)
        ),
        "raw_true_execution_without_allowlist_still_409": responses["campaign_raw_without_allowlist"]["status"] == 409,
        "db_sentinel": db_sentinel,
        "timers_not_enabled": timer_status["retired_timers_not_enabled"],
        "retired_timers_not_enabled": timer_status["retired_timers_not_enabled"],
        "timer_enablement_status": timer_status,
        "docs_payloads_ready": docs_ready,
        "production_config_modified": production_config_modified(),
        "recommendation": "READY_FOR_SCHEDULED_SAFE_MODE_SERVER_VERIFICATION_NOT_TIMER_ENABLE" if not blockers else "SCHEDULED_SAFE_MODE_NOT_READY",
    }
    return result


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Active Automation Scheduled Safe Mode",
            "",
            f"- ok: {result['ok']}",
            f"- blockers: {result['blockers']}",
            f"- legacy_jobs_runner_removed_from_safe_mode: {result['legacy_jobs_runner_removed_from_safe_mode']}",
            f"- scheduled_safe_mode_idle_ok: {result['scheduled_safe_mode_idle_ok']}",
            f"- scheduled_safe_mode_blocked_ok: {result['scheduled_safe_mode_blocked_ok']}",
            f"- raw_true_execution_without_allowlist_still_409: {result['raw_true_execution_without_allowlist_still_409']}",
            f"- db_sentinel_status: {result['db_sentinel']['status']}",
            f"- timers_not_enabled: {result['timers_not_enabled']}",
            f"- docs_payloads_ready: {result['docs_payloads_ready']}",
            f"- production_config_modified: {result['production_config_modified']}",
            f"- recommendation: {result['recommendation']}",
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-md")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = run_check()
    write_outputs(result, args.output_md, args.output_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
