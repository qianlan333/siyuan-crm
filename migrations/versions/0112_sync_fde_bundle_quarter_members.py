"""sync FDE bundle signups into the quarterly service-period product.

Revision ID: 0112_sync_fde_quarter_members
Revises: 0111_wechat_shop_mobile_projection
"""

from __future__ import annotations

from alembic import op


revision = "0112_sync_fde_quarter_members"
down_revision = "0111_wechat_shop_mobile_projection"
branch_labels = None
depends_on = None


SOURCE_PRODUCT_CODE = "SOAK-FDE-BUNDLE-S1"
TARGET_PRODUCT_CODE = "ces"
TARGET_PRODUCT_NAME = "老黄的 AI+ 进化同行圈/每季度"
DURATION_DAYS = 90
AUDIT_EVENT_PREFIX = "service_period:admin_adjusted:"
MIGRATION_KEY = "0112_sync_fde_quarter_members"


_SYNC_SQL = f"""
WITH target_product AS (
    SELECT
        sp.id AS service_product_id,
        sp.trade_product_id,
        sp.membership_config_id,
        sp.duration_days
    FROM service_period_products sp
    JOIN wechat_pay_products wp ON wp.id = sp.trade_product_id
    WHERE sp.tenant_id = 'aicrm'
      AND sp.deleted = FALSE
      AND sp.duration_days = {DURATION_DAYS}
      AND wp.product_code = '{TARGET_PRODUCT_CODE}'
      AND wp.name = '{TARGET_PRODUCT_NAME}'
    LIMIT 1
),
source_orders AS (
    SELECT DISTINCT ON (o.unionid)
        o.id AS order_id,
        o.out_trade_no,
        o.unionid,
        o.paid_at,
        o.payer_name_snapshot,
        COALESCE(
            NULLIF(identity.primary_external_userid, ''),
            NULLIF(o.metadata_json #>> '{{payer_identity,external_userid}}', ''),
            ''
        ) AS external_userid,
        target.service_product_id,
        target.trade_product_id,
        target.membership_config_id,
        target.duration_days
    FROM wechat_pay_orders o
    CROSS JOIN target_product target
    LEFT JOIN crm_user_identity identity ON identity.unionid = o.unionid
    WHERE o.product_code = '{SOURCE_PRODUCT_CODE}'
      AND (o.status = 'paid' OR o.trade_state = 'SUCCESS')
      AND o.paid_at IS NOT NULL
      AND COALESCE(o.unionid, '') <> ''
      AND COALESCE(o.refunded_amount_total, 0) = 0
      AND LOWER(COALESCE(o.refund_status, '')) NOT IN (
          'requested', 'processing', 'refund_processing',
          'partial_refunded', 'full_refunded'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM service_period_events synced
          WHERE synced.tenant_id = 'aicrm'
            AND synced.service_product_id = target.service_product_id
            AND synced.unionid = o.unionid
            AND synced.payload_json ->> 'migration' = '{MIGRATION_KEY}'
      )
    ORDER BY o.unionid, o.paid_at ASC, o.id ASC
),
existing AS MATERIALIZED (
    SELECT entitlement.*
    FROM service_period_entitlements entitlement
    JOIN source_orders source
      ON source.service_product_id = entitlement.service_product_id
     AND source.unionid = entitlement.unionid
    WHERE entitlement.tenant_id = 'aicrm'
    FOR UPDATE
),
upserted AS (
    INSERT INTO service_period_entitlements (
        tenant_id,
        service_product_id,
        trade_product_id,
        unionid,
        external_userid_snapshot,
        membership_config_id,
        status,
        start_at,
        end_at,
        last_order_id,
        last_out_trade_no,
        renewal_count,
        metadata_json,
        created_at,
        updated_at
    )
    SELECT
        'aicrm',
        source.service_product_id,
        source.trade_product_id,
        source.unionid,
        source.external_userid,
        source.membership_config_id,
        'active',
        source.paid_at,
        source.paid_at + INTERVAL '{DURATION_DAYS} days',
        source.order_id,
        source.out_trade_no,
        0,
        jsonb_build_object(
            'payer_name', source.payer_name_snapshot,
            'fde_bundle_quarter_membership_sync', jsonb_build_object(
                'migration', '{MIGRATION_KEY}',
                'source_product_code', '{SOURCE_PRODUCT_CODE}',
                'source_order_id', source.order_id,
                'source_out_trade_no', source.out_trade_no,
                'source_paid_at', source.paid_at,
                'duration_days', {DURATION_DAYS}
            )
        ),
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    FROM source_orders source
    LEFT JOIN existing previous
      ON previous.service_product_id = source.service_product_id
     AND previous.unionid = source.unionid
    ON CONFLICT (tenant_id, service_product_id, unionid) DO UPDATE SET
        trade_product_id = EXCLUDED.trade_product_id,
        external_userid_snapshot = COALESCE(
            NULLIF(EXCLUDED.external_userid_snapshot, ''),
            service_period_entitlements.external_userid_snapshot
        ),
        membership_config_id = EXCLUDED.membership_config_id,
        status = 'active',
        start_at = EXCLUDED.start_at,
        end_at = EXCLUDED.end_at,
        last_order_id = EXCLUDED.last_order_id,
        last_out_trade_no = EXCLUDED.last_out_trade_no,
        metadata_json = COALESCE(service_period_entitlements.metadata_json, '{{}}'::jsonb)
            || EXCLUDED.metadata_json,
        updated_at = CURRENT_TIMESTAMP
    RETURNING *
)
INSERT INTO service_period_events (
    tenant_id,
    event_id,
    service_product_id,
    entitlement_id,
    trade_product_id,
    order_id,
    out_trade_no,
    unionid,
    event_type,
    duration_days,
    before_start_at,
    before_end_at,
    after_start_at,
    after_end_at,
    payload_json,
    created_at
)
SELECT
    'aicrm',
    '{AUDIT_EVENT_PREFIX}' || source.out_trade_no,
    source.service_product_id,
    synced.id,
    source.trade_product_id,
    source.order_id,
    source.out_trade_no,
    source.unionid,
    'admin_adjusted',
    {DURATION_DAYS},
    previous.start_at,
    previous.end_at,
    synced.start_at,
    synced.end_at,
    jsonb_build_object(
        'migration', '{MIGRATION_KEY}',
        'source_product_code', '{SOURCE_PRODUCT_CODE}',
        'target_product_code', '{TARGET_PRODUCT_CODE}',
        'created_entitlement', previous.id IS NULL,
        'before', CASE WHEN previous.id IS NULL THEN NULL ELSE to_jsonb(previous) END,
        'after', to_jsonb(synced)
    ),
    CURRENT_TIMESTAMP
FROM upserted synced
JOIN source_orders source
  ON source.service_product_id = synced.service_product_id
 AND source.unionid = synced.unionid
LEFT JOIN existing previous
  ON previous.service_product_id = synced.service_product_id
 AND previous.unionid = synced.unionid
ON CONFLICT (event_id) DO NOTHING
"""


