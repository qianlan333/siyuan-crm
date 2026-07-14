"""add commerce payment/refund fulfillment invariants.

Revision ID: 0101_commerce_fulfillment_invariants
Revises: 0100_external_effect_delivery_lease
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0101_commerce_fulfillment_invariants"
down_revision = "0100_external_effect_delivery_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``wechat_pay_refunds`` belongs to the imported pre-Alembic baseline.  A
    # new empty deployment has no such optional commerce table, while existing
    # deployments must still receive all three invariants.
    if not inspect(op.get_bind()).has_table("wechat_pay_refunds"):
        return
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_wechat_pay_refunds_out_refund_no
        ON wechat_pay_refunds (out_refund_no)
        WHERE out_refund_no <> ''
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_wechat_pay_refunds_refund_id
        ON wechat_pay_refunds (refund_id)
        WHERE refund_id <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_refunds_order_active
        ON wechat_pay_refunds (order_id, created_at DESC, id DESC)
        WHERE LOWER(COALESCE(status, '')) NOT IN ('failed', 'closed', 'abnormal', 'success')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_refunds_order_active")
    op.execute("DROP INDEX IF EXISTS uq_wechat_pay_refunds_refund_id")
    op.execute("DROP INDEX IF EXISTS uq_wechat_pay_refunds_out_refund_no")
