"""drop legacy identity columns from customer fact read sources.

Revision ID: 0068_unionid_customer_fact_cleanup
Revises: 0067_unionid_campaign_frequency_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0068_unionid_customer_fact_cleanup"
down_revision = "0067_unionid_campaign_frequency_cleanup"
branch_labels = None
depends_on = None


LEGACY_COLUMNS_BY_TABLE = {
    "contact_tags": ["external_userid"],
    "archived_messages": ["external_userid"],
    "class_user_status_current": ["external_userid", "mobile_snapshot"],
    "class_user_status_history": ["external_userid", "mobile_snapshot"],
    "wechat_shop_orders": ["buyer_mobile", "openid"],
}


def upgrade() -> None:
    for table_name in LEGACY_COLUMNS_BY_TABLE:
        _enqueue_unresolved_external_rows(table_name)
    for table_name, column_names in LEGACY_COLUMNS_BY_TABLE.items():
        _create_unionid_index(table_name)
        for column_name in column_names:
            op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS {column_name}")


def _create_unionid_index(table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table_name}') IS NOT NULL THEN
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS %I ON %I (unionid) WHERE unionid <> %L',
                    'ix_{table_name}_unionid',
                    '{table_name}',
                    ''
                );
            END IF;
        END $$;
        """
    )


def _enqueue_unresolved_external_rows(table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table_name}') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = '{table_name}' AND column_name = 'external_userid'
               ) THEN
                EXECUTE $sql$
                    INSERT INTO crm_user_identity_resolution_queue (
                        source_type,
                        source_key,
                        external_userid,
                        payload_json,
                        reason,
                        status,
                        first_seen_at,
                        last_seen_at,
                        created_at,
                        updated_at
                    )
                    SELECT
                        '{table_name}',
                        '{table_name}:' || target.ctid::text,
                        target.external_userid,
                        jsonb_build_object(
                            'source_table', '{table_name}',
                            'external_userid', target.external_userid,
                            'ctid', target.ctid::text
                        ),
                        'missing_unionid',
                        'pending',
                        NOW(),
                        NOW(),
                        NOW(),
                        NOW()
                    FROM {table_name} target
                    WHERE COALESCE(target.unionid, '') = ''
                      AND COALESCE(target.external_userid, '') <> ''
                    ON CONFLICT (source_type, source_key) WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
                    DO UPDATE SET
                        external_userid = COALESCE(NULLIF(EXCLUDED.external_userid, ''), crm_user_identity_resolution_queue.external_userid),
                        payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                        reason = EXCLUDED.reason,
                        last_seen_at = NOW(),
                        updated_at = NOW()
                $sql$;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS contact_tags ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS archived_messages ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    for table_name in ["class_user_status_current", "class_user_status_history"]:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''")
