"""wechat pay order identity repair"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0062_wechat_pay_order_identity_repair"
down_revision = "0061_automation_agent_type_fixed_script"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This revision is one of several historical heads branching from 0061.  A
    # fresh install may visit it before the separate baseline branch has ever
    # created ``wechat_pay_orders``.  The repair queue was temporary and is
    # retired again by 0091, so skipping it is the only valid empty-schema
    # behavior; deployed schemas that own the source table keep the old repair
    # migration unchanged.
    if not inspect(op.get_bind()).has_table("wechat_pay_orders"):
        return
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_pay_order_identity_repair (
            order_id BIGINT PRIMARY KEY REFERENCES wechat_pay_orders(id) ON DELETE CASCADE,
            out_trade_no TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'retryable', 'succeeded', 'exhausted', 'skipped')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            next_retry_at TIMESTAMPTZ,
            matched_by TEXT NOT NULL DEFAULT '',
            resolved_external_userid TEXT NOT NULL DEFAULT '',
            resolved_owner_userid TEXT NOT NULL DEFAULT '',
            last_error_code TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            last_attempted_at TIMESTAMPTZ,
            repaired_at TIMESTAMPTZ,
            detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_order_identity_repair_due
        ON wechat_pay_order_identity_repair (status, next_retry_at, order_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wechat_pay_order_identity_repair_trade_no
        ON wechat_pay_order_identity_repair (out_trade_no)
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wechat_pay_orders') IS NULL THEN
                RETURN;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'wechat_pay_orders'
                  AND column_name = 'external_userid'
            ) THEN
                EXECUTE $sql$
                    CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_missing_identity_paid
                    ON wechat_pay_orders (paid_at, id)
                    WHERE COALESCE(external_userid, '') = ''
                      AND (status = 'paid' OR trade_state = 'SUCCESS')
                $sql$;
            ELSIF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'wechat_pay_orders'
                  AND column_name = 'unionid'
            ) THEN
                EXECUTE $sql$
                    CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_missing_identity_paid
                    ON wechat_pay_orders (paid_at, id)
                    WHERE COALESCE(unionid, '') = ''
                      AND (status = 'paid' OR trade_state = 'SUCCESS')
                $sql$;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_orders_missing_identity_paid")
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_order_identity_repair_trade_no")
    op.execute("DROP INDEX IF EXISTS idx_wechat_pay_order_identity_repair_due")
    op.execute("DROP TABLE IF EXISTS wechat_pay_order_identity_repair")
