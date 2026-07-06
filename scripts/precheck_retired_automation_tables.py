#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path


ensure_repo_root_on_path()


DROP_CANDIDATES = [
    "automation_event_v2",
    "automation_membership_v2",
    "automation_stage_entry_v2",
    "automation_task_plan_v2",
    "automation_program",
    "automation_program_config_block",
    "automation_program_member",
    "automation_program_member_stage_history",
    "automation_program_admission_attempt",
    "automation_program_channel_binding",
    "automation_member_audience_entry",
    "automation_operation_task",
    "automation_member",
    "automation_execution_trace",
    "conversion_dispatch_log",
    "automation_workflow",
    "automation_workflow_goal",
    "automation_workflow_node",
    "automation_workflow_node_transition",
    "automation_workflow_node_content",
    "automation_workflow_node_content_variant",
    "automation_workflow_execution",
    "automation_workflow_execution_item",
    "automation_event",
]


PRESERVE_SAMPLES = [
    "automation_channel",
    "automation_channel_contact",
    "automation_channel_assignee",
    "automation_channel_assignment_event",
    "automation_channel_entry_effect_log",
    "automation_channel_qrcode_asset",
    "automation_channel_scene_alias",
    "automation_agent_config",
    "automation_agent_run",
    "automation_agent_llm_call_log",
    "automation_agent_output",
    "automation_agents",
    "automation_agent_idempotency",
    "automation_agent_audit_log",
]


TEMPORAL_TYPES = {
    "timestamp with time zone",
    "timestamp without time zone",
    "date",
}


TIME_NAMES = {
    "created_at",
    "updated_at",
    "occurred_at",
    "raw_occurred_at",
    "entered_at",
    "exited_at",
    "joined_at",
    "started_at",
    "finished_at",
    "completed_at",
    "scheduled_at",
    "due_at",
    "published_at",
    "archived_at",
    "bound_at",
    "unbound_at",
    "last_run_at",
    "next_run_at",
    "submitted_at",
}


class PsqlReadOnlyClient:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def query_lines(self, sql: str) -> list[str]:
        command = [
            "psql",
            self.database_url,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            sql,
        ]
        output = subprocess.check_output(command, text=True)
        return [line for line in output.splitlines() if line]

    def scalar(self, sql: str) -> str:
        lines = self.query_lines(sql)
        return lines[0] if lines else ""


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def table_exists(client: PsqlReadOnlyClient, table_name: str) -> bool:
    return client.scalar(f"SELECT to_regclass('public.{table_name}') IS NOT NULL") == "t"


def table_columns(client: PsqlReadOnlyClient, table_name: str) -> list[dict[str, str]]:
    lines = client.query_lines(
        "SELECT column_name || '|' || data_type "
        "FROM information_schema.columns "
        f"WHERE table_schema = 'public' AND table_name = {sql_literal(table_name)} "
        "ORDER BY ordinal_position"
    )
    columns: list[dict[str, str]] = []
    for line in lines:
        name, data_type = line.split("|", 1)
        columns.append({"name": name, "data_type": data_type})
    return columns


def temporal_columns(columns: list[dict[str, str]]) -> list[str]:
    selected: list[str] = []
    for column in columns:
        name = column["name"]
        if column["data_type"] not in TEMPORAL_TYPES:
            continue
        if name in TIME_NAMES or name.endswith("_at") or name.endswith("_date"):
            selected.append(name)
    return selected


