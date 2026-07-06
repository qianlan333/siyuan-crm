from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFTST_PATH = ROOT / "tests" / "conftest.py"
DROP_MIGRATION_PATH = ROOT / "migrations" / "versions" / "0053_retire_legacy_automation_tables.py"
LEGACY_COLUMN_MIGRATION_PATH = ROOT / "migrations" / "versions" / "0004_cloud_orchestrator.py"

AUTOMATION_BATCH_C_TABLES = {
    "automation_event",
    "automation_operation_task",
    "automation_workflow_execution",
    "automation_workflow_execution_item",
}


def test_batch_c_tables_are_already_dropped_by_0053() -> None:
    source = DROP_MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in AUTOMATION_BATCH_C_TABLES:
        assert f'"{table_name}"' in source
    assert "DROP TABLE IF EXISTS {table_name} CASCADE" in source


def test_batch_c_tables_are_not_recreated_by_test_fixture() -> None:
    source = CONFTST_PATH.read_text(encoding="utf-8")

    for table_name in AUTOMATION_BATCH_C_TABLES:
        assert f'"{table_name}"' not in source
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" not in source


def test_legacy_column_migration_skips_absent_retired_tables() -> None:
    source = LEGACY_COLUMN_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "def _has_table" in source
    assert "if _has_table(table) and not _has_column(table, column_name):" in source
