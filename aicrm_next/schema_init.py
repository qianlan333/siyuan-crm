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
SAFE_NEXT_SCHEMA_EXTRA_TABLE_NAMES = (
    "automation_event_v2",
    "automation_membership_v2",
    "automation_stage_entry_v2",
    "automation_task_plan_v2",
    "wechat_shop_refunds",
    "wechat_shop_sync_runs",
)
SAFE_NEXT_SCHEMA_SQL = Path(__file__).resolve().parents[1] / "scripts" / "siyuan_migration" / "06_safe_next_schema_init.sql"


def _sql_statements(sql: str) -> list[str]:
    return [statement.strip() for statement in sql.split(";") if statement.strip()]


def init_next_schema_safe(engine: Engine | None = None, *, prefer_sql_file: bool | None = None) -> list[str]:
    """Create missing AI-CRM Next read-model tables and indexes without dropping data."""

    explicit_engine = engine is not None
    engine = engine or get_engine()
    if prefer_sql_file is None:
        prefer_sql_file = engine.dialect.name == "postgresql"

    if prefer_sql_file:
        sql = SAFE_NEXT_SCHEMA_SQL.read_text(encoding="utf-8")
        with engine.begin() as connection:
            for statement in _sql_statements(sql):
                connection.execute(text(statement))
        if not explicit_engine:
            ensure_admin_sso_state_schema()
        return [table.name for table in SAFE_NEXT_SCHEMA_TABLES] + list(SAFE_NEXT_SCHEMA_EXTRA_TABLE_NAMES)

    for table in SAFE_NEXT_SCHEMA_TABLES:
        table.create(bind=engine, checkfirst=True)
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)
    if explicit_engine:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS admin_sso_states (
                        state_token TEXT PRIMARY KEY,
                        login_kind TEXT NOT NULL DEFAULT 'wecom_qr',
                        next_path TEXT NOT NULL DEFAULT '/admin',
                        expires_at TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_sso_states_expires_at ON admin_sso_states (expires_at)"))
    else:
        ensure_admin_sso_state_schema()
    return [table.name for table in SAFE_NEXT_SCHEMA_TABLES]
