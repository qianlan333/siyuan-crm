from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "migrations" / "versions" / "0074_drop_user_ops_legacy_tables.py"
CONFTST_PATH = ROOT / "tests" / "conftest.py"

USER_OPS_LEGACY_TABLES = {
    "user_ops_lead_pool_current",
    "user_ops_lead_pool_history",
    "user_ops_pool_current",
    "user_ops_pool_history",
    "user_ops_send_records",
    "user_ops_deferred_jobs",
}


def test_user_ops_legacy_drop_migration_has_exact_batch_a_scope() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in USER_OPS_LEGACY_TABLES:
        assert f'"{table_name}"' in source
        assert f"DROP TABLE IF EXISTS {{table_name}} CASCADE" in source
        assert '"CREATE " "TABLE IF NOT EXISTS"' in source

    assert "user_ops_pool_current_next" not in source
    assert "user_ops_send_records_next" not in source


def test_user_ops_legacy_tables_removed_from_fixture_truncate_list() -> None:
    source = CONFTST_PATH.read_text(encoding="utf-8")

    for table_name in USER_OPS_LEGACY_TABLES:
        assert f'"{table_name}"' not in source
