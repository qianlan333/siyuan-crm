#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
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


READINESS_GET_ROUTES = [
    "/admin",
    "/admin/customers",
    "/admin/questionnaires",
    "/admin/wechat-pay/products",
    "/admin/image-library",
    "/admin/attachment-library",
    "/admin/miniprogram-library",
    "/admin/automation-conversion",
    "/api/customers",
    "/api/admin/questionnaires",
    "/api/admin/wechat-pay/products",
    "/api/admin/image-library",
    "/api/admin/attachment-library",
    "/api/admin/miniprogram-library",
    "/api/admin/automation-conversion/overview",
    "/api/h5/wechat/oauth/start?next=/admin",
    "/api/h5/wechat-pay/oauth/start?next=/admin",
]

READINESS_POST_ROUTES = [
    "/wecom/external-contact/callback",
    "/api/wecom/events",
    "/api/admin/automation-conversion/reply-monitor/run-due",
    "/api/admin/automation-conversion/reply-monitor/capture",
    "/api/admin/automation-conversion/jobs/run-due",
    "/api/admin/cloud-orchestrator/campaigns/run-due",
    "/api/h5/wechat-pay/notify",
    "/api/h5/wechat-pay/jsapi/orders",
]

PRODUCTION_CONFIG_PATTERNS = (
    "nginx",
    "systemd",
    ".service",
    ".timer",
    "deploy/",
    ".github/workflows/deploy",
)

QUESTIONNAIRE_FIXTURE_SLUGS = {"hxc-activation-v1", "disabled-demo"}
FIXTURE_STATUS_VALUES = {"fixture", "fake", "partial", "fixture_boundary"}


