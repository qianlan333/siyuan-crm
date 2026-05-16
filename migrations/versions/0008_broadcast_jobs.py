"""broadcast_jobs — 统一群发任务队列

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-10

新建 broadcast_jobs 表，把分散在 6 条链路（campaigns / SOP / workflow /
cloud_orchestrator / focus_send / user_ops_deferred）的"未来该发的批次"
统一到一个队列里。后续单一 worker (run_broadcast_queue_worker.py) 轮询
该表，按 batch_key 聚合后调 dispatch_wecom_task() 真发。

设计要点：
- 一个 job = 一次群发批次（含多 user），target_external_userids 是 JSON 数组
- AI 草稿用 status='waiting_approval' + requires_approval=true，运营 confirm 后转 'queued'
- 取消用软删（status='cancelled' + cancelled_by/cancelled_at/cancel_reason），便于审计
- 失败不自动重试（status='failed' + last_error），由运营手动 retry
- (source_table, source_id, scheduled_for) 唯一索引，避免重复展平入队
"""
from __future__ import annotations

from alembic import op


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broadcast_jobs (
            id BIGSERIAL PRIMARY KEY,
            source_type TEXT NOT NULL DEFAULT ''
                CHECK (source_type IN ('campaign', 'sop', 'workflow', 'cloud_plan', 'focus_send', 'deferred', 'manual')),
            source_id TEXT NOT NULL DEFAULT '',
            source_table TEXT NOT NULL DEFAULT '',
            scheduled_for TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            priority INTEGER NOT NULL DEFAULT 100,
            batch_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('waiting_approval', 'queued', 'claimed', 'sent', 'failed', 'cancelled')),
            requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
            approved_by TEXT NOT NULL DEFAULT '',
            approved_at TIMESTAMPTZ,
            cancelled_by TEXT NOT NULL DEFAULT '',
            cancelled_at TIMESTAMPTZ,
            cancel_reason TEXT NOT NULL DEFAULT '',
            target_external_userids JSONB NOT NULL DEFAULT '[]'::jsonb,
            target_count INTEGER NOT NULL DEFAULT 0,
            target_summary TEXT NOT NULL DEFAULT '',
            content_type TEXT NOT NULL DEFAULT 'text',
            content_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            content_summary TEXT NOT NULL DEFAULT '',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            outbound_task_id BIGINT,
            sent_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            trace_id TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            claimed_at TIMESTAMPTZ,
            sent_at TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_due
        ON broadcast_jobs (status, scheduled_for, priority, id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_timeline
        ON broadcast_jobs (scheduled_for DESC, status, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_source
        ON broadcast_jobs (source_type, source_id, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broadcast_jobs_trace
        ON broadcast_jobs (trace_id, id DESC)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_broadcast_jobs_source_scheduled
        ON broadcast_jobs (source_table, source_id, scheduled_for)
        WHERE source_id <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_broadcast_jobs_source_scheduled")
    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_trace")
    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_source")
    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_timeline")
    op.execute("DROP INDEX IF EXISTS idx_broadcast_jobs_due")
    op.execute("DROP TABLE IF EXISTS broadcast_jobs")
