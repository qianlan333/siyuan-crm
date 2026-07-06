"""perf indexes + automation_execution_trace + outbound_event_outbox

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-04

Adds:
- composite index ``(external_userid, dispatched_at DESC)`` on
  ``conversion_dispatch_log`` so that ``MAX(dispatched_at) WHERE external_userid=?``
  stops scanning the partition.
- ``automation_execution_trace`` so that ``run_due_conversion_workflows`` can
  record a per-customer per-decision audit trail and offline replay tools can
  reconstruct why a customer was/was not processed.
- ``outbound_event_outbox`` for the Sprint 2 transactional-outbox pattern
  (table created here so Sprint 2 can drop in the scanner without a separate
  migration).

All DDL uses ``IF NOT EXISTS`` so re-running on a database already initialised
from the PostgreSQL schema bootstrap is a no-op.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    schema = None if bind.dialect.name == "sqlite" else "public"
    return inspect(bind).has_table(table, schema=schema)


def upgrade() -> None:
    if _has_table("conversion_dispatch_log"):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversion_dispatch_log_external_dispatched
            ON conversion_dispatch_log (external_userid, dispatched_at DESC)
            """
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_execution_trace (
            id BIGSERIAL PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            workflow_node_id TEXT,
            external_userid TEXT,
            member_id BIGINT,
            decision_point TEXT NOT NULL,
            decision_outcome TEXT NOT NULL,
            reason TEXT,
            request_id TEXT,
            job_id TEXT,
            parent_request_id TEXT,
            payload_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS outbound_event_outbox (
            id BIGSERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            target_name TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            idempotency_key TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TIMESTAMPTZ,
            last_error TEXT,
            request_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_execution_trace_workflow
        ON automation_execution_trace (workflow_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_execution_trace_external
        ON automation_execution_trace (external_userid, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outbound_event_outbox_status_next
        ON outbound_event_outbox (status, next_attempt_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_outbound_event_outbox_idempotency
        ON outbound_event_outbox (idempotency_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_outbound_event_outbox_idempotency")
    op.execute("DROP INDEX IF EXISTS idx_outbound_event_outbox_status_next")
    op.execute("DROP INDEX IF EXISTS idx_automation_execution_trace_external")
    op.execute("DROP INDEX IF EXISTS idx_automation_execution_trace_workflow")
    op.execute("DROP INDEX IF EXISTS idx_conversion_dispatch_log_external_dispatched")
    op.execute("DROP TABLE IF EXISTS outbound_event_outbox")
    op.execute("DROP TABLE IF EXISTS automation_execution_trace")
