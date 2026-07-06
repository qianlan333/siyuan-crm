"""add channel multi staff assignment tables.

Revision ID: 0036_channel_multi_staff_assignment
Revises: 0035_wechat_shop_refunds
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0036_channel_multi_staff_assignment"
down_revision = "0035_wechat_shop_refunds"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    schema = None if bind.dialect.name == "sqlite" else "public"
    return inspect(bind).has_table(table, schema=schema)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS assignment_mode TEXT NOT NULL DEFAULT 'single_owner'
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS assignment_strategy TEXT NOT NULL DEFAULT 'ratio'
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS overflow_policy TEXT NOT NULL DEFAULT 'least_loaded'
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_channel
        ADD COLUMN IF NOT EXISTS assignment_config_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    channel_reference = " REFERENCES automation_channel(id) ON DELETE CASCADE" if _has_table("automation_channel") else ""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel_assignee (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL__CHANNEL_REFERENCE__,
            staff_id TEXT NOT NULL,
            display_name_snapshot TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 0,
            ratio_percent INTEGER,
            max_scans_24h INTEGER,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel_id, staff_id)
        )
        """.replace("__CHANNEL_REFERENCE__", channel_reference)
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_assignee_active
        ON automation_channel_assignee(channel_id, status, priority, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel_assignment_event (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL__CHANNEL_REFERENCE__,
            assignee_staff_id TEXT NOT NULL DEFAULT '',
            strategy TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'assigned',
            unionid TEXT NOT NULL DEFAULT '',
            wecom_user_id TEXT NOT NULL DEFAULT '',
            source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            converted_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """.replace("__CHANNEL_REFERENCE__", channel_reference)
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_assignment_24h
        ON automation_channel_assignment_event(channel_id, assignee_staff_id, assigned_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_assignment_unionid
        ON automation_channel_assignment_event(channel_id, unionid)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_assignment_unionid")
    op.execute("DROP INDEX IF EXISTS idx_channel_assignment_24h")
    op.execute("DROP TABLE IF EXISTS automation_channel_assignment_event")
    op.execute("DROP INDEX IF EXISTS idx_channel_assignee_active")
    op.execute("DROP TABLE IF EXISTS automation_channel_assignee")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS assignment_config_json")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS overflow_policy")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS assignment_strategy")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS assignment_mode")
