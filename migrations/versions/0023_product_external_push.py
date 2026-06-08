"""product external push webhook metadata"""

from __future__ import annotations

from alembic import op


revision = "0023_product_external_push"
down_revision = "0022_next_automation_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_push_config (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            webhook_url TEXT NOT NULL DEFAULT '',
            push_type TEXT NOT NULL DEFAULT '',
            expires_at_ts BIGINT,
            day INTEGER,
            frequency INTEGER,
            remark TEXT NOT NULL DEFAULT '',
            custom_params JSONB NOT NULL DEFAULT '{}'::jsonb,
            secret TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_external_push_config_target_event
        ON external_push_config (tenant_id, target_type, target_id, event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_push_config_target
        ON external_push_config (tenant_id, target_type, target_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_push_config_event
        ON external_push_config (tenant_id, event_type)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_push_delivery (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            config_id BIGINT NOT NULL REFERENCES external_push_config(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            delivery_id TEXT NOT NULL UNIQUE,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            order_id BIGINT NOT NULL DEFAULT 0,
            product_id BIGINT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sending', 'success', 'failed', 'retrying', 'gave_up', 'skipped')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            request_url TEXT NOT NULL DEFAULT '',
            request_headers JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_body JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_status INTEGER,
            response_body TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            next_retry_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_external_push_delivery_config_order_event
        ON external_push_delivery (config_id, order_id, event_type)
        WHERE order_id > 0
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_push_delivery_order
        ON external_push_delivery (tenant_id, order_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_push_delivery_retry
        ON external_push_delivery (status, next_retry_at)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS domain_event_outbox (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            event_type TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'processing', 'success', 'failed', 'gave_up', 'skipped')),
            retry_count INTEGER NOT NULL DEFAULT 0,
            next_retry_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_domain_event_outbox_event_aggregate
        ON domain_event_outbox (tenant_id, event_type, aggregate_type, aggregate_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_domain_event_outbox_status_retry
        ON domain_event_outbox (status, next_retry_at, id ASC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_domain_event_outbox_status_retry")
    op.execute("DROP INDEX IF EXISTS uq_domain_event_outbox_event_aggregate")
    op.execute("DROP TABLE IF EXISTS domain_event_outbox")
    op.execute("DROP INDEX IF EXISTS idx_external_push_delivery_retry")
    op.execute("DROP INDEX IF EXISTS idx_external_push_delivery_order")
    op.execute("DROP INDEX IF EXISTS uq_external_push_delivery_config_order_event")
    op.execute("DROP TABLE IF EXISTS external_push_delivery")
    op.execute("DROP INDEX IF EXISTS idx_external_push_config_event")
    op.execute("DROP INDEX IF EXISTS idx_external_push_config_target")
    op.execute("DROP INDEX IF EXISTS uq_external_push_config_target_event")
    op.execute("DROP TABLE IF EXISTS external_push_config")
