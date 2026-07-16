"""add HuangXiaoCan membership and usage audience read view.

Revision ID: 0060_ai_audience_hxc_member_usage_view
Revises: 0059_ai_audience_simple_sql_runtime
"""

from __future__ import annotations

from alembic import op


revision = "0060_ai_audience_hxc_member_usage_view"
down_revision = "0059_ai_audience_simple_sql_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS audience_read")
    _create_huangxiaocan_member_usage_view()


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS audience_read.huangxiaocan_member_usage_status_v1")


def _create_huangxiaocan_member_usage_view() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.huangxiaocan_member_usage_status_v1 AS
        SELECT ''::text AS external_userid,
               NULL::bigint AS person_id,
               ''::text AS mobile_hash,
               ''::text AS unionid,
               ''::text AS owner_userid,
               false::boolean AS is_member,
               false::boolean AS is_registered,
               NULL::timestamptz AS registered_at,
               false::boolean AS has_real_usage,
               NULL::timestamptz AS first_used_at,
               NULL::timestamptz AS last_used_at,
               NULL::timestamptz AS member_since,
               NULL::timestamptz AS membership_expires_at,
               ''::text AS membership_tier,
               ''::text AS membership_status,
               ''::text AS membership_source,
               ''::text AS registration_source,
               ''::text AS usage_source,
               CURRENT_TIMESTAMP AS updated_at,
               '{}'::jsonb AS payload_json
        WHERE FALSE
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            membership_parts text[] := ARRAY[]::text[];
            registration_parts text[] := ARRAY[]::text[];
            usage_parts text[] := ARRAY[]::text[];
            hxc_snapshot_external_expr text := '''''::text';
            hxc_snapshot_unionid_expr text := '''''::text';
            membership_sql text;
            registration_sql text;
            usage_sql text;
        BEGIN
            IF to_regclass('audience_read.wecom_contacts_v1') IS NULL THEN
                RETURN;
            END IF;

            IF to_regclass('public.user_ops_hxc_dashboard_snapshot') IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'user_ops_hxc_dashboard_snapshot' AND column_name = 'external_userid'
                ) THEN
                    hxc_snapshot_external_expr := 'COALESCE(s.external_userid, '''')::text';
                END IF;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'user_ops_hxc_dashboard_snapshot' AND column_name = 'unionid'
                ) THEN
                    hxc_snapshot_unionid_expr := 'COALESCE(s.unionid, '''')::text';
                END IF;
                membership_parts := array_append(membership_parts, format($sql$
                    SELECT %s AS external_userid,
                           CASE WHEN COALESCE(s.mobile, '') <> '' THEN md5(s.mobile) ELSE '' END::text AS mobile_hash,
                           %s AS unionid,
                           (
                               COALESCE(s.hxc_member_hit, false)
                               OR COALESCE(s.membership_status, '') IN ('active', 'valid', 'premium', 'standard', 'trial')
                               OR s.membership_end_at > CURRENT_TIMESTAMP
                           )::boolean AS is_member,
                           s.hxc_registered_at::timestamptz AS member_since,
                           s.membership_end_at::timestamptz AS membership_expires_at,
                           COALESCE(s.membership_type, '')::text AS membership_tier,
                           COALESCE(s.membership_status, '')::text AS membership_status,
                           'user_ops_hxc_dashboard_snapshot'::text AS source
                    FROM public.user_ops_hxc_dashboard_snapshot s
                    WHERE COALESCE(%s, '') <> ''
                       OR COALESCE(s.mobile, '') <> ''
                       OR COALESCE(%s, '') <> ''
                $sql$, hxc_snapshot_external_expr, hxc_snapshot_unionid_expr, hxc_snapshot_external_expr, hxc_snapshot_unionid_expr));
                registration_parts := array_append(registration_parts, format($sql$
                    SELECT %s AS external_userid,
                           CASE WHEN COALESCE(s.mobile, '') <> '' THEN md5(s.mobile) ELSE '' END::text AS mobile_hash,
                           %s AS unionid,
                           (COALESCE(s.hxc_user_hit, false) OR s.hxc_registered_at IS NOT NULL)::boolean AS is_registered,
                           s.hxc_registered_at::timestamptz AS registered_at,
                           'user_ops_hxc_dashboard_snapshot'::text AS source
                    FROM public.user_ops_hxc_dashboard_snapshot s
                    WHERE COALESCE(s.hxc_user_hit, false)
                       OR s.hxc_registered_at IS NOT NULL
                $sql$, hxc_snapshot_external_expr, hxc_snapshot_unionid_expr));
                usage_parts := array_append(usage_parts, format($sql$
                    SELECT %s AS external_userid,
                           CASE WHEN COALESCE(s.mobile, '') <> '' THEN md5(s.mobile) ELSE '' END::text AS mobile_hash,
                           %s AS unionid,
                           true::boolean AS has_real_usage,
                           COALESCE(last_msg_at::timestamptz, refreshed_at::timestamptz) AS used_at,
                           'user_ops_hxc_dashboard_snapshot'::text AS source
                    FROM public.user_ops_hxc_dashboard_snapshot s
                    WHERE COALESCE(s.conv_chat, 0) > 0
                       OR COALESCE(s.conv_consult, 0) > 0
                       OR COALESCE(s.conv_lesson, 0) > 0
                       OR COALESCE(s.msg_user, 0) > 0
                       OR COALESCE(s.msg_ai, 0) > 0
                       OR COALESCE(s.consult_completed, 0) > 0
                       OR s.last_msg_at IS NOT NULL
                $sql$, hxc_snapshot_external_expr, hxc_snapshot_unionid_expr));
            END IF;

            IF to_regclass('public.new_version_user_subscriptions') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'new_version_user_subscriptions' AND column_name = 'phone'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'new_version_user_subscriptions' AND column_name = 'expires_at'
               ) THEN
                membership_parts := array_append(membership_parts, $sql$
                    SELECT ''::text AS external_userid,
                           md5(phone)::text AS mobile_hash,
                           ''::text AS unionid,
                           (expires_at > CURRENT_TIMESTAMP)::boolean AS is_member,
                           NULL::timestamptz AS member_since,
                           expires_at::timestamptz AS membership_expires_at,
                           ''::text AS membership_tier,
                           CASE WHEN expires_at > CURRENT_TIMESTAMP THEN 'active' ELSE 'expired' END::text AS membership_status,
                           'new_version_user_subscriptions.phone'::text AS source
                    FROM public.new_version_user_subscriptions
                    WHERE COALESCE(phone, '') <> ''
                $sql$);
                registration_parts := array_append(registration_parts, $sql$
                    SELECT ''::text AS external_userid,
                           md5(phone)::text AS mobile_hash,
                           ''::text AS unionid,
                           true::boolean AS is_registered,
                           NULL::timestamptz AS registered_at,
                           'new_version_user_subscriptions.phone'::text AS source
                    FROM public.new_version_user_subscriptions
                    WHERE COALESCE(phone, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('audience_read.registration_status_v1') IS NOT NULL THEN
                registration_parts := array_append(registration_parts, $sql$
                    SELECT COALESCE(external_userid, '')::text AS external_userid,
                           COALESCE(mobile_hash, '')::text AS mobile_hash,
                           ''::text AS unionid,
                           COALESCE(is_registered, false)::boolean AS is_registered,
                           registered_at::timestamptz AS registered_at,
                           COALESCE(source, 'registration_status_v1')::text AS source
                    FROM audience_read.registration_status_v1
                    WHERE COALESCE(external_userid, '') <> ''
                       OR COALESCE(mobile_hash, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('audience_read.huangyoucan_registered_identities_v1') IS NOT NULL THEN
                registration_parts := array_append(registration_parts, $sql$
                    SELECT ''::text AS external_userid,
                           CASE WHEN identity_type = 'mobile_hash' THEN COALESCE(identity_value, '') ELSE '' END::text AS mobile_hash,
                           CASE WHEN identity_type = 'unionid' THEN COALESCE(identity_value, '') ELSE '' END::text AS unionid,
                           true::boolean AS is_registered,
                           registered_at::timestamptz AS registered_at,
                           COALESCE(registered_source, 'huangyoucan_registered_identities_v1')::text AS source
                    FROM audience_read.huangyoucan_registered_identities_v1
                    WHERE identity_type IN ('mobile_hash', 'unionid')
                      AND COALESCE(identity_value, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('public.customer_recent_message_next') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'customer_recent_message_next' AND column_name = 'unionid'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'customer_recent_message_next' AND column_name = 'send_time'
               ) THEN
                usage_parts := array_append(usage_parts, $sql$
                    SELECT ''::text AS external_userid,
                           ''::text AS mobile_hash,
                           COALESCE(unionid, '')::text AS unionid,
                           true::boolean AS has_real_usage,
                           send_time::timestamptz AS used_at,
                           'customer_recent_message_next'::text AS source
                    FROM public.customer_recent_message_next
                    WHERE COALESCE(unionid, '') <> ''
                $sql$);
            ELSIF to_regclass('public.customer_recent_message_next') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'customer_recent_message_next' AND column_name = 'external_userid'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'customer_recent_message_next' AND column_name = 'send_time'
               ) THEN
                usage_parts := array_append(usage_parts, $sql$
                    SELECT COALESCE(external_userid, '')::text AS external_userid,
                           ''::text AS mobile_hash,
                           ''::text AS unionid,
                           true::boolean AS has_real_usage,
                           send_time::timestamptz AS used_at,
                           'customer_recent_message_next'::text AS source
                    FROM public.customer_recent_message_next
                    WHERE COALESCE(external_userid, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('public.automation_laohuang_chat_job') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_laohuang_chat_job' AND column_name = 'external_contact_id'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_laohuang_chat_job' AND column_name = 'status'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_laohuang_chat_job' AND column_name = 'phone'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_laohuang_chat_job' AND column_name = 'created_at'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_laohuang_chat_job' AND column_name = 'updated_at'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_laohuang_chat_job' AND column_name = 'finished_at'
               ) THEN
                usage_parts := array_append(usage_parts, $sql$
                    SELECT COALESCE(external_contact_id, '')::text AS external_userid,
                           CASE WHEN COALESCE(phone, '') <> '' THEN md5(phone) ELSE '' END::text AS mobile_hash,
                           ''::text AS unionid,
                           true::boolean AS has_real_usage,
                           COALESCE(finished_at::timestamptz, updated_at::timestamptz, created_at::timestamptz, CURRENT_TIMESTAMP) AS used_at,
                           'automation_laohuang_chat_job'::text AS source
                    FROM public.automation_laohuang_chat_job
                    WHERE COALESCE(status, '') IN ('accepted', 'send_success', 'callback_success')
                      AND (COALESCE(external_contact_id, '') <> '' OR COALESCE(phone, '') <> '')
                $sql$);
            END IF;

            IF to_regclass('public.user_ops_huangxiaocan_activation_source') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_huangxiaocan_activation_source' AND column_name = 'mobile'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_huangxiaocan_activation_source' AND column_name = 'activation_state'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_huangxiaocan_activation_source' AND column_name = 'is_active'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_huangxiaocan_activation_source' AND column_name = 'created_at'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_huangxiaocan_activation_source' AND column_name = 'updated_at'
               ) THEN
                usage_parts := array_append(usage_parts, $sql$
                    SELECT ''::text AS external_userid,
                           CASE WHEN COALESCE(mobile, '') <> '' THEN md5(mobile) ELSE '' END::text AS mobile_hash,
                           ''::text AS unionid,
                           true::boolean AS has_real_usage,
                           COALESCE(updated_at::timestamptz, created_at::timestamptz, CURRENT_TIMESTAMP) AS used_at,
                           'user_ops_huangxiaocan_activation_source'::text AS source
                    FROM public.user_ops_huangxiaocan_activation_source
                    WHERE COALESCE(is_active, true)
                      AND COALESCE(activation_state, '') = 'activated'
                      AND COALESCE(mobile, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('public.user_ops_activation_status_source') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_activation_status_source' AND column_name = 'mobile'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_activation_status_source' AND column_name = 'activation_status'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_activation_status_source' AND column_name = 'is_active'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_activation_status_source' AND column_name = 'created_at'
               )
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'user_ops_activation_status_source' AND column_name = 'updated_at'
               ) THEN
                usage_parts := array_append(usage_parts, $sql$
                    SELECT ''::text AS external_userid,
                           CASE WHEN COALESCE(mobile, '') <> '' THEN md5(mobile) ELSE '' END::text AS mobile_hash,
                           ''::text AS unionid,
                           true::boolean AS has_real_usage,
                           COALESCE(updated_at::timestamptz, created_at::timestamptz, CURRENT_TIMESTAMP) AS used_at,
                           'user_ops_activation_status_source'::text AS source
                    FROM public.user_ops_activation_status_source
                    WHERE COALESCE(is_active, true)
                      AND COALESCE(activation_status, '') = 'activated'
                      AND COALESCE(mobile, '') <> ''
                $sql$);
            END IF;

            membership_sql := COALESCE(
                array_to_string(membership_parts, ' UNION ALL '),
                $empty$
                    SELECT ''::text AS external_userid,
                           ''::text AS mobile_hash,
                           ''::text AS unionid,
                           false::boolean AS is_member,
                           NULL::timestamptz AS member_since,
                           NULL::timestamptz AS membership_expires_at,
                           ''::text AS membership_tier,
                           ''::text AS membership_status,
                           ''::text AS source
                    WHERE FALSE
                $empty$
            );
            registration_sql := COALESCE(
                array_to_string(registration_parts, ' UNION ALL '),
                $empty$
                    SELECT ''::text AS external_userid,
                           ''::text AS mobile_hash,
                           ''::text AS unionid,
                           false::boolean AS is_registered,
                           NULL::timestamptz AS registered_at,
                           ''::text AS source
                    WHERE FALSE
                $empty$
            );
            usage_sql := COALESCE(
                array_to_string(usage_parts, ' UNION ALL '),
                $empty$
                    SELECT ''::text AS external_userid,
                           ''::text AS mobile_hash,
                           ''::text AS unionid,
                           false::boolean AS has_real_usage,
                           NULL::timestamptz AS used_at,
                           ''::text AS source
                    WHERE FALSE
                $empty$
            );

            EXECUTE format($view$
                CREATE OR REPLACE VIEW audience_read.huangxiaocan_member_usage_status_v1 AS
                WITH membership_sources AS (
                    %s
                ),
                registration_sources AS (
                    %s
                ),
                usage_sources AS (
                    %s
                )
                SELECT
                    wc.external_userid::text AS external_userid,
                    NULL::bigint AS person_id,
                    COALESCE(wc.mobile_hash, '')::text AS mobile_hash,
                    COALESCE(wc.unionid, '')::text AS unionid,
                    COALESCE(wc.owner_userid, '')::text AS owner_userid,
                    COALESCE(bool_or(ms.is_member), false)::boolean AS is_member,
                    COALESCE(bool_or(rs.is_registered), false)::boolean AS is_registered,
                    min(rs.registered_at)::timestamptz AS registered_at,
                    COALESCE(bool_or(us.has_real_usage), false)::boolean AS has_real_usage,
                    min(us.used_at)::timestamptz AS first_used_at,
                    max(us.used_at)::timestamptz AS last_used_at,
                    min(ms.member_since)::timestamptz AS member_since,
                    max(ms.membership_expires_at)::timestamptz AS membership_expires_at,
                    COALESCE(string_agg(DISTINCT NULLIF(ms.membership_tier, ''), ','), '')::text AS membership_tier,
                    COALESCE(string_agg(DISTINCT NULLIF(ms.membership_status, ''), ','), '')::text AS membership_status,
                    COALESCE(string_agg(DISTINCT NULLIF(ms.source, ''), ','), '')::text AS membership_source,
                    COALESCE(string_agg(DISTINCT NULLIF(rs.source, ''), ','), '')::text AS registration_source,
                    COALESCE(string_agg(DISTINCT NULLIF(us.source, ''), ','), '')::text AS usage_source,
                    NULLIF(greatest(
                        COALESCE(max(ms.membership_expires_at), '-infinity'::timestamptz),
                        COALESCE(max(us.used_at), '-infinity'::timestamptz),
                        COALESCE(max(rs.registered_at), '-infinity'::timestamptz),
                        COALESCE(max(wc.updated_at), '-infinity'::timestamptz)
                    ), '-infinity'::timestamptz) AS updated_at,
                    jsonb_build_object(
                        'membership_source', COALESCE(string_agg(DISTINCT NULLIF(ms.source, ''), ','), ''),
                        'registration_source', COALESCE(string_agg(DISTINCT NULLIF(rs.source, ''), ','), ''),
                        'usage_source', COALESCE(string_agg(DISTINCT NULLIF(us.source, ''), ','), ''),
                        'has_mobile_hash', COALESCE(wc.mobile_hash, '') <> '',
                        'has_unionid', COALESCE(wc.unionid, '') <> ''
                    ) AS payload_json
                FROM audience_read.wecom_contacts_v1 wc
                LEFT JOIN membership_sources ms
                  ON (COALESCE(ms.external_userid, '') <> '' AND ms.external_userid = wc.external_userid)
                  OR (COALESCE(ms.mobile_hash, '') <> '' AND ms.mobile_hash = COALESCE(wc.mobile_hash, ''))
                  OR (COALESCE(ms.unionid, '') <> '' AND ms.unionid = COALESCE(wc.unionid, ''))
                LEFT JOIN registration_sources rs
                  ON (COALESCE(rs.external_userid, '') <> '' AND rs.external_userid = wc.external_userid)
                  OR (COALESCE(rs.mobile_hash, '') <> '' AND rs.mobile_hash = COALESCE(wc.mobile_hash, ''))
                  OR (COALESCE(rs.unionid, '') <> '' AND rs.unionid = COALESCE(wc.unionid, ''))
                LEFT JOIN usage_sources us
                  ON (COALESCE(us.external_userid, '') <> '' AND us.external_userid = wc.external_userid)
                  OR (COALESCE(us.mobile_hash, '') <> '' AND us.mobile_hash = COALESCE(wc.mobile_hash, ''))
                  OR (COALESCE(us.unionid, '') <> '' AND us.unionid = COALESCE(wc.unionid, ''))
                WHERE COALESCE(wc.external_userid, '') <> ''
                GROUP BY wc.external_userid, wc.mobile_hash, wc.unionid, wc.owner_userid
            $view$, membership_sql, registration_sql, usage_sql);
        END $$;
        """
    )