def non_temporal_time_like_columns(columns: list[dict[str, str]]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for column in columns:
        name = column["name"]
        if column["data_type"] in TEMPORAL_TYPES:
            continue
        if name in TIME_NAMES or name.endswith("_at") or name.endswith("_date"):
            selected.append(column)
    return selected


def inspect_table(client: PsqlReadOnlyClient, table_name: str, *, window_days: int) -> dict[str, Any]:
    exists = table_exists(client, table_name)
    item: dict[str, Any] = {
        "table": table_name,
        "exists": exists,
    }
    if not exists:
        return item

    columns = table_columns(client, table_name)
    temporal = temporal_columns(columns)
    item.update(
        {
            "total_count": count_rows(client, table_name),
            "temporal_columns": temporal,
            "non_temporal_time_like_columns": non_temporal_time_like_columns(columns),
            "recent_window_count": recent_rows(client, table_name, temporal, window_days=window_days),
            "max_times": max_times(client, table_name, temporal),
        }
    )
    return item


def count_rows(client: PsqlReadOnlyClient, table_name: str) -> int:
    value = client.scalar(f"SELECT count(*) FROM public.{sql_identifier(table_name)}")
    return int(value or "0")


def recent_rows(client: PsqlReadOnlyClient, table_name: str, temporal: list[str], *, window_days: int) -> int | None:
    if not temporal:
        return None
    predicate = " OR ".join(
        f"{sql_identifier(column)} >= now() - interval '{int(window_days)} days'"
        for column in temporal
    )
    value = client.scalar(f"SELECT count(*) FROM public.{sql_identifier(table_name)} WHERE {predicate}")
    return int(value or "0")


def max_times(client: PsqlReadOnlyClient, table_name: str, temporal: list[str]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for column in temporal:
        value = client.scalar(
            f"SELECT max({sql_identifier(column)})::text FROM public.{sql_identifier(table_name)}"
        )
        result[column] = value or None
    return result


def parse_pg_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) >= 3 and normalized[-3] in {"+", "-"} and normalized[-2:].isdigit():
        normalized = f"{normalized}:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def timestamp_sort_key(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


def latest_table_time(item: dict[str, Any]) -> str | None:
    latest: datetime | None = None
    latest_text: str | None = None
    for value in (item.get("max_times") or {}).values():
        parsed = parse_pg_timestamp(value)
        if parsed is None:
            continue
        if latest is None or timestamp_sort_key(parsed) > timestamp_sort_key(latest):
            latest = parsed
            latest_text = value
    return latest_text


def blocker_summary(recent_blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "table": item.get("table"),
            "recent_window_count": item.get("recent_window_count"),
            "total_count": item.get("total_count"),
            "latest_time": latest_table_time(item),
        }
        for item in recent_blockers
    ]


def earliest_safe_recheck_at(recent_blockers: list[dict[str, Any]], *, window_days: int) -> str | None:
    latest: datetime | None = None
    for item in recent_blockers:
        latest_text = latest_table_time(item)
        parsed = parse_pg_timestamp(latest_text)
        if parsed is None:
            continue
        if latest is None or timestamp_sort_key(parsed) > timestamp_sort_key(latest):
            latest = parsed
    if latest is None:
        return None
    return (latest + timedelta(days=int(window_days))).isoformat()


def run_precheck(client: PsqlReadOnlyClient, *, window_days: int) -> dict[str, Any]:
    drop_candidates = [
        inspect_table(client, table_name, window_days=window_days)
        for table_name in DROP_CANDIDATES
    ]
    preserve_samples = [
        inspect_table(client, table_name, window_days=window_days)
        for table_name in PRESERVE_SAMPLES
    ]
    recent_blockers = [
        item for item in drop_candidates
        if item.get("exists") and (item.get("recent_window_count") or 0) > 0
    ]
    missing_drop_candidates = [
        item["table"] for item in drop_candidates
        if not item.get("exists")
    ]
    safe_to_drop = not recent_blockers
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "window_days": window_days,
        "safe_to_drop": safe_to_drop,
        "existing_drop_candidate_count": sum(1 for item in drop_candidates if item.get("exists")),
        "missing_drop_candidates": missing_drop_candidates,
        "latest_recent_blocker_time": None if safe_to_drop else earliest_safe_recheck_at(recent_blockers, window_days=0),
        "earliest_safe_recheck_at": None if safe_to_drop else earliest_safe_recheck_at(recent_blockers, window_days=window_days),
        "recent_blocker_summary": blocker_summary(recent_blockers),
        "recent_blockers": recent_blockers,
        "drop_candidates": drop_candidates,
        "preserve_samples": preserve_samples,
        "notes": [
            "This precheck is read-only and does not create, update, delete, truncate, or drop data.",
            "PR-4 physical cleanup can proceed only when recent_blockers is empty.",
            "earliest_safe_recheck_at is derived from recent blocker max timestamps plus window_days; rerun precheck before creating a drop migration.",
            "Preserve samples are inspected to catch accidental inclusion of channel/agent tables in cleanup scope.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only precheck before physically dropping retired automation runtime/program tables."
    )
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print(json.dumps({"ok": False, "error": "database_url_missing"}, ensure_ascii=False), file=sys.stderr)
        return 2

    payload = run_precheck(PsqlReadOnlyClient(database_url), window_days=max(1, int(args.window_days or 7)))
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
