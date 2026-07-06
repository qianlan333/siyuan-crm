"""harden id-dev runtime baseline tables.

Revision ID: 0077_id_dev_runtime_baseline
Revises: 0076_create_missing_baseline_runtime_tables
"""

from __future__ import annotations

from alembic import op


revision = "0077_id_dev_runtime_baseline"
down_revision = "0076_create_missing_baseline_runtime_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _harden_user_ops_pool()
    _create_sidebar_profile_fields()
    _create_wecom_customer_acquisition_links()
    _create_archived_messages()
    _create_wechat_shop_orders()


def _harden_user_ops_pool() -> None:
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS customer_name_snapshot VARCHAR(255) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS owner_userid VARCHAR(128)")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS owner_display_name VARCHAR(255) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS class_term_no VARCHAR(80)")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS class_term_label VARCHAR(255) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS source_type VARCHAR(80) NOT NULL DEFAULT 'lead_pool'")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS activation_bucket VARCHAR(40) NOT NULL DEFAULT 'pending_input'")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS activation_bucket_label VARCHAR(80) NOT NULL DEFAULT '激活待录入'")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS auto_do_not_disturb_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE IF EXISTS user_ops_pool_current_next ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.user_ops_pool_current_next') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = 'user_ops_pool_current_next'
                     AND column_name = 'customer_name'
               ) THEN
                UPDATE user_ops_pool_current_next
                SET customer_name_snapshot = COALESCE(NULLIF(customer_name_snapshot, ''), customer_name, '')
                WHERE COALESCE(customer_name_snapshot, '') = ''
                  AND COALESCE(customer_name, '') <> '';
            END IF;
        END $$;
        """
    )
    for index_name, statement in [
        ("ix_user_ops_pool_current_next_unionid", "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_unionid ON user_ops_pool_current_next (unionid)"),
        ("ix_user_ops_pool_current_next_owner_userid", "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_owner_userid ON user_ops_pool_current_next (owner_userid)"),
        ("ix_user_ops_pool_current_next_class_term_no", "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_class_term_no ON user_ops_pool_current_next (class_term_no)"),
        ("ix_user_ops_pool_current_next_activation_bucket", "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_activation_bucket ON user_ops_pool_current_next (activation_bucket)"),
    ]:
        _create_index_if_table_exists("user_ops_pool_current_next", statement)
    for column_name in ["person_id", "mobile", "external_userid", "is_mobile_bound", "customer_name"]:
        op.execute(f"ALTER TABLE IF EXISTS user_ops_pool_current_next DROP COLUMN IF EXISTS {column_name}")


def _create_sidebar_profile_fields() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sidebar_customer_profile_fields (
            unionid TEXT PRIMARY KEY,
            source TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            industry_description TEXT NOT NULL DEFAULT '',
            needs_blockers_followup TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("ALTER TABLE IF EXISTS sidebar_customer_profile_fields ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.sidebar_customer_profile_fields') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = 'sidebar_customer_profile_fields'
                     AND column_name = 'external_userid'
               ) THEN
                UPDATE sidebar_customer_profile_fields profile
                SET unionid = identity.unionid
                FROM crm_user_identity identity
                WHERE COALESCE(profile.unionid, '') = ''
                  AND COALESCE(profile.external_userid, '') <> ''
                  AND (
                      identity.primary_external_userid = profile.external_userid
                      OR jsonb_exists(identity.external_userids_json, profile.external_userid)
                  );
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE IF EXISTS sidebar_customer_profile_fields DROP COLUMN IF EXISTS external_userid")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_sidebar_customer_profile_fields_unionid ON sidebar_customer_profile_fields (unionid) WHERE unionid <> ''")


def _create_wecom_customer_acquisition_links() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wecom_customer_acquisition_links (
            id BIGSERIAL PRIMARY KEY,
            automation_channel_id BIGINT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            customer_channel TEXT NOT NULL DEFAULT '',
            link_url TEXT NOT NULL DEFAULT '',
            final_url TEXT NOT NULL DEFAULT '',
            link_name TEXT NOT NULL DEFAULT '',
            initial_audience_code TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_wecom_customer_acquisition_links_channel_active
        ON wecom_customer_acquisition_links (automation_channel_id, status, updated_at DESC, id DESC)
        """
    )


