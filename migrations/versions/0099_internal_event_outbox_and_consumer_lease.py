"""add transactional internal event outbox and consumer lease CAS.

Revision ID: 0099_internal_event_outbox_and_consumer_lease
Revises: 0098_admin_session_revocation
"""

from __future__ import annotations

from alembic import op


revision = "0099_internal_event_outbox_and_consumer_lease"
down_revision = "0098_admin_session_revocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS internal_event_consumer_run "
        "ADD COLUMN IF NOT EXISTS lease_token TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_internal_event_consumer_run_auto_due "
        "ON internal_event_consumer_run (status, next_retry_at, locked_at, id) "
        "WHERE status IN ('pending', 'failed_retryable', 'running')"
    )
    op.execute(
        "ALTER TABLE IF EXISTS internal_event_consumer_attempt "
        "DROP CONSTRAINT IF EXISTS internal_event_consumer_attempt_status_check"
    )
    op.execute(
        "ALTER TABLE IF EXISTS internal_event_consumer_attempt "
        "ADD CONSTRAINT internal_event_consumer_attempt_status_check "
        "CHECK (status IN ("
        "'succeeded', 'failed_retryable', 'failed_terminal', 'blocked', 'skipped', 'manual_retry'"
        "))"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_event_outbox (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            outbox_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            event_version INTEGER NOT NULL DEFAULT 1,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            subject_type TEXT NOT NULL DEFAULT '',
            subject_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT '',
            actor_type TEXT NOT NULL DEFAULT 'system',
            source_module TEXT NOT NULL DEFAULT '',
            source_route TEXT NOT NULL DEFAULT '',
            source_command_id TEXT NOT NULL DEFAULT '',
            trace_id TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            correlation_id TEXT NOT NULL DEFAULT '',
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending'
                CONSTRAINT internal_event_outbox_status_check
                CHECK (status IN ('pending', 'running', 'relayed', 'failed_retryable', 'failed_terminal')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 10,
            next_retry_at TIMESTAMPTZ,
            lease_token TEXT NOT NULL DEFAULT '',
            locked_at TIMESTAMPTZ,
            locked_by TEXT NOT NULL DEFAULT '',
            internal_event_id TEXT NOT NULL DEFAULT '',
            last_error_code TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            relayed_at TIMESTAMPTZ,
            CONSTRAINT uq_internal_event_outbox_tenant_idempotency
                UNIQUE (tenant_id, idempotency_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_internal_event_outbox_due "
        "ON internal_event_outbox (status, next_retry_at, locked_at, id) "
        "WHERE status IN ('pending', 'failed_retryable', 'running')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_internal_event_outbox_event "
        "ON internal_event_outbox (internal_event_id) WHERE internal_event_id <> ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_internal_event_outbox_event")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_outbox_due")
    op.execute("DROP TABLE IF EXISTS internal_event_outbox")
    op.execute(
        "ALTER TABLE IF EXISTS internal_event_consumer_attempt "
        "DROP CONSTRAINT IF EXISTS internal_event_consumer_attempt_status_check"
    )
    op.execute(
        "ALTER TABLE IF EXISTS internal_event_consumer_attempt "
        "ADD CONSTRAINT internal_event_consumer_attempt_status_check "
        "CHECK (status IN ('succeeded', 'failed_retryable', 'failed_terminal', 'blocked', 'skipped'))"
    )
    op.execute("DROP INDEX IF EXISTS idx_internal_event_consumer_run_auto_due")
    op.execute(
        "ALTER TABLE IF EXISTS internal_event_consumer_run "
        "DROP COLUMN IF EXISTS lease_token"
    )
