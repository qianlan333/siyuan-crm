"""automation agent runtime config and webhook queue.

Revision ID: 0054_automation_agent_runtime_config
Revises: 0053_retire_legacy_automation_tables
"""

from __future__ import annotations

from alembic import op


revision = "0054_automation_agent_runtime_config"
down_revision = "0053_retire_legacy_automation_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agent_runtime_config (
            id BIGSERIAL PRIMARY KEY,
            agent_code TEXT NOT NULL,
            agent_name TEXT NOT NULL DEFAULT '',
            bound_package_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'archived')),
            draft_role_prompt TEXT NOT NULL DEFAULT '',
            draft_task_prompt TEXT NOT NULL DEFAULT '',
            published_role_prompt TEXT NOT NULL DEFAULT '',
            published_task_prompt TEXT NOT NULL DEFAULT '',
            draft_version INTEGER NOT NULL DEFAULT 0,
            published_version INTEGER NOT NULL DEFAULT 0,
            fixed_content_package_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            inbound_webhook_secret TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            archived_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_agent_runtime_active_code
        ON automation_agent_runtime_config (agent_code)
        WHERE status <> 'archived'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_runtime_status
        ON automation_agent_runtime_config (status, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agent_webhook_batch (
            id BIGSERIAL PRIMARY KEY,
            batch_id TEXT NOT NULL UNIQUE,
            agent_code TEXT NOT NULL,
            bound_package_key TEXT NOT NULL DEFAULT '',
            source_event_type TEXT NOT NULL DEFAULT '',
            refresh_run_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            received_count INTEGER NOT NULL DEFAULT 0,
            deduped_count INTEGER NOT NULL DEFAULT 0,
            accepted_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'partial_failed', 'failed')),
            request_headers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_agent_webhook_batch_idempotency
        ON automation_agent_webhook_batch (idempotency_key)
        WHERE idempotency_key <> ''
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_agent_webhook_item (
            id BIGSERIAL PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES automation_agent_webhook_batch(batch_id) ON DELETE RESTRICT,
            agent_code TEXT NOT NULL,
            unionid TEXT NOT NULL,
            external_event_id TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'generated', 'callback_succeeded', 'callback_failed', 'failed', 'failed_retryable')),
            context_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            prompt_preview TEXT NOT NULL DEFAULT '',
            raw_agent_output TEXT NOT NULL DEFAULT '',
            content_package_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            callback_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            callback_status TEXT NOT NULL DEFAULT '',
            callback_response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_agent_webhook_item_batch_unionid UNIQUE (batch_id, unionid)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_agent_webhook_item_event
        ON automation_agent_webhook_item (external_event_id)
        WHERE external_event_id <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_agent_webhook_item_status
        ON automation_agent_webhook_item (status, created_at ASC, id ASC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_automation_agent_webhook_item_status")
    op.execute("DROP INDEX IF EXISTS uq_automation_agent_webhook_item_event")
    op.execute("DROP TABLE IF EXISTS automation_agent_webhook_item")
    op.execute("DROP INDEX IF EXISTS uq_automation_agent_webhook_batch_idempotency")
    op.execute("DROP TABLE IF EXISTS automation_agent_webhook_batch")
    op.execute("DROP INDEX IF EXISTS idx_automation_agent_runtime_status")
    op.execute("DROP INDEX IF EXISTS uq_automation_agent_runtime_active_code")
    op.execute("DROP TABLE IF EXISTS automation_agent_runtime_config")
