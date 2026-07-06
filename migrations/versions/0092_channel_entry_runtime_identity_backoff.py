"""add backoff controls for channel entry runtime identity retries.

Revision ID: 0092_channel_entry_runtime_identity_backoff
Revises: 0091_retire_wechat_pay_order_identity_repair
"""

from __future__ import annotations

from alembic import op


revision = "0092_channel_entry_runtime_identity_backoff"
down_revision = "0091_retire_wechat_pay_order_identity_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_channel_entry_runtime
        ADD COLUMN IF NOT EXISTS identity_attempt_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS identity_next_attempt_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS identity_last_error TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_entry_runtime_identity_due
        ON automation_channel_entry_runtime (identity_status, identity_next_attempt_at, updated_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_entry_runtime_identity_due")
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_channel_entry_runtime
        DROP COLUMN IF EXISTS identity_last_error,
        DROP COLUMN IF EXISTS identity_next_attempt_at,
        DROP COLUMN IF EXISTS identity_attempt_count
        """
    )
