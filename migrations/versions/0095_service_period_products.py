"""add service period products.

Revision ID: 0095_service_period_products
Revises: 0094_user_ops_external_effect_send_records
"""

from __future__ import annotations

from alembic import op


revision = "0095_service_period_products"
down_revision = "0094_user_ops_external_effect_send_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_period_products (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            trade_product_id BIGINT NOT NULL REFERENCES wechat_pay_products(id) ON DELETE RESTRICT,
            link_slug TEXT NOT NULL,
            membership_config_id TEXT NOT NULL DEFAULT '',
            membership_config_name TEXT NOT NULL DEFAULT '',
            duration_days INTEGER NOT NULL CHECK (duration_days > 0),
            deleted BOOLEAN NOT NULL DEFAULT FALSE,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_service_period_products_trade_product_id
        ON service_period_products (trade_product_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_service_period_products_link_slug
        ON service_period_products (link_slug)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_period_products_updated
        ON service_period_products (tenant_id, deleted, updated_at DESC, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_period_entitlements (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            service_product_id BIGINT NOT NULL REFERENCES service_period_products(id) ON DELETE RESTRICT,
            trade_product_id BIGINT NOT NULL REFERENCES wechat_pay_products(id) ON DELETE RESTRICT,
            unionid TEXT NOT NULL,
            external_userid_snapshot TEXT NOT NULL DEFAULT '',
            mobile_snapshot TEXT NOT NULL DEFAULT '',
            membership_config_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','disabled','refunded')),
            start_at TIMESTAMPTZ NOT NULL,
            end_at TIMESTAMPTZ NOT NULL,
            last_order_id BIGINT,
            last_out_trade_no TEXT NOT NULL DEFAULT '',
            renewal_count INTEGER NOT NULL DEFAULT 0,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, service_product_id, unionid)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_period_entitlements_product_status_end
        ON service_period_entitlements (service_product_id, status, end_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_period_entitlements_unionid
        ON service_period_entitlements (unionid)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_period_entitlements_last_order
        ON service_period_entitlements (last_order_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_period_events (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            event_id TEXT NOT NULL UNIQUE,
            service_product_id BIGINT NOT NULL REFERENCES service_period_products(id) ON DELETE RESTRICT,
            entitlement_id BIGINT REFERENCES service_period_entitlements(id) ON DELETE SET NULL,
            trade_product_id BIGINT NOT NULL REFERENCES wechat_pay_products(id) ON DELETE RESTRICT,
            order_id BIGINT,
            out_trade_no TEXT NOT NULL DEFAULT '',
            unionid TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'activated',
                    'renewed',
                    'expired',
                    'disabled',
                    'refunded',
                    'grant_failed_missing_unionid',
                    'membership_sync_failed',
                    'admin_adjusted'
                )
            ),
            duration_days INTEGER NOT NULL DEFAULT 0,
            before_start_at TIMESTAMPTZ,
            before_end_at TIMESTAMPTZ,
            after_start_at TIMESTAMPTZ,
            after_end_at TIMESTAMPTZ,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_service_period_events_event_once
        ON service_period_events (tenant_id, event_type, out_trade_no)
        WHERE out_trade_no <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_period_events_product_created
        ON service_period_events (service_product_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_service_period_events_unionid_created
        ON service_period_events (unionid, created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_service_period_events_unionid_created")
    op.execute("DROP INDEX IF EXISTS idx_service_period_events_product_created")
    op.execute("DROP INDEX IF EXISTS uq_service_period_events_event_once")
    op.execute("DROP TABLE IF EXISTS service_period_events")

    op.execute("DROP INDEX IF EXISTS idx_service_period_entitlements_last_order")
    op.execute("DROP INDEX IF EXISTS idx_service_period_entitlements_unionid")
    op.execute("DROP INDEX IF EXISTS idx_service_period_entitlements_product_status_end")
    op.execute("DROP TABLE IF EXISTS service_period_entitlements")

    op.execute("DROP INDEX IF EXISTS idx_service_period_products_updated")
    op.execute("DROP INDEX IF EXISTS uq_service_period_products_link_slug")
    op.execute("DROP INDEX IF EXISTS uq_service_period_products_trade_product_id")
    op.execute("DROP TABLE IF EXISTS service_period_products")
