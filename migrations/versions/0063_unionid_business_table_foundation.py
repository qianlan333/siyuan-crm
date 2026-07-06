"""add unionid columns to core business read tables.

Revision ID: 0063_unionid_business_table_foundation
Revises: 0062_unionid_identity_refactor
"""

from __future__ import annotations

from alembic import op


revision = "0063_unionid_business_table_foundation"
down_revision = "0062_unionid_identity_refactor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS alipay_pay_orders ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    for column_name in ["buyer_id", "mobile_snapshot", "identity_snapshot"]:
        op.execute(f"ALTER TABLE IF EXISTS alipay_pay_orders DROP COLUMN IF EXISTS {column_name}")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alipay_pay_orders_unionid_created
        ON alipay_pay_orders (unionid, created_at DESC, id DESC)
        WHERE unionid <> ''
        """
    )

    for table_name in [
        "customer_list_index_next",
        "customer_detail_snapshot_next",
        "customer_timeline_event_next",
        "customer_recent_message_next",
    ]:
        op.execute(f"ALTER TABLE IF EXISTS {table_name} ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")

    for table_name in [
        "customer_list_index_next",
        "customer_detail_snapshot_next",
        "customer_timeline_event_next",
        "customer_recent_message_next",
    ]:
        _backfill_read_model_unionid(table_name)
        _enqueue_unresolved_read_model_identity(table_name)

    for table_name in [
        "customer_list_index_next",
        "customer_detail_snapshot_next",
        "customer_timeline_event_next",
        "customer_recent_message_next",
    ]:
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS ix_{table_name}_unionid
            ON {table_name} (unionid)
            WHERE unionid <> ''
            """
        )
    _drop_dependent_audience_views()
    _drop_customer_read_model_legacy_identity_columns()


def _backfill_read_model_unionid(table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table_name}') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = '{table_name}' AND column_name = 'external_userid'
               ) THEN
                UPDATE {table_name} target
                SET unionid = cui.unionid
                FROM crm_user_identity cui
                WHERE COALESCE(target.unionid, '') = ''
                  AND COALESCE(target.external_userid, '') <> ''
                  AND (
                      cui.primary_external_userid = target.external_userid
                      OR jsonb_exists(cui.external_userids_json, target.external_userid)
                  );
            END IF;
        END $$;
        """
    )


def _enqueue_unresolved_read_model_identity(table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table_name}') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = '{table_name}' AND column_name = 'external_userid'
               ) THEN
                INSERT INTO crm_user_identity_resolution_queue (
                    source_type,
                    source_key,
                    source_table,
                    source_id,
                    external_userid,
                    payload_json,
                    reason,
                    status,
                    next_attempt_at,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                )
                SELECT
                    'customer_read_model_migration',
                    '{table_name}:' || target.id::text,
                    '{table_name}',
                    target.id::text,
                    target.external_userid,
                    to_jsonb(target),
                    'missing_unionid',
                    'pending',
                    NOW(),
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
                    last_seen_at = NOW(),
                    updated_at = NOW();
            END IF;
        END $$;
        """
    )


def _drop_customer_read_model_legacy_identity_columns() -> None:
    legacy_columns_by_table = {
        "customer_list_index_next": ["external_userid", "person_id"],
        "customer_detail_snapshot_next": ["external_userid", "person_id"],
        "customer_timeline_event_next": ["external_userid"],
        "customer_recent_message_next": ["external_userid"],
    }
    for table_name, column_names in legacy_columns_by_table.items():
        for column_name in column_names:
            op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS {column_name}")


def _drop_dependent_audience_views() -> None:
    op.execute("DROP VIEW IF EXISTS audience_read.huangxiaocan_member_usage_status_v1")


def downgrade() -> None:
    for table_name in [
        "customer_recent_message_next",
        "customer_timeline_event_next",
        "customer_detail_snapshot_next",
        "customer_list_index_next",
    ]:
        op.execute(f"DROP INDEX IF EXISTS ix_{table_name}_unionid")
        op.execute(f"ALTER TABLE IF EXISTS {table_name} DROP COLUMN IF EXISTS unionid")
    op.execute("DROP INDEX IF EXISTS idx_alipay_pay_orders_unionid_created")
    op.execute("ALTER TABLE IF EXISTS alipay_pay_orders DROP COLUMN IF EXISTS unionid")
