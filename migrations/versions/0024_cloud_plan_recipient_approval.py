"""cloud plan recipient approval materialization.

Revision ID: 0024_cloud_plan_approval
Revises: 0023_product_external_push, 0023_group_ops_webhook_rules
"""

from __future__ import annotations

from alembic import op


revision = "0024_cloud_plan_approval"
down_revision = ("0023_product_external_push", "0023_group_ops_webhook_rules")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS cloud_broadcast_plans
        ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS owner_userid TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'pending_review',
        ADD COLUMN IF NOT EXISTS run_status TEXT NOT NULL DEFAULT 'draft'
        """
    )
    op.execute(
        """
        UPDATE cloud_broadcast_plans
        SET display_name = COALESCE(NULLIF(display_name, ''), NULLIF(intent, ''), plan_id),
            run_status = COALESCE(NULLIF(run_status, ''), status, 'draft'),
            review_status = CASE
                WHEN status = 'rejected' THEN 'rejected'
                WHEN status = 'committed' THEN 'approved'
                ELSE COALESCE(NULLIF(review_status, ''), 'pending_review')
            END
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_broadcast_plan_recipients (
            id BIGSERIAL PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES cloud_broadcast_plans(plan_id) ON DELETE CASCADE,
            external_userid TEXT NOT NULL,
            owner_userid TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            planned_message_count INTEGER NOT NULL DEFAULT 0,
            approval_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (approval_status IN ('pending', 'approved', 'rejected')),
            send_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (send_status IN ('pending', 'queued', 'sending', 'sent', 'failed', 'cancelled')),
            approved_by TEXT NOT NULL DEFAULT '',
            approved_at TIMESTAMPTZ,
            rejected_by TEXT NOT NULL DEFAULT '',
            rejected_at TIMESTAMPTZ,
            reject_reason TEXT NOT NULL DEFAULT '',
            broadcast_job_id BIGINT,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_cloud_broadcast_plan_recipients_plan_external
        ON cloud_broadcast_plan_recipients (plan_id, external_userid)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plan_recipients_plan_status
        ON cloud_broadcast_plan_recipients (plan_id, approval_status, send_status, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plan_recipients_external
        ON cloud_broadcast_plan_recipients (external_userid)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_broadcast_plan_recipient_messages (
            id BIGSERIAL PRIMARY KEY,
            plan_id TEXT NOT NULL REFERENCES cloud_broadcast_plans(plan_id) ON DELETE CASCADE,
            recipient_id BIGINT NOT NULL REFERENCES cloud_broadcast_plan_recipients(id) ON DELETE CASCADE,
            external_userid TEXT NOT NULL,
            sequence_index INTEGER NOT NULL DEFAULT 1,
            day_offset INTEGER NOT NULL DEFAULT 0,
            send_time TEXT NOT NULL DEFAULT '',
            content_text TEXT NOT NULL DEFAULT '',
            content_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            attachments_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'queued', 'sent', 'failed', 'skipped')),
            sent_at TIMESTAMPTZ,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plan_recipient_messages_recipient
        ON cloud_broadcast_plan_recipient_messages (recipient_id, sequence_index)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cloud_broadcast_plan_recipient_messages_recipient")
    op.execute("DROP TABLE IF EXISTS cloud_broadcast_plan_recipient_messages")
    op.execute("DROP INDEX IF EXISTS idx_cloud_broadcast_plan_recipients_external")
    op.execute("DROP INDEX IF EXISTS idx_cloud_broadcast_plan_recipients_plan_status")
    op.execute("DROP INDEX IF EXISTS uq_cloud_broadcast_plan_recipients_plan_external")
    op.execute("DROP TABLE IF EXISTS cloud_broadcast_plan_recipients")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plans DROP COLUMN IF EXISTS run_status")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plans DROP COLUMN IF EXISTS review_status")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plans DROP COLUMN IF EXISTS owner_userid")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plans DROP COLUMN IF EXISTS display_name")
