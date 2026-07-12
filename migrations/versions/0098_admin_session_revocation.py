"""add the server-side admin session revocation version.

Revision ID: 0098_admin_session_revocation
Revises: 0097_service_period_unionid_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0098_admin_session_revocation"
down_revision = "0097_service_period_unionid_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE IF EXISTS admin_users "
        "ADD COLUMN IF NOT EXISTS session_version BIGINT NOT NULL DEFAULT 1"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_questionnaire_submissions_result_token "
        "ON questionnaire_submissions (result_token) WHERE result_token <> ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_submissions_result_token")
    op.execute(
        "ALTER TABLE IF EXISTS admin_users "
        "DROP COLUMN IF EXISTS session_version"
    )
