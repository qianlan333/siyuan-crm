"""drop external identity columns from campaign and frequency tables.

Revision ID: 0067_unionid_campaign_frequency_cleanup
Revises: 0066_unionid_broadcast_target_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0067_unionid_campaign_frequency_cleanup"
down_revision = "0066_unionid_broadcast_target_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _prepare_segment_member_snapshots()
    _prepare_campaign_members()
    _prepare_frequency_consumption()
    _prepare_agent_run_outputs()


def _backfill_unionid_from_external(table: str, external_column: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table}') IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = '{external_column}'
               ) THEN
                EXECUTE $sql$
                    UPDATE {table} target
                    SET unionid = cui.unionid
                    FROM crm_user_identity cui
                    WHERE COALESCE(target.unionid, '') = ''
                      AND COALESCE(target.{external_column}, '') <> ''
                      AND (
                          cui.primary_external_userid = target.{external_column}
                          OR jsonb_exists(cui.external_userids_json, target.{external_column})
                      )
                $sql$;
            END IF;
        END $$;
        """
    )


def _prepare_segment_member_snapshots() -> None:
    op.execute("ALTER TABLE IF EXISTS segment_member_snapshots ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    _backfill_unionid_from_external("segment_member_snapshots", "external_contact_id")
    op.execute("ALTER TABLE IF EXISTS segment_member_snapshots DROP COLUMN IF EXISTS external_contact_id")


def _prepare_campaign_members() -> None:
    op.execute("ALTER TABLE IF EXISTS campaign_members ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    _backfill_unionid_from_external("campaign_members", "external_contact_id")
    op.execute("DROP INDEX IF EXISTS idx_campaign_members_external")
    _create_index_if_table_exists(
        "campaign_members",
        "CREATE INDEX IF NOT EXISTS idx_campaign_members_unionid ON campaign_members (unionid, campaign_id, id DESC)",
    )
    op.execute("ALTER TABLE IF EXISTS campaign_members DROP COLUMN IF EXISTS external_contact_id")


def _prepare_frequency_consumption() -> None:
    op.execute("ALTER TABLE IF EXISTS automation_frequency_consumption ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
    _backfill_unionid_from_external("automation_frequency_consumption", "external_contact_id")
    op.execute("DROP INDEX IF EXISTS idx_automation_frequency_consumption_external_window")
    _create_index_if_table_exists(
        "automation_frequency_consumption",
        """
        CREATE INDEX IF NOT EXISTS idx_automation_frequency_consumption_unionid_window
        ON automation_frequency_consumption (unionid, budget_id, consumed_at DESC)
        """,
    )
    op.execute("ALTER TABLE IF EXISTS automation_frequency_consumption DROP COLUMN IF EXISTS external_contact_id")


def _prepare_agent_run_outputs() -> None:
    for table in ("automation_agent_run", "automation_agent_output"):
        op.execute(f"ALTER TABLE IF EXISTS {table} ADD COLUMN IF NOT EXISTS unionid TEXT NOT NULL DEFAULT ''")
        _backfill_unionid_from_external(table, "external_contact_id")
        _create_index_if_table_exists(
            table,
            f"CREATE INDEX IF NOT EXISTS ix_{table}_unionid ON {table} (unionid) WHERE unionid <> ''",
        )
        op.execute(f"ALTER TABLE IF EXISTS {table} DROP COLUMN IF EXISTS external_contact_id")


def _create_index_if_table_exists(table: str, statement: str) -> None:
    escaped_statement = statement.replace("'", "''")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table}') IS NOT NULL THEN
                EXECUTE '{escaped_statement}';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS segment_member_snapshots ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS campaign_members ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_frequency_consumption ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_agent_run ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE IF EXISTS automation_agent_output ADD COLUMN IF NOT EXISTS external_contact_id TEXT NOT NULL DEFAULT ''")
