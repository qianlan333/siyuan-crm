"""drop external target columns from broadcast and automation target tables.

Revision ID: 0066_unionid_broadcast_target_cleanup
Revises: 0065_unionid_submission_payment_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0066_unionid_broadcast_target_cleanup"
down_revision = "0065_unionid_submission_payment_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _prepare_broadcast_jobs()
    _prepare_cloud_broadcast_recipients()
    _prepare_channel_assignment_events()
    _prepare_automation_agent_items()


def _prepare_broadcast_jobs() -> None:
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs ADD COLUMN IF NOT EXISTS target_unionids_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.broadcast_jobs') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'broadcast_jobs' AND column_name = 'target_external_userids'
               ) THEN
                EXECUTE $sql$
                    UPDATE broadcast_jobs job
                    SET target_unionids_json = COALESCE(resolved.unionids, '[]'::jsonb)
                    FROM (
                        SELECT job_inner.id,
                               COALESCE(jsonb_agg(DISTINCT cui.unionid) FILTER (WHERE cui.unionid IS NOT NULL), '[]'::jsonb) AS unionids
                        FROM broadcast_jobs job_inner
                        CROSS JOIN LATERAL jsonb_array_elements_text(job_inner.target_external_userids) AS external_ids(external_userid)
                        JOIN crm_user_identity cui
                          ON cui.primary_external_userid = external_ids.external_userid
                          OR jsonb_exists(cui.external_userids_json, external_ids.external_userid)
                        GROUP BY job_inner.id
                    ) resolved
                    WHERE job.id = resolved.id
                      AND jsonb_array_length(job.target_unionids_json) = 0
                $sql$;
            END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_broadcast_jobs_target_unionids_json ON broadcast_jobs USING GIN (target_unionids_json)")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_status_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_status_check
        CHECK (status IN ('waiting_approval', 'queued', 'claimed', 'sent', 'failed', 'blocked', 'cancelled'))
        """
    )
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS target_external_userids")


def _prepare_cloud_broadcast_recipients() -> None:
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plan_recipients ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plan_recipient_messages ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.cloud_broadcast_plan_recipients') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'cloud_broadcast_plan_recipients' AND column_name = 'external_userid'
               ) THEN
                EXECUTE $sql$
                    UPDATE cloud_broadcast_plan_recipients recipient
                    SET unionid = cui.unionid
                    FROM crm_user_identity cui
                    WHERE COALESCE(recipient.unionid, '') = ''
                      AND COALESCE(recipient.external_userid, '') <> ''
                      AND (
                          cui.primary_external_userid = recipient.external_userid
                          OR jsonb_exists(cui.external_userids_json, recipient.external_userid)
                      )
                $sql$;
            END IF;

            IF to_regclass('public.cloud_broadcast_plan_recipient_messages') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'cloud_broadcast_plan_recipient_messages' AND column_name = 'external_userid'
               ) THEN
                EXECUTE $sql$
                    UPDATE cloud_broadcast_plan_recipient_messages message
                    SET unionid = COALESCE(
                        NULLIF((
                            SELECT recipient.unionid
                            FROM cloud_broadcast_plan_recipients recipient
                            WHERE recipient.id = message.recipient_id
                            LIMIT 1
                        ), ''),
                        (
                            SELECT cui.unionid
                            FROM crm_user_identity cui
                            WHERE cui.primary_external_userid = message.external_userid
                               OR jsonb_exists(cui.external_userids_json, message.external_userid)
                            LIMIT 1
                        ),
                        ''
                    )
                    WHERE COALESCE(message.unionid, '') = ''
                $sql$;
            END IF;
        END $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_cloud_broadcast_plan_recipients_external")
    op.execute("DROP INDEX IF EXISTS uq_cloud_broadcast_plan_recipients_plan_external")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_cloud_broadcast_plan_recipients_plan_unionid ON cloud_broadcast_plan_recipients (plan_id, unionid) WHERE unionid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cloud_broadcast_plan_recipients_unionid ON cloud_broadcast_plan_recipients (unionid)")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plan_recipient_messages DROP COLUMN IF EXISTS external_userid")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plan_recipients DROP COLUMN IF EXISTS external_userid")


def _prepare_channel_assignment_events() -> None:
    op.execute("ALTER TABLE IF EXISTS automation_channel_assignment_event ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_channel_assignment_event') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_channel_assignment_event' AND column_name = 'external_contact_id'
               ) THEN
                EXECUTE $sql$
                    UPDATE automation_channel_assignment_event event
                    SET unionid = cui.unionid
                    FROM crm_user_identity cui
                    WHERE COALESCE(event.unionid, '') = ''
                      AND COALESCE(event.external_contact_id, '') <> ''
                      AND (
                          cui.primary_external_userid = event.external_contact_id
                          OR jsonb_exists(cui.external_userids_json, event.external_contact_id)
                      )
                $sql$;
            END IF;
        END $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_channel_assignment_external")
    op.execute("CREATE INDEX IF NOT EXISTS idx_channel_assignment_unionid ON automation_channel_assignment_event(channel_id, unionid)")
    op.execute("ALTER TABLE IF EXISTS automation_channel_assignment_event DROP COLUMN IF EXISTS external_contact_id")


def _prepare_automation_agent_items() -> None:
    op.execute("ALTER TABLE IF EXISTS automation_agent_webhook_item ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.automation_agent_webhook_item') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'automation_agent_webhook_item' AND column_name = 'external_userid'
               ) THEN
                EXECUTE $sql$
                    UPDATE automation_agent_webhook_item item
                    SET unionid = cui.unionid
                    FROM crm_user_identity cui
                    WHERE COALESCE(item.unionid, '') = ''
                      AND COALESCE(item.external_userid, '') <> ''
                      AND (
                          cui.primary_external_userid = item.external_userid
                          OR jsonb_exists(cui.external_userids_json, item.external_userid)
                      )
                $sql$;
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE IF EXISTS automation_agent_webhook_item DROP CONSTRAINT IF EXISTS uq_automation_agent_webhook_item_batch_external")
    op.execute("ALTER TABLE IF EXISTS automation_agent_webhook_item DROP CONSTRAINT IF EXISTS uq_automation_agent_webhook_item_batch_unionid")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_agent_webhook_item_batch_unionid ON automation_agent_webhook_item (batch_id, unionid) WHERE unionid <> ''")
    op.execute("ALTER TABLE IF EXISTS automation_agent_webhook_item DROP COLUMN IF EXISTS external_userid")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs ADD COLUMN IF NOT EXISTS target_external_userids JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plan_recipients ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS cloud_broadcast_plan_recipient_messages ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_channel_assignment_event ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_agent_webhook_item ADD COLUMN IF NOT EXISTS external_userid TEXT NOT NULL DEFAULT ''")
