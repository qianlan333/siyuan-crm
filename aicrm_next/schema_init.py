from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from aicrm_next.customer_read_model.models import (
    customer_detail_snapshot_next,
    customer_list_index_next,
    customer_recent_message_next,
    customer_timeline_event_next,
)
from aicrm_next.ops_enrollment.models import (
    user_ops_do_not_disturb_next,
    user_ops_pool_current_next,
    user_ops_send_records_next,
)
from aicrm_next.shared.db_session import get_engine
from aicrm_next.auth_wecom.service import ensure_admin_sso_state_schema

SAFE_NEXT_SCHEMA_TABLES = (
    customer_list_index_next,
    customer_detail_snapshot_next,
    customer_timeline_event_next,
    customer_recent_message_next,
    user_ops_pool_current_next,
    user_ops_do_not_disturb_next,
    user_ops_send_records_next,
)
SAFE_NEXT_SCHEMA_SQL = Path(__file__).resolve().parents[1] / "scripts" / "siyuan_migration" / "06_safe_next_schema_init.sql"


def _sql_statements(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def init_next_schema_safe(engine: Engine | None = None, *, prefer_sql_file: bool | None = None) -> list[str]:
    """Create missing AI-CRM Next read-model tables and indexes without dropping data."""

    engine = engine or get_engine()
    if prefer_sql_file is None:
        prefer_sql_file = engine.dialect.name == "postgresql"

    if prefer_sql_file:
        sql = SAFE_NEXT_SCHEMA_SQL.read_text(encoding="utf-8")
        with engine.begin() as connection:
            for statement in _sql_statements(sql):
                connection.execute(text(statement))
        ensure_admin_sso_state_schema()
        return [table.name for table in SAFE_NEXT_SCHEMA_TABLES]

    for table in SAFE_NEXT_SCHEMA_TABLES:
        table.create(bind=engine, checkfirst=True)
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)
    ensure_admin_sso_state_schema()
    return [table.name for table in SAFE_NEXT_SCHEMA_TABLES]
