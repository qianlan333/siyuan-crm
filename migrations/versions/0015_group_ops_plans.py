"""group ops plans native tables.

Revision ID: 0015
Revises: 0014
"""
from __future__ import annotations

from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_plans (
            id BIGSERIAL PRIMARY KEY,
            plan_code TEXT NOT NULL DEFAULT '',
            plan_name TEXT NOT NULL,
            plan_type TEXT NOT NULL CHECK (plan_type IN ('standard', 'webhook')),
            owner_userid TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'disabled')),
            webhook_key TEXT NOT NULL DEFAULT '',
            webhook_token_hash TEXT NOT NULL DEFAULT '',
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
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_group_ops_plans_code
        ON automation_group_ops_plans (plan_code)
        WHERE plan_code <> ''
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_group_ops_plans_webhook_key
        ON automation_group_ops_plans (webhook_key)
        WHERE webhook_key <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_group_ops_plans_list
        ON automation_group_ops_plans (status, plan_type, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_plan_groups (
            id BIGSERIAL PRIMARY KEY,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            chat_id TEXT NOT NULL,
            group_name_snapshot TEXT NOT NULL DEFAULT '',
            owner_userid_snapshot TEXT NOT NULL DEFAULT '',
            internal_member_count_snapshot INTEGER NOT NULL DEFAULT 0,
            external_member_count_snapshot INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            removed_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_group_ops_plan_groups_active
        ON automation_group_ops_plan_groups (plan_id, chat_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_group_ops_plan_groups_chat
        ON automation_group_ops_plan_groups (chat_id, status, plan_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_plan_nodes (
            id BIGSERIAL PRIMARY KEY,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            day_index INTEGER NOT NULL DEFAULT 1,
            trigger_time_label TEXT NOT NULL DEFAULT '',
            action_title TEXT NOT NULL DEFAULT '',
            text_content TEXT NOT NULL DEFAULT '',
            attachments_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            content_package_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            sort_order INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'disabled', 'deleted')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_group_ops_plan_nodes_order
        ON automation_group_ops_plan_nodes (plan_id, status, day_index ASC, sort_order ASC, id ASC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_group_ops_webhook_events (
            id BIGSERIAL PRIMARY KEY,
            plan_id BIGINT NOT NULL REFERENCES automation_group_ops_plans(id) ON DELETE CASCADE,
            idempotency_key TEXT NOT NULL,
            request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            normalized_content_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            scheduled_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'accepted' CHECK (status IN ('accepted', 'queued', 'duplicate', 'rejected', 'failed')),
            broadcast_job_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_group_ops_webhook_events_idempotency
        ON automation_group_ops_webhook_events (plan_id, idempotency_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_group_ops_webhook_events_plan_created
        ON automation_group_ops_webhook_events (plan_id, created_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wecom_group_chat_snapshots (
            chat_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            owner_name TEXT NOT NULL DEFAULT '',
            admin_userids TEXT NOT NULL DEFAULT '[]',
            internal_member_count INTEGER NOT NULL DEFAULT 0,
            external_member_count INTEGER NOT NULL DEFAULT 0,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wecom_group_chat_snapshots_owner
        ON wecom_group_chat_snapshots (owner_userid, status, synced_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_wecom_group_chat_snapshots_name
        ON wecom_group_chat_snapshots (group_name)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_wecom_group_chat_snapshots_name")
    op.execute("DROP INDEX IF EXISTS idx_wecom_group_chat_snapshots_owner")
    op.execute("DROP TABLE IF EXISTS wecom_group_chat_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_automation_group_ops_webhook_events_plan_created")
    op.execute("DROP INDEX IF EXISTS uq_automation_group_ops_webhook_events_idempotency")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_webhook_events")
    op.execute("DROP INDEX IF EXISTS idx_automation_group_ops_plan_nodes_order")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_plan_nodes")
    op.execute("DROP INDEX IF EXISTS idx_automation_group_ops_plan_groups_chat")
    op.execute("DROP INDEX IF EXISTS uq_automation_group_ops_plan_groups_active")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_plan_groups")
    op.execute("DROP INDEX IF EXISTS idx_automation_group_ops_plans_list")
    op.execute("DROP INDEX IF EXISTS uq_automation_group_ops_plans_webhook_key")
    op.execute("DROP INDEX IF EXISTS uq_automation_group_ops_plans_code")
    op.execute("DROP TABLE IF EXISTS automation_group_ops_plans")
