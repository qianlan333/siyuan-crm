"""external effect queue"""

from __future__ import annotations

from alembic import op


revision = "0039_external_effect_queue"
down_revision = "0038_merge_duplicate_channel_wechat_shop_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_effect_job (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            effect_type TEXT NOT NULL,
            adapter_name TEXT NOT NULL,
            operation TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            business_type TEXT NOT NULL DEFAULT '',
            business_id TEXT NOT NULL DEFAULT '',
            source_module TEXT NOT NULL DEFAULT '',
            source_route TEXT NOT NULL DEFAULT '',
            source_event_id TEXT NOT NULL DEFAULT '',
            source_command_id TEXT NOT NULL DEFAULT '',
            trace_id TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            correlation_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT '',
            actor_type TEXT NOT NULL DEFAULT 'system',
            risk_level TEXT NOT NULL DEFAULT 'medium',
            requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
            execution_mode TEXT NOT NULL DEFAULT 'shadow',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN (
                    'planned', 'approved', 'queued', 'dispatching', 'succeeded',
                    'failed_retryable', 'failed_terminal', 'blocked', 'cancelled', 'expired'
                )),
            priority INTEGER NOT NULL DEFAULT 100,
            scheduled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            next_retry_at TIMESTAMPTZ,
            locked_at TIMESTAMPTZ,
            locked_by TEXT NOT NULL DEFAULT '',
            last_attempt_id TEXT NOT NULL DEFAULT '',
            last_error_code TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMPTZ,
            executed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_external_effect_job_tenant_idempotency
        ON external_effect_job (tenant_id, idempotency_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_job_due
        ON external_effect_job (status, scheduled_at, priority, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_job_target
        ON external_effect_job (target_type, target_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_job_business
        ON external_effect_job (business_type, business_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_job_trace
        ON external_effect_job (trace_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_job_effect_type
        ON external_effect_job (effect_type, status)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_effect_attempt (
            id BIGSERIAL PRIMARY KEY,
            attempt_id TEXT NOT NULL UNIQUE,
            job_id BIGINT NOT NULL REFERENCES external_effect_job(id) ON DELETE CASCADE,
            adapter_name TEXT NOT NULL,
            adapter_mode TEXT NOT NULL DEFAULT 'none',
            operation TEXT NOT NULL,
            trace_id TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
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
        CREATE INDEX IF NOT EXISTS idx_external_effect_attempt_job
        ON external_effect_attempt (job_id, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_effect_attempt_trace
        ON external_effect_attempt (trace_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_external_effect_attempt_trace")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_attempt_job")
    op.execute("DROP TABLE IF EXISTS external_effect_attempt")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_job_effect_type")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_job_trace")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_job_business")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_job_target")
    op.execute("DROP INDEX IF EXISTS idx_external_effect_job_due")
    op.execute("DROP INDEX IF EXISTS uq_external_effect_job_tenant_idempotency")
    op.execute("DROP TABLE IF EXISTS external_effect_job")