@contextmanager
def production_probe_env():
    old = {key: os.environ.get(key) for key in os.environ.keys()}
    os.environ.setdefault("AICRM_NEXT_ENV", "production")
    os.environ.setdefault("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    os.environ.setdefault("AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN", "1")
    os.environ.setdefault("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    os.environ.setdefault("SECRET_KEY", "next-production-runtime-gap-probe")
    os.environ.setdefault("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    try:
        yield
    finally:
        for key in list(os.environ.keys()):
            if key not in old:
                os.environ.pop(key, None)
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _client() -> TestClient:
    module = importlib.import_module("aicrm_next.main")
    return TestClient(module.create_app())


def _route_probe(client: TestClient) -> dict[str, Any]:
    probes: dict[str, Any] = {}
    for path in READINESS_GET_ROUTES:
        try:
            response = client.get(path, follow_redirects=False)
        except Exception as exc:
            probes[f"GET {path}"] = {
                "status_code": 503,
                "not_404": True,
                "route_owner": "",
                "facade": "",
                "location": "",
                "json": {"error": f"probe_route_unavailable:{exc.__class__.__name__}"},
            }
            continue
        json_payload: Any = None
        try:
            json_payload = response.json()
        except Exception:
            json_payload = None
        probes[f"GET {path}"] = {
            "status_code": response.status_code,
            "not_404": response.status_code != 404,
            "route_owner": response.headers.get("X-AICRM-Route-Owner", ""),
            "facade": response.headers.get("X-AICRM-Compatibility-Facade", ""),
            "location": response.headers.get("location", ""),
            "json": json_payload,
        }
    for path in READINESS_POST_ROUTES:
        try:
            response = client.post(path, json={}, headers={"X-AICRM-Dry-Run": "1"}, follow_redirects=False)
        except Exception as exc:
            probes[f"POST {path}"] = {
                "status_code": 503,
                "not_404": True,
                "route_owner": "",
                "facade": "",
                "json": {"error": f"probe_route_unavailable:{exc.__class__.__name__}"},
            }
            continue
        probes[f"POST {path}"] = {
            "status_code": response.status_code,
            "not_404": response.status_code != 404,
            "route_owner": response.headers.get("X-AICRM-Route-Owner", ""),
            "facade": response.headers.get("X-AICRM-Compatibility-Facade", ""),
        }
    return probes


def _git_modified_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    files: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        files.append(line[3:].strip())
    return files


def production_config_modified() -> bool:
    for path in _git_modified_files():
        normalized = path.lower()
        if normalized.startswith("docs/"):
            continue
        if any(pattern in normalized for pattern in PRODUCTION_CONFIG_PATTERNS):
            return True
    return False


def _static_fixture_modules() -> list[str]:
    targets = [
        "aicrm_next/customer_read_model/repo.py",
        "aicrm_next/questionnaire/repo.py",
        "aicrm_next/commerce/repo.py",
        "aicrm_next/media_library/repo.py",
        "aicrm_next/automation_engine/repo.py",
    ]
    return [target for target in targets if (ROOT / target).exists() and "fixture" in (ROOT / target).read_text()]


def _using_local_probe_database(database_url: str) -> bool:
    return "127.0.0.1:1/aicrm_probe" in database_url or "localhost:1/aicrm_probe" in database_url


def _questionnaire_content_blockers(routes: dict[str, Any], *, local_probe_database: bool) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    blockers: list[str] = []
    result = routes.get("GET /api/admin/questionnaires") or {}
    payload = result.get("json") if isinstance(result.get("json"), dict) else {}
    status = int(result.get("status_code") or 0)
    if status >= 500:
        item = f"questionnaire_production_data_unavailable status={status}"
        if local_probe_database:
            warnings.append(f"{item} in local probe DB")
        else:
            blockers.append(item)
        return blockers, warnings
    items = payload.get("questionnaires") or payload.get("items") or []
    slugs = {
        str(item.get("slug") or "").strip()
        for item in items
        if isinstance(item, dict) and str(item.get("slug") or "").strip()
    }
    if status == 200 and slugs and slugs.issubset(QUESTIONNAIRE_FIXTURE_SLUGS):
        blockers.append("questionnaire_fixture_demo_only")
    source_status = str(payload.get("source_status") or "").strip().lower()
    if source_status in FIXTURE_STATUS_VALUES:
        blockers.append(f"questionnaire_fixture_source_status={source_status}")
    return blockers, warnings


def _automation_content_blockers(routes: dict[str, Any], *, local_probe_database: bool) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    blockers: list[str] = []
    result = routes.get("GET /api/admin/automation-conversion/overview") or {}
    payload = result.get("json") if isinstance(result.get("json"), dict) else {}
    status = int(result.get("status_code") or 0)
    if status >= 500:
        item = f"automation_production_data_unavailable status={status}"
        if local_probe_database:
            warnings.append(f"{item} in local probe DB")
        else:
            blockers.append(item)
        return blockers, warnings
    generated_at = str(payload.get("generated_at") or "").strip().lower()
    status_value = str(payload.get("status") or "").strip().lower()
    source_status = str(payload.get("source_status") or "").strip().lower()
    if generated_at == "fixture":
        blockers.append("automation_generated_at_fixture")
    if status_value == "partial":
        blockers.append("automation_status_partial")
    if source_status in FIXTURE_STATUS_VALUES:
        blockers.append(f"automation_fixture_source_status={source_status}")
    return blockers, warnings


def _oauth_blockers(routes: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for path in ["/api/h5/wechat/oauth/start", "/api/h5/wechat-pay/oauth/start"]:
        route_name = next((name for name in routes if name.startswith(f"GET {path}")), f"GET {path}")
        result = routes.get(route_name) or {}
        status = int(result.get("status_code") or 0)
        payload = result.get("json") if isinstance(result.get("json"), dict) else {}
        location = str(result.get("location") or "")
        redirect_url = str(payload.get("redirect_url") or "")
        if status == 500 or status >= 502:
            blockers.append(f"oauth_start_500:{path}:{status}")
        if "localhost" in location or "localhost" in redirect_url:
            blockers.append(f"oauth_redirect_uri_localhost:{path}")
    return blockers


def run_check() -> dict[str, Any]:
    with production_probe_env():
        database_url = os.environ.get("DATABASE_URL", "")
        local_probe_database = _using_local_probe_database(database_url)
        client = _client()
        health = client.get("/health").json()
        routes = _route_probe(client)
    route_404_blockers = [name for name, result in routes.items() if not result["not_404"]]
    questionnaire_blockers, questionnaire_warnings = _questionnaire_content_blockers(
        routes, local_probe_database=local_probe_database
    )
    automation_blockers, automation_warnings = _automation_content_blockers(routes, local_probe_database=local_probe_database)
    oauth_blockers = _oauth_blockers(routes)
    content_blockers = questionnaire_blockers + automation_blockers
    warnings = questionnaire_warnings + automation_warnings
    timer_disabled = [
        "aicrm-reply-monitor-run-due.timer",
        "aicrm-reply-monitor-capture.timer",
        "aicrm-automation-jobs-run-due.timer",
        "aicrm-campaign-run-due.timer",
    ]
    result = {
        "ok": not route_404_blockers and not content_blockers and not oauth_blockers and not production_config_modified(),
        "health": health,
        "database_mode": health.get("database_mode"),
        "fixture_in_production": bool(health.get("fixture_mode")) and os.getenv("AICRM_NEXT_ENV") == "production",
        "route_results": routes,
        "route_404_blockers": route_404_blockers,
        "content_blockers": content_blockers,
        "oauth_blockers": oauth_blockers,
        "warnings": warnings,
        "questionnaire_production_data_ready": not questionnaire_blockers and not questionnaire_warnings,
        "automation_production_data_ready": not automation_blockers and not automation_warnings,
        "timers_currently_disabled": timer_disabled,
        "callback_currently_has_5013_fallback": True,
        "fixture_only_modules_present": _static_fixture_modules(),
        "fake_or_disabled_adapter_warning": "D7 fake/staging-disabled adapters remain contract-only unless production env enables real adapters.",
        "production_config_modified": production_config_modified(),
    }
    return result


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if output_md:
        lines = [
            "# Next Production Runtime Gaps",
            "",
            f"- ok: {result['ok']}",
            f"- database_mode: {result['database_mode']}",
            f"- production_config_modified: {result['production_config_modified']}",
            f"- route_404_blockers: {result['route_404_blockers']}",
            f"- content_blockers: {result['content_blockers']}",
            f"- oauth_blockers: {result['oauth_blockers']}",
            f"- warnings: {result['warnings']}",
            f"- callback_currently_has_5013_fallback: {result['callback_currently_has_5013_fallback']}",
            "",
            "## Routes",
        ]
        for name, payload in result["route_results"].items():
            lines.append(f"- {name}: {payload['status_code']} not_404={payload['not_404']} facade={payload['facade']}")
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
