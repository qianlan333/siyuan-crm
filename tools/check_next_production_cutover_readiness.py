#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_next_production_runtime_gaps import run_check as run_gap_check
from tools.check_active_automation_run_due_guardrails import run_check as run_active_automation_guardrail_check


def run_check() -> dict[str, Any]:
    gaps = run_gap_check()
    active_guardrails = run_active_automation_guardrail_check()
    route_404_blockers = gaps.get("route_404_blockers", [])
    content_blockers = gaps.get("content_blockers", [])
    oauth_blockers = gaps.get("oauth_blockers", [])
    callback_ready = not any("callback" in item or "api/wecom/events" in item for item in route_404_blockers)
    payment_routes_ready = not any("wechat-pay" in item or "alipay" in item for item in route_404_blockers)
    oauth_routes_ready = not any("oauth" in item for item in route_404_blockers) and not oauth_blockers
    active_guardrails_ok = bool(active_guardrails.get("ok"))
    active_guardrail_db_sentinel_ok = bool((active_guardrails.get("db_sentinel") or {}).get("ok"))
    legacy_fallbacks_still_required = [
        "5013 callback fallback until Next callback observation window passes",
        "legacy payment/OAuth/WeCom domain services via Next compatibility facade",
    ]
    result = {
        "ok": gaps.get("ok", False) and active_guardrails_ok,
        "database_mode": gaps.get("database_mode"),
        "fixture_in_production": False,
        "route_404_blockers": route_404_blockers,
        "content_blockers": content_blockers,
        "oauth_blockers": oauth_blockers,
        "callback_ready": callback_ready,
        "payment_routes_ready": payment_routes_ready,
        "oauth_routes_ready": oauth_routes_ready,
        "legacy_fallbacks_still_required": legacy_fallbacks_still_required,
        "safe_to_enable_timers": False,
        "safe_to_remove_5013_callback_fallback": False,
        "production_config_modified": gaps.get("production_config_modified", False),
        "runtime_gap_check": gaps,
        "active_automation_guardrails_ok": active_guardrails_ok,
        "active_guardrail_db_sentinel_ok": active_guardrail_db_sentinel_ok,
        "active_automation_guardrails": active_guardrails,
    }
    return result


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if output_md:
        lines = [
            "# Next Production Cutover Readiness",
            "",
            f"- ok: {result['ok']}",
            f"- database_mode: {result['database_mode']}",
            f"- route_404_blockers: {result['route_404_blockers']}",
            f"- content_blockers: {result['content_blockers']}",
            f"- oauth_blockers: {result['oauth_blockers']}",
            f"- callback_ready: {result['callback_ready']}",
            f"- payment_routes_ready: {result['payment_routes_ready']}",
            f"- oauth_routes_ready: {result['oauth_routes_ready']}",
            f"- safe_to_enable_timers: {result['safe_to_enable_timers']}",
            f"- active_automation_guardrails_ok: {result['active_automation_guardrails_ok']}",
            f"- active_guardrail_db_sentinel_ok: {result['active_guardrail_db_sentinel_ok']}",
            f"- safe_to_remove_5013_callback_fallback: {result['safe_to_remove_5013_callback_fallback']}",
            "",
            "## Legacy Fallbacks Still Required",
        ]
        for item in result["legacy_fallbacks_still_required"]:
            lines.append(f"- {item}")
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
