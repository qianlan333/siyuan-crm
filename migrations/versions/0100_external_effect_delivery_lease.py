"""external effect delivery lease and truthful result states.

Revision ID: 0100_external_effect_delivery_lease
Revises: 0099_internal_event_outbox_and_consumer_lease
"""

from __future__ import annotations

from alembic import op


revision = "0100_external_effect_delivery_lease"
down_revision = "0099_internal_event_outbox_and_consumer_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE external_effect_job
        ADD COLUMN IF NOT EXISTS lease_token TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS dispatch_started_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS side_effect_executed BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS provider_result_received BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS result_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS reconciliation_required BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ
        """
    )
    op.execute("ALTER TABLE external_effect_job DROP CONSTRAINT IF EXISTS external_effect_job_status_check")
    op.execute(
        """
        ALTER TABLE external_effect_job
        ADD CONSTRAINT external_effect_job_status_check
        CHECK (status IN (
            'planned', 'approved', 'queued', 'dispatching', 'succeeded', 'simulated',
            'unknown_after_dispatch', 'failed_retryable', 'failed_terminal', 'blocked',
            'cancelled', 'expired'
        ))
        """
    )
    op.execute("ALTER TABLE external_effect_attempt DROP CONSTRAINT IF EXISTS external_effect_attempt_status_check")
    op.execute(
        """
        ALTER TABLE external_effect_attempt
        ADD CONSTRAINT external_effect_attempt_status_check
        CHECK (status IN (
            'succeeded', 'simulated', 'unknown_after_dispatch', 'failed_retryable',
            'failed_terminal', 'blocked', 'skipped'
        ))
        """
    )

    op.execute(
        """
        UPDATE external_effect_job j
        SET side_effect_executed = LOWER(COALESCE(a.response_summary_json->>'real_external_call_executed', 'false'))
                IN ('true', '1', 'yes'),
            provider_result_received = (
                a.response_summary_json ?| ARRAY[
                    'status_code', 'http_status', 'errcode', 'wecom_msgid_present',
                    'audit_id', 'receipt_id', 'provider_status', 'refund_id_present'
                ]
            ),
            result_summary_json = COALESCE(a.response_summary_json, '{}'::jsonb)
        FROM external_effect_attempt a
        WHERE a.attempt_id = j.last_attempt_id
        """
    )
    op.execute(
        """
        UPDATE external_effect_job j
        SET status = 'simulated', completed_at = COALESCE(j.executed_at, j.updated_at),
            reconciliation_required = FALSE
        FROM external_effect_attempt a
        WHERE j.status = 'succeeded'
          AND a.attempt_id = j.last_attempt_id
          AND j.side_effect_executed = FALSE
          AND (
              LOWER(COALESCE(a.adapter_mode, '')) IN ('fake', 'fixture', 'simulated', 'test_fake')
              OR LOWER(COALESCE(a.response_summary_json->>'mode', '')) = 'fake'
              OR LOWER(COALESCE(a.response_summary_json->>'adapter_mode', '')) = 'fake'
          )
        """
    )
    op.execute(
        """
        UPDATE external_effect_job
        SET status = 'unknown_after_dispatch', reconciliation_required = TRUE,
            last_error_code = CASE WHEN last_error_code = '' THEN 'migration_found_dispatching' ELSE last_error_code END,
            last_error_message = CASE WHEN last_error_message = '' THEN 'Dispatch ownership was active during R07 cutover; reconcile before retry.' ELSE last_error_message END,
            lease_token = '', lease_expires_at = NULL, locked_by = '', locked_at = NULL,
            completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE status = 'dispatching'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_job_lease_due
        ON external_effect_job (status, lease_expires_at, scheduled_at, priority, id)
        WHERE status IN ('queued', 'failed_retryable', 'dispatching')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_job_reconciliation
        ON external_effect_job (status, updated_at, id)
        WHERE reconciliation_required = TRUE OR status = 'unknown_after_dispatch'
        """
    )

    _expand_broadcast_simulated_status()


def _expand_broadcast_simulated_status() -> None:
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


def downgrade() -> None:
    op.execute("UPDATE broadcast_jobs SET status = 'blocked' WHERE status = 'simulated'")
    op.execute("UPDATE cloud_broadcast_plan_recipients SET send_status = 'failed' WHERE send_status = 'simulated'")
    op.execute("UPDATE cloud_broadcast_plan_recipient_messages SET status = 'failed' WHERE status = 'simulated'")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_status_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_status_check
        CHECK (status IN (
            'waiting_approval', 'queued', 'claimed', 'sent', 'failed', 'failed_retryable',
            'failed_terminal', 'blocked', 'cancelled'
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
        CHECK (send_status IN ('pending', 'queued', 'sending', 'sent', 'failed', 'cancelled'))
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
        CHECK (status IN ('pending', 'queued', 'sent', 'failed', 'skipped'))
        """
    )

    op.execute("UPDATE external_effect_job SET status = 'blocked' WHERE status = 'simulated'")
    op.execute("UPDATE external_effect_job SET status = 'failed_terminal' WHERE status = 'unknown_after_dispatch'")
    op.execute("UPDATE external_effect_attempt SET status = 'skipped' WHERE status = 'simulated'")
    op.execute("UPDATE external_effect_attempt SET status = 'failed_terminal' WHERE status = 'unknown_after_dispatch'")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_job_reconciliation")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_job_lease_due")
    op.execute("ALTER TABLE external_effect_attempt DROP CONSTRAINT IF EXISTS external_effect_attempt_status_check")
    op.execute(
        """
        ALTER TABLE external_effect_attempt
        ADD CONSTRAINT external_effect_attempt_status_check
        CHECK (status IN ('succeeded', 'failed_retryable', 'failed_terminal', 'blocked', 'skipped'))
        """
    )
    op.execute("ALTER TABLE external_effect_job DROP CONSTRAINT IF EXISTS external_effect_job_status_check")
    op.execute(
        """
        ALTER TABLE external_effect_job
        ADD CONSTRAINT external_effect_job_status_check
        CHECK (status IN (
            'planned', 'approved', 'queued', 'dispatching', 'succeeded',
            'failed_retryable', 'failed_terminal', 'blocked', 'cancelled', 'expired'
        ))
        """
    )
    for column in (
        "completed_at",
        "reconciliation_required",
        "result_summary_json",
        "provider_result_received",
        "side_effect_executed",
        "dispatch_started_at",
        "lease_expires_at",
        "lease_token",
    ):
        op.execute(f"ALTER TABLE external_effect_job DROP COLUMN IF EXISTS {column}")
