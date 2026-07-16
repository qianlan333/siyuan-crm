"""persist the authoritative internal-event fan-out manifest.

Revision ID: 0122_internal_event_fanout_manifest
Revises: 0121_service_period_member_grid_sharing
"""

from __future__ import annotations

from alembic import op


revision = "0122_internal_event_fanout_manifest"
down_revision = "0121_service_period_member_grid_sharing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE internal_event
        ADD COLUMN IF NOT EXISTS fanout_manifest_version TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS fanout_manifest_hash TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS fanout_manifest_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        ADD COLUMN IF NOT EXISTS expected_consumer_count INTEGER NOT NULL DEFAULT 0
            CHECK (expected_consumer_count >= 0)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_internal_event_fanout_manifest_gap
        ON internal_event (event_type, created_at, id)
        WHERE fanout_manifest_hash <> '' AND expected_consumer_count > 0
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_internal_event_fanout_manifest_gap")
    op.execute("ALTER TABLE internal_event DROP COLUMN IF EXISTS expected_consumer_count")
    op.execute("ALTER TABLE internal_event DROP COLUMN IF EXISTS fanout_manifest_json")
    op.execute("ALTER TABLE internal_event DROP COLUMN IF EXISTS fanout_manifest_hash")
    op.execute("ALTER TABLE internal_event DROP COLUMN IF EXISTS fanout_manifest_version")
