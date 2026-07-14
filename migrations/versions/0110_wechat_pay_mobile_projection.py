"""backfill paid order mobiles into canonical user identity.

Revision ID: 0110_wechat_pay_mobile_projection
Revises: 0109_questionnaire_auto_execute
"""

from __future__ import annotations

from alembic import op


revision = "0110_wechat_pay_mobile_projection"
down_revision = "0109_questionnaire_auto_execute"
branch_labels = None
depends_on = None


_BACKFILL_SQL = """
        WITH raw_candidates AS (
            SELECT
                o.unionid,
                regexp_replace(
                    COALESCE(
                        NULLIF(o.metadata_json #>> '{payer_identity,mobile}', ''),
                        NULLIF(o.metadata_json #>> '{buyer_identity,mobile}', '')
                    ),
                    '[^0-9]',
                    '',
                    'g'
                ) AS mobile,
                COALESCE(NULLIF(o.metadata_json #>> '{payer_identity,external_userid}', ''), '') AS external_userid,
                COALESCE(NULLIF(o.metadata_json #>> '{payer_identity,openid}', ''), '') AS openid,
                COALESCE(NULLIF(o.metadata_json #>> '{payer_identity,owner_userid}', ''), '') AS owner_userid,
                COALESCE(NULLIF(o.payer_name_snapshot, ''), '') AS customer_name,
                o.out_trade_no,
                COALESCE(o.paid_at, o.updated_at, o.created_at) AS identity_seen_at,
                o.id
            FROM wechat_pay_orders o
            WHERE COALESCE(o.unionid, '') <> ''
              AND (o.status = 'paid' OR o.trade_state = 'SUCCESS')
        ),
        valid_candidates AS (
            SELECT *
            FROM raw_candidates
            WHERE mobile ~ '^1[0-9]{10}$'
        ),
        latest_per_unionid AS (
            SELECT DISTINCT ON (unionid)
                unionid,
                mobile,
                external_userid,
                openid,
                owner_userid,
                customer_name,
                out_trade_no,
                identity_seen_at,
                id
            FROM valid_candidates
            ORDER BY unionid, identity_seen_at DESC, id DESC
        ),
        ambiguity_checked AS (
            SELECT
                candidate.*,
                COUNT(*) OVER (PARTITION BY candidate.mobile) AS mobile_unionid_count
            FROM latest_per_unionid candidate
        ),
        safe_candidates AS (
            SELECT candidate.*
            FROM ambiguity_checked candidate
            WHERE candidate.mobile_unionid_count = 1
              AND NOT EXISTS (
                  SELECT 1
                  FROM crm_user_identity other
                  WHERE other.unionid <> candidate.unionid
                    AND regexp_replace(
                        COALESCE(NULLIF(other.mobile_normalized, ''), NULLIF(other.mobile, ''), ''),
                        '[^0-9]',
                        '',
                        'g'
                    ) = candidate.mobile
              )
        )
        INSERT INTO crm_user_identity (
            unionid,
            primary_external_userid,
            primary_openid,
            mobile,
            mobile_normalized,
            mobile_verified,
            mobile_source,
            customer_name,
            primary_owner_userid,
            profile_json,
            identity_status,
            unionid_resolved_at,
            first_seen_at,
            last_seen_at,
            created_at,
            updated_at
        )
        SELECT
            candidate.unionid,
            candidate.external_userid,
            candidate.openid,
            candidate.mobile,
            candidate.mobile,
            TRUE,
            'wechat_pay_order',
            candidate.customer_name,
            candidate.owner_userid,
            jsonb_build_object(
                'wechat_pay_mobile_projection_backfill',
                jsonb_build_object('out_trade_no', candidate.out_trade_no, 'migration', '0110')
            ),
            'active',
            candidate.identity_seen_at,
            candidate.identity_seen_at,
            candidate.identity_seen_at,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM safe_candidates candidate
        ON CONFLICT (unionid) DO UPDATE SET
            mobile = EXCLUDED.mobile,
            mobile_normalized = EXCLUDED.mobile_normalized,
            mobile_verified = crm_user_identity.mobile_verified OR EXCLUDED.mobile_verified,
            mobile_source = CASE
                WHEN COALESCE(NULLIF(crm_user_identity.mobile_source, ''), '') = '' THEN EXCLUDED.mobile_source
                ELSE crm_user_identity.mobile_source
            END,
            primary_external_userid = COALESCE(
                NULLIF(crm_user_identity.primary_external_userid, ''),
                NULLIF(EXCLUDED.primary_external_userid, ''),
                crm_user_identity.primary_external_userid
            ),
            primary_openid = COALESCE(
                NULLIF(crm_user_identity.primary_openid, ''),
                NULLIF(EXCLUDED.primary_openid, ''),
                crm_user_identity.primary_openid
            ),
            primary_owner_userid = COALESCE(
                NULLIF(crm_user_identity.primary_owner_userid, ''),
                NULLIF(EXCLUDED.primary_owner_userid, ''),
                crm_user_identity.primary_owner_userid
            ),
            customer_name = COALESCE(
                NULLIF(crm_user_identity.customer_name, ''),
                NULLIF(EXCLUDED.customer_name, ''),
                crm_user_identity.customer_name
            ),
            profile_json = COALESCE(crm_user_identity.profile_json, '{}'::jsonb) || EXCLUDED.profile_json,
            last_seen_at = GREATEST(crm_user_identity.last_seen_at, EXCLUDED.last_seen_at),
            updated_at = CURRENT_TIMESTAMP
        WHERE COALESCE(crm_user_identity.mobile, '') = ''
           OR crm_user_identity.mobile = EXCLUDED.mobile
           OR crm_user_identity.mobile_normalized = EXCLUDED.mobile_normalized
"""


def upgrade() -> None:
    op.execute(_BACKFILL_SQL)


def downgrade() -> None:
    # Canonical identity enrichment is intentionally retained on code rollback;
    # deleting verified customer contact data would be destructive.
    pass
