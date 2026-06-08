"""broadcast_jobs leases and recoverable outbound intent

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-21
"""
from __future__ import annotations

from alembic import op


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD COLUMN IF NOT EXISTS claim_token TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_lease
        ON broadcast_jobs (status, claim_token, lease_expires_at, id ASC)
        WHERE status = 'claimed' AND claim_token <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_lease")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS lease_expires_at")
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP COLUMN IF EXISTS claim_token")
