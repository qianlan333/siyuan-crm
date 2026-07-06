"""clean up final non-boundary legacy identity columns.

Revision ID: 0078_final_legacy_identity_cleanup
Revises: 0077_id_dev_runtime_baseline
"""

from __future__ import annotations

from alembic import op


revision = "0078_final_legacy_identity_cleanup"
down_revision = "0077_id_dev_runtime_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _harden_channel_entry_effect_log()
    _drop_contacts_external_userid()
    op.execute("ALTER TABLE IF EXISTS automation_touch_delivery_log DROP COLUMN IF EXISTS external_userid")
    op.execute("ALTER TABLE IF EXISTS user_ops_do_not_disturb_next DROP COLUMN IF EXISTS external_userid")


def _harden_channel_entry_effect_log() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_channel_entry_effect_log (
            id BIGSERIAL PRIMARY KEY,
            event_log_id BIGINT,
            channel_id BIGINT,
            scene_value TEXT NOT NULL DEFAULT '',
            unionid TEXT NOT NULL DEFAULT '',
            owner_staff_id TEXT NOT NULL DEFAULT '',
            effect_type TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'attempted',
            reason TEXT NOT NULL DEFAULT '',
            request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("ALTER TABLE IF EXISTS automation_channel_entry_effect_log ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_channel_entry_effect_log') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = 'automation_channel_entry_effect_log'
                     AND column_name = 'external_contact_id'
               ) THEN
                UPDATE automation_channel_entry_effect_log log
                SET request_json = COALESCE(log.request_json, '{}'::jsonb)
                    || jsonb_build_object('external_contact_id', log.external_contact_id)
                WHERE COALESCE(log.external_contact_id, '') <> ''
                  AND NOT (COALESCE(log.request_json, '{}'::jsonb) ? 'external_contact_id');

                UPDATE automation_channel_entry_effect_log log
                SET unionid = identity.unionid
                FROM crm_user_identity identity
                WHERE COALESCE(log.unionid, '') = ''
                  AND COALESCE(log.external_contact_id, '') <> ''
                  AND (
                      identity.primary_external_userid = log.external_contact_id
                      OR jsonb_exists(identity.external_userids_json, log.external_contact_id)
                  );
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE IF EXISTS automation_channel_entry_effect_log DROP COLUMN IF EXISTS external_contact_id")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_entry_effect_type_key
        ON automation_channel_entry_effect_log (effect_type, idempotency_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_channel_entry_effect_log_unionid_created
        ON automation_channel_entry_effect_log (unionid, created_at DESC, id DESC)
        WHERE unionid <> ''
        """
    )


def _drop_contacts_external_userid() -> None:
    op.execute("ALTER TABLE IF EXISTS contacts ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.contacts') IS NOT NULL
               AND EXISTS (
                   SELECT 1
                   FROM information_schema.columns
                   WHERE table_schema = 'public'
                     AND table_name = 'contacts'
                     AND column_name = 'external_userid'
               ) THEN
                UPDATE contacts contact
                SET unionid = identity.unionid
                FROM crm_user_identity identity
                WHERE COALESCE(contact.unionid, '') = ''
                  AND COALESCE(contact.external_userid, '') <> ''
                  AND (
                      identity.primary_external_userid = contact.external_userid
                      OR jsonb_exists(identity.external_userids_json, contact.external_userid)
                  );
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE IF EXISTS contacts DROP COLUMN IF EXISTS external_userid")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.contacts') IS NOT NULL THEN
                CREATE INDEX IF NOT EXISTS ix_contacts_unionid_updated
                ON contacts (unionid, updated_at DESC, id DESC)
                WHERE unionid <> '';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_channel_entry_effect_log_unionid_created")
