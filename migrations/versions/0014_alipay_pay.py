"""alipay_pay — 支付宝 WAP 支付订单表.

Revision ID: 0014
Revises: 0013
"""
from __future__ import annotations

from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alipay_pay_orders (
            id BIGSERIAL PRIMARY KEY,
            out_trade_no TEXT NOT NULL UNIQUE,
            trade_no TEXT NOT NULL DEFAULT '',
            order_source TEXT NOT NULL DEFAULT 'h5_alipay_wap',
            client_order_ref TEXT NOT NULL DEFAULT '',
            product_code TEXT NOT NULL DEFAULT '',
            product_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            amount_total INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            unionid TEXT NOT NULL DEFAULT '',
            buyer_logon_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'created',
            trade_status TEXT NOT NULL DEFAULT '',
            success_url TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            notify_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            return_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            refunded_amount_total INTEGER NOT NULL DEFAULT 0,
            refund_status TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            expires_at TIMESTAMPTZ,
            paid_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alipay_pay_orders_status_created
        ON alipay_pay_orders (status, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alipay_pay_orders_product_created
        ON alipay_pay_orders (product_code, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alipay_pay_orders_unionid_created
        ON alipay_pay_orders (unionid, created_at DESC, id DESC)
        WHERE unionid <> ''
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_alipay_pay_orders_trade_no
        ON alipay_pay_orders (trade_no)
        WHERE trade_no <> ''
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS alipay_pay_order_events (
            id BIGSERIAL PRIMARY KEY,
            out_trade_no TEXT NOT NULL REFERENCES alipay_pay_orders(out_trade_no) ON DELETE CASCADE,
            event_type TEXT NOT NULL DEFAULT '',
            trade_no TEXT NOT NULL DEFAULT '',
            trade_status TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            headers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alipay_pay_order_events_order
        ON alipay_pay_order_events (out_trade_no, created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alipay_pay_order_events_order")
    op.execute("DROP TABLE IF EXISTS alipay_pay_order_events")
    op.execute("DROP INDEX IF EXISTS idx_alipay_pay_orders_trade_no")
    op.execute("DROP INDEX IF EXISTS idx_alipay_pay_orders_unionid_created")
    op.execute("DROP INDEX IF EXISTS idx_alipay_pay_orders_product_created")
    op.execute("DROP INDEX IF EXISTS idx_alipay_pay_orders_status_created")
    op.execute("DROP TABLE IF EXISTS alipay_pay_orders")
