"""wechat_pay_products - 商品管理与长图切片.

Revision ID: 0012
Revises: 0011
"""
from __future__ import annotations

from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_products (
            id BIGSERIAL PRIMARY KEY,
            product_code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            amount_total INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'disabled')),
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            cta_text TEXT NOT NULL DEFAULT '立即报名',
            require_mobile BOOLEAN NOT NULL DEFAULT FALSE,
            lead_program_id BIGINT,
            lead_channel_id BIGINT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_wechat_pay_products_code
        ON wechat_pay_products (product_code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_products_status_updated
        ON wechat_pay_products (status, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_product_page_slices (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES wechat_pay_products(id) ON DELETE CASCADE,
            image_library_id BIGINT NOT NULL REFERENCES image_library(id) ON DELETE RESTRICT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_product_slices_product_order
        ON wechat_pay_product_page_slices (product_id, sort_order ASC, id ASC)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wechat_pay_product_page_slices")
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_products_status_updated")
    op.execute("DROP INDEX IF EXISTS uq_wechat_pay_products_code")
    op.execute("DROP TABLE IF EXISTS wechat_pay_products")
