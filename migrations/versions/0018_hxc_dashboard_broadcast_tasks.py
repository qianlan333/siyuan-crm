"""hxc dashboard broadcast tasks.

Revision ID: 0018
Revises: 0017
"""
from __future__ import annotations

from alembic import op


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hxc_dashboard_broadcast_tasks (
            id BIGSERIAL PRIMARY KEY,
            task_id TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL DEFAULT 'hxc_dashboard_broadcast',
            source_id TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL,
            sender_userid TEXT NOT NULL DEFAULT '',
            audience_filter JSONB NOT NULL DEFAULT '{}'::jsonb,
            selected_customer_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            content_package JSONB NOT NULL DEFAULT '{}'::jsonb,
            audience_total INTEGER NOT NULL DEFAULT 0,
            eligible_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            skipped_by_reason JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'created'
                CHECK (status IN ('created', 'degraded', 'production_unavailable')),
            dispatch_status TEXT NOT NULL DEFAULT 'pending_external_dispatch',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (source_type, source_id, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hxc_dashboard_broadcast_tasks_created
        ON hxc_dashboard_broadcast_tasks (created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_hxc_dashboard_broadcast_tasks_created")
    op.execute("DROP TABLE IF EXISTS hxc_dashboard_broadcast_tasks")
