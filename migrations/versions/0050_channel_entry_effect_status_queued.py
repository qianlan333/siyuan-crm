"""Allow queued channel-entry effect log status.

Revision ID: 0050_channel_entry_effect_status_queued
Revises: 0049_group_ops_workspace_governance
Create Date: 2026-06-25
"""

from alembic import op


revision = "0050_channel_entry_effect_status_queued"
down_revision = "0049_group_ops_workspace_governance"
branch_labels = None
depends_on = None


CHECK_NAME = "automation_channel_entry_effect_log_status_check"
TABLE_NAME = "automation_channel_entry_effect_log"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{TABLE_NAME}') IS NOT NULL THEN
                ALTER TABLE {TABLE_NAME} DROP CONSTRAINT IF EXISTS {CHECK_NAME};
                ALTER TABLE {TABLE_NAME}
                    ADD CONSTRAINT {CHECK_NAME}
                    CHECK (status IN ('skipped', 'attempted', 'success', 'failed', 'queued'));
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{TABLE_NAME}') IS NOT NULL THEN
                UPDATE {TABLE_NAME}
                SET status = 'attempted'
                WHERE status = 'queued';

                ALTER TABLE {TABLE_NAME} DROP CONSTRAINT IF EXISTS {CHECK_NAME};
                ALTER TABLE {TABLE_NAME}
                    ADD CONSTRAINT {CHECK_NAME}
                    CHECK (status IN ('skipped', 'attempted', 'success', 'failed'));
            END IF;
        END $$;
        """
    )
