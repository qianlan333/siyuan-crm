from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

EXPECTED_TABLES = {
    "user_ops_pool_current_next",
    "user_ops_do_not_disturb_next",
    "user_ops_send_records_next",
    "customer_list_index_next",
    "customer_detail_snapshot_next",
    "customer_timeline_event_next",
    "customer_recent_message_next",
}

pytestmark = pytest.mark.postgres_integration


def test_postgres_alembic_upgrade_and_downgrade(alembic_config: Config, safe_postgres_database_url: str) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    engine = create_engine(safe_postgres_database_url, future=True)
    try:
        table_names = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES <= table_names
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "base")
    engine = create_engine(safe_postgres_database_url, future=True)
    try:
        table_names = set(inspect(engine).get_table_names())
        assert EXPECTED_TABLES.isdisjoint(table_names)
    finally:
        engine.dispose()
