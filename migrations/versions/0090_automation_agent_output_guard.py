"""automation agent output guard controls.

Revision ID: 0090_automation_agent_output_guard
Revises: 0089_broadcast_retry_reclaim
"""

from __future__ import annotations

from alembic import op


revision = "0090_automation_agent_output_guard"
down_revision = "0089_broadcast_retry_reclaim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_agent_runtime_config
        ADD COLUMN IF NOT EXISTS need_human_review BOOLEAN NOT NULL DEFAULT FALSE
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS automation_agent_runtime_config DROP COLUMN IF EXISTS need_human_review")
