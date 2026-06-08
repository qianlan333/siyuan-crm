"""broadcast job hourly report records

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op


revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_job_hourly_reports (
            id BIGSERIAL PRIMARY KEY,
            report_key TEXT NOT NULL UNIQUE,
            window_start TIMESTAMPTZ NOT NULL,
            window_end TIMESTAMPTZ NOT NULL,
            channel TEXT NOT NULL DEFAULT 'feishu',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'sent', 'failed')),
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT,
            sent_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_job_hourly_reports_window
        ON broadcast_job_hourly_reports (channel, window_start DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_broadcast_job_hourly_reports_window")
    op.execute("DROP TABLE IF EXISTS broadcast_job_hourly_reports")
