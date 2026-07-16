"""ai audience ops tables and read views.

Revision ID: 0045_ai_audience_ops
Revises: 0044_retire_legacy_webhook_deprecations
"""

from __future__ import annotations

from alembic import op


revision = "0045_ai_audience_ops"
down_revision = "0044_retire_legacy_webhook_deprecations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS audience_read")
    _create_tables()
    _create_source_column_guards()
    _create_views()


def downgrade() -> None:
    for view_name in (
        "channel_entries_v1",
        "wecom_contacts_v1",
        "orders_v1",
        "questionnaire_submissions_v1",
        "identity_universe_v1",
    ):
        op.execute(f"DROP VIEW IF EXISTS audience_read.{view_name}")
    op.execute("ALTER TABLE IF EXISTS ai_audience_package DROP CONSTRAINT IF EXISTS fk_ai_audience_package_current_version")
    op.execute("DROP TABLE IF EXISTS ai_audience_package_dependency")
    op.execute("DROP TABLE IF EXISTS ai_audience_inbound_webhook_event")
    op.execute("DROP TABLE IF EXISTS ai_audience_outbound_subscription")
    op.execute("DROP TABLE IF EXISTS ai_audience_member_event")
    op.execute("DROP TABLE IF EXISTS ai_audience_member_current")
    op.execute("DROP TABLE IF EXISTS ai_audience_package_run")
    op.execute("DROP TABLE IF EXISTS ai_audience_package_version")
    op.execute("DROP TABLE IF EXISTS ai_audience_package")
    op.execute("DROP SCHEMA IF EXISTS audience_read")


