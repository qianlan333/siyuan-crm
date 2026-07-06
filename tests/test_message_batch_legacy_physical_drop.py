from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "migrations" / "versions" / "0075_drop_message_batch_legacy_tables.py"
CONFTST_PATH = ROOT / "tests" / "conftest.py"

MESSAGE_BATCH_LEGACY_TABLES = {
    "message_batches",
    "message_batch_items",
}


def test_message_batch_legacy_drop_migration_has_exact_batch_b_scope() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in MESSAGE_BATCH_LEGACY_TABLES:
        assert f'"{table_name}"' in source
    assert "DROP TABLE IF EXISTS {table_name} CASCADE" in source
    assert '"CREATE " "TABLE IF NOT EXISTS"' in source
    assert "broadcast_jobs" not in source
    assert "broadcast_job_events" not in source


def test_message_batch_legacy_tables_removed_from_fixture_truncate_list() -> None:
    source = CONFTST_PATH.read_text(encoding="utf-8")

    for table_name in MESSAGE_BATCH_LEGACY_TABLES:
        assert f'"{table_name}"' not in source
