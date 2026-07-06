"""broadcast retry states and reclaim scheduling.

Revision ID: 0089_broadcast_retry_reclaim
Revises: 0088_channel_entry_identity_best_effort
"""

from __future__ import annotations

from alembic import op


revision = "0089_broadcast_retry_reclaim"
down_revision = "0088_channel_entry_identity_best_effort"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_status_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_status_check
        CHECK (
            status IN (
                'waiting_approval', 'queued', 'claimed', 'sent', 'failed', 'failed_retryable',
                'failed_terminal', 'blocked', 'cancelled'
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_reclaim_due
        ON broadcast_jobs (status, next_retry_at, lease_expires_at, scheduled_for, priority, id ASC)
        WHERE status IN ('queued', 'claimed', 'failed_retryable')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_reclaim_due")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_status_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_status_check
        CHECK (status IN ('waiting_approval', 'queued', 'claimed', 'sent', 'failed', 'blocked', 'cancelled'))
        """
    )
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS next_retry_at")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS max_attempts")
