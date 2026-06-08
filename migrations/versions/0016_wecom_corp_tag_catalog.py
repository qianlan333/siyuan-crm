"""wecom corp tag catalog cache.

Revision ID: 0016
Revises: 0015
"""
from __future__ import annotations

from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wecom_corp_tag_groups (
            group_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL DEFAULT '',
            group_key TEXT NOT NULL DEFAULT '',
            tag_count INTEGER NOT NULL DEFAULT 0,
            raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            synced_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wecom_corp_tag_groups_name
        ON wecom_corp_tag_groups (group_name)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wecom_corp_tags (
            tag_id TEXT PRIMARY KEY,
            tag_name TEXT NOT NULL DEFAULT '',
            group_id TEXT NOT NULL DEFAULT '',
            group_name TEXT NOT NULL DEFAULT '',
            order_index INTEGER NOT NULL DEFAULT 0,
            deleted_at TIMESTAMPTZ,
            raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            synced_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wecom_corp_tags_group
        ON wecom_corp_tags (group_id, deleted_at, order_index, tag_name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wecom_corp_tags_deleted
        ON wecom_corp_tags (deleted_at, synced_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wecom_corp_tags_deleted")
    op.execute("DROP INDEX IF EXISTS idx_wecom_corp_tags_group")
    op.execute("DROP TABLE IF EXISTS wecom_corp_tags")
    op.execute("DROP INDEX IF EXISTS idx_wecom_corp_tag_groups_name")
    op.execute("DROP TABLE IF EXISTS wecom_corp_tag_groups")