_ROLLBACK_SQL = f"""
UPDATE service_period_entitlements entitlement
SET
    trade_product_id = (event.payload_json #>> '{{before,trade_product_id}}')::BIGINT,
    external_userid_snapshot = COALESCE(event.payload_json #>> '{{before,external_userid_snapshot}}', ''),
    membership_config_id = COALESCE(event.payload_json #>> '{{before,membership_config_id}}', ''),
    status = event.payload_json #>> '{{before,status}}',
    start_at = (event.payload_json #>> '{{before,start_at}}')::TIMESTAMPTZ,
    end_at = (event.payload_json #>> '{{before,end_at}}')::TIMESTAMPTZ,
    last_order_id = NULLIF(event.payload_json #>> '{{before,last_order_id}}', '')::BIGINT,
    last_out_trade_no = COALESCE(event.payload_json #>> '{{before,last_out_trade_no}}', ''),
    renewal_count = COALESCE((event.payload_json #>> '{{before,renewal_count}}')::INTEGER, 0),
    metadata_json = COALESCE(event.payload_json #> '{{before,metadata_json}}', '{{}}'::jsonb),
    created_at = (event.payload_json #>> '{{before,created_at}}')::TIMESTAMPTZ,
    updated_at = (event.payload_json #>> '{{before,updated_at}}')::TIMESTAMPTZ
FROM service_period_events event
WHERE event.tenant_id = 'aicrm'
  AND event.payload_json ->> 'migration' = '{MIGRATION_KEY}'
  AND COALESCE((event.payload_json ->> 'created_entitlement')::BOOLEAN, FALSE) = FALSE
  AND entitlement.id = event.entitlement_id
  AND entitlement.last_out_trade_no = event.out_trade_no
  AND entitlement.start_at = event.after_start_at
  AND entitlement.end_at = event.after_end_at;

DELETE FROM service_period_entitlements entitlement
USING service_period_events event
WHERE event.tenant_id = 'aicrm'
  AND event.payload_json ->> 'migration' = '{MIGRATION_KEY}'
  AND COALESCE((event.payload_json ->> 'created_entitlement')::BOOLEAN, FALSE) = TRUE
  AND entitlement.id = event.entitlement_id
  AND entitlement.last_out_trade_no = event.out_trade_no
  AND entitlement.start_at = event.after_start_at
  AND entitlement.end_at = event.after_end_at
  AND NOT EXISTS (
      SELECT 1
      FROM service_period_events later
      WHERE later.entitlement_id = entitlement.id
        AND later.id <> event.id
  );

DELETE FROM service_period_events
WHERE tenant_id = 'aicrm'
  AND payload_json ->> 'migration' = '{MIGRATION_KEY}';
"""


def upgrade() -> None:
    op.execute(_SYNC_SQL)


def downgrade() -> None:
    op.execute(_ROLLBACK_SQL)
