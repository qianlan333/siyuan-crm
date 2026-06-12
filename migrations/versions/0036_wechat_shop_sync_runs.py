"""add wechat shop order sync run audit table.

Revision ID: 0036_wechat_shop_sync_runs
Revises: 0035_wechat_shop_refunds
"""

from __future__ import annotations

from alembic import op


revision = "0036_wechat_shop_sync_runs"
down_revision = "0035_wechat_shop_refunds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_shop_sync_runs (
            id BIGSERIAL PRIMARY KEY,
            sync_type TEXT NOT NULL DEFAULT '',
            time_mode TEXT NOT NULL DEFAULT '',
            range_start TIMESTAMPTZ,
            range_end TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'running',
            scanned_count INTEGER NOT NULL DEFAULT 0,
            synced_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            next_key TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_shop_sync_runs_started
        ON wechat_shop_sync_runs (started_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_shop_sync_runs_type_status
        ON wechat_shop_sync_runs (sync_type, status, range_end DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_shop_sync_runs_type_status")
    op.execute("DROP INDEX IF EXISTS idx_wechat_shop_sync_runs_started")
    op.execute("DROP TABLE IF EXISTS wechat_shop_sync_runs")
