"""group ops workspace governance tables.

Revision ID: 0049_group_ops_workspace_governance
Revises: 0048_group_ops_workspace_request_review_audit_action

This migration creates only the governance schema proposed by the P1 Group Ops
Workspace Governance RFC. The schema is intentionally limited to sanitized
summaries, hashes, counts, internal references, statuses, actors, timestamps,
and audit metadata. It must not store raw receivers, external user identifiers,
phone/mobile numbers, raw chat/member identifiers, openid/unionid values,
token or secret material, Authorization headers, raw target lists, raw message
bodies, raw callback bodies, or any direct-send target payload.
"""

from __future__ import annotations

from alembic import op


revision = "0049_group_ops_workspace_governance"
down_revision = "0048_group_ops_workspace_request_review_audit_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_ops_workspace_governance_reviews (
            id BIGSERIAL PRIMARY KEY,
            review_id TEXT NOT NULL,
            draft_id TEXT NOT NULL REFERENCES group_ops_workspace_drafts(draft_id) ON DELETE CASCADE,
            review_status TEXT NOT NULL DEFAULT 'governance_not_started'
                CHECK (review_status IN (
                    'governance_not_started',
                    'approval_pending',
                    'allowlist_pending',
                    'gray_window_pending',
                    'governance_approved',
                    'governance_rejected',
                    'governance_expired'
                )),
            requested_by TEXT NOT NULL DEFAULT '',
            approved_by TEXT NOT NULL DEFAULT '',
            rejected_by TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            snapshot_hash TEXT NOT NULL DEFAULT '',
            sanitized_payload_hash TEXT NOT NULL DEFAULT '',
            audit_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_governance_reviews_review_id
        ON group_ops_workspace_governance_reviews (review_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_governance_reviews_idempotency
        ON group_ops_workspace_governance_reviews (draft_id, idempotency_key)
        WHERE idempotency_key <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_reviews_draft
        ON group_ops_workspace_governance_reviews (draft_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_reviews_status
        ON group_ops_workspace_governance_reviews (review_status, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_reviews_expires_at
        ON group_ops_workspace_governance_reviews (expires_at, review_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_reviews_created_at
        ON group_ops_workspace_governance_reviews (created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_reviews_updated_at
        ON group_ops_workspace_governance_reviews (updated_at DESC, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_ops_workspace_governance_review_steps (
            id BIGSERIAL PRIMARY KEY,
            review_id TEXT NOT NULL REFERENCES group_ops_workspace_governance_reviews(review_id) ON DELETE CASCADE,
            step_id TEXT NOT NULL,
            step_type TEXT NOT NULL
                CHECK (step_type IN ('operator_approval', 'receiver_allowlist', 'gray_window')),
            step_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (step_status IN ('pending', 'approved', 'rejected', 'expired')),
            actor_id TEXT NOT NULL DEFAULT '',
            actor_label TEXT NOT NULL DEFAULT '',
            idempotency_key TEXT NOT NULL DEFAULT '',
            snapshot_hash TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_governance_review_steps_step_id
        ON group_ops_workspace_governance_review_steps (step_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_governance_review_steps_idempotency
        ON group_ops_workspace_governance_review_steps (review_id, step_id, idempotency_key)
        WHERE idempotency_key <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_review_steps_review
        ON group_ops_workspace_governance_review_steps (review_id, step_type, id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_review_steps_type_status
        ON group_ops_workspace_governance_review_steps (step_type, step_status, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_review_steps_created_at
        ON group_ops_workspace_governance_review_steps (created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_governance_review_steps_updated_at
        ON group_ops_workspace_governance_review_steps (updated_at DESC, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_ops_workspace_allowlist_snapshots (
            id BIGSERIAL PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            review_id TEXT NOT NULL REFERENCES group_ops_workspace_governance_reviews(review_id) ON DELETE CASCADE,
            allowlist_hash TEXT NOT NULL DEFAULT '',
            allowlist_count INTEGER NOT NULL DEFAULT 0,
            allowlist_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_reference_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_allowlist_snapshots_snapshot_id
        ON group_ops_workspace_allowlist_snapshots (snapshot_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_allowlist_snapshots_review
        ON group_ops_workspace_allowlist_snapshots (review_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_allowlist_snapshots_hash
        ON group_ops_workspace_allowlist_snapshots (allowlist_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_allowlist_snapshots_expires_at
        ON group_ops_workspace_allowlist_snapshots (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_allowlist_snapshots_created_at
        ON group_ops_workspace_allowlist_snapshots (created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_allowlist_snapshots_updated_at
        ON group_ops_workspace_allowlist_snapshots (updated_at DESC, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS group_ops_workspace_gray_window_approvals (
            id BIGSERIAL PRIMARY KEY,
            approval_id TEXT NOT NULL,
            review_id TEXT NOT NULL REFERENCES group_ops_workspace_governance_reviews(review_id) ON DELETE CASCADE,
            start_at TIMESTAMPTZ NOT NULL,
            end_at TIMESTAMPTZ NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            window_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (window_status IN ('pending', 'approved', 'rejected', 'expired')),
            approved_by TEXT NOT NULL DEFAULT '',
            rejected_by TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (end_at > start_at)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_group_ops_workspace_gray_window_approvals_approval_id
        ON group_ops_workspace_gray_window_approvals (approval_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_gray_window_approvals_review
        ON group_ops_workspace_gray_window_approvals (review_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_gray_window_approvals_status
        ON group_ops_workspace_gray_window_approvals (window_status, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_gray_window_approvals_window
        ON group_ops_workspace_gray_window_approvals (start_at, end_at, window_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_gray_window_approvals_created_at
        ON group_ops_workspace_gray_window_approvals (created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_ops_workspace_gray_window_approvals_updated_at
        ON group_ops_workspace_gray_window_approvals (updated_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_gray_window_approvals_updated_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_gray_window_approvals_created_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_gray_window_approvals_window")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_gray_window_approvals_status")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_gray_window_approvals_review")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_gray_window_approvals_approval_id")
    op.execute("DROP TABLE IF EXISTS group_ops_workspace_gray_window_approvals")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_allowlist_snapshots_updated_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_allowlist_snapshots_created_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_allowlist_snapshots_expires_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_allowlist_snapshots_hash")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_allowlist_snapshots_review")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_allowlist_snapshots_snapshot_id")
    op.execute("DROP TABLE IF EXISTS group_ops_workspace_allowlist_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_review_steps_updated_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_review_steps_created_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_review_steps_type_status")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_review_steps_review")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_governance_review_steps_idempotency")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_governance_review_steps_step_id")
    op.execute("DROP TABLE IF EXISTS group_ops_workspace_governance_review_steps")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_reviews_updated_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_reviews_created_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_reviews_expires_at")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_reviews_status")
    op.execute("DROP INDEX IF EXISTS idx_group_ops_workspace_governance_reviews_draft")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_governance_reviews_idempotency")
    op.execute("DROP INDEX IF EXISTS uq_group_ops_workspace_governance_reviews_review_id")
    op.execute("DROP TABLE IF EXISTS group_ops_workspace_governance_reviews")
