"""add reusable group invite cards.

Revision ID: 0117_group_invite_cards
Revises: 0116_questionnaire_operations_config
"""

from __future__ import annotations

from alembic import op


revision = "0117_group_invite_cards"
down_revision = "0116_questionnaire_operations_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_invite_library (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            pic_url TEXT NOT NULL DEFAULT '',
            join_url TEXT NOT NULL,
            config_id TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT '',
            chat_id_list JSONB NOT NULL DEFAULT '[]'::jsonb,
            auto_create_room BOOLEAN NOT NULL DEFAULT TRUE,
            room_base_name TEXT NOT NULL DEFAULT '',
            room_base_id INTEGER,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_group_invite_join_url
                CHECK (join_url ~ '^https://work\\.weixin\\.qq\\.com/gm/'),
            CONSTRAINT ck_group_invite_room_base_id
                CHECK (room_base_id IS NULL OR room_base_id >= 0)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_invite_library_enabled_updated
        ON group_invite_library (enabled, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        ALTER TABLE automation_channel
        ADD COLUMN IF NOT EXISTS welcome_group_invite_library_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE automation_channel DROP COLUMN IF EXISTS welcome_group_invite_library_ids")
    op.execute("DROP TABLE IF EXISTS group_invite_library")
