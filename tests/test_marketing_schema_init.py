from __future__ import annotations

from pathlib import Path

import pytest

from wecom_ability_service.db import get_db, init_db

REQUIRED_TABLES = {
    "marketing_automation_configs",
    "marketing_automation_question_rules",
    "customer_value_segment_current",
    "customer_value_segment_history",
    "customer_marketing_state_current",
    "customer_marketing_state_history",
    "conversion_dispatch_log",
}

REQUIRED_INDEXES = {
    "idx_customer_value_segment_current_external_userid",
    "idx_customer_value_segment_current_segment",
    "idx_customer_marketing_state_current_external_userid",
    "idx_customer_marketing_state_current_main_stage",
    "idx_customer_marketing_state_current_sub_stage",
    "idx_customer_marketing_state_current_eligible_for_conversion",
    "idx_conversion_dispatch_log_batch_id",
    "idx_conversion_dispatch_log_external_userid",
    "idx_conversion_dispatch_log_dispatch_status",
}


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


def _pg_object_names(db, object_type: str) -> set[str]:
    """Return current-schema table or index names."""
    if object_type == "table":
        rows = db.execute(
            """
            SELECT table_name AS name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
            """
        ).fetchall()
    elif object_type == "index":
        rows = db.execute(
            """
            SELECT indexname AS name
            FROM pg_indexes
            WHERE schemaname = current_schema()
            """
        ).fetchall()
    else:
        rows = []
    return {str(row["name"]) for row in rows}


def test_init_db_creates_marketing_automation_tables_and_indexes_idempotently(app):
    with app.app_context():
        init_db()
        init_db()

        db = get_db()
        table_names = _pg_object_names(db, "table")
        index_names = _pg_object_names(db, "index")

        assert REQUIRED_TABLES.issubset(table_names)
        assert REQUIRED_INDEXES.issubset(index_names)


def test_init_db_backfills_missing_marketing_automation_tables_on_existing_pg_db(app):
    with app.app_context():
        init_db()

        db = get_db()
        for table_name in [
            "conversion_dispatch_log",
            "customer_marketing_state_history",
            "customer_marketing_state_current",
            "customer_value_segment_history",
            "customer_value_segment_current",
            "marketing_automation_question_rules",
            "marketing_automation_configs",
        ]:
            db.execute(f"DROP TABLE IF EXISTS {table_name}")
        db.commit()

        init_db()

        table_names = _pg_object_names(db, "table")
        assert REQUIRED_TABLES.issubset(table_names)


def test_postgres_schema_includes_required_marketing_automation_tables_and_indexes():
    schema_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "schema_postgres.sql"
    schema_text = schema_path.read_text(encoding="utf-8")

    for table_name in REQUIRED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in schema_text

    for index_name in REQUIRED_INDEXES:
        assert f"CREATE INDEX IF NOT EXISTS {index_name}" in schema_text


def test_postgres_init_adds_program_id_columns_before_schema_indexes():
    db_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "db" / "migrations" / "postgres_migrations.py"
    source = db_path.read_text(encoding="utf-8")
    init_postgres_source = source[source.index("def _init_postgres") :]
    schema_replay_index = init_postgres_source.index("schema_path = Path(current_app.root_path) / \"schema_postgres.sql\"")

    for table_name in (
        "automation_profile_segment_template",
        "automation_workflow",
        "automation_workflow_execution",
    ):
        table_index = init_postgres_source.index(f"ALTER TABLE IF EXISTS {table_name}")
        assert "ADD COLUMN IF NOT EXISTS program_id BIGINT" in init_postgres_source[table_index:schema_replay_index]
        assert table_index < schema_replay_index


def test_postgres_init_keeps_index_prerequisite_alters_before_schema_replay_only():
    db_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "db" / "migrations" / "postgres_migrations.py"
    source = db_path.read_text(encoding="utf-8")
    init_postgres_source = source[source.index("def _init_postgres") :]
    schema_replay_index = init_postgres_source.index("schema_path = Path(current_app.root_path) / \"schema_postgres.sql\"")
    before_schema = init_postgres_source[:schema_replay_index]
    after_schema = init_postgres_source[schema_replay_index:]

    for fragment in (
        "ADD COLUMN IF NOT EXISTS scenario_code TEXT NOT NULL DEFAULT 'one_to_one'",
        "ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT ''",
        "ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'approved'",
        "ADD COLUMN IF NOT EXISTS created_by_agent TEXT NOT NULL DEFAULT ''",
        "ADD COLUMN IF NOT EXISTS last_error_text TEXT NOT NULL DEFAULT ''",
        "ADD COLUMN IF NOT EXISTS last_error_at TEXT NOT NULL DEFAULT ''",
        "ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS next_node_id BIGINT",
        "ADD COLUMN IF NOT EXISTS segment_id BIGINT",
        "ADD COLUMN IF NOT EXISTS campaign_id BIGINT",
    ):
        assert fragment in before_schema
        assert fragment not in after_schema


def test_postgres_init_backfills_miniprogram_thumb_image_id_column():
    db_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "db" / "migrations" / "postgres_migrations.py"
    source = db_path.read_text(encoding="utf-8")

    assert "def _ensure_postgres_miniprogram_library_thumb_image_id" in source
    assert "ALTER TABLE IF EXISTS miniprogram_library" in source
    assert "ADD COLUMN IF NOT EXISTS thumb_image_id BIGINT" in source
    assert "_ensure_postgres_miniprogram_library_thumb_image_id(db)" in source


def test_postgres_init_backfills_hxc_dashboard_v6_columns():
    db_path = Path(__file__).resolve().parents[1] / "wecom_ability_service" / "db" / "migrations" / "postgres_migrations.py"
    source = db_path.read_text(encoding="utf-8")

    assert "_HXC_DASHBOARD_V6_COLUMN_DEFS" in source
    assert '"hxc_member_level", "TEXT NOT NULL DEFAULT \'\'' in source
    assert '"active_goals_count", "INTEGER NOT NULL DEFAULT 0"' in source
    assert '"growth_credit_balance", "INTEGER"' in source
    assert "ADD COLUMN IF NOT EXISTS {name} {column_type}" in source
    assert "_ensure_postgres_hxc_dashboard_v6_columns(db)" in source
