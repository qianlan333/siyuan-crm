from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from scripts import precheck_retired_automation_tables as precheck


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_retirement_migration():
    path = PROJECT_ROOT / "migrations" / "versions" / "0053_retire_legacy_automation_tables.py"
    spec = importlib.util.spec_from_file_location("retire_legacy_automation_tables_0053", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_automation_member_retirement_migration():
    path = PROJECT_ROOT / "migrations" / "versions" / "0070_retire_automation_member_table.py"
    spec = importlib.util.spec_from_file_location("retire_automation_member_table_0070", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_conversion_trace_retirement_migration():
    path = PROJECT_ROOT / "migrations" / "versions" / "0071_retire_conversion_trace_tables.py"
    spec = importlib.util.spec_from_file_location("retire_conversion_trace_tables_0071", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retired_automation_precheck_scope_keeps_agent_and_channel_tables_out_of_drop_candidates():
    drop_tables = set(precheck.DROP_CANDIDATES)
    preserve_tables = set(precheck.PRESERVE_SAMPLES)

    assert "automation_event_v2" in drop_tables
    assert "automation_membership_v2" in drop_tables
    assert "automation_task_plan_v2" in drop_tables
    assert "automation_program_channel_binding" in drop_tables
    assert "automation_program" in drop_tables
    assert "automation_member" in drop_tables
    assert "automation_execution_trace" in drop_tables
    assert "conversion_dispatch_log" in drop_tables

    assert "automation_channel_contact" in preserve_tables
    assert "automation_channel_qrcode_asset" in preserve_tables
    assert "automation_agent_config" in preserve_tables
    assert "automation_agent_run" in preserve_tables
    assert "automation_agent_llm_call_log" in preserve_tables
    assert "automation_agent_output" in preserve_tables

    assert not (drop_tables & preserve_tables)


def test_retired_automation_drop_migration_matches_precheck_scope():
    migration = _load_retirement_migration()
    member_migration = _load_automation_member_retirement_migration()
    trace_migration = _load_conversion_trace_retirement_migration()
    drop_tables = set(migration.DROP_TABLES) | set(member_migration.DROP_TABLES) | set(trace_migration.DROP_TABLES)

    assert set(precheck.DROP_CANDIDATES) <= drop_tables
    assert not (drop_tables & set(precheck.PRESERVE_SAMPLES))
    assert "automation_agent_run" not in drop_tables
    assert "automation_channel_contact" not in drop_tables
    assert "ai_audience_package" not in drop_tables
    assert "automation_member_interaction_stats" in set(member_migration.DROP_VIEWS)
    assert "idx_conversion_dispatch_log_external_dispatched" in set(trace_migration.DROP_INDEXES)


def test_temporal_detection_keeps_text_time_like_columns_out_of_recent_predicate():
    columns = [
        {"name": "created_at", "data_type": "timestamp with time zone"},
        {"name": "entered_at", "data_type": "text"},
        {"name": "finished_at", "data_type": "text"},
        {"name": "payload_json", "data_type": "jsonb"},
    ]

    assert precheck.temporal_columns(columns) == ["created_at"]
    assert precheck.non_temporal_time_like_columns(columns) == [
        {"name": "entered_at", "data_type": "text"},
        {"name": "finished_at", "data_type": "text"},
    ]


def test_precheck_derives_safe_recheck_time_from_recent_blocker_max_times():
    blocker = {
        "table": "automation_event_v2",
        "exists": True,
        "total_count": 69,
        "recent_window_count": 1,
        "max_times": {
            "created_at": "2026-06-23 09:07:39.557454+08",
            "occurred_at": "2026-06-23 09:07:39.557198+08",
        },
    }

    assert precheck.latest_table_time(blocker) == "2026-06-23 09:07:39.557454+08"
    assert precheck.blocker_summary([blocker]) == [
        {
            "table": "automation_event_v2",
            "recent_window_count": 1,
            "total_count": 69,
            "latest_time": "2026-06-23 09:07:39.557454+08",
        }
    ]
    assert precheck.earliest_safe_recheck_at([blocker], window_days=7) == "2026-06-30T09:07:39.557454+08:00"


def test_run_precheck_blocks_physical_drop_when_recent_drop_candidate_exists(monkeypatch):
    monkeypatch.setattr(precheck, "DROP_CANDIDATES", ["automation_event_v2", "automation_program"])
    monkeypatch.setattr(precheck, "PRESERVE_SAMPLES", ["automation_channel_contact", "automation_agent_output"])

    def fake_inspect_table(_client, table_name, *, window_days):
        if table_name == "automation_event_v2":
            return {
                "table": table_name,
                "exists": True,
                "total_count": 1,
                "recent_window_count": 1,
                "max_times": {"created_at": "2026-06-23 09:07:39.557454+08"},
            }
        return {"table": table_name, "exists": True, "recent_window_count": 0}

    monkeypatch.setattr(precheck, "inspect_table", fake_inspect_table)

    result = precheck.run_precheck(object(), window_days=7)

    assert result["safe_to_drop"] is False
    assert result["latest_recent_blocker_time"] == "2026-06-23T09:07:39.557454+08:00"
    assert result["earliest_safe_recheck_at"] == "2026-06-30T09:07:39.557454+08:00"
    assert result["recent_blocker_summary"] == [
        {
            "table": "automation_event_v2",
            "recent_window_count": 1,
            "total_count": 1,
            "latest_time": "2026-06-23 09:07:39.557454+08",
        }
    ]
    assert [item["table"] for item in result["recent_blockers"]] == ["automation_event_v2"]
    assert {item["table"] for item in result["preserve_samples"]} == {
        "automation_channel_contact",
        "automation_agent_output",
    }


def test_main_requires_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(precheck.sys, "argv", ["precheck_retired_automation_tables.py"])

    exit_code = precheck.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.err)["error"] == "database_url_missing"


def test_psql_client_uses_psql_read_only_query_shape(monkeypatch):
    captured = {}

    def fake_check_output(command, *, text):
        captured["command"] = command
        captured["text"] = text
        return "t\n"

    monkeypatch.setattr(precheck.subprocess, "check_output", fake_check_output)

    client = precheck.PsqlReadOnlyClient("postgresql://example")
    assert client.scalar("SELECT 1") == "t"

    command = captured["command"]
    assert command[:2] == ["psql", "postgresql://example"]
    assert "-X" in command
    assert "ON_ERROR_STOP=1" in command
    assert "-At" in command
    assert command[-1] == "SELECT 1"
