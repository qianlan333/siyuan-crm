"""add questionnaire lead-channel completion binding.

Revision ID: 0116_questionnaire_operations_config
Revises: 0115_wecom_media_leases
"""

from __future__ import annotations

from alembic import op


revision = "0116_questionnaire_operations_config"
down_revision = "0115_wecom_media_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE questionnaires ADD COLUMN IF NOT EXISTS lead_channel_id BIGINT")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_questionnaires_lead_channel'
                  AND conrelid = 'questionnaires'::regclass
            ) THEN
                ALTER TABLE questionnaires
                    ADD CONSTRAINT fk_questionnaires_lead_channel
                    FOREIGN KEY (lead_channel_id)
                    REFERENCES automation_channel(id)
                    ON DELETE SET NULL;
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaires_lead_channel_id
            ON questionnaires (lead_channel_id)
            WHERE lead_channel_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_questionnaires_lead_channel_id")
    op.execute("ALTER TABLE questionnaires DROP CONSTRAINT IF EXISTS fk_questionnaires_lead_channel")
    op.execute("ALTER TABLE questionnaires DROP COLUMN IF EXISTS lead_channel_id")
