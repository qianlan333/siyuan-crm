"""backfill paid WeChat Shop mobiles into canonical user identity.

Revision ID: 0111_wechat_shop_mobile_projection
Revises: 0110_wechat_pay_mobile_projection
"""

from __future__ import annotations

from alembic import op


revision = "0111_wechat_shop_mobile_projection"
down_revision = "0110_wechat_pay_mobile_projection"
branch_labels = None
depends_on = None


_BACKFILL_SQL = """
        WITH raw_candidates AS (
            SELECT
                TRIM(o.unionid) AS unionid,
                regexp_replace(
                    COALESCE(
                        NULLIF(o.raw_order_json #>> '{order,order_detail,delivery_info,address_info,virtual_order_tel_number}', ''),
                        NULLIF(o.raw_order_json #>> '{order,order_detail,delivery_info,address_info,purchaser_tel_number}', ''),
                        NULLIF(o.raw_order_json #>> '{order,order_detail,delivery_info,address_info,tel_number}', ''),
                        NULLIF(o.raw_order_json #>> '{order_detail,delivery_info,address_info,virtual_order_tel_number}', ''),
                        NULLIF(o.raw_order_json #>> '{order_detail,delivery_info,address_info,purchaser_tel_number}', ''),
                        NULLIF(o.raw_order_json #>> '{order_detail,delivery_info,address_info,tel_number}', '')
                    ),
                    '[^0-9]',
                    '',
                    'g'
                ) AS mobile,
                COALESCE(
                    NULLIF(o.raw_order_json #>> '{order,openid}', ''),
                    NULLIF(o.raw_order_json #>> '{order,order_detail,openid}', ''),
                    NULLIF(o.raw_order_json #>> '{order,order_detail,pay_info,openid}', ''),
                    NULLIF(o.raw_order_json #>> '{openid}', ''),
                    NULLIF(o.raw_order_json #>> '{order_detail,openid}', ''),
                    NULLIF(o.raw_order_json #>> '{order_detail,pay_info,openid}', ''),
                    ''
                ) AS openid,
                o.order_id,
                COALESCE(o.paid_at, o.updated_at, o.created_at) AS identity_seen_at,
                o.id
            FROM wechat_shop_orders o
            WHERE o.paid_at IS NOT NULL
              AND COALESCE(TRIM(o.unionid), '') <> ''
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
                openid,
                order_id,
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
            primary_openid,
            mobile,
            mobile_normalized,
            mobile_verified,
            mobile_source,
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
            candidate.openid,
            candidate.mobile,
            candidate.mobile,
            TRUE,
            'wechat_shop_order',
            jsonb_build_object(
                'wechat_shop_mobile_projection_backfill',
                jsonb_build_object('order_id', candidate.order_id, 'migration', '0111')
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
            primary_openid = COALESCE(
                NULLIF(crm_user_identity.primary_openid, ''),
                NULLIF(EXCLUDED.primary_openid, ''),
                crm_user_identity.primary_openid
            ),
            profile_json = COALESCE(crm_user_identity.profile_json, '{}'::jsonb) || EXCLUDED.profile_json,
            last_seen_at = GREATEST(
                COALESCE(crm_user_identity.last_seen_at, EXCLUDED.last_seen_at),
                EXCLUDED.last_seen_at
            ),
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
