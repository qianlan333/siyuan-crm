"""automation runtime v2 tables.

Revision ID: 0031_automation_runtime_v2
Revises: 0030_wechat_pay_unionid_idx
"""

from __future__ import annotations

from alembic import op


revision = "0031_automation_runtime_v2"
down_revision = "0030_wechat_pay_unionid_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_event_v2 (
            id BIGSERIAL PRIMARY KEY,
            event_uid TEXT NOT NULL,
            event_type TEXT NOT NULL,
            program_id BIGINT NULL,
            channel_id BIGINT NULL,
            binding_id BIGINT NULL,
            unionid TEXT NOT NULL DEFAULT '',
            phone TEXT,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            raw_occurred_at TIMESTAMPTZ NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            idempotency_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_event_v2_source UNIQUE (source_type, source_id),
            CONSTRAINT uq_automation_event_v2_idempotency UNIQUE (idempotency_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_event_v2_program_event ON automation_event_v2 (program_id, event_type, occurred_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_event_v2_unionid ON automation_event_v2 (unionid) WHERE unionid <> ''")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_membership_v2 (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL,
            unionid TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            source_channel_id BIGINT NULL,
            source_binding_id BIGINT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            current_stage TEXT NOT NULL DEFAULT 'pending_questionnaire',
            current_stage_entry_id BIGINT NULL,
            joined_at TIMESTAMPTZ NOT NULL,
            exited_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_membership_v2_program_unionid UNIQUE (program_id, unionid)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_membership_v2_unionid ON automation_membership_v2 (unionid) WHERE unionid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_membership_v2_program_stage ON automation_membership_v2 (program_id, current_stage, status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_stage_entry_v2 (
            id BIGSERIAL PRIMARY KEY,
            membership_id BIGINT NOT NULL,
            program_id BIGINT NOT NULL,
            stage_code TEXT NOT NULL,
            entered_at TIMESTAMPTZ NOT NULL,
            exited_at TIMESTAMPTZ NULL,
            source_event_id BIGINT NOT NULL,
            entry_reason TEXT NOT NULL,
            snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_automation_stage_entry_v2_source UNIQUE (membership_id, stage_code, source_event_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_stage_entry_v2_program_stage ON automation_stage_entry_v2 (program_id, stage_code, entered_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_task_plan_v2 (
            id BIGSERIAL PRIMARY KEY,
            program_id BIGINT NOT NULL,
            task_id BIGINT NOT NULL,
            membership_id BIGINT NOT NULL,
            event_id BIGINT NULL,
            stage_entry_id BIGINT NULL,
            schedule_key TEXT NOT NULL DEFAULT '',
            trigger_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            skip_reason TEXT NOT NULL DEFAULT '',
            diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            rendered_content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            broadcast_job_id BIGINT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_task_plan_v2_event ON automation_task_plan_v2 (task_id, membership_id, event_id) WHERE event_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_task_plan_v2_stage ON automation_task_plan_v2 (task_id, membership_id, stage_entry_id) WHERE stage_entry_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_task_plan_v2_schedule ON automation_task_plan_v2 (task_id, membership_id, schedule_key) WHERE schedule_key <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS idx_automation_task_plan_v2_program_status ON automation_task_plan_v2 (program_id, status, created_at)")

    op.execute("ALTER TABLE IF EXISTS automation_operation_task DROP CONSTRAINT IF EXISTS automation_operation_task_trigger_type_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_operation_task
        ADD CONSTRAINT automation_operation_task_trigger_type_check
        CHECK (trigger_type IN ('scheduled_daily', 'audience_entered', 'on_event', 'on_enter_stage', 'scheduled', 'webhook_push'))
        """
    )
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_source_type_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_source_type_check
        CHECK (source_type IN ('campaign', 'sop', 'workflow', 'operation_task', 'cloud_plan', 'focus_send', 'deferred', 'manual', 'automation_runtime_v2'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS broadcast_jobs DROP CONSTRAINT IF EXISTS broadcast_jobs_source_type_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS broadcast_jobs
        ADD CONSTRAINT broadcast_jobs_source_type_check
        CHECK (source_type IN ('campaign', 'sop', 'workflow', 'operation_task', 'cloud_plan', 'focus_send', 'deferred', 'manual'))
        """
    )
    op.execute("ALTER TABLE IF EXISTS automation_operation_task DROP CONSTRAINT IF EXISTS automation_operation_task_trigger_type_check")
    op.execute(
        """
        ALTER TABLE IF EXISTS automation_operation_task
        ADD CONSTRAINT automation_operation_task_trigger_type_check
        CHECK (trigger_type IN ('scheduled_daily', 'audience_entered'))
        """
    )
    op.execute("DROP TABLE IF EXISTS automation_task_plan_v2")
    op.execute("DROP TABLE IF EXISTS automation_stage_entry_v2")
    op.execute("DROP TABLE IF EXISTS automation_membership_v2")
    op.execute("DROP TABLE IF EXISTS automation_event_v2")
