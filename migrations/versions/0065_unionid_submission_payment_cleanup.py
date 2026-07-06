"""drop legacy identity columns from submission and payment facts.

Revision ID: 0065_unionid_submission_payment_cleanup
Revises: 0064_unionid_ops_automation_foundation
"""

from __future__ import annotations

from alembic import op

from migrations.audience_read import ensure_audience_read_schema


revision = "0065_unionid_submission_payment_cleanup"
down_revision = "0064_unionid_ops_automation_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS audience_read.questionnaire_submissions_v1")
    op.execute("DROP VIEW IF EXISTS audience_read.orders_v1")
    _prepare_questionnaire_submissions()
    _prepare_wechat_pay_orders()
    _recreate_audience_read_views()


def _prepare_questionnaire_submissions() -> None:
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.questionnaire_submissions') IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'questionnaire_submissions' AND column_name = 'external_userid'
                ) THEN
                    EXECUTE $sql$
                        UPDATE questionnaire_submissions qs
                        SET unionid = cui.unionid
                        FROM crm_user_identity cui
                        WHERE COALESCE(qs.unionid, '') = ''
                          AND COALESCE(qs.external_userid, '') <> ''
                          AND (cui.primary_external_userid = qs.external_userid OR jsonb_exists(cui.external_userids_json, qs.external_userid))
                    $sql$;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'questionnaire_submissions' AND column_name = 'openid'
                ) THEN
                    EXECUTE $sql$
                        UPDATE questionnaire_submissions qs
                        SET unionid = cui.unionid
                        FROM crm_user_identity cui
                        WHERE COALESCE(qs.unionid, '') = ''
                          AND COALESCE(qs.openid, '') <> ''
                          AND jsonb_exists(cui.openids_json, qs.openid)
                    $sql$;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'questionnaire_submissions' AND column_name = 'respondent_key'
                ) THEN
                    EXECUTE $sql$
                        UPDATE questionnaire_submissions
                        SET unionid = respondent_key
                        WHERE COALESCE(unionid, '') = ''
                          AND COALESCE(respondent_key, '') <> ''
                    $sql$;
                END IF;
            END IF;
        END $$;
        """
    )
    _create_index_if_table_exists(
        "questionnaire_submissions",
        "CREATE INDEX IF NOT EXISTS idx_questionnaire_submissions_unionid_submitted ON questionnaire_submissions (unionid, submitted_at DESC, id DESC) WHERE unionid <> ''",
    )
    for column_name in ["identity_map_id", "respondent_key", "openid", "external_userid", "mobile_snapshot"]:
        op.execute(f"ALTER TABLE IF EXISTS questionnaire_submissions DROP COLUMN IF EXISTS {column_name}")


def _prepare_wechat_pay_orders() -> None:
    op.execute("ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wechat_pay_orders') IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'wechat_pay_orders' AND column_name = 'external_userid'
                ) THEN
                    EXECUTE $sql$
                        UPDATE wechat_pay_orders orders
                        SET unionid = cui.unionid
                        FROM crm_user_identity cui
                        WHERE COALESCE(orders.unionid, '') = ''
                          AND COALESCE(orders.external_userid, '') <> ''
                          AND (cui.primary_external_userid = orders.external_userid OR jsonb_exists(cui.external_userids_json, orders.external_userid))
                    $sql$;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'wechat_pay_orders' AND column_name = 'payer_openid'
                ) THEN
                    EXECUTE $sql$
                        UPDATE wechat_pay_orders orders
                        SET unionid = cui.unionid
                        FROM crm_user_identity cui
                        WHERE COALESCE(orders.unionid, '') = ''
                          AND COALESCE(orders.payer_openid, '') <> ''
                          AND jsonb_exists(cui.openids_json, orders.payer_openid)
                    $sql$;
                END IF;

                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'wechat_pay_orders' AND column_name = 'respondent_key'
                ) THEN
                    EXECUTE $sql$
                        UPDATE wechat_pay_orders
                        SET unionid = respondent_key
                        WHERE COALESCE(unionid, '') = ''
                          AND COALESCE(respondent_key, '') <> ''
                    $sql$;
                END IF;
            END IF;
        END $$;
        """
    )
    _create_index_if_table_exists(
        "wechat_pay_orders",
        "CREATE INDEX IF NOT EXISTS idx_wechat_pay_orders_unionid_created ON wechat_pay_orders (unionid, created_at DESC, id DESC) WHERE unionid <> ''",
    )
    for column_name in ["payer_openid", "respondent_key", "external_userid", "userid_snapshot", "mobile_snapshot"]:
        op.execute(f"ALTER TABLE IF EXISTS wechat_pay_orders DROP COLUMN IF EXISTS {column_name}")


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


