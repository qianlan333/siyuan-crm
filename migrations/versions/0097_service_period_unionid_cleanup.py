"""remove the service period mobile identity snapshot.

Revision ID: 0097_service_period_unionid_cleanup
Revises: 0096_admin_wecom_directory_members
"""

from __future__ import annotations

from alembic import op


revision = "0097_service_period_unionid_cleanup"
down_revision = "0096_admin_wecom_directory_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS service_period_entitlements "
        "DROP COLUMN IF EXISTS mobile_snapshot"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS service_period_entitlements "
        "ADD COLUMN IF NOT EXISTS mobile_snapshot TEXT NOT NULL DEFAULT ''"
    )
