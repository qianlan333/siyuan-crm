"""add channel multi staff assignment tables.

Revision ID: 0036_channel_multi_staff_assignment
Revises: 0035_wechat_shop_refunds
"""

from __future__ import annotations

from alembic import op


revision = "0036_channel_multi_staff_assignment"
down_revision = "0035_wechat_shop_refunds"
branch_labels = None
depends_on = None


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
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel_assignee (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL REFERENCES automation_channel(id) ON DELETE CASCADE,
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
        """
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
            channel_id BIGINT NOT NULL REFERENCES automation_channel(id) ON DELETE CASCADE,
            assignee_staff_id TEXT NOT NULL DEFAULT '',
            strategy TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'assigned',
            external_contact_id TEXT NOT NULL DEFAULT '',
            wecom_user_id TEXT NOT NULL DEFAULT '',
            source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            converted_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_assignment_24h
        ON automation_channel_assignment_event(channel_id, assignee_staff_id, assigned_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_assignment_external
        ON automation_channel_assignment_event(channel_id, external_contact_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_assignment_external")
    op.execute("DROP INDEX IF EXISTS idx_channel_assignment_24h")
    op.execute("DROP TABLE IF EXISTS automation_channel_assignment_event")
    op.execute("DROP INDEX IF EXISTS idx_channel_assignee_active")
    op.execute("DROP TABLE IF EXISTS automation_channel_assignee")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS assignment_config_json")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS overflow_policy")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS assignment_strategy")
    op.execute("ALTER TABLE IF EXISTS automation_channel DROP COLUMN IF EXISTS assignment_mode")
