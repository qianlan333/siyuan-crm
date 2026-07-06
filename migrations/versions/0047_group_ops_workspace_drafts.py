"""group ops workspace draft persistence tables.

Revision ID: 0047_group_ops_workspace_drafts
Revises: 0046_ai_audience_publish_and_subscription_dedupe

This migration creates only the draft storage schema proposed by the P1 Group
Ops Workspace Draft Persistence RFC. The schema is intentionally limited to
sanitized structures, internal references, guardrail summaries, approval
requirements, and audit metadata. It must not store receiver plaintext,
external user identifiers, mobile numbers, raw chat/member identifiers,
openid/unionid values, token or secret material, Authorization headers, raw
message/callback bodies, or direct-send target lists.
"""

from __future__ import annotations

from alembic import op


revision = "0047_group_ops_workspace_drafts"
down_revision = "0046_ai_audience_publish_and_subscription_dedupe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_ops_workspace_drafts (
            id BIGSERIAL PRIMARY KEY,
            draft_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'aicrm',
            admin_scope TEXT NOT NULL DEFAULT '',
            source_plan_id TEXT NOT NULL DEFAULT '',
            draft_status TEXT NOT NULL DEFAULT 'draft'
                CHECK (draft_status IN ('draft', 'ready_for_review', 'archived', 'rejected')),
            version INTEGER NOT NULL DEFAULT 1,
            idempotency_key TEXT NOT NULL DEFAULT '',
            snapshot_hash TEXT NOT NULL DEFAULT '',
            sanitized_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            guardrail_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            approval_requirements_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            archived_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_drafts_draft_id
        ON group_ops_workspace_drafts (draft_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_drafts_tenant_idempotency
        ON group_ops_workspace_drafts (tenant_id, admin_scope, idempotency_key)
        WHERE idempotency_key <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_drafts_status
        ON group_ops_workspace_drafts (draft_status, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_drafts_source_plan
        ON group_ops_workspace_drafts (source_plan_id, draft_status, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_drafts_created_at
        ON group_ops_workspace_drafts (created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_drafts_updated_at
        ON group_ops_workspace_drafts (updated_at DESC, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_ops_workspace_draft_items (
            id BIGSERIAL PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES group_ops_workspace_drafts(draft_id) ON DELETE CASCADE,
            item_type TEXT NOT NULL,
            item_ref_id TEXT NOT NULL DEFAULT '',
            item_order INTEGER NOT NULL DEFAULT 0,
            sanitized_item_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            guardrail_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_draft_items_draft
        ON group_ops_workspace_draft_items (draft_id, item_order ASC, id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_draft_items_type
        ON group_ops_workspace_draft_items (item_type, item_ref_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_ops_workspace_draft_audit_logs (
            id BIGSERIAL PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES group_ops_workspace_drafts(draft_id) ON DELETE CASCADE,
            action TEXT NOT NULL
                CHECK (action IN ('create', 'update', 'archive', 'request-review', 'reject')),
            actor_id TEXT NOT NULL DEFAULT '',
            actor_label TEXT NOT NULL DEFAULT '',
            actor_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            version INTEGER NOT NULL DEFAULT 1,
            snapshot_hash TEXT NOT NULL DEFAULT '',
            before_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_draft_audit_logs_draft
        ON group_ops_workspace_draft_audit_logs (draft_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_draft_audit_logs_action
        ON group_ops_workspace_draft_audit_logs (action, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_draft_audit_logs_action")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_draft_audit_logs_draft")
    op.execute("DROP TABLE IF EXISTS group_ops_workspace_draft_audit_logs")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_draft_items_type")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_draft_items_draft")
    op.execute("DROP TABLE IF EXISTS group_ops_workspace_draft_items")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_drafts_updated_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_drafts_created_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_drafts_source_plan")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_drafts_status")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_drafts_tenant_idempotency")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_drafts_draft_id")
    op.execute("DROP TABLE IF EXISTS group_ops_workspace_drafts")
