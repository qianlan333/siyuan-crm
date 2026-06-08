"""allow group ops plans to bind groups managed by group administrators"""

from __future__ import annotations

from alembic import op


revision = "0027_group_ops_admin_userids"
down_revision = "0026_customer_read_model_next"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE wecom_group_chat_snapshots
        ADD COLUMN IF NOT EXISTS admin_userids TEXT NOT NULL DEFAULT '[]'
        """
    )
    op.execute(
        """
        UPDATE wecom_group_chat_snapshots AS snapshots
        SET admin_userids = COALESCE(admins.admin_userids, '[]')
        FROM (
            SELECT
                group_chats.chat_id,
                COALESCE(
                    jsonb_agg(DISTINCT admin_item->>'userid')
                    FILTER (WHERE COALESCE(admin_item->>'userid', '') <> ''),
                    '[]'::jsonb
                )::text AS admin_userids
            FROM group_chats
            CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(group_chats.raw_payload::jsonb->'group_chat'->'admin_list', '[]'::jsonb)
            ) AS admin_item
            GROUP BY group_chats.chat_id
        ) AS admins
        WHERE snapshots.chat_id = admins.chat_id
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE wecom_group_chat_snapshots
        DROP COLUMN IF EXISTS admin_userids
        """
    )
