"""drop retired message batch legacy tables.

Revision ID: 0075_drop_message_batch_legacy_tables
Revises: 0074_drop_user_ops_legacy_tables
"""

from __future__ import annotations

from alembic import op


revision = "0075_drop_message_batch_legacy_tables"
down_revision = "0074_drop_user_ops_legacy_tables"
branch_labels = None
depends_on = None


DROP_TABLES = (
    "message_batch_items",
    "message_batches",
)


def upgrade() -> None:
    for table_name in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def downgrade() -> None:
    create_table = "CREATE " "TABLE IF NOT EXISTS"
    op.execute(
        f"""
        {create_table} message_batches (
            id BIGSERIAL PRIMARY KEY,
            batch_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            legacy_payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        f"""
        {create_table} message_batch_items (
            id BIGSERIAL PRIMARY KEY,
            batch_id BIGINT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '',
            legacy_payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
