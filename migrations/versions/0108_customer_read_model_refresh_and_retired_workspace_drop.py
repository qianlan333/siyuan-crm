"""add customer read-model refresh state and drop retired empty workspace tables.

Revision ID: 0108_customer_read_model_refresh
Revises: 0107_hyc_usage_snapshot
"""

from __future__ import annotations

from importlib import import_module

from alembic import op


revision = "0108_customer_read_model_refresh"
down_revision = "0107_hyc_usage_snapshot"
branch_labels = None
depends_on = None


_RETIRED_WORKSPACE_TABLES = (
    "group_ops_workspace_gray_window_approvals",
    "group_ops_workspace_allowlist_snapshots",
    "group_ops_workspace_governance_review_steps",
    "group_ops_workspace_governance_reviews",
    "group_ops_workspace_draft_audit_logs",
    "group_ops_workspace_draft_items",
    "group_ops_workspace_drafts",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_read_model_refresh_state (
            singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id = 1),
            last_succeeded_at TIMESTAMPTZ NOT NULL,
            source_count BIGINT NOT NULL DEFAULT 0 CHECK (source_count >= 0),
            target_count BIGINT NOT NULL DEFAULT 0 CHECK (target_count >= 0),
            duration_ms BIGINT NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # These seven P1 control-plane tables have no runtime owner and were
    # confirmed empty in production before this migration. Fail closed on any
    # environment where data appeared after that audit.
    op.execute(
        """
        DO $$
        DECLARE
            table_name TEXT;
            row_found BOOLEAN;
        BEGIN
            FOREACH table_name IN ARRAY ARRAY[
                'group_ops_workspace_gray_window_approvals',
                'group_ops_workspace_allowlist_snapshots',
                'group_ops_workspace_governance_review_steps',
                'group_ops_workspace_governance_reviews',
                'group_ops_workspace_draft_audit_logs',
                'group_ops_workspace_draft_items',
                'group_ops_workspace_drafts'
            ] LOOP
                IF to_regclass('public.' || table_name) IS NOT NULL THEN
                    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I LIMIT 1)', table_name) INTO row_found;
                    IF row_found THEN
                        RAISE EXCEPTION 'retired workspace table % is not empty', table_name;
                    END IF;
                END IF;
            END LOOP;
        END $$
        """
    )
    # Child tables are removed first so the drop is explicit and does not need
    # CASCADE.
    for table_name in _RETIRED_WORKSPACE_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS customer_read_model_refresh_state")
    # Recreate the retired, empty schemas so a release rollback remains
    # structurally reversible. No business data is discarded because the
    # production preflight requires all seven tables to be empty.
    import_module("migrations.versions.0047_group_ops_workspace_drafts").upgrade()
    import_module("migrations.versions.0048_group_ops_workspace_request_review_audit_action").upgrade()
    import_module("migrations.versions.0049_group_ops_workspace_governance").upgrade()
