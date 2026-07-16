"""add external radar read path index.

Revision ID: 0118_external_radar_read_api
Revises: 0117_group_invite_cards
"""

from __future__ import annotations

from alembic import op


revision = "0118_external_radar_read_api"
down_revision = "0117_group_invite_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_radar_click_events_external_feed
        ON radar_click_events (id DESC, created_at DESC)
        WHERE stage IN ('authorized', 'authorized_click')
           OR (
                stage = 'landing'
                AND COALESCE(NULLIF(unionid, ''), NULLIF(openid, ''), NULLIF(external_userid, '')) IS NOT NULL
           )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_radar_click_events_external_feed")
