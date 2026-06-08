from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POSTGRES_MIGRATIONS = ROOT / "wecom_ability_service" / "db" / "migrations" / "postgres_migrations.py"
ALEMBIC_GROUP_OPS = ROOT / "migrations" / "versions" / "0015_group_ops_plans.py"

GROUP_OPS_TABLES = {
    "automation_group_ops_plans",
    "automation_group_ops_plan_groups",
    "automation_group_ops_plan_nodes",
    "automation_group_ops_webhook_events",
    "wecom_group_chat_snapshots",
}


def test_group_ops_schema_is_covered_by_production_init_db_bootstrap() -> None:
    source = POSTGRES_MIGRATIONS.read_text(encoding="utf-8")
    bootstrap_source = source[
        source.index("def _ensure_postgres_group_ops_tables") : source.index("def _init_postgres")
    ]
    init_source = source[source.index("def _init_postgres") :]

    assert "_ensure_postgres_group_ops_tables(db)" in init_source
    for table_name in GROUP_OPS_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in bootstrap_source


def test_group_ops_alembic_tables_match_production_bootstrap_tables() -> None:
    migration_source = ALEMBIC_GROUP_OPS.read_text(encoding="utf-8")
    bootstrap_source = POSTGRES_MIGRATIONS.read_text(encoding="utf-8")

    for table_name in GROUP_OPS_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in migration_source
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in bootstrap_source


def test_group_ops_node_content_package_column_is_bootstrapped() -> None:
    migration_source = ALEMBIC_GROUP_OPS.read_text(encoding="utf-8")
    bootstrap_source = POSTGRES_MIGRATIONS.read_text(encoding="utf-8")
    followup_migration = (ROOT / "migrations" / "versions" / "0016_group_ops_node_content_package.py").read_text(encoding="utf-8")

    assert "content_package_json JSONB NOT NULL DEFAULT '{}'::jsonb" in migration_source
    assert "ADD COLUMN IF NOT EXISTS content_package_json JSONB NOT NULL DEFAULT '{}'::jsonb" in followup_migration
    assert "content_package_json JSONB NOT NULL DEFAULT '{}'::jsonb" in bootstrap_source


def test_group_ops_admin_userids_column_is_bootstrapped() -> None:
    migration_source = ALEMBIC_GROUP_OPS.read_text(encoding="utf-8")
    bootstrap_source = POSTGRES_MIGRATIONS.read_text(encoding="utf-8")
    followup_migration = (ROOT / "migrations" / "versions" / "0027_group_ops_admin_userids.py").read_text(encoding="utf-8")

    assert "admin_userids TEXT NOT NULL DEFAULT '[]'" in migration_source
    assert "ADD COLUMN IF NOT EXISTS admin_userids TEXT NOT NULL DEFAULT '[]'" in followup_migration
    assert "admin_userids TEXT NOT NULL DEFAULT '[]'" in bootstrap_source
