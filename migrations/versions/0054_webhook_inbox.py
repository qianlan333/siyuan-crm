"""compatibility bridge for deployed webhook inbox revision.

Revision ID: 0054_webhook_inbox
Revises:
"""

from __future__ import annotations

from alembic import op


revision = "0054_webhook_inbox"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep production's overlay revision addressable by the formal chain."""

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_inbox (
            id BIGSERIAL PRIMARY KEY,
            provider TEXT NOT NULL,
            event_family TEXT NOT NULL,
            route TEXT NOT NULL,
            method TEXT NOT NULL DEFAULT 'POST',
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            corp_id TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',
            change_type TEXT NOT NULL DEFAULT '',
            external_event_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL,
            raw_query_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw_headers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw_body BYTEA,
            payload_xml TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            processing_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'received'
                CHECK (status IN (
                    'received', 'processing', 'succeeded', 'failed_retryable',
                    'failed_terminal', 'dead_letter', 'ignored'
                )),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 8,
            next_retry_at TIMESTAMPTZ,
            locked_at TIMESTAMPTZ,
            locked_by TEXT NOT NULL DEFAULT '',
            last_error_code TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_webhook_inbox_tenant_provider_idempotency
                UNIQUE (tenant_id, provider, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_webhook_inbox_due
        ON webhook_inbox (provider, status, next_retry_at, locked_at, received_at, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_webhook_inbox_event_family
        ON webhook_inbox (provider, event_family, status, received_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_webhook_inbox_external_event
        ON webhook_inbox (provider, external_event_id)
        WHERE external_event_id <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_webhook_inbox_status_updated
        ON webhook_inbox (status, updated_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_webhook_inbox_status_updated")
    op.execute("DROP INDEX IF EXISTS idx_webhook_inbox_external_event")
    op.execute("DROP INDEX IF EXISTS idx_webhook_inbox_event_family")
    op.execute("DROP INDEX IF EXISTS idx_webhook_inbox_due")
    op.execute("DROP TABLE IF EXISTS webhook_inbox")
