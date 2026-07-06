"""add ai audience package version parameters.

Revision ID: 0052_ai_audience_package_version_parameters
Revises: 0051_ai_audience_sender_whitelist
"""

from __future__ import annotations

from alembic import op


revision = "0052_ai_audience_package_version_parameters"
down_revision = "0051_ai_audience_sender_whitelist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ai_audience_package_version
        ADD COLUMN IF NOT EXISTS parameters_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE ai_audience_package_version
        DROP COLUMN IF EXISTS parameters_json
        """
    )
