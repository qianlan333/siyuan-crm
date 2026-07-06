"""repair HuangYouCan unregistered audience snapshot unionid output.

Revision ID: 0093_huangyoucan_unregistered_unionid_snapshot
Revises: 0092_channel_entry_runtime_identity_backoff
"""

from __future__ import annotations

from alembic import op


revision = "0093_huangyoucan_unregistered_unionid_snapshot"
down_revision = "0092_channel_entry_runtime_identity_backoff"
branch_labels = None
depends_on = None


NEW_SNAPSHOT_SQL = """
SELECT 'external_userid' AS identity_type,
    wc.external_userid AS identity_value,
    'huangyoucan_unregistered:' || wc.external_userid AS event_source_key,
    jsonb_build_object(
        'audience_key', 'huangyoucan_wecom_unregistered',
        'external_userid', wc.external_userid,
        'unionid', wc.unionid,
        'owner_userid', wc.owner_userid,
        'customer_name', wc.customer_name,
        'has_mobile_hash', COALESCE(wc.mobile_hash, '') <> '',
        'has_unionid', COALESCE(wc.unionid, '') <> '',
        'registered_mobile_match', false,
        'registered_unionid_match', false
    ) AS payload_json,
    wc.external_userid,
    wc.unionid,
    wc.mobile_hash,
    wc.owner_userid,
    wc.updated_at AS event_at
FROM audience_read.wecom_contacts_v1 wc
LEFT JOIN audience_read.huangyoucan_registered_identities_v1 registered_mobile
    ON registered_mobile.identity_type = 'mobile_hash'
   AND registered_mobile.identity_value = wc.mobile_hash
   AND COALESCE(wc.mobile_hash, '') <> ''
LEFT JOIN audience_read.huangyoucan_registered_identities_v1 registered_union
    ON registered_union.identity_type = 'unionid'
   AND registered_union.identity_value = wc.unionid
   AND COALESCE(wc.unionid, '') <> ''
WHERE wc.owner_userid = :owner_userid
  AND COALESCE(wc.external_userid, '') <> ''
  AND (COALESCE(wc.status, '') = '' OR wc.status = 'active')
  AND (COALESCE(wc.mobile_hash, '') <> '' OR COALESCE(wc.unionid, '') <> '')
  AND registered_mobile.identity_value IS NULL
  AND registered_union.identity_value IS NULL
"""


OLD_SNAPSHOT_SQL = """
SELECT 'external_userid' AS identity_type,
    wc.external_userid AS identity_value,
    'huangyoucan_unregistered:' || wc.external_userid AS event_source_key,
    jsonb_build_object(
        'audience_key', 'huangyoucan_wecom_unregistered',
        'owner_userid', wc.owner_userid,
        'customer_name', wc.customer_name,
        'has_mobile_hash', COALESCE(wc.mobile_hash, '') <> '',
        'has_unionid', COALESCE(wc.unionid, '') <> '',
        'registered_mobile_match', false,
        'registered_unionid_match', false
    ) AS payload_json,
    wc.external_userid,
    wc.mobile_hash,
    wc.owner_userid,
    wc.updated_at AS event_at
FROM audience_read.wecom_contacts_v1 wc
LEFT JOIN audience_read.huangyoucan_registered_identities_v1 registered_mobile
    ON registered_mobile.identity_type = 'mobile_hash'
   AND registered_mobile.identity_value = wc.mobile_hash
   AND COALESCE(wc.mobile_hash, '') <> ''
LEFT JOIN audience_read.huangyoucan_registered_identities_v1 registered_union
    ON registered_union.identity_type = 'unionid'
   AND registered_union.identity_value = wc.unionid
   AND COALESCE(wc.unionid, '') <> ''
WHERE wc.owner_userid = :owner_userid
  AND COALESCE(wc.external_userid, '') <> ''
  AND (COALESCE(wc.status, '') = '' OR wc.status = 'active')
  AND (COALESCE(wc.mobile_hash, '') <> '' OR COALESCE(wc.unionid, '') <> '')
  AND registered_mobile.identity_value IS NULL
  AND registered_union.identity_value IS NULL
"""


def upgrade() -> None:
    _update_seed_snapshot_sql(NEW_SNAPSHOT_SQL)


def downgrade() -> None:
    _update_seed_snapshot_sql(OLD_SNAPSHOT_SQL)


def _update_seed_snapshot_sql(sql_text: str) -> None:
    op.execute(
        f"""
        UPDATE ai_audience_package_version v
        SET snapshot_sql_text = '{_sql_literal(sql_text)}',
            validation_errors_json = '[]'::jsonb
        FROM ai_audience_package p
        WHERE p.id = v.package_id
          AND p.package_key = 'huangyoucan_wecom_unregistered'
          AND v.version_number = 1
        """
    )


def _sql_literal(sql_text: str) -> str:
    return sql_text.strip().replace("'", "''").replace(":owner_userid", r"\:owner_userid")
