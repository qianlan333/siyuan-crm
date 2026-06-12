"""add wechat pay order unionid lookup index.

Revision ID: 0030_wechat_pay_unionid_idx
Revises: 0029_user_ops_prod_tables
"""

from __future__ import annotations

from alembic import op


revision = "0030_wechat_pay_unionid_idx"
down_revision = "0029_user_ops_prod_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wechat_pay_orders') IS NOT NULL THEN
                CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_unionid_created
                ON wechat_pay_orders (unionid, created_at DESC, id DESC)
                WHERE unionid IS NOT NULL AND unionid <> '';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_orders_unionid_created")