def _create_archived_messages() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS archived_messages (
            id BIGSERIAL PRIMARY KEY,
            seq BIGINT NOT NULL DEFAULT 0,
            msgid TEXT NOT NULL DEFAULT '',
            chat_type TEXT NOT NULL DEFAULT 'private',
            unionid TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            sender TEXT NOT NULL DEFAULT '',
            receiver TEXT NOT NULL DEFAULT '',
            msgtype TEXT NOT NULL DEFAULT 'text',
            content TEXT NOT NULL DEFAULT '',
            send_time TIMESTAMPTZ,
            raw_payload TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_archived_messages_msgid ON archived_messages (msgid) WHERE msgid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_archived_messages_unionid_send_time ON archived_messages (unionid, send_time DESC, id DESC) WHERE unionid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_archived_messages_owner_send_time ON archived_messages (owner_userid, send_time DESC, id DESC) WHERE owner_userid <> ''")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS archive_sync_state (
            state_key TEXT PRIMARY KEY,
            last_seq BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_wechat_shop_orders() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_shop_orders (
            id BIGSERIAL PRIMARY KEY,
            order_id TEXT NOT NULL DEFAULT '',
            provider TEXT NOT NULL DEFAULT 'wechat_shop',
            provider_label TEXT NOT NULL DEFAULT '微信小店',
            deal_recorded BOOLEAN NOT NULL DEFAULT FALSE,
            returned_recorded BOOLEAN NOT NULL DEFAULT FALSE,
            business_status TEXT NOT NULL DEFAULT '',
            status_code TEXT NOT NULL DEFAULT '',
            status_label TEXT NOT NULL DEFAULT '',
            paid_at TIMESTAMPTZ,
            returned_at TIMESTAMPTZ,
            amount_total BIGINT NOT NULL DEFAULT 0,
            refunded_amount_total BIGINT NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            transaction_id TEXT NOT NULL DEFAULT '',
            payment_method TEXT NOT NULL DEFAULT '',
            unionid TEXT NOT NULL DEFAULT '',
            product_name TEXT NOT NULL DEFAULT '',
            product_code TEXT NOT NULL DEFAULT '',
            product_count INTEGER NOT NULL DEFAULT 0,
            deliver_method TEXT NOT NULL DEFAULT '',
            is_virtual_delivery BOOLEAN NOT NULL DEFAULT FALSE,
            virtual_account_no TEXT NOT NULL DEFAULT '',
            virtual_account_type TEXT NOT NULL DEFAULT '',
            aftersale_order_count INTEGER NOT NULL DEFAULT 0,
            on_aftersale_order_count INTEGER NOT NULL DEFAULT 0,
            finish_aftersale_sku_count INTEGER NOT NULL DEFAULT 0,
            raw_order_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_event_type TEXT NOT NULL DEFAULT '',
            last_event_at TIMESTAMPTZ,
            synced_at TIMESTAMPTZ,
            sync_status TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_wechat_shop_orders_order_id ON wechat_shop_orders (order_id) WHERE order_id <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wechat_shop_orders_unionid_created ON wechat_shop_orders (unionid, created_at DESC, id DESC) WHERE unionid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wechat_shop_orders_paid_at ON wechat_shop_orders (paid_at DESC, id DESC)")
    for column_name in ["buyer_mobile", "openid"]:
        op.execute(f"ALTER TABLE IF EXISTS wechat_shop_orders DROP COLUMN IF EXISTS {column_name}")


def _create_index_if_table_exists(table_name: str, statement: str) -> None:
    escaped_statement = statement.replace("'", "''")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table_name}') IS NOT NULL THEN
                EXECUTE '{escaped_statement}';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_wechat_shop_orders_paid_at")
    op.execute("DROP INDEX IF EXISTS ix_wechat_shop_orders_unionid_created")
    op.execute("DROP INDEX IF EXISTS ux_wechat_shop_orders_order_id")
    op.execute("DROP TABLE IF EXISTS wechat_shop_orders")
    op.execute("DROP TABLE IF EXISTS archive_sync_state")
    op.execute("DROP INDEX IF EXISTS ix_archived_messages_owner_send_time")
    op.execute("DROP INDEX IF EXISTS ix_archived_messages_unionid_send_time")
    op.execute("DROP INDEX IF EXISTS ux_archived_messages_msgid")
    op.execute("DROP TABLE IF EXISTS archived_messages")
    op.execute("DROP INDEX IF EXISTS ix_wecom_customer_acquisition_links_channel_active")
    op.execute("DROP TABLE IF EXISTS wecom_customer_acquisition_links")
    op.execute("DROP TABLE IF EXISTS sidebar_customer_profile_fields")
