"""completion target json fields"""

from __future__ import annotations

from alembic import op


revision = "0041_completion_target_json"
down_revision = "0040_external_effect_test_receiver"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.questionnaires') IS NOT NULL THEN
                ALTER TABLE questionnaires
                ADD COLUMN IF NOT EXISTS completion_target_json JSONB;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wechat_pay_products') IS NOT NULL THEN
                ALTER TABLE wechat_pay_products
                ADD COLUMN IF NOT EXISTS completion_target_json JSONB;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wechat_pay_products') IS NOT NULL THEN
                ALTER TABLE wechat_pay_products DROP COLUMN IF EXISTS completion_target_json;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.questionnaires') IS NOT NULL THEN
                ALTER TABLE questionnaires DROP COLUMN IF EXISTS completion_target_json;
            END IF;
        END $$;
        """
    )
