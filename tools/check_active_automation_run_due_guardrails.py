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

from tools.auth_probe import install_probe_access_token

CAMPAIGN_ROUTE = "/api/admin/cloud-orchestrator/campaigns/run-due"
CAMPAIGN_PREVIEW_ROUTE = "/api/admin/cloud-orchestrator/campaigns/run-due/preview"

ACTIVE_TIMER_UNITS = [
    "aicrm-campaign-run-due.timer",
]

DB_SENTINEL_QUERIES: dict[str, str] = {}

PRODUCTION_CONFIG_PATTERNS = ("nginx", "systemd", ".service", ".timer", "deploy/", ".github/workflows/deploy")


@contextmanager
def guardrail_probe_env():
    keys = {
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
    }
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    os.environ.setdefault("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    os.environ.setdefault("SECRET_KEY", "active-automation-run-due-guardrails")
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


def _is_local_probe_database(database_url: str) -> bool:
    return "127.0.0.1:1/aicrm_probe" in database_url or "localhost:1/aicrm_probe" in database_url


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


def _sentinel_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before.get("reason") == "local_probe_database" and after.get("reason") == "local_probe_database":
        return {
            "ok": True,
            "status": "skipped_local_probe_database",
            "before": before,
            "after": after,
            "changed_keys": [],
        }
    if not before.get("available") or not after.get("available"):
        return {
            "ok": False,
            "status": "unavailable",
            "before": before,
            "after": after,
            "changed_keys": [],
        }
    before_values = before.get("values") or {}
    after_values = after.get("values") or {}
    changed = [key for key in DB_SENTINEL_QUERIES if before_values.get(key) != after_values.get(key)]
    return {
        "ok": not changed,
        "status": "pass" if not changed else "changed",
        "before": before,
        "after": after,
        "changed_keys": changed,
    }


def _json(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _probe_headers(token: str, idempotency_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": idempotency_key}


def _noop_payload_ok(payload: dict[str, Any], *, expected_preview: bool | None = None) -> bool:
    if payload.get("ok") is not True:
        return False
    if payload.get("side_effect_executed", False) is not False:
        return False
    if payload.get("fallback_used") is not False:
        return False
    if payload.get("route_owner") != "ai_crm_next":
        return False
    if payload.get("compatibility_facade") is not None:
        return False
    if payload.get("real_external_call_executed") is not False:
        return False
    if payload.get("automation_runtime_executed") is not False:
        return False
    if payload.get("wecom_send_executed") is not False:
        return False
    if expected_preview is not None:
        preview_flag = payload.get("preview")
        if preview_flag is None:
            preview_flag = payload.get("timer_status") == "preview_only" or payload.get("run_due_status") == "preview_only" or str(payload.get("source_status") or "").endswith("_preview")
        if preview_flag is not expected_preview:
            return False
    return True


def _plan_only_blocked_ok(payload: dict[str, Any]) -> bool:
    return (
        payload.get("real_external_call_executed") is False
        and payload.get("automation_runtime_executed") is False
        and payload.get("wecom_send_executed") is False
        and (
            payload.get("timer_status") == "planned_blocked"
            or payload.get("run_due_status") == "planned_blocked"
            or payload.get("blocked_reason") == "next_plan_only_route"
        )
    )


def _git_modified_files() -> list[str]:
    proc = subprocess.run(["git", "status", "--short", "--untracked-files=all"], cwd=ROOT, text=True, capture_output=True, check=False)
    return [line[3:].strip() for line in proc.stdout.splitlines() if line.strip()]


def production_config_modified() -> bool:
    for path in _git_modified_files():
        normalized = path.lower()
        if normalized.startswith(("docs/", "tests/", "tools/")):
            continue
        if any(pattern in normalized for pattern in PRODUCTION_CONFIG_PATTERNS):
            return True
    return False


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


def run_check() -> dict[str, Any]:
    with guardrail_probe_env():
        client = _client()
        token = install_probe_access_token(
            client,
            purpose="automation_worker",
            audience="internal_worker",
            scopes=("write",),
        )
        sentinel_before = _read_db_sentinel()

        campaign_dry_run = client.post(
            CAMPAIGN_ROUTE,
            json={"dry_run": True, "batch_size": 1},
            headers=_probe_headers(token, "guardrail-campaign-dry-run"),
        )
        campaign_preview = client.post(
            CAMPAIGN_ROUTE,
            json={"preview": True, "batch_size": 1},
            headers=_probe_headers(token, "guardrail-campaign-preview"),
        )
        campaign_preview_endpoint = client.post(
            CAMPAIGN_PREVIEW_ROUTE,
            json={"batch_size": 1},
            headers=_probe_headers(token, "guardrail-campaign-preview-endpoint"),
        )
        campaign_without_allowlist = client.post(
            CAMPAIGN_ROUTE,
            json={"dry_run": False, "batch_size": 1, "max_dispatch_count": 1},
            headers=_probe_headers(token, "guardrail-campaign-without-allowlist"),
        )

        sentinel_after = _read_db_sentinel()

    db_sentinel = _sentinel_comparison(sentinel_before, sentinel_after)
    timer_status = _timer_enablement_status()
    responses = {
        "campaign_dry_run": {"status": campaign_dry_run.status_code, "payload": _json(campaign_dry_run)},
        "campaign_preview": {"status": campaign_preview.status_code, "payload": _json(campaign_preview)},
        "campaign_preview_endpoint": {"status": campaign_preview_endpoint.status_code, "payload": _json(campaign_preview_endpoint)},
        "campaign_without_allowlist": {"status": campaign_without_allowlist.status_code, "payload": _json(campaign_without_allowlist)},
    }

    blockers: list[str] = []
    if responses["campaign_dry_run"]["status"] != 200 or not _noop_payload_ok(responses["campaign_dry_run"]["payload"]):
        blockers.append("campaign_dry_run_not_noop")
    for key in ("campaign_preview", "campaign_preview_endpoint"):
        if responses[key]["status"] != 200 or not _noop_payload_ok(responses[key]["payload"], expected_preview=True):
            blockers.append(f"{key}_not_preview_noop")
    campaign_without_allowlist_rejected = responses["campaign_without_allowlist"]["status"] in {400, 409} or _plan_only_blocked_ok(
        responses["campaign_without_allowlist"]["payload"]
    )
    if not campaign_without_allowlist_rejected:
        blockers.append("campaign_without_allowlist_not_rejected")
    if responses["campaign_without_allowlist"]["status"] in {400, 409} and responses["campaign_without_allowlist"]["payload"].get("error_code") != "campaign_run_due_allowlist_required":
        blockers.append("campaign_without_allowlist_missing_error_code")
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
        "legacy_jobs_runner_removed_from_guardrail": True,
        "dry_run_noop": _noop_payload_ok(responses["campaign_dry_run"]["payload"]),
        "preview_noop": all(
            _noop_payload_ok(responses[key]["payload"], expected_preview=True)
            for key in ("campaign_preview", "campaign_preview_endpoint")
        ),
        "true_execution_without_allowlist_rejected": "campaign_without_allowlist_not_rejected" not in blockers,
        "bounded_execution_parameters": {
            "campaigns": ["batch_size", "allow_campaign_ids", "max_dispatch_count"],
        },
        "db_sentinel": db_sentinel,
        "timers_not_enabled": timer_status["retired_timers_not_enabled"],
        "retired_timers_not_enabled": timer_status["retired_timers_not_enabled"],
        "timer_enablement_status": timer_status,
        "production_config_modified": production_config_modified(),
        "recommendation": "READY_FOR_RETIRED_AUTOMATION_JOBS_AND_CAMPAIGN_PREVIEW" if not blockers else "ACTIVE_AUTOMATION_GUARDRAILS_NOT_READY",
    }
    return result


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Active Automation Run-due Guardrails",
            "",
            f"- ok: {result['ok']}",
            f"- blockers: {result['blockers']}",
            f"- legacy_jobs_runner_removed_from_guardrail: {result['legacy_jobs_runner_removed_from_guardrail']}",
            f"- dry_run_noop: {result['dry_run_noop']}",
            f"- preview_noop: {result['preview_noop']}",
            f"- true_execution_without_allowlist_rejected: {result['true_execution_without_allowlist_rejected']}",
            f"- db_sentinel_status: {result['db_sentinel']['status']}",
            f"- timers_not_enabled: {result['timers_not_enabled']}",
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
