"""dedupe ai audience outbound subscriptions.

Revision ID: 0046_ai_audience_publish_and_subscription_dedupe
Revises: 0045_ai_audience_ops
"""

from __future__ import annotations

from alembic import op


revision = "0046_ai_audience_publish_and_subscription_dedupe"
down_revision = "0045_ai_audience_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY package_id, trigger_event_type, target_type, webhook_url
                    ORDER BY id ASC
                ) AS rn
            FROM ai_audience_outbound_subscription
            WHERE status = 'active'
        )
        UPDATE ai_audience_outbound_subscription s
        SET status = 'paused',
            updated_at = CURRENT_TIMESTAMP
        FROM ranked r
        WHERE s.id = r.id
          AND r.rn > 1
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_audience_active_subscription_target
        ON ai_audience_outbound_subscription (
            package_id,
            trigger_event_type,
            target_type,
            webhook_url
        )
        WHERE status = 'active'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_ai_audience_active_subscription_target")
