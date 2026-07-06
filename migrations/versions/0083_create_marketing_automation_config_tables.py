"""create marketing automation config tables.

Revision ID: 0083_create_marketing_automation_config_tables
Revises: 0082_direct_send_broadcast_source_types
"""

from __future__ import annotations

from alembic import op


revision = "0083_create_marketing_automation_config_tables"
down_revision = "0082_direct_send_broadcast_source_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS marketing_automation_configs (
            id BIGSERIAL PRIMARY KEY,
            automation_key TEXT NOT NULL DEFAULT '',
            automation_name TEXT NOT NULL DEFAULT '',
            target_event TEXT NOT NULL DEFAULT 'signup_success',
            channel_type TEXT NOT NULL DEFAULT 'text_message',
            status TEXT NOT NULL DEFAULT 'active',
            do_not_start_after_hour INTEGER NOT NULL DEFAULT 23,
            config_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_marketing_automation_configs_key
        ON marketing_automation_configs (automation_key)
        WHERE automation_key <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_marketing_automation_configs_status
        ON marketing_automation_configs (status)
        WHERE status <> ''
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS marketing_automation_question_rules (
            id BIGSERIAL PRIMARY KEY,
            automation_config_id BIGINT NOT NULL DEFAULT 0,
            questionnaire_id BIGINT,
            question_id BIGINT,
            rule_code TEXT NOT NULL DEFAULT '',
            rule_name TEXT NOT NULL DEFAULT '',
            answer_match_type TEXT NOT NULL DEFAULT 'any_of',
            answer_match_value_json TEXT NOT NULL DEFAULT '[]',
            score_delta INTEGER NOT NULL DEFAULT 0,
            segment_hint TEXT NOT NULL DEFAULT '',
            stage_hint TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            rule_payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_marketing_automation_question_rules_config_active
        ON marketing_automation_question_rules (automation_config_id, is_active, sort_order, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_marketing_automation_question_rules_questionnaire
        ON marketing_automation_question_rules (questionnaire_id)
        WHERE questionnaire_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS marketing_automation_question_rules")
    op.execute("DROP TABLE IF EXISTS marketing_automation_configs")
