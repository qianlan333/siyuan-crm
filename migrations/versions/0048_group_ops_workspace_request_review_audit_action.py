"""allow request_review audit action for group ops workspace drafts.

Revision ID: 0048_group_ops_workspace_request_review_audit_action
Revises: 0047_group_ops_workspace_drafts

This migration only updates the draft audit action constraint so the backend
request-review API can store action="request_review". It does not create
execution, Push Center, broadcast, or external effect write paths.
"""

from __future__ import annotations

from alembic import op


revision = "0048_group_ops_workspace_request_review_audit_action"
down_revision = "0047_group_ops_workspace_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS group_ops_workspace_draft_audit_logs
        DROP CONSTRAINT IF EXISTS group_ops_workspace_draft_audit_logs_action_check
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS group_ops_workspace_draft_audit_logs
        ADD CONSTRAINT group_ops_workspace_draft_audit_logs_action_check
        CHECK (action IN ('create', 'update', 'archive', 'request-review', 'request_review', 'reject'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS group_ops_workspace_draft_audit_logs
        DROP CONSTRAINT IF EXISTS group_ops_workspace_draft_audit_logs_action_check
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS group_ops_workspace_draft_audit_logs
        ADD CONSTRAINT group_ops_workspace_draft_audit_logs_action_check
        CHECK (action IN ('create', 'update', 'archive', 'request-review', 'reject'))
        """
    )
