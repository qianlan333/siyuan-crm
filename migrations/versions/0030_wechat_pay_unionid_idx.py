"""add wechat pay order unionid lookup index.

Revision ID: 0030_wechat_pay_unionid_idx
Revises: 0029_user_ops_prod_tables
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0030_wechat_pay_unionid_idx"
down_revision = "0029_user_ops_prod_tables"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    schema = None if bind.dialect.name == "sqlite" else "public"
    return inspect(bind).has_table(table, schema=schema)


def upgrade() -> None:
    if not _has_table("wechat_pay_orders"):
        return

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_unionid_created
        ON wechat_pay_orders (unionid, created_at DESC, id DESC)
        WHERE unionid IS NOT NULL AND unionid <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_orders_unionid_created")
