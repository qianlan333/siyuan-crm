"""drop legacy external_userid from automation channel contact facts.

Revision ID: 0069_unionid_channel_contact_cleanup
Revises: 0068_unionid_customer_fact_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0069_unionid_channel_contact_cleanup"
down_revision = "0068_unionid_customer_fact_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_channel_contact') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = 'automation_channel_contact'
                     AND column_name = 'external_userid'
               ) THEN
                INSERT INTO crm_user_identity_resolution_queue (
                    source_type,
                    source_key,
                    external_userid,
                    payload_json,
                    reason,
                    status,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                )
                SELECT
                    'automation_channel_contact',
                    'automation_channel_contact:' || contact.id::text,
                    contact.external_userid,
                    jsonb_build_object(
                        'source_table', 'automation_channel_contact',
                        'source_id', contact.id,
                        'channel_id', contact.channel_id,
                        'external_userid', contact.external_userid
                    ),
                    'missing_unionid',
                    'pending',
                    NOW(),
                    NOW(),
                    NOW(),
                    NOW()
                FROM automation_channel_contact contact
                WHERE COALESCE(contact.unionid, '') = ''
                  AND COALESCE(contact.external_userid, '') <> ''
                ON CONFLICT (source_type, source_key) WHERE status = 'pending' AND source_type <> '' AND source_key <> ''
                DO UPDATE SET
                    external_userid = COALESCE(NULLIF(EXCLUDED.external_userid, ''), crm_user_identity_resolution_queue.external_userid),
                    payload_json = crm_user_identity_resolution_queue.payload_json || EXCLUDED.payload_json,
                    reason = EXCLUDED.reason,
                    last_seen_at = NOW(),
                    updated_at = NOW();
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact DROP COLUMN IF EXISTS external_userid")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS automation_channel_contact ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
