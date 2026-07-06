"""add unionid-first identity foundation.

Revision ID: 0062_unionid_identity_refactor
Revises: 0061_automation_agent_type_fixed_script
"""

from __future__ import annotations

from alembic import op


revision = "0062_unionid_identity_refactor"
down_revision = "0061_automation_agent_type_fixed_script"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_user_identity (
            unionid TEXT PRIMARY KEY,
            primary_external_userid TEXT NOT NULL DEFAULT '',
            external_userids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            primary_openid TEXT NOT NULL DEFAULT '',
            openids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            mobile TEXT NOT NULL DEFAULT '',
            mobile_normalized TEXT NOT NULL DEFAULT '',
            mobile_verified BOOLEAN NOT NULL DEFAULT FALSE,
            mobile_source TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            remark TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            avatar TEXT NOT NULL DEFAULT '',
            gender INTEGER,
            profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            primary_owner_userid TEXT NOT NULL DEFAULT '',
            follow_users_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            legacy_person_id TEXT NOT NULL DEFAULT '',
            legacy_identity_map_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            legacy_sources_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            identity_status TEXT NOT NULL DEFAULT 'active' CHECK (identity_status IN ('active', 'pending_merge', 'conflict', 'deleted')),
            unionid_resolved_at TIMESTAMPTZ,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_polled_at TIMESTAMPTZ,
            next_poll_at TIMESTAMPTZ,
            poll_attempt_count INTEGER NOT NULL DEFAULT 0,
            last_poll_error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_external_userids_json ON crm_user_identity USING GIN (external_userids_json)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_openids_json ON crm_user_identity USING GIN (openids_json)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_mobile_normalized ON crm_user_identity (mobile_normalized) WHERE mobile_normalized <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_primary_external_userid ON crm_user_identity (primary_external_userid) WHERE primary_external_userid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_primary_owner_userid ON crm_user_identity (primary_owner_userid) WHERE primary_owner_userid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_next_poll_at ON crm_user_identity (next_poll_at) WHERE next_poll_at IS NOT NULL")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS corp_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS avatar TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS wecom_external_contact_identity_map ADD COLUMN IF NOT EXISTS gender INTEGER")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_user_identity_resolution_queue (
            id BIGSERIAL PRIMARY KEY,
            source_type TEXT NOT NULL DEFAULT '',
            source_key TEXT NOT NULL DEFAULT '',
            source_table TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            corp_id TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            openid TEXT NOT NULL DEFAULT '',
            mobile TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'polling', 'resolved', 'conflict', 'failed', 'ignored')),
            resolved_unionid TEXT NOT NULL DEFAULT '',
            conflict_reason TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            next_attempt_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_resolution_queue_status ON crm_user_identity_resolution_queue (status, next_attempt_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_resolution_queue_external_userid ON crm_user_identity_resolution_queue (external_userid) WHERE external_userid <> ''")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_crm_user_identity_resolution_queue_pending_source
        ON crm_user_identity_resolution_queue (source_type, source_key)
        WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_user_identity_conflicts (
            id BIGSERIAL PRIMARY KEY,
            conflict_type TEXT NOT NULL DEFAULT '',
            unionid TEXT NOT NULL DEFAULT '',
            candidate_unionid TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            openid TEXT NOT NULL DEFAULT '',
            mobile TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            source_key TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'open',
            resolution_status TEXT NOT NULL DEFAULT 'open' CHECK (resolution_status IN ('open', 'ignored', 'merged', 'manual_fixed')),
            resolution_note TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_conflicts_status ON crm_user_identity_conflicts (status, conflict_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_conflicts_unionid ON crm_user_identity_conflicts (unionid)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_user_identity_merge_audit (
            id BIGSERIAL PRIMARY KEY,
            from_unionid TEXT NOT NULL DEFAULT '',
            to_unionid TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            operator TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_crm_user_identity_merge_audit_to_unionid ON crm_user_identity_merge_audit (to_unionid, created_at DESC)")

    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.wecom_external_contact_identity_map') IS NOT NULL THEN
                INSERT INTO crm_user_identity (
                    unionid,
                    openids_json,
                    external_userids_json,
                    customer_name,
                    avatar,
                    gender,
                    profile_json,
                    primary_owner_userid,
                    follow_users_json,
                    legacy_identity_map_ids_json,
                    primary_external_userid,
                    primary_openid,
                    identity_status,
                    unionid_resolved_at,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at,
                    last_polled_at,
                    legacy_sources_json
                )
                SELECT
                    im.unionid,
                    COALESCE(jsonb_agg(DISTINCT NULLIF(im.openid, '')) FILTER (WHERE COALESCE(im.openid, '') <> ''), '[]'::jsonb),
                    COALESCE(jsonb_agg(DISTINCT NULLIF(im.external_userid, '')) FILTER (WHERE COALESCE(im.external_userid, '') <> ''), '[]'::jsonb),
                    COALESCE(MAX(NULLIF(im.name, '')), ''),
                    COALESCE(MAX(NULLIF(im.avatar, '')), ''),
                    COALESCE(MAX(im.gender), NULL),
                    jsonb_strip_nulls(jsonb_build_object(
                        'name', MAX(NULLIF(im.name, '')),
                        'avatar', MAX(NULLIF(im.avatar, '')),
                        'gender', MAX(im.gender)
                    )),
                    COALESCE((ARRAY_AGG(NULLIF(im.follow_user_userid, '') ORDER BY im.updated_at DESC NULLS LAST, im.id DESC) FILTER (WHERE COALESCE(im.follow_user_userid, '') <> ''))[1], ''),
                    COALESCE(jsonb_agg(DISTINCT jsonb_build_object('userid', im.follow_user_userid)) FILTER (WHERE COALESCE(im.follow_user_userid, '') <> ''), '[]'::jsonb),
                    COALESCE(jsonb_agg(DISTINCT im.id::text) FILTER (WHERE im.id IS NOT NULL), '[]'::jsonb),
                    COALESCE((ARRAY_AGG(NULLIF(im.external_userid, '') ORDER BY im.updated_at DESC NULLS LAST, im.id DESC) FILTER (WHERE COALESCE(im.external_userid, '') <> ''))[1], ''),
                    COALESCE((ARRAY_AGG(NULLIF(im.openid, '') ORDER BY im.updated_at DESC NULLS LAST, im.id DESC) FILTER (WHERE COALESCE(im.openid, '') <> ''))[1], ''),
                    CASE LOWER(COALESCE((ARRAY_AGG(NULLIF(im.status, '') ORDER BY im.updated_at DESC NULLS LAST, im.id DESC) FILTER (WHERE COALESCE(im.status, '') <> ''))[1], 'active'))
                        WHEN 'pending_merge' THEN 'pending_merge'
                        WHEN 'conflict' THEN 'conflict'
                        WHEN 'deleted' THEN 'deleted'
                        WHEN 'inactive' THEN 'deleted'
                        ELSE 'active'
                    END,
                    COALESCE(MAX(im.updated_at), NOW()),
                    COALESCE(MIN(im.updated_at), NOW()),
                    COALESCE(MAX(im.updated_at), NOW()),
                    NOW(),
                    NOW(),
                    COALESCE(MAX(im.updated_at), NOW()),
                    jsonb_build_object('wecom_external_contact_identity_map', TRUE)
                FROM wecom_external_contact_identity_map im
                WHERE COALESCE(im.unionid, '') <> ''
                GROUP BY im.unionid
                ON CONFLICT (unionid) DO UPDATE SET
                    openids_json = (
                        SELECT COALESCE(jsonb_agg(DISTINCT value), '[]'::jsonb)
                        FROM jsonb_array_elements_text(crm_user_identity.openids_json || EXCLUDED.openids_json) AS merged(value)
                    ),
                    external_userids_json = (
                        SELECT COALESCE(jsonb_agg(DISTINCT value), '[]'::jsonb)
                        FROM jsonb_array_elements_text(crm_user_identity.external_userids_json || EXCLUDED.external_userids_json) AS merged(value)
                    ),
                    customer_name = COALESCE(NULLIF(EXCLUDED.customer_name, ''), crm_user_identity.customer_name),
                    avatar = COALESCE(NULLIF(EXCLUDED.avatar, ''), crm_user_identity.avatar),
                    gender = COALESCE(EXCLUDED.gender, crm_user_identity.gender),
                    profile_json = crm_user_identity.profile_json || EXCLUDED.profile_json,
                    primary_owner_userid = COALESCE(NULLIF(EXCLUDED.primary_owner_userid, ''), crm_user_identity.primary_owner_userid),
                    follow_users_json = CASE
                        WHEN jsonb_array_length(EXCLUDED.follow_users_json) > 0 THEN EXCLUDED.follow_users_json
                        ELSE crm_user_identity.follow_users_json
                    END,
                    legacy_identity_map_ids_json = (
                        SELECT COALESCE(jsonb_agg(DISTINCT value), '[]'::jsonb)
                        FROM jsonb_array_elements_text(crm_user_identity.legacy_identity_map_ids_json || EXCLUDED.legacy_identity_map_ids_json) AS merged(value)
                    ),
                    primary_external_userid = COALESCE(NULLIF(EXCLUDED.primary_external_userid, ''), crm_user_identity.primary_external_userid),
                    primary_openid = COALESCE(NULLIF(EXCLUDED.primary_openid, ''), crm_user_identity.primary_openid),
                    identity_status = COALESCE(NULLIF(EXCLUDED.identity_status, ''), crm_user_identity.identity_status),
                    unionid_resolved_at = COALESCE(crm_user_identity.unionid_resolved_at, EXCLUDED.unionid_resolved_at),
                    last_seen_at = GREATEST(crm_user_identity.last_seen_at, EXCLUDED.last_seen_at),
                    last_polled_at = GREATEST(COALESCE(crm_user_identity.last_polled_at, EXCLUDED.last_polled_at), EXCLUDED.last_polled_at),
                    legacy_sources_json = crm_user_identity.legacy_sources_json || EXCLUDED.legacy_sources_json,
                    updated_at = NOW();

                INSERT INTO crm_user_identity_resolution_queue (
                    source_type,
                    source_key,
                    corp_id,
                    external_userid,
                    openid,
                    payload_json,
                    reason,
                    status,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                )
                SELECT
                    'wecom_external_contact',
                    im.external_userid,
                    COALESCE(im.corp_id, ''),
                    im.external_userid,
                    COALESCE(im.openid, ''),
                    jsonb_strip_nulls(jsonb_build_object(
                        'external_userid', im.external_userid,
                        'openid', NULLIF(im.openid, ''),
                        'follow_user_userid', NULLIF(im.follow_user_userid, ''),
                        'name', NULLIF(im.name, '')
                    )),
                    'missing_unionid',
                    'pending',
                    COALESCE(im.updated_at, NOW()),
                    COALESCE(im.updated_at, NOW()),
                    NOW(),
                    NOW()
                FROM wecom_external_contact_identity_map im
                WHERE COALESCE(im.unionid, '') = ''
                  AND COALESCE(im.external_userid, '') <> ''
                ON CONFLICT (source_type, source_key) WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
                DO UPDATE SET
                    openid = COALESCE(NULLIF(EXCLUDED.openid, ''), crm_user_identity_resolution_queue.openid),
                    payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                    reason = EXCLUDED.reason,
                    last_seen_at = NOW(),
                    updated_at = NOW();
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.external_contact_bindings') IS NOT NULL
               AND to_regclass('public.people') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'people' AND column_name = 'mobile'
               ) THEN
                UPDATE crm_user_identity cui
                SET mobile = COALESCE(NULLIF(p.mobile, ''), cui.mobile),
                    mobile_normalized = COALESCE(NULLIF(p.mobile, ''), cui.mobile_normalized),
                    mobile_verified = cui.mobile_verified OR COALESCE(NULLIF(p.mobile, ''), '') <> '',
                    mobile_source = COALESCE(NULLIF(cui.mobile_source, ''), 'legacy_external_contact_binding'),
                    legacy_person_id = COALESCE(NULLIF(cui.legacy_person_id, ''), b.person_id::text),
                    legacy_sources_json = cui.legacy_sources_json || jsonb_build_object('external_contact_bindings', TRUE, 'people', TRUE),
                    updated_at = NOW()
                FROM external_contact_bindings b
                JOIN people p ON p.id::text = b.person_id::text
                WHERE COALESCE(b.external_userid, '') <> ''
                  AND (cui.primary_external_userid = b.external_userid OR jsonb_exists(cui.external_userids_json, b.external_userid))
                  AND COALESCE(p.mobile, '') <> '';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crm_user_identity_merge_audit")
    op.execute("DROP TABLE IF EXISTS crm_user_identity_conflicts")
    op.execute("DROP TABLE IF EXISTS crm_user_identity_resolution_queue")
    op.execute("DROP TABLE IF EXISTS crm_user_identity")
