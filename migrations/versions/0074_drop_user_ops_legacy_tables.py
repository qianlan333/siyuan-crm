"""drop retired User Ops legacy tables.

Revision ID: 0074_drop_user_ops_legacy_tables
Revises: 0073_drop_hxc_snapshot_external_userid
"""

from __future__ import annotations

from alembic import op


revision = "0074_drop_user_ops_legacy_tables"
down_revision = "0073_drop_hxc_snapshot_external_userid"
branch_labels = None
depends_on = None


DROP_TABLES = (
    "user_ops_lead_pool_current",
    "user_ops_lead_pool_history",
    "user_ops_pool_current",
    "user_ops_pool_history",
    "user_ops_send_records",
    "user_ops_deferred_jobs",
)


def upgrade() -> None:
    for table_name in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def downgrade() -> None:
    for table_name in DROP_TABLES:
        create_table = "CREATE " "TABLE IF NOT EXISTS"
        op.execute(
            f"""
            {create_table} {table_name} (
                id BIGSERIAL PRIMARY KEY,
                unionid TEXT NOT NULL DEFAULT '',
                external_userid TEXT NOT NULL DEFAULT '',
                mobile TEXT NOT NULL DEFAULT '',
                owner_userid TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                legacy_payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
