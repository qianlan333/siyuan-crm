"""add durable questionnaire identity continuation jobs.

Lifecycle manifest entry:
- table: questionnaire_continuation_job
- lifecycle: canonical
- write_owner: aicrm_next.questionnaire

Rollback note:
- Disable AICRM_QUESTIONNAIRE_CONTINUATION_ENABLED and the UnionID gate first.
- The additive table may remain during application rollback; downgrade is only
  for a coordinated schema rollback after consumers are stopped.

Revision ID: 0124_questionnaire_continuation_jobs
Revises: 0123_required_physical_schema_repair
"""

from __future__ import annotations

from alembic import op


revision = "0124_questionnaire_continuation_jobs"
down_revision = "0123_required_physical_schema_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE questionnaire_submissions
        ADD COLUMN IF NOT EXISTS unionid_verification_source TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE questionnaire_submissions
        ADD COLUMN IF NOT EXISTS unionid_verified_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_continuation_job (
            id BIGSERIAL PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            submission_id BIGINT NOT NULL REFERENCES questionnaire_submissions(id) ON DELETE CASCADE,
            questionnaire_id BIGINT NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
            unionid TEXT NOT NULL CHECK (BTRIM(unionid) <> ''),
            action_type TEXT NOT NULL CHECK (
                action_type IN ('wecom_tag', 'questionnaire_agent_followup')
            ),
            status TEXT NOT NULL DEFAULT 'waiting_identity' CHECK (
                status IN (
                    'waiting_identity', 'dispatching', 'dispatched',
                    'expired', 'blocked_conflict', 'failed_terminal'
                )
            ),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            max_attempts INTEGER NOT NULL DEFAULT 20 CHECK (max_attempts > 0),
            next_attempt_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL,
            identity_ready_at TIMESTAMPTZ,
            dispatched_at TIMESTAMPTZ,
            downstream_ref_type TEXT NOT NULL DEFAULT '',
            downstream_ref_id TEXT NOT NULL DEFAULT '',
            last_error_code TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            source_event_id TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_questionnaire_continuation_submission_action
                UNIQUE (submission_id, action_type)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_continuation_wakeup
        ON questionnaire_continuation_job (unionid, status, expires_at, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_questionnaire_continuation_operations
        ON questionnaire_continuation_job (questionnaire_id, status, created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_continuation_operations")
    op.execute("DROP INDEX IF EXISTS idx_questionnaire_continuation_wakeup")
    op.execute("DROP TABLE IF EXISTS questionnaire_continuation_job")
    op.execute("ALTER TABLE questionnaire_submissions DROP COLUMN IF EXISTS unionid_verified_at")
    op.execute("ALTER TABLE questionnaire_submissions DROP COLUMN IF EXISTS unionid_verification_source")
