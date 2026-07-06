"""allow direct send broadcast source types.

Revision ID: 0082_direct_send_broadcast_source_types
Revises: 0081_create_customer_status_baseline_tables
"""

from __future__ import annotations

from alembic import op


revision = "0082_direct_send_broadcast_source_types"
down_revision = "0081_create_customer_status_baseline_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_source_type_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_source_type_check
        CHECK (
            source_type IN (
                'campaign',
                'sop',
                'workflow',
                'operation_task',
                'cloud_plan',
                'focus_send',
                'deferred',
                'manual',
                'automation_runtime_v2',
                'external_campaign',
                'direct_send'
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_source_type_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_source_type_check
        CHECK (
            source_type IN (
                'campaign',
                'sop',
                'workflow',
                'operation_task',
                'cloud_plan',
                'focus_send',
                'deferred',
                'manual',
                'automation_runtime_v2'
            )
        )
        """
    )