def _create_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_package (
            id BIGSERIAL PRIMARY KEY,
            package_key TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            natural_language_definition TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            query_mode TEXT NOT NULL DEFAULT 'hybrid',
            identity_policy TEXT NOT NULL DEFAULT 'external_userid',
            current_version_id BIGINT,
            incremental_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            daily_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            incremental_interval_seconds INTEGER NOT NULL DEFAULT 180,
            daily_refresh_time TEXT NOT NULL DEFAULT ('03' || ':' || '00'),
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            lookback_seconds INTEGER NOT NULL DEFAULT 600,
            last_incremental_watermark_at TIMESTAMPTZ,
            last_daily_refreshed_at TIMESTAMPTZ,
            next_incremental_refresh_at TIMESTAMPTZ,
            next_daily_refresh_at TIMESTAMPTZ,
            lease_token TEXT NOT NULL DEFAULT '',
            lease_expires_at TIMESTAMPTZ,
            paused_reason TEXT NOT NULL DEFAULT '',
            inbound_webhook_secret TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_ai_audience_package_key UNIQUE (package_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_package_version (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            version_number INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            incremental_sql_text TEXT NOT NULL DEFAULT '',
            snapshot_sql_text TEXT NOT NULL DEFAULT '',
            ai_prompt TEXT NOT NULL DEFAULT '',
            ai_rationale TEXT NOT NULL DEFAULT '',
            natural_language_explanation TEXT NOT NULL DEFAULT '',
            dependencies_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            explain_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            sample_rows_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            validation_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMPTZ,
            CONSTRAINT uq_ai_audience_package_version_number UNIQUE (package_id, version_number)
        )
        """
    )
    op.execute("ALTER TABLE IF EXISTS ai_audience_package DROP CONSTRAINT IF EXISTS fk_ai_audience_package_current_version")
    op.execute(
        """
        ALTER TABLE ai_audience_package
        ADD CONSTRAINT fk_ai_audience_package_current_version
        FOREIGN KEY (current_version_id)
        REFERENCES ai_audience_package_version(id)
        ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_package_run (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            version_id BIGINT REFERENCES ai_audience_package_version(id) ON DELETE SET NULL,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            refresh_started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            refresh_finished_at TIMESTAMPTZ,
            last_watermark_at TIMESTAMPTZ,
            next_watermark_at TIMESTAMPTZ,
            returned_count INTEGER NOT NULL DEFAULT 0,
            entered_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            exited_count INTEGER NOT NULL DEFAULT 0,
            member_event_count INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_member_current (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            identity_type TEXT NOT NULL,
            identity_value TEXT NOT NULL,
            unionid TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            mobile_hash TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            event_source_key TEXT NOT NULL DEFAULT '',
            payload_hash TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            first_entered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            exited_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_ai_audience_member_current_identity UNIQUE (package_id, identity_type, identity_value)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_member_event (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            run_id BIGINT REFERENCES ai_audience_package_run(id) ON DELETE SET NULL,
            member_current_id BIGINT REFERENCES ai_audience_member_current(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            identity_type TEXT NOT NULL,
            identity_value TEXT NOT NULL,
            unionid TEXT NOT NULL DEFAULT '',
            mobile_hash TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            event_source_key TEXT NOT NULL DEFAULT '',
            payload_hash TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            internal_event_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_ai_audience_member_event_idempotency UNIQUE (idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_outbound_subscription (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'active',
            trigger_event_type TEXT NOT NULL DEFAULT 'entered',
            dispatch_mode TEXT NOT NULL DEFAULT 'per_member',
            target_type TEXT NOT NULL DEFAULT 'webhook',
            webhook_url TEXT NOT NULL DEFAULT '',
            signing_secret TEXT NOT NULL DEFAULT '',
            headers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_template_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            execution_mode TEXT NOT NULL DEFAULT 'execute',
            requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_inbound_webhook_event (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            external_event_id TEXT NOT NULL DEFAULT '',
            member_event_id BIGINT REFERENCES ai_audience_member_event(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT '',
            message_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            action_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            signature_valid BOOLEAN NOT NULL DEFAULT FALSE,
            idempotency_key TEXT NOT NULL,
            external_effect_job_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_ai_audience_inbound_webhook_idempotency UNIQUE (idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_audience_package_dependency (
            id BIGSERIAL PRIMARY KEY,
            package_id BIGINT NOT NULL REFERENCES ai_audience_package(id) ON DELETE CASCADE,
            version_id BIGINT REFERENCES ai_audience_package_version(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL DEFAULT '',
            source_key TEXT NOT NULL DEFAULT '',
            view_name TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_ai_audience_package_dependency UNIQUE (package_id, version_id, source_type, source_key, view_name)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_audience_package_incremental_due
        ON ai_audience_package(status, next_incremental_refresh_at)
        WHERE status = 'active' AND incremental_enabled = TRUE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_audience_package_daily_due
        ON ai_audience_package(status, next_daily_refresh_at)
        WHERE status = 'active' AND daily_enabled = TRUE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_audience_member_current_package_status
        ON ai_audience_member_current(package_id, status, first_entered_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_audience_member_event_package_time
        ON ai_audience_member_event(package_id, occurred_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_audience_outbound_subscription_package
        ON ai_audience_outbound_subscription(package_id, status, trigger_event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_audience_dependency_source
        ON ai_audience_package_dependency(source_type, source_key, package_id)
        """
    )


def _create_source_column_guards() -> None:
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS questionnaire_id BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS respondent_key TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS total_score INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS final_tags JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS assessment_result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS source_channel TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS campaign_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS staff_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS follow_user_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact ADD COLUMN IF NOT EXISTS owner_staff_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact ADD COLUMN IF NOT EXISTS first_channel_entered_at TIMESTAMPTZ")
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact ADD COLUMN IF NOT EXISTS last_channel_entered_at TIMESTAMPTZ")
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact ADD COLUMN IF NOT EXISTS source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS out_trade_no TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS transaction_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS userid_snapshot TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS product_code TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS product_name TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS trade_state TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS amount_total INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE IF EXISTS external_contact_bindings ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS external_contact_bindings ADD COLUMN IF NOT EXISTS person_id TEXT")
    op.execute("ALTER TABLE IF EXISTS external_contact_bindings ADD COLUMN IF NOT EXISTS first_owner_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS external_contact_bindings ADD COLUMN IF NOT EXISTS last_owner_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS external_contact_bindings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS openid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS follow_user_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ")


def _create_views() -> None:
    _empty_views()
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.external_contact_bindings') IS NOT NULL
               AND to_regclass('public.wecom_external_contact_identity_map') IS NOT NULL
               AND to_regclass('public.automation_channel_contact') IS NOT NULL THEN
                CREATE OR REPLACE VIEW audience_read.identity_universe_v1 AS
                SELECT
                    CASE WHEN b.person_id::text ~ '^[0-9]+$' THEN b.person_id::text::bigint ELSE NULL END AS person_id,
                    COALESCE(b.external_userid, '')::text AS external_userid,
                    ''::text AS mobile_hash,
                    COALESCE(NULLIF(b.last_owner_userid, ''), NULLIF(b.first_owner_userid, ''), '')::text AS owner_userid,
                    'external_userid'::text AS identity_type,
                    COALESCE(b.external_userid, '')::text AS identity_value,
                    'external_contact_bindings'::text AS source_table,
                    COALESCE(b.updated_at::timestamptz, CURRENT_TIMESTAMP) AS updated_at
                FROM external_contact_bindings b
                WHERE COALESCE(b.external_userid, '') <> ''
                UNION ALL
                SELECT
                    NULL::bigint AS person_id,
                    COALESCE(im.external_userid, '')::text AS external_userid,
                    ''::text AS mobile_hash,
                    COALESCE(NULLIF(im.follow_user_userid, ''), '')::text AS owner_userid,
                    'external_userid'::text AS identity_type,
                    COALESCE(im.external_userid, '')::text AS identity_value,
                    'wecom_external_contact_identity_map'::text AS source_table,
                    COALESCE(im.updated_at::timestamptz, CURRENT_TIMESTAMP) AS updated_at
                FROM wecom_external_contact_identity_map im
                WHERE COALESCE(im.external_userid, '') <> ''
                UNION ALL
                SELECT
                    NULL::bigint AS person_id,
                    COALESCE(NULLIF(cc.external_userid, ''), cc.external_contact_id, '')::text AS external_userid,
                    ''::text AS mobile_hash,
                    COALESCE(cc.owner_staff_id, '')::text AS owner_userid,
                    'external_userid'::text AS identity_type,
                    COALESCE(NULLIF(cc.external_userid, ''), cc.external_contact_id, '')::text AS identity_value,
                    'automation_channel_contact'::text AS source_table,
                    COALESCE(cc.updated_at::timestamptz, CURRENT_TIMESTAMP) AS updated_at
                FROM automation_channel_contact cc
                WHERE COALESCE(NULLIF(cc.external_userid, ''), cc.external_contact_id, '') <> '';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.questionnaire_submissions') IS NOT NULL THEN
                CREATE OR REPLACE VIEW audience_read.questionnaire_submissions_v1 AS
                SELECT
                    qs.id::bigint AS submission_id,
                    qs.questionnaire_id::bigint AS questionnaire_id,
                    COALESCE(qs.respondent_key, '')::text AS respondent_key,
                    COALESCE(qs.external_userid, '')::text AS external_userid,
                    CASE WHEN COALESCE(qs.mobile_snapshot, '') <> '' THEN md5(qs.mobile_snapshot) ELSE '' END::text AS mobile_hash,
                    COALESCE(NULLIF(qs.staff_id, ''), NULLIF(qs.follow_user_userid, ''), '')::text AS owner_userid,
                    COALESCE(qs.submitted_at, qs.created_at, CURRENT_TIMESTAMP)::timestamptz AS submitted_at,
                    qs.total_score::integer AS total_score,
                    COALESCE(qs.final_tags, '[]'::jsonb) AS final_tags_json,
                    COALESCE(qs.assessment_result_snapshot, '{}'::jsonb) AS assessment_result_json,
                    jsonb_build_object(
                        'submission_id', qs.id,
                        'questionnaire_id', qs.questionnaire_id,
                        'respondent_key', COALESCE(qs.respondent_key, ''),
                        'source_channel', COALESCE(qs.source_channel, ''),
                        'campaign_id', COALESCE(qs.campaign_id, ''),
                        'total_score', qs.total_score
                    ) AS payload_json
                FROM questionnaire_submissions qs;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wechat_pay_orders') IS NOT NULL THEN
                CREATE OR REPLACE VIEW audience_read.orders_v1 AS
                SELECT
                    o.id::bigint AS order_id,
                    COALESCE(o.out_trade_no, '')::text AS out_trade_no,
                    COALESCE(o.transaction_id, '')::text AS transaction_id,
                    COALESCE(o.external_userid, '')::text AS external_userid,
                    CASE WHEN COALESCE(o.mobile_snapshot, '') <> '' THEN md5(o.mobile_snapshot) ELSE '' END::text AS mobile_hash,
                    COALESCE(o.userid_snapshot, '')::text AS owner_userid,
                    COALESCE(o.product_code, '')::text AS product_code,
                    COALESCE(o.product_name, '')::text AS product_name,
                    COALESCE(o.status, '')::text AS status,
                    COALESCE(o.trade_state, '')::text AS trade_state,
                    COALESCE(o.amount_total, 0)::integer AS amount_total,
                    o.paid_at::timestamptz AS paid_at,
                    COALESCE(o.created_at, CURRENT_TIMESTAMP)::timestamptz AS created_at,
                    COALESCE(o.metadata_json, '{}'::jsonb) AS metadata_json,
                    jsonb_build_object(
                        'order_id', o.id,
                        'out_trade_no', COALESCE(o.out_trade_no, ''),
                        'transaction_id', COALESCE(o.transaction_id, ''),
                        'product_code', COALESCE(o.product_code, ''),
                        'amount_total', COALESCE(o.amount_total, 0),
                        'status', COALESCE(o.status, ''),
                        'trade_state', COALESCE(o.trade_state, '')
                    ) AS payload_json
                FROM wechat_pay_orders o;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wecom_external_contact_identity_map') IS NOT NULL THEN
                CREATE OR REPLACE VIEW audience_read.wecom_contacts_v1 AS
                SELECT
                    COALESCE(im.external_userid, '')::text AS external_userid,
                    COALESCE(im.unionid, '')::text AS unionid,
                    COALESCE(im.openid, '')::text AS openid,
                    COALESCE(NULLIF(im.follow_user_userid, ''), '')::text AS owner_userid,
                    COALESCE(im.name, '')::text AS customer_name,
                    COALESCE(im.status, '')::text AS status,
                    COALESCE(im.updated_at::timestamptz, CURRENT_TIMESTAMP) AS updated_at,
                    jsonb_build_object(
                        'external_userid', COALESCE(im.external_userid, ''),
                        'unionid', COALESCE(im.unionid, ''),
                        'openid', COALESCE(im.openid, ''),
                        'owner_userid', COALESCE(im.follow_user_userid, ''),
                        'name', COALESCE(im.name, ''),
                        'status', COALESCE(im.status, '')
                    ) AS payload_json
                FROM wecom_external_contact_identity_map im
                WHERE COALESCE(im.external_userid, '') <> '';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_channel_contact') IS NOT NULL
               AND to_regclass('public.automation_channel') IS NOT NULL THEN
                CREATE OR REPLACE VIEW audience_read.channel_entries_v1 AS
                SELECT
                    cc.id::bigint AS channel_entry_id,
                    cc.channel_id::bigint AS channel_id,
                    COALESCE(c.channel_code, '')::text AS channel_code,
                    COALESCE(c.channel_name, '')::text AS channel_name,
                    COALESCE(c.scene_value, '')::text AS scene_value,
                    COALESCE(NULLIF(cc.external_userid, ''), cc.external_contact_id, '')::text AS external_userid,
                    COALESCE(cc.owner_staff_id, '')::text AS owner_userid,
                    COALESCE(cc.first_channel_entered_at, cc.created_at, CURRENT_TIMESTAMP)::timestamptz AS first_entered_at,
                    COALESCE(cc.last_channel_entered_at, cc.updated_at, CURRENT_TIMESTAMP)::timestamptz AS last_entered_at,
                    COALESCE(cc.enter_count, 1)::integer AS enter_count,
                    COALESCE(cc.source_payload_json, '{}'::jsonb) AS source_payload_json,
                    jsonb_build_object(
                        'channel_entry_id', cc.id,
                        'channel_id', cc.channel_id,
                        'channel_code', COALESCE(c.channel_code, ''),
                        'channel_name', COALESCE(c.channel_name, ''),
                        'scene_value', COALESCE(c.scene_value, ''),
                        'external_userid', COALESCE(NULLIF(cc.external_userid, ''), cc.external_contact_id, ''),
                        'owner_userid', COALESCE(cc.owner_staff_id, ''),
                        'enter_count', COALESCE(cc.enter_count, 1)
                    ) AS payload_json
                FROM automation_channel_contact cc
                LEFT JOIN automation_channel c ON c.id = cc.channel_id
                WHERE COALESCE(NULLIF(cc.external_userid, ''), cc.external_contact_id, '') <> '';
            END IF;
        END $$;
        """
    )


def _empty_views() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.identity_universe_v1 AS
        SELECT NULL::bigint AS person_id, ''::text AS external_userid, ''::text AS mobile_hash,
               ''::text AS owner_userid, ''::text AS identity_type, ''::text AS identity_value,
               ''::text AS source_table, NULL::timestamptz AS updated_at
        WHERE FALSE
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.questionnaire_submissions_v1 AS
        SELECT NULL::bigint AS submission_id, NULL::bigint AS questionnaire_id, ''::text AS respondent_key,
               ''::text AS external_userid, ''::text AS mobile_hash, ''::text AS owner_userid,
               NULL::timestamptz AS submitted_at, 0::integer AS total_score, '[]'::jsonb AS final_tags_json,
               '{}'::jsonb AS assessment_result_json, '{}'::jsonb AS payload_json
        WHERE FALSE
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.orders_v1 AS
        SELECT NULL::bigint AS order_id, ''::text AS out_trade_no, ''::text AS transaction_id,
               ''::text AS external_userid, ''::text AS mobile_hash, ''::text AS owner_userid,
               ''::text AS product_code, ''::text AS product_name, ''::text AS status, ''::text AS trade_state,
               0::integer AS amount_total, NULL::timestamptz AS paid_at, NULL::timestamptz AS created_at,
               '{}'::jsonb AS metadata_json, '{}'::jsonb AS payload_json
        WHERE FALSE
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.wecom_contacts_v1 AS
        SELECT ''::text AS external_userid, ''::text AS unionid, ''::text AS openid,
               ''::text AS owner_userid, ''::text AS customer_name, ''::text AS status,
               NULL::timestamptz AS updated_at, '{}'::jsonb AS payload_json
        WHERE FALSE
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.channel_entries_v1 AS
        SELECT NULL::bigint AS channel_entry_id, NULL::bigint AS channel_id, ''::text AS channel_code,
               ''::text AS channel_name, ''::text AS scene_value, ''::text AS external_userid,
               ''::text AS owner_userid, NULL::timestamptz AS first_entered_at,
               NULL::timestamptz AS last_entered_at, 0::integer AS enter_count,
               '{}'::jsonb AS source_payload_json, '{}'::jsonb AS payload_json
        WHERE FALSE
        """
    )
