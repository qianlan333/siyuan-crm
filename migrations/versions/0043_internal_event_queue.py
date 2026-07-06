"""internal event queue"""

from __future__ import annotations

from alembic import op


revision = "0043_internal_event_queue"
down_revision = "0042_legacy_webhook_deprecation_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_event (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            event_id TEXT NOT NULL UNIQUE,
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
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_internal_event_tenant_idempotency UNIQUE (tenant_id, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_type_occurred
        ON internal_event (event_type, occurred_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_aggregate
        ON internal_event (aggregate_type, aggregate_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_subject
        ON internal_event (subject_type, subject_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_trace
        ON internal_event (trace_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_event_consumer_run (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            event_id TEXT NOT NULL REFERENCES internal_event(event_id) ON DELETE CASCADE,
            consumer_name TEXT NOT NULL,
            consumer_type TEXT NOT NULL DEFAULT 'projection',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN (
                    'pending', 'running', 'succeeded', 'failed_retryable',
                    'failed_terminal', 'blocked', 'skipped'
                )),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            next_retry_at TIMESTAMPTZ,
            locked_at TIMESTAMPTZ,
            locked_by TEXT NOT NULL DEFAULT '',
            last_attempt_id TEXT NOT NULL DEFAULT '',
            last_error_code TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            result_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMPTZ,
            CONSTRAINT uq_internal_event_consumer_run_tenant_event_consumer
                UNIQUE (tenant_id, event_id, consumer_name)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_consumer_run_due
        ON internal_event_consumer_run (status, next_retry_at, locked_at, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_consumer_run_event
        ON internal_event_consumer_run (event_id, consumer_name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_consumer_run_consumer
        ON internal_event_consumer_run (consumer_name, status)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS internal_event_consumer_attempt (
            id BIGSERIAL PRIMARY KEY,
            attempt_id TEXT NOT NULL UNIQUE,
            consumer_run_id BIGINT NOT NULL REFERENCES internal_event_consumer_run(id) ON DELETE CASCADE,
            consumer_name TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('succeeded', 'failed_retryable', 'failed_terminal', 'blocked', 'skipped')),
            request_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_consumer_attempt_run
        ON internal_event_consumer_attempt (consumer_run_id, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_consumer_attempt_consumer
        ON internal_event_consumer_attempt (consumer_name, status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_internal_event_consumer_attempt_consumer")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_consumer_attempt_run")
    op.execute("DROP TABLE IF EXISTS internal_event_consumer_attempt")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_consumer_run_consumer")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_consumer_run_event")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_consumer_run_due")
    op.execute("DROP TABLE IF EXISTS internal_event_consumer_run")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_trace")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_subject")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_aggregate")
    op.execute("DROP INDEX IF EXISTS idx_internal_event_type_occurred")
    op.execute("DROP TABLE IF EXISTS internal_event")
