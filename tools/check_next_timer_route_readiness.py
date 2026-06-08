#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
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

TIMER_ROUTES = [
    "/api/admin/automation-conversion/reply-monitor/run-due",
    "/api/admin/automation-conversion/reply-monitor/capture",
    "/api/admin/automation-conversion/jobs/run-due",
    "/api/admin/cloud-orchestrator/campaigns/run-due",
]

DB_SENTINEL_QUERIES = {
    "automation_reply_monitor_config.updated_at": "SELECT MAX(updated_at)::text AS value FROM automation_reply_monitor_config",
    "automation_sop_batch.max_id": "SELECT MAX(id)::text AS value FROM automation_sop_batch",
    "automation_sop_batch_item.max_id": "SELECT MAX(id)::text AS value FROM automation_sop_batch_item",
    "automation_sop_progress.updated_at": "SELECT MAX(updated_at)::text AS value FROM automation_sop_progress",
    "automation_workflow_execution.max_id": "SELECT MAX(id)::text AS value FROM automation_workflow_execution",
    "automation_workflow_execution_item.max_id": "SELECT MAX(id)::text AS value FROM automation_workflow_execution_item",
    "user_ops_send_records.max_id": "SELECT MAX(id)::text AS value FROM user_ops_send_records",
    "outbound_tasks.max_id": "SELECT MAX(id)::text AS value FROM outbound_tasks",
}


@contextmanager
def timer_probe_env():
    keys = {
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"),
        "AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN": os.environ.get("AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
    }
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    os.environ.setdefault("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    os.environ.setdefault("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    os.environ.setdefault("SECRET_KEY", "next-timer-route-readiness")
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
    except Exception as exc:  # pragma: no cover - depends on live production DB
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


def run_check() -> dict[str, Any]:
    with timer_probe_env():
        client = _client()
        results: dict[str, Any] = {}
        sentinel_before = _read_db_sentinel()
        probe_token = os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
        for route in TIMER_ROUTES:
            unauth = client.post(route, json={}, follow_redirects=False)
            header_dry_run = client.post(
                route,
                json={},
                headers={"Authorization": f"Bearer {probe_token}", "X-AICRM-Dry-Run": "1"},
                follow_redirects=False,
            )
            body_dry_run = client.post(
                route,
                json={"dry_run": True},
                headers={"Authorization": f"Bearer {probe_token}"},
                follow_redirects=False,
            )
            query_dry_run = client.post(
                f"{route}?dry_run=true",
                json={},
                headers={"Authorization": f"Bearer {probe_token}"},
                follow_redirects=False,
            )
            dry_run_payloads = []
            for response in [header_dry_run, body_dry_run, query_dry_run]:
                try:
                    dry_run_payloads.append(response.json())
                except Exception:
                    dry_run_payloads.append({})
            results[route] = {
                "unauth_status": unauth.status_code,
                "header_dry_run_status": header_dry_run.status_code,
                "body_dry_run_status": body_dry_run.status_code,
                "query_dry_run_status": query_dry_run.status_code,
                "route_not_404": unauth.status_code != 404
                and header_dry_run.status_code != 404
                and body_dry_run.status_code != 404
                and query_dry_run.status_code != 404,
                "auth_guard_present": unauth.status_code in {401, 403},
                "dry_run_or_noop_available": all(response.status_code == 200 for response in [header_dry_run, body_dry_run, query_dry_run]),
                "dry_run_noop": all(
                    payload.get("ok") is True
                    and payload.get("dry_run") is True
                    and payload.get("side_effect_executed", False) is False
                    and payload.get("fallback_used") is False
                    and payload.get("route_owner") == "ai_crm_next"
                    and payload.get("compatibility_facade") is None
                    and payload.get("real_external_call_executed") is False
                    for payload in dry_run_payloads
                ),
                "dry_run_payloads": dry_run_payloads,
            }
        sentinel_after = _read_db_sentinel()
        db_sentinel = _sentinel_comparison(sentinel_before, sentinel_after)
        overview = client.get("/api/admin/automation-conversion/overview", follow_redirects=False)
        try:
            overview_payload: Any = overview.json()
        except Exception:
            overview_payload = {}
        automation_production_data_ready = (
            overview.status_code == 200
            and str(overview_payload.get("generated_at") or "").strip().lower() != "fixture"
            and str(overview_payload.get("status") or "").strip().lower() != "partial"
            and str(overview_payload.get("source_status") or "").strip().lower() == "production_postgres"
        )
    blockers = [
        route
        for route, payload in results.items()
        if not payload["route_not_404"]
        or not payload["auth_guard_present"]
        or not payload["dry_run_or_noop_available"]
        or not payload["dry_run_noop"]
    ]
    if not db_sentinel["ok"]:
        blockers.append("dry_run_db_sentinel_not_passed")
    warnings: list[str] = []
    if not automation_production_data_ready:
        warnings.append("automation_production_data_not_ready")
    result = {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "timer_routes": results,
        "automation_overview_status": overview.status_code,
        "automation_overview": overview_payload,
        "automation_production_data_ready": automation_production_data_ready,
        "dry_run_db_sentinel": db_sentinel,
        "safe_to_enable_timers": not blockers and not warnings and db_sentinel["ok"],
        "recommendation": "READY_TO_ENABLE_TIMERS_AFTER_SERVER_ENV_TOKEN_VERIFICATION" if not blockers and not warnings else "TIMER_ROUTE_GUARD_READY_WITH_SERVER_DATA_WARNING" if not blockers else "TIMER_ROUTES_NOT_READY",
    }
    return result


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if output_md:
        lines = [
            "# Next Timer Route Readiness",
            "",
            f"- ok: {result['ok']}",
            f"- safe_to_enable_timers: {result['safe_to_enable_timers']}",
            f"- automation_production_data_ready: {result['automation_production_data_ready']}",
            f"- blockers: {result['blockers']}",
            f"- warnings: {result['warnings']}",
            "",
            "## Timer Routes",
        ]
        for route, payload in result["timer_routes"].items():
            lines.append(
                f"- {route}: unauth={payload['unauth_status']} "
                f"header_dry_run={payload['header_dry_run_status']} "
                f"body_dry_run={payload['body_dry_run_status']} "
                f"query_dry_run={payload['query_dry_run_status']} "
                f"guard={payload['auth_guard_present']}"
            )
        lines.extend(["", "## DB Sentinel", f"- status: {result['dry_run_db_sentinel']['status']}"])
        Path(output_md).write_text("\n".join(lines) + "\n")


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
