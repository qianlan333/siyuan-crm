"""add crash-safe broadcast delivery state and evidence.

Revision ID: 0103_broadcast_delivery_state_machine
Revises: 0102_questionnaire_radar_invariants
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0103_broadcast_delivery_state_machine"
down_revision = "0102_questionnaire_radar_invariants"
branch_labels = None
depends_on = None


_BROADCAST_STATUSES = """
    'waiting_approval', 'queued', 'claimed', 'dispatching', 'sent', 'simulated',
    'failed', 'failed_retryable', 'failed_terminal', 'blocked', 'cancelled',
    'unknown_after_dispatch'
"""

_RECIPIENT_STATUSES = """
    'pending', 'queued', 'sending', 'dispatching', 'sent', 'simulated', 'failed',
    'failed_retryable', 'failed_terminal', 'blocked', 'cancelled',
    'unknown_after_dispatch'
"""

_MESSAGE_STATUSES = """
    'pending', 'queued', 'dispatching', 'sent', 'simulated', 'failed',
    'failed_retryable', 'failed_terminal', 'blocked', 'skipped',
    'unknown_after_dispatch'
"""


def upgrade() -> None:
    if _has_table("outbound_tasks"):
        op.execute("ALTER TABLE outbound_tasks ADD COLUMN IF NOT EXISTS broadcast_job_id BIGINT")
        op.execute("ALTER TABLE outbound_tasks ADD COLUMN IF NOT EXISTS task_type TEXT NOT NULL DEFAULT 'outbound_task'")
        op.execute("ALTER TABLE outbound_tasks ADD COLUMN IF NOT EXISTS request_payload JSONB NOT NULL DEFAULT '{}'::jsonb")
        op.execute("ALTER TABLE outbound_tasks ADD COLUMN IF NOT EXISTS response_payload JSONB NOT NULL DEFAULT '{}'::jsonb")
        op.execute("ALTER TABLE outbound_tasks ADD COLUMN IF NOT EXISTS wecom_task_id TEXT NOT NULL DEFAULT ''")
        op.execute("ALTER TABLE outbound_tasks ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT ''")
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_outbound_tasks_broadcast_job "
            "ON outbound_tasks (broadcast_job_id) WHERE broadcast_job_id IS NOT NULL"
        )

    if _has_table("broadcast_jobs"):
        op.execute("ALTER TABLE broadcast_jobs ADD COLUMN IF NOT EXISTS dispatch_started_at TIMESTAMPTZ")
        op.execute("ALTER TABLE broadcast_jobs ADD COLUMN IF NOT EXISTS side_effect_executed BOOLEAN NOT NULL DEFAULT FALSE")
        op.execute("ALTER TABLE broadcast_jobs ADD COLUMN IF NOT EXISTS provider_result_received BOOLEAN NOT NULL DEFAULT FALSE")
        op.execute("ALTER TABLE broadcast_jobs ADD COLUMN IF NOT EXISTS result_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb")
        op.execute("ALTER TABLE broadcast_jobs ADD COLUMN IF NOT EXISTS reconciliation_required BOOLEAN NOT NULL DEFAULT FALSE")
        op.execute("ALTER TABLE broadcast_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ")
        op.execute("ALTER TABLE broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_status_check")
        op.execute(
            f"""
            ALTER TABLE broadcast_jobs
            ADD CONSTRAINT broadcast_jobs_status_check
            CHECK (status IN ({_BROADCAST_STATUSES}))
            """
        )

        # A pre-R10 claim may have crossed the provider boundary. Conservatively
        # stop it for reconciliation instead of allowing the new worker to resend.
        op.execute(
            """
            UPDATE broadcast_jobs
            SET status = 'unknown_after_dispatch',
                reconciliation_required = TRUE,
                provider_result_received = FALSE,
                result_summary_json = jsonb_build_object('migration_reason', 'claimed_at_r10_cutover'),
                claim_token = '',
                lease_expires_at = NULL,
                next_retry_at = NULL,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'claimed'
            """
        )
        op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_reclaim_due")
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_reclaim_due
            ON broadcast_jobs (status, next_retry_at, lease_expires_at, scheduled_for, priority, id ASC)
            WHERE status IN ('queued', 'claimed', 'failed_retryable')
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_reconciliation
            ON broadcast_jobs (status, updated_at, id)
            WHERE reconciliation_required = TRUE OR status = 'unknown_after_dispatch'
            """
        )

    if _has_table("cloud_broadcast_plan_recipients"):
        op.execute(
            "ALTER TABLE cloud_broadcast_plan_recipients "
            "DROP CONSTRAINT IF EXISTS cloud_broadcast_plan_recipients_send_status_check"
        )
        op.execute(
            f"""
            ALTER TABLE cloud_broadcast_plan_recipients
            ADD CONSTRAINT cloud_broadcast_plan_recipients_send_status_check
            CHECK (send_status IN ({_RECIPIENT_STATUSES}))
            """
        )

    if _has_table("cloud_broadcast_plan_recipient_messages"):
        op.execute(
            "ALTER TABLE cloud_broadcast_plan_recipient_messages "
            "DROP CONSTRAINT IF EXISTS cloud_broadcast_plan_recipient_messages_status_check"
        )
        op.execute(
            f"""
            ALTER TABLE cloud_broadcast_plan_recipient_messages
            ADD CONSTRAINT cloud_broadcast_plan_recipient_messages_status_check
            CHECK (status IN ({_MESSAGE_STATUSES}))
            """
        )


