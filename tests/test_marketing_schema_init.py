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


def _sqlite_object_names(db, object_type: str) -> set[str]:
    """PG-only：用 information_schema 替代 SQLite 的 sqlite_master。

    object_type 仅支持 ``'table'`` / ``'index'``。
    """
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
        table_names = _sqlite_object_names(db, "table")
        index_names = _sqlite_object_names(db, "index")

        assert REQUIRED_TABLES.issubset(table_names)
        assert REQUIRED_INDEXES.issubset(index_names)


def test_init_db_backfills_missing_marketing_automation_tables_on_existing_sqlite_db(app):
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

        table_names = _sqlite_object_names(db, "table")
        assert REQUIRED_TABLES.issubset(table_names)


@pytest.mark.skip(reason="2026-05 砍 SQLite 后此 test 测的 SQLite migration 路径不再适用（AUTOINCREMENT / DROP TABLE 等 SQLite-only 语法）")
def test_init_db_adds_program_id_before_schema_indexes_on_existing_sqlite_db(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            CREATE TABLE automation_channel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_code TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                scene_value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE TABLE automation_profile_segment_template (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_code TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE TABLE automation_workflow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_code TEXT NOT NULL UNIQUE,
                workflow_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            CREATE TABLE automation_workflow_execution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id TEXT NOT NULL UNIQUE,
                workflow_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                scheduled_for TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.commit()

        init_db()

        channel_columns = {row["name"] for row in db.execute("PRAGMA table_info(automation_channel)").fetchall()}
        template_columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(automation_profile_segment_template)").fetchall()
        }
        workflow_columns = {row["name"] for row in db.execute("PRAGMA table_info(automation_workflow)").fetchall()}
        execution_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(automation_workflow_execution)").fetchall()
        }
        index_names = _sqlite_object_names(db, "index")
        assert "program_id" in channel_columns
        assert "program_id" in template_columns
        assert "program_id" in workflow_columns
        assert "program_id" in execution_columns
        assert "idx_automation_channel_program" in index_names
        assert "idx_automation_profile_segment_template_program" in index_names
        assert "idx_automation_workflow_program" in index_names
        assert "idx_automation_workflow_execution_program" in index_names


@pytest.mark.skip(reason="2026-05 砍 SQLite 后此 test 测的 SQLite migration 路径不再适用（DROP TABLE 等 SQLite-only 语法）")
def test_init_db_rebuilds_legacy_marketing_state_current_without_fake_external_userid(app):
    with app.app_context():
        init_db()
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (701, '13800138701', 'tp-701', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute("DROP TABLE customer_marketing_state_current")
        db.execute(
            """
            CREATE TABLE customer_marketing_state_current (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER,
                external_userid TEXT NOT NULL UNIQUE,
                automation_key TEXT NOT NULL DEFAULT 'signup_conversion_v1',
                main_stage TEXT NOT NULL DEFAULT 'pending',
                sub_stage TEXT NOT NULL DEFAULT '',
                eligible_for_conversion INTEGER NOT NULL DEFAULT 0,
                lifecycle_status TEXT NOT NULL DEFAULT 'idle',
                last_batch_id INTEGER,
                last_batch_status TEXT NOT NULL DEFAULT '',
                last_batch_window_start TEXT NOT NULL DEFAULT '',
                last_batch_window_end TEXT NOT NULL DEFAULT '',
                last_trigger_message_at TEXT NOT NULL DEFAULT '',
                entered_at TEXT,
                exited_at TEXT,
                exit_reason TEXT NOT NULL DEFAULT '',
                state_payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            INSERT INTO customer_marketing_state_current (
                id, person_id, external_userid, automation_key, main_stage, sub_stage,
                eligible_for_conversion, lifecycle_status, state_payload_json
            )
            VALUES (1, 701, 'person:701', 'signup_conversion_v1', 'prospect', 'mobile_only', 0, 'prospect', '{}')
            """
        )
        db.commit()

        init_db()

        rows = db.execute(
            """
            SELECT person_id, external_userid, sub_stage
            FROM customer_marketing_state_current
            WHERE person_id = 701
            """
        ).fetchall()
        assert [dict(row) for row in rows] == [
            {"person_id": 701, "external_userid": "", "sub_stage": "mobile_only"}
        ]

        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (702, '13800138702', 'tp-702', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO customer_marketing_state_current (
                person_id, external_userid, automation_key, main_stage, sub_stage,
                activated, converted, eligible_for_conversion, lifecycle_status,
                last_activation_at, last_conversion_marked_at, last_message_at,
                last_batch_status, last_batch_window_start, last_batch_window_end,
                last_trigger_message_at, exit_reason, state_payload_json
            )
            VALUES (?, '', 'signup_conversion_v1', 'prospect', 'mobile_only', 0, 0, 0, 'prospect', '', '', '', '', '', '', '', '', '{}')
            """,
            (702,),
        )
        db.commit()


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
