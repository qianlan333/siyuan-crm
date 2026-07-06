"""clean target-only legacy identity residue.

Revision ID: 0079_final_target_schema_cleanup
Revises: 0078_final_legacy_identity_cleanup
"""

from __future__ import annotations

from alembic import op


revision = "0079_final_target_schema_cleanup"
down_revision = "0078_final_legacy_identity_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS customer_timeline_event_next DROP COLUMN IF EXISTS person_id")
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.contacts') IS NOT NULL THEN
                DELETE FROM contacts WHERE COALESCE(unionid, '') = '';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    pass
