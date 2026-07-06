"""channel entry identity best-effort diagnostics.

Revision ID: 0088_channel_entry_identity_best_effort
Revises: 0087_merge_order_identity_repair_head
"""

from __future__ import annotations

from alembic import op


revision = "0088_channel_entry_identity_best_effort"
down_revision = "0087_merge_order_identity_repair_head"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS wecom_external_contact_event_logs
        ADD COLUMN IF NOT EXISTS identity_sync_status TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS identity_sync_error_code TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS identity_sync_error_message TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS identity_sync_response_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel_entry_runtime (
            id BIGSERIAL PRIMARY KEY,
            corp_id TEXT NOT NULL DEFAULT '',
            event_log_id BIGINT,
            channel_id BIGINT,
            scene_value TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            follow_user_userid TEXT NOT NULL DEFAULT '',
            welcome_code_present BOOLEAN NOT NULL DEFAULT FALSE,
            unionid TEXT NOT NULL DEFAULT '',
            identity_status TEXT NOT NULL DEFAULT 'pending',
            runtime_status TEXT NOT NULL DEFAULT 'received',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_channel_entry_runtime_event
        ON automation_channel_entry_runtime (corp_id, external_userid, follow_user_userid, scene_value)
        WHERE external_userid <> '' AND scene_value <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_channel_entry_runtime_identity_status
        ON automation_channel_entry_runtime (identity_status, updated_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_entry_runtime_identity_status")
    op.execute("DROP INDEX IF EXISTS ux_channel_entry_runtime_event")
    op.execute("DROP TABLE IF EXISTS automation_channel_entry_runtime")
    op.execute(
        """
        ALTER TABLE IF EXISTS wecom_external_contact_event_logs
        DROP COLUMN IF EXISTS identity_sync_response_json,
        DROP COLUMN IF EXISTS identity_sync_error_message,
        DROP COLUMN IF EXISTS identity_sync_error_code,
        DROP COLUMN IF EXISTS identity_sync_status
        """
    )
