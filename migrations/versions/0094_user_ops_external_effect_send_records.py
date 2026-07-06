"""user ops external effect send record projection.

Revision ID: 0094_user_ops_external_effect_send_records
Revises: 0093_huangyoucan_unregistered_unionid_snapshot
"""

from __future__ import annotations

from alembic import op


revision = "0094_user_ops_external_effect_send_records"
down_revision = "0093_huangyoucan_unregistered_unionid_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records_next
        ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
        ADD COLUMN IF NOT EXISTS execution_backend TEXT NOT NULL DEFAULT 'legacy_fake',
        ADD COLUMN IF NOT EXISTS external_effect_job_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        ADD COLUMN IF NOT EXISTS external_effect_status_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS planned_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS queued_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS dispatching_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS succeeded_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS failed_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS blocked_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS cancelled_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS last_refreshed_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_ops_send_records_idempotency_key
        ON user_ops_send_records_next (idempotency_key)
        WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_ops_send_records_next_backend
        ON user_ops_send_records_next (execution_backend, status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_ops_send_records_next_backend")
    op.execute("DROP INDEX IF EXISTS uq_user_ops_send_records_idempotency_key")
    op.execute(
        """
        ALTER TABLE IF EXISTS user_ops_send_records_next
        DROP COLUMN IF EXISTS last_refreshed_at,
        DROP COLUMN IF EXISTS cancelled_count,
        DROP COLUMN IF EXISTS blocked_count,
        DROP COLUMN IF EXISTS failed_count,
        DROP COLUMN IF EXISTS succeeded_count,
        DROP COLUMN IF EXISTS dispatching_count,
        DROP COLUMN IF EXISTS queued_count,
        DROP COLUMN IF EXISTS planned_count,
        DROP COLUMN IF EXISTS external_effect_status_summary_json,
        DROP COLUMN IF EXISTS external_effect_job_ids_json,
        DROP COLUMN IF EXISTS execution_backend,
        DROP COLUMN IF EXISTS idempotency_key
        """
    )