def _has_table(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def downgrade() -> None:
    # Never make an ambiguous dispatch retryable during rollback.
    op.execute("UPDATE broadcast_jobs SET status = 'blocked' WHERE status IN ('dispatching', 'unknown_after_dispatch')")
    op.execute(
        "UPDATE cloud_broadcast_plan_recipients SET send_status = 'failed' "
        "WHERE send_status IN ('dispatching', 'unknown_after_dispatch', 'failed_retryable', 'failed_terminal', 'blocked')"
    )
    op.execute(
        "UPDATE cloud_broadcast_plan_recipient_messages SET status = 'failed' "
        "WHERE status IN ('dispatching', 'unknown_after_dispatch', 'failed_retryable', 'failed_terminal', 'blocked')"
    )

    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_reconciliation")
    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_reclaim_due")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_status_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_status_check
        CHECK (status IN (
            'waiting_approval', 'queued', 'claimed', 'sent', 'simulated', 'failed',
            'failed_retryable', 'failed_terminal', 'blocked', 'cancelled'
        ))
        """
    )
    op.execute(
        "ALTER TABLE IF EXISTS cloud_broadcast_plan_recipients "
        "DROP CONSTRAINT IF EXISTS cloud_broadcast_plan_recipients_send_status_check"
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS cloud_broadcast_plan_recipients
        ADD CONSTRAINT cloud_broadcast_plan_recipients_send_status_check
        CHECK (send_status IN ('pending', 'queued', 'sending', 'sent', 'simulated', 'failed', 'cancelled'))
        """
    )
    op.execute(
        "ALTER TABLE IF EXISTS cloud_broadcast_plan_recipient_messages "
        "DROP CONSTRAINT IF EXISTS cloud_broadcast_plan_recipient_messages_status_check"
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS cloud_broadcast_plan_recipient_messages
        ADD CONSTRAINT cloud_broadcast_plan_recipient_messages_status_check
        CHECK (status IN ('pending', 'queued', 'sent', 'simulated', 'failed', 'skipped'))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_reclaim_due
        ON broadcast_jobs (status, next_retry_at, lease_expires_at, scheduled_for, priority, id ASC)
        WHERE status IN ('queued', 'claimed', 'failed_retryable')
        """
    )
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS completed_at")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS reconciliation_required")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS result_summary_json")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS provider_result_received")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS side_effect_executed")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS dispatch_started_at")
    op.execute("DROP INDEX IF EXISTS uq_outbound_tasks_broadcast_job")
    op.execute("ALTER TABLE IF EXISTS outbound_tasks DROP COLUMN IF EXISTS broadcast_job_id")
