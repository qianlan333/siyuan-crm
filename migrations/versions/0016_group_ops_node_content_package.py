"""add group ops node content package.

Revision ID: 0016
Revises: 0015
"""
from __future__ import annotations

from alembic import op


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE automation_group_ops_plan_nodes
        ADD COLUMN IF NOT EXISTS content_package_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE automation_group_ops_plan_nodes
        DROP COLUMN IF EXISTS content_package_json
        """
    )
