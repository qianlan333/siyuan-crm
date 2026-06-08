"""broadcast queue notification settings

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op


revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_queue_notification_settings (
            id BIGSERIAL PRIMARY KEY,
            channel TEXT NOT NULL DEFAULT 'feishu',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            webhook_url TEXT NOT NULL,
            validation_status TEXT NOT NULL DEFAULT 'unverified'
                CHECK (validation_status IN ('unverified', 'valid', 'invalid')),
            validated_at TIMESTAMPTZ,
            last_validation_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_broadcast_queue_notification_settings_channel
        ON broadcast_queue_notification_settings(channel)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_broadcast_queue_notification_settings_channel")
    op.execute("DROP TABLE IF EXISTS broadcast_queue_notification_settings")
