"""add wechat shop refund request audit table.

Revision ID: 0035_wechat_shop_refunds
Revises: 0034_reset_miniprogram_only_material_jobs_20260611
"""

from __future__ import annotations

from alembic import op


revision = "0035_wechat_shop_refunds"
down_revision = "0034_reset_miniprogram_only_material_jobs_20260611"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_shop_refunds (
            id BIGSERIAL PRIMARY KEY,
            order_id TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            out_refund_no TEXT NOT NULL UNIQUE,
            aftersale_id TEXT NOT NULL DEFAULT '',
            refund_amount_total INTEGER NOT NULL DEFAULT 0,
            order_amount_total INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'requested',
            reason TEXT NOT NULL DEFAULT '',
            requested_by TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT '',
            request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_shop_refunds_order
        ON wechat_shop_refunds (order_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_shop_refunds_status
        ON wechat_shop_refunds (status, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_shop_refunds_aftersale
        ON wechat_shop_refunds (aftersale_id)
        WHERE aftersale_id <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_shop_refunds_aftersale")
    op.execute("DROP INDEX IF EXISTS idx_wechat_shop_refunds_status")
    op.execute("DROP INDEX IF EXISTS idx_wechat_shop_refunds_order")
    op.execute("DROP TABLE IF EXISTS wechat_shop_refunds")
