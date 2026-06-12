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

REPLY_MONITOR_SERVICE = ROOT / "aicrm_next" / "automation_engine" / "timers.py"
RUNTIME_API = ROOT / "aicrm_next" / "automation_engine" / "api.py"
TEST_FILE = ROOT / "tests" / "test_reply_monitor_run_due_invalid_phone.py"

SEND_SENTINEL_TABLES = ["user_ops_send_records", "outbound_tasks"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_check() -> dict[str, Any]:
    service_source = _read(REPLY_MONITOR_SERVICE)
    api_source = _read(RUNTIME_API)
    test_source = _read(TEST_FILE)
    item_level_failure = all(
        token in service_source
        for token in [
            "PlanReplyMonitorRunDueCommand",
            "next_reply_monitor_run_due_plan",
            "reply_monitor_run_due_executed",
            "SideEffectPlan",
        ]
    )
    systemd_compatible_status = "api_plan_automation_conversion_reply_monitor_run_due" in api_source and "status_code" in api_source
    sentinel_covered = all(table in test_source for table in SEND_SENTINEL_TABLES)
    invalid_phone_tested = "invalid phone" in test_source and "response.status_code == 200" in test_source
    blockers: list[str] = []
    if not item_level_failure:
        blockers.append("reply_monitor_item_level_failure_policy_missing")
    if not systemd_compatible_status:
        blockers.append("reply_monitor_partial_failure_not_mapped_to_2xx")
    if not sentinel_covered:
        blockers.append("send_side_effect_sentinel_missing")
    if not invalid_phone_tested:
        blockers.append("invalid_phone_2xx_test_missing")
    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": [],
        "item_level_failure_policy": item_level_failure,
        "systemd_compatible_2xx_policy": systemd_compatible_status,
        "invalid_phone_route_test": invalid_phone_tested,
        "send_side_effect_sentinel_tables": SEND_SENTINEL_TABLES,
        "send_side_effect_sentinel_covered": sentinel_covered,
        "timers_enabled_by_this_change": False,
        "recommendation": "READY_FOR_REPLY_MONITOR_RUN_DUE_TIMER_VALIDATION_NOT_ENABLED" if not blockers else "REPLY_MONITOR_RUN_DUE_NOT_READY",
    }


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Reply Monitor Run-Due Readiness",
            "",
            f"- ok: {result['ok']}",
            f"- blockers: {result['blockers']}",
            f"- item_level_failure_policy: {result['item_level_failure_policy']}",
            f"- systemd_compatible_2xx_policy: {result['systemd_compatible_2xx_policy']}",
            f"- send_side_effect_sentinel_covered: {result['send_side_effect_sentinel_covered']}",
            f"- timers_enabled_by_this_change: {result['timers_enabled_by_this_change']}",
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
