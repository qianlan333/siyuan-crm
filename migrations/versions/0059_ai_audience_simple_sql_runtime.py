"""add AI audience simple SQL runtime fields.

Revision ID: 0059_ai_audience_simple_sql_runtime
Revises: 0058_merge_webhook_inbox_and_huangyoucan_audience
"""

from __future__ import annotations

from alembic import op

from migrations.audience_read import ensure_audience_read_schema


revision = "0059_ai_audience_simple_sql_runtime"
down_revision = "0058_merge_webhook_inbox_and_huangyoucan_audience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    audience_read_available = ensure_audience_read_schema()
    op.execute(
        """
        ALTER TABLE ai_audience_package_version
        ADD COLUMN IF NOT EXISTS simple_sql_text TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE ai_audience_package_version
        ADD COLUMN IF NOT EXISTS simple_compiled_sql_text TEXT NOT NULL DEFAULT ''
        """
    )
    if audience_read_available:
        _create_registration_status_view()


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS audience_read.registration_status_v1")
    op.execute(
        """
        ALTER TABLE ai_audience_package_version
        DROP COLUMN IF EXISTS simple_compiled_sql_text
        """
    )
    op.execute(
        """
        ALTER TABLE ai_audience_package_version
        DROP COLUMN IF EXISTS simple_sql_text
        """
    )


def _create_registration_status_view() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW audience_read.registration_status_v1 AS
        SELECT ''::text AS external_userid,
               NULL::bigint AS person_id,
               ''::text AS mobile_hash,
               false::boolean AS is_registered,
               NULL::timestamptz AS registered_at,
               ''::text AS source
        WHERE FALSE
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            parts text[] := ARRAY[]::text[];
        BEGIN
            IF to_regclass('public.external_contact_bindings') IS NOT NULL
               AND to_regclass('public.people') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'people' AND column_name = 'mobile'
               ) THEN
                parts := array_append(parts, $sql$
                    SELECT COALESCE(b.external_userid, '')::text AS external_userid,
                           CASE WHEN b.person_id::text ~ '^[0-9]+$' THEN b.person_id::text::bigint ELSE NULL END AS person_id,
                           CASE WHEN COALESCE(p.mobile, '') <> '' THEN md5(p.mobile) ELSE '' END::text AS mobile_hash,
                           (COALESCE(p.mobile, '') <> '')::boolean AS is_registered,
                           COALESCE(b.updated_at::timestamptz, CURRENT_TIMESTAMP) AS registered_at,
                           'people.mobile'::text AS source
                    FROM public.external_contact_bindings b
                    JOIN public.people p ON p.id::text = b.person_id::text
                    WHERE COALESCE(b.external_userid, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('public.new_version_users') IS NOT NULL
               AND to_regclass('audience_read.wecom_contacts_v1') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'new_version_users' AND column_name = 'phone'
               ) THEN
                parts := array_append(parts, $sql$
                    SELECT COALESCE(wc.external_userid, '')::text AS external_userid,
                           NULL::bigint AS person_id,
                           md5(u.phone)::text AS mobile_hash,
                           true::boolean AS is_registered,
                           CURRENT_TIMESTAMP AS registered_at,
                           'new_version_users.phone'::text AS source
                    FROM public.new_version_users u
                    JOIN audience_read.wecom_contacts_v1 wc ON wc.mobile_hash = md5(u.phone)
                    WHERE COALESCE(u.phone, '') <> ''
                      AND COALESCE(wc.external_userid, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('public.new_version_memberships') IS NOT NULL
               AND to_regclass('audience_read.wecom_contacts_v1') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'new_version_memberships' AND column_name = 'phone'
               ) THEN
                parts := array_append(parts, $sql$
                    SELECT COALESCE(wc.external_userid, '')::text AS external_userid,
                           NULL::bigint AS person_id,
                           md5(m.phone)::text AS mobile_hash,
                           true::boolean AS is_registered,
                           CURRENT_TIMESTAMP AS registered_at,
                           'new_version_memberships.phone'::text AS source
                    FROM public.new_version_memberships m
                    JOIN audience_read.wecom_contacts_v1 wc ON wc.mobile_hash = md5(m.phone)
                    WHERE COALESCE(m.phone, '') <> ''
                      AND COALESCE(wc.external_userid, '') <> ''
                $sql$);
            END IF;

            IF to_regclass('public.new_version_wechat_auth') IS NOT NULL
               AND to_regclass('audience_read.wecom_contacts_v1') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'new_version_wechat_auth' AND column_name = 'unionid'
               ) THEN
                parts := array_append(parts, $sql$
                    SELECT COALESCE(wc.external_userid, '')::text AS external_userid,
                           NULL::bigint AS person_id,
                           COALESCE(wc.mobile_hash, '')::text AS mobile_hash,
                           true::boolean AS is_registered,
                           CURRENT_TIMESTAMP AS registered_at,
                           'new_version_wechat_auth.unionid'::text AS source
                    FROM public.new_version_wechat_auth a
                    JOIN audience_read.wecom_contacts_v1 wc ON wc.unionid = a.unionid
                    WHERE COALESCE(a.unionid, '') <> ''
                      AND COALESCE(wc.external_userid, '') <> ''
                $sql$);
            END IF;

            IF array_length(parts, 1) > 0 THEN
                EXECUTE 'CREATE OR REPLACE VIEW audience_read.registration_status_v1 AS '
                    || array_to_string(parts, ' UNION ALL ');
            END IF;
        END $$;
        """
    )
