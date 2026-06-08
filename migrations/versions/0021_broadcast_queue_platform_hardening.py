"""broadcast queue platform hardening metadata

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-28
"""
from __future__ import annotations

from alembic import op


revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD COLUMN IF NOT EXISTS business_domain TEXT,
        ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
        ADD COLUMN IF NOT EXISTS channel TEXT,
        ADD COLUMN IF NOT EXISTS target_kind TEXT,
        ADD COLUMN IF NOT EXISTS failure_type TEXT,
        ADD COLUMN IF NOT EXISTS retry_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        UPDATE broadcast_jobs
        SET business_domain = CASE
            WHEN source_table = 'automation_group_ops_plans' THEN 'group_ops'
            WHEN content_payload->>'channel' = 'wecom_customer_group' THEN 'group_ops'
            WHEN source_type = 'cloud_plan' THEN 'ai_assistant'
            WHEN source_type IN ('campaign', 'sop', 'workflow', 'operation_task', 'focus_send', 'deferred') THEN 'automation_ops'
            WHEN source_type = 'manual' THEN 'manual'
            ELSE 'unknown'
        END
        WHERE business_domain IS NULL OR business_domain = ''
        """
    )
    op.execute(
        """
        UPDATE broadcast_jobs
        SET channel = CASE
            WHEN content_payload->>'channel' = 'wecom_customer_group' THEN 'wecom_customer_group'
            WHEN source_table = 'automation_group_ops_plans' THEN 'wecom_customer_group'
            ELSE 'unknown'
        END
        WHERE channel IS NULL OR channel = ''
        """
    )
    op.execute(
        """
        UPDATE broadcast_jobs
        SET target_kind = 'unknown'
        WHERE target_kind IS NULL OR target_kind = ''
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_broadcast_jobs_idempotency_key
        ON broadcast_jobs (idempotency_key)
        WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_job_events (
            id BIGSERIAL PRIMARY KEY,
            job_id BIGINT NOT NULL,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            actor_type TEXT,
            actor_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_job_events_job_id
        ON broadcast_job_events (job_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_job_events_event_type_created_at
        ON broadcast_job_events (event_type, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_job_events_created_at
        ON broadcast_job_events (created_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_broadcast_job_events_created_at")
    op.execute("DROP INDEX IF EXISTS idx_broadcast_job_events_event_type_created_at")
    op.execute("DROP INDEX IF EXISTS idx_broadcast_job_events_job_id")
    op.execute("DROP TABLE IF EXISTS broadcast_job_events")
    op.execute("DROP INDEX IF EXISTS uq_broadcast_jobs_idempotency_key")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS metadata_json")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS retry_policy_json")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS failure_type")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS target_kind")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS channel")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS business_domain")