def _recreate_audience_read_views() -> None:
    if not ensure_audience_read_schema():
        return
    op.execute(
        """
        DO $$
        DECLARE
            updated_at_expr TEXT;
        BEGIN
            IF to_regclass('public.questionnaire_submissions') IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'questionnaire_submissions' AND column_name = 'updated_at'
                ) THEN
                    updated_at_expr := 'qs.updated_at';
                ELSIF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'questionnaire_submissions' AND column_name = 'submitted_at'
                ) THEN
                    updated_at_expr := 'qs.submitted_at';
                ELSE
                    updated_at_expr := 'qs.created_at';
                END IF;

                EXECUTE format($sql$
                CREATE OR REPLACE VIEW audience_read.questionnaire_submissions_v1 AS
                SELECT
                    qs.id AS submission_id,
                    qs.questionnaire_id,
                    qs.unionid,
                    COALESCE(identity.primary_external_userid, '')::text AS external_userid,
                    qs.follow_user_userid AS owner_userid,
                    ''::text AS mobile_hash,
                    qs.submitted_at,
                    qs.created_at,
                    %s AS updated_at,
                    qs.total_score,
                    qs.final_tags,
                    qs.assessment_result_snapshot,
                    'unionid'::text AS identity_type,
                    qs.unionid::text AS identity_value,
                    jsonb_build_object(
                        'submission_id', qs.id,
                        'questionnaire_id', qs.questionnaire_id,
                        'unionid', qs.unionid,
                        'score', qs.total_score,
                        'tags', qs.final_tags
                    ) AS payload_json
                FROM questionnaire_submissions qs
                LEFT JOIN crm_user_identity identity ON identity.unionid = qs.unionid
                $sql$, updated_at_expr);
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
                    o.id AS order_id,
                    o.out_trade_no,
                    o.transaction_id,
                    o.unionid,
                    COALESCE(identity.primary_external_userid, '')::text AS external_userid,
                    ''::text AS mobile_hash,
                    ''::text AS owner_userid,
                    o.product_code,
                    o.product_name,
                    o.status,
                    o.trade_state,
                    o.amount_total,
                    o.paid_at,
                    o.created_at,
                    o.metadata_json,
                    'unionid'::text AS identity_type,
                    o.unionid::text AS identity_value,
                    jsonb_build_object(
                        'order_id', o.id,
                        'out_trade_no', o.out_trade_no,
                        'unionid', o.unionid,
                        'product_code', o.product_code,
                        'amount_total', o.amount_total,
                        'status', o.status,
                        'trade_state', o.trade_state
                    ) AS payload_json
                FROM wechat_pay_orders o
                LEFT JOIN crm_user_identity identity ON identity.unionid = o.unionid;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for column_name in ["payer_openid", "respondent_key", "external_userid", "userid_snapshot", "mobile_snapshot"]:
        op.execute(f"ALTER TABLE IF EXISTS wechat_pay_orders ADD COLUMN IF NOT EXISTS {column_name} TEXT NOT NULL DEFAULT ''")
    for column_name in ["respondent_key", "openid", "external_userid", "mobile_snapshot"]:
        op.execute(f"ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS {column_name} TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS questionnaire_submissions ADD COLUMN IF NOT EXISTS identity_map_id BIGINT")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_submissions_unionid_submitted")
