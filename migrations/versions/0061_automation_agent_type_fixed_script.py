"""add automation agent fixed script type.

Revision ID: 0061_automation_agent_type_fixed_script
Revises: 0060_ai_audience_hxc_member_usage_view
"""

from __future__ import annotations

from alembic import op


revision = "0061_automation_agent_type_fixed_script"
down_revision = "0060_ai_audience_hxc_member_usage_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE automation_agent_runtime_config
        ADD COLUMN IF NOT EXISTS automation_type TEXT NOT NULL DEFAULT 'agent'
        """
    )
    op.execute(
        """
        UPDATE automation_agent_runtime_config
        SET automation_type = 'agent'
        WHERE automation_type IS NULL OR automation_type = ''
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_automation_agent_runtime_config_type'
            ) THEN
                ALTER TABLE automation_agent_runtime_config
                ADD CONSTRAINT ck_automation_agent_runtime_config_type
                CHECK (automation_type IN ('agent', 'fixed_script'));
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE automation_agent_runtime_config
        DROP CONSTRAINT IF EXISTS ck_automation_agent_runtime_config_type
        """
    )
    op.execute("ALTER TABLE automation_agent_runtime_config DROP COLUMN IF EXISTS automation_type")
