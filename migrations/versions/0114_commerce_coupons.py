"""add fixed-amount commerce coupons.

Revision ID: 0114_commerce_coupons
Revises: 0113_operation_cycles
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0114_commerce_coupons"
down_revision = "0113_operation_cycles"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS commerce_coupons (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            public_slug TEXT NOT NULL,
            name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 45),
            discount_amount_total INTEGER NOT NULL CHECK (discount_amount_total > 0),
            currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'stopped', 'archived')),
            total_issue_limit INTEGER NOT NULL CHECK (total_issue_limit > 0),
            per_user_issue_limit INTEGER NOT NULL DEFAULT 1 CHECK (per_user_issue_limit > 0),
            issued_count INTEGER NOT NULL DEFAULT 0 CHECK (issued_count >= 0),
            claim_starts_at TIMESTAMPTZ NOT NULL,
            claim_ends_at TIMESTAMPTZ NOT NULL,
            validity_mode TEXT NOT NULL
                CHECK (validity_mode IN ('fixed_range', 'relative_days')),
            use_starts_at TIMESTAMPTZ,
            use_ends_at TIMESTAMPTZ,
            relative_validity_days INTEGER,
            instructions TEXT NOT NULL DEFAULT '' CHECK (char_length(instructions) <= 200),
            first_claim_at TIMESTAMPTZ,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_commerce_coupons_claim_window
                CHECK (claim_starts_at < claim_ends_at),
            CONSTRAINT ck_commerce_coupons_issue_limits
                CHECK (per_user_issue_limit <= total_issue_limit AND issued_count <= total_issue_limit),
            CONSTRAINT uq_commerce_coupons_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT ck_commerce_coupons_validity_configuration CHECK (
                (
                    validity_mode = 'fixed_range'
                    AND use_starts_at IS NOT NULL
                    AND use_ends_at IS NOT NULL
                    AND use_starts_at < use_ends_at
                    AND claim_ends_at <= use_ends_at
                    AND relative_validity_days IS NULL
                )
                OR
                (
                    validity_mode = 'relative_days'
                    AND use_starts_at IS NULL
                    AND use_ends_at IS NULL
                    AND relative_validity_days > 0
                )
            )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_coupons_public_slug
        ON commerce_coupons (public_slug)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_commerce_coupons_tenant_status_window
        ON commerce_coupons (tenant_id, status, claim_starts_at, claim_ends_at, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS commerce_coupon_product_bindings (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            coupon_id BIGINT NOT NULL REFERENCES commerce_coupons(id) ON DELETE CASCADE,
            trade_product_id BIGINT NOT NULL REFERENCES wechat_pay_products(id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_commerce_coupon_product_binding UNIQUE (coupon_id, trade_product_id),
            CONSTRAINT fk_commerce_coupon_bindings_coupon_tenant
                FOREIGN KEY (tenant_id, coupon_id)
                REFERENCES commerce_coupons (tenant_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_commerce_coupon_bindings_product
        ON commerce_coupon_product_bindings (tenant_id, trade_product_id, coupon_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS commerce_coupon_claims (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            coupon_id BIGINT NOT NULL REFERENCES commerce_coupons(id) ON DELETE RESTRICT,
            claim_no TEXT NOT NULL,
            unionid TEXT NOT NULL CHECK (btrim(unionid) <> ''),
            discount_amount_total INTEGER NOT NULL CHECK (discount_amount_total > 0),
            currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
            valid_from TIMESTAMPTZ NOT NULL,
            valid_until TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'available'
                CHECK (status IN ('available', 'reserved', 'consumed', 'expired')),
            idempotency_key_hash TEXT NOT NULL CHECK (btrim(idempotency_key_hash) <> ''),
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reserved_at TIMESTAMPTZ,
            consumed_at TIMESTAMPTZ,
            expired_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_commerce_coupon_claims_validity CHECK (valid_from < valid_until),
            CONSTRAINT uq_commerce_coupon_claims_tenant_id UNIQUE (tenant_id, id),
            CONSTRAINT fk_commerce_coupon_claims_coupon_tenant
                FOREIGN KEY (tenant_id, coupon_id)
                REFERENCES commerce_coupons (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT uq_commerce_coupon_claim_idempotency
                UNIQUE (tenant_id, coupon_id, unionid, idempotency_key_hash)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_coupon_claims_claim_no
        ON commerce_coupon_claims (claim_no)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_commerce_coupon_claims_user_eligible
        ON commerce_coupon_claims (tenant_id, unionid, status, valid_until, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_commerce_coupon_claims_coupon_user
        ON commerce_coupon_claims (tenant_id, coupon_id, unionid, claimed_at, id)
        """
    )

    # Keep order_id unbound during initial table creation; this remains safe
    # for the repository's imported-baseline bootstrap where the optional order
    # table is inspected separately below.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS commerce_coupon_redemptions (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            claim_id BIGINT NOT NULL REFERENCES commerce_coupon_claims(id) ON DELETE RESTRICT,
            order_id BIGINT NOT NULL,
            out_trade_no TEXT NOT NULL CHECK (btrim(out_trade_no) <> ''),
            status TEXT NOT NULL DEFAULT 'reserved'
                CHECK (status IN ('reserved', 'consumed', 'released')),
            original_amount_total INTEGER NOT NULL CHECK (original_amount_total > 0),
            discount_amount_total INTEGER NOT NULL CHECK (discount_amount_total > 0),
            payable_amount_total INTEGER NOT NULL CHECK (payable_amount_total > 0),
            currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
            reserved_until TIMESTAMPTZ NOT NULL,
            idempotency_key_hash TEXT NOT NULL DEFAULT '',
            release_reason TEXT NOT NULL DEFAULT '',
            reserved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            consumed_at TIMESTAMPTZ,
            released_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_commerce_coupon_redemptions_claim_tenant
                FOREIGN KEY (tenant_id, claim_id)
                REFERENCES commerce_coupon_claims (tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT ck_commerce_coupon_redemptions_amounts CHECK (
                discount_amount_total < original_amount_total
                AND payable_amount_total = original_amount_total - discount_amount_total
            )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_coupon_redemptions_active_claim
        ON commerce_coupon_redemptions (claim_id)
        WHERE status IN ('reserved', 'consumed')
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_coupon_redemptions_order_id
        ON commerce_coupon_redemptions (order_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_coupon_redemptions_out_trade_no
        ON commerce_coupon_redemptions (tenant_id, out_trade_no)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_commerce_coupon_redemptions_idempotency
        ON commerce_coupon_redemptions (tenant_id, claim_id, idempotency_key_hash)
        WHERE idempotency_key_hash <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_commerce_coupon_redemptions_reconcile
        ON commerce_coupon_redemptions (status, reserved_until, id)
        """
    )

    if _has_table("wechat_pay_orders"):
        op.execute("ALTER TABLE wechat_pay_orders ADD COLUMN IF NOT EXISTS subtotal_amount_total INTEGER")
        op.execute(
            "ALTER TABLE wechat_pay_orders "
            "ADD COLUMN IF NOT EXISTS discount_amount_total INTEGER NOT NULL DEFAULT 0"
        )
        op.execute("ALTER TABLE wechat_pay_orders ADD COLUMN IF NOT EXISTS coupon_claim_id BIGINT")
        op.execute(
            "ALTER TABLE wechat_pay_orders "
            "ADD COLUMN IF NOT EXISTS coupon_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb"
        )
        op.execute(
            "ALTER TABLE wechat_pay_orders "
            "ADD COLUMN IF NOT EXISTS reconciliation_not_found_count INTEGER NOT NULL DEFAULT 0"
        )
        op.execute(
            "ALTER TABLE wechat_pay_orders "
            "ADD COLUMN IF NOT EXISTS reconciliation_last_checked_at TIMESTAMPTZ"
        )
        op.execute(
            "ALTER TABLE wechat_pay_orders "
            "ADD COLUMN IF NOT EXISTS provider_unknown_at TIMESTAMPTZ"
        )
        op.execute(
            "UPDATE wechat_pay_orders "
            "SET subtotal_amount_total = amount_total "
            "WHERE subtotal_amount_total IS NULL"
        )
        op.execute(
            "ALTER TABLE wechat_pay_orders "
            "ALTER COLUMN subtotal_amount_total SET DEFAULT 0, "
            "ALTER COLUMN subtotal_amount_total SET NOT NULL"
        )
        op.execute("ALTER TABLE wechat_pay_orders DROP CONSTRAINT IF EXISTS fk_wechat_pay_orders_coupon_claim")
        op.execute(
            "ALTER TABLE wechat_pay_orders "
            "ADD CONSTRAINT fk_wechat_pay_orders_coupon_claim "
            "FOREIGN KEY (coupon_claim_id) REFERENCES commerce_coupon_claims(id) ON DELETE RESTRICT"
        )

        # Old order writers do not know subtotal_amount_total yet.  Populate the
        # no-coupon value before enforcing the amount equation so the additive
        # migration does not break those callers during a rolling deployment.
        op.execute(
            """
            CREATE OR REPLACE FUNCTION commerce_sync_wechat_pay_order_coupon_amounts()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.coupon_claim_id IS NULL
                   AND NEW.discount_amount_total = 0
                   AND (
                       (TG_OP = 'INSERT' AND NEW.subtotal_amount_total = 0)
                       OR (
                           TG_OP = 'UPDATE'
                           AND NEW.amount_total <> OLD.amount_total
                           AND NEW.subtotal_amount_total = OLD.subtotal_amount_total
                       )
                   )
                THEN
                    NEW.subtotal_amount_total := NEW.amount_total;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_wechat_pay_orders_coupon_amounts ON wechat_pay_orders")
        op.execute(
            """
            CREATE TRIGGER trg_wechat_pay_orders_coupon_amounts
            BEFORE INSERT OR UPDATE OF amount_total, subtotal_amount_total, discount_amount_total, coupon_claim_id
            ON wechat_pay_orders
            FOR EACH ROW
            EXECUTE FUNCTION commerce_sync_wechat_pay_order_coupon_amounts()
            """
        )
        op.execute("ALTER TABLE wechat_pay_orders DROP CONSTRAINT IF EXISTS ck_wechat_pay_orders_coupon_amounts")
        op.execute(
            """
            ALTER TABLE wechat_pay_orders
            ADD CONSTRAINT ck_wechat_pay_orders_coupon_amounts CHECK (
                subtotal_amount_total >= 0
                AND discount_amount_total >= 0
                AND discount_amount_total <= subtotal_amount_total
                AND amount_total = subtotal_amount_total - discount_amount_total
                AND (
                    (coupon_claim_id IS NULL AND discount_amount_total = 0)
                    OR (coupon_claim_id IS NOT NULL AND discount_amount_total > 0)
                )
                AND (coupon_claim_id IS NULL OR amount_total > 0)
            )
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_coupon_claim
            ON wechat_pay_orders (coupon_claim_id)
            WHERE coupon_claim_id IS NOT NULL
            """
        )
        op.execute(
            """
            ALTER TABLE commerce_coupon_redemptions
            ADD CONSTRAINT fk_commerce_coupon_redemptions_order
            FOREIGN KEY (order_id) REFERENCES wechat_pay_orders(id) ON DELETE RESTRICT
            """
        )


def downgrade() -> None:
    if _has_table("wechat_pay_orders"):
        op.execute(
            "ALTER TABLE IF EXISTS commerce_coupon_redemptions "
            "DROP CONSTRAINT IF EXISTS fk_commerce_coupon_redemptions_order"
        )
        op.execute("DROP INDEX IF EXISTS idx_wechat_pay_orders_coupon_claim")
        op.execute("ALTER TABLE wechat_pay_orders DROP CONSTRAINT IF EXISTS ck_wechat_pay_orders_coupon_amounts")
        op.execute("DROP TRIGGER IF EXISTS trg_wechat_pay_orders_coupon_amounts ON wechat_pay_orders")
        op.execute("DROP FUNCTION IF EXISTS commerce_sync_wechat_pay_order_coupon_amounts()")
        op.execute("ALTER TABLE wechat_pay_orders DROP CONSTRAINT IF EXISTS fk_wechat_pay_orders_coupon_claim")
        op.execute("ALTER TABLE wechat_pay_orders DROP COLUMN IF EXISTS provider_unknown_at")
        op.execute("ALTER TABLE wechat_pay_orders DROP COLUMN IF EXISTS reconciliation_last_checked_at")
        op.execute("ALTER TABLE wechat_pay_orders DROP COLUMN IF EXISTS reconciliation_not_found_count")
        op.execute("ALTER TABLE wechat_pay_orders DROP COLUMN IF EXISTS coupon_snapshot_json")
        op.execute("ALTER TABLE wechat_pay_orders DROP COLUMN IF EXISTS coupon_claim_id")
        op.execute("ALTER TABLE wechat_pay_orders DROP COLUMN IF EXISTS discount_amount_total")
        op.execute("ALTER TABLE wechat_pay_orders DROP COLUMN IF EXISTS subtotal_amount_total")

    op.execute("DROP TABLE IF EXISTS commerce_coupon_redemptions")
    op.execute("DROP TABLE IF EXISTS commerce_coupon_claims")
    op.execute("DROP TABLE IF EXISTS commerce_coupon_product_bindings")
    op.execute("DROP TABLE IF EXISTS commerce_coupons")
