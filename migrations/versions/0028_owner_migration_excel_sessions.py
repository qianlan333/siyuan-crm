"""owner migration excel sessions and execution results"""

from __future__ import annotations

from alembic import op


revision = "0028_owner_excel_sessions"
down_revision = "0027_group_ops_admin_userids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_migration_import_sessions (
            session_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL DEFAULT '',
            file_hash TEXT NOT NULL DEFAULT '',
            source_owner_userid TEXT NOT NULL,
            target_owner_userid TEXT NOT NULL,
            include_wecom_transfer BOOLEAN NOT NULL DEFAULT TRUE,
            transfer_welcome_msg TEXT NOT NULL DEFAULT '',
            rows_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            row_stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            operator TEXT NOT NULL DEFAULT 'crm_console',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_migration_previews (
            preview_token TEXT PRIMARY KEY,
            preview_hash TEXT NOT NULL,
            scope_type TEXT NOT NULL,
            session_id TEXT NOT NULL DEFAULT '',
            file_hash TEXT NOT NULL DEFAULT '',
            source_owner_userid TEXT NOT NULL,
            target_owner_userid TEXT NOT NULL,
            source_owner_display_name TEXT NOT NULL DEFAULT '',
            target_owner_display_name TEXT NOT NULL DEFAULT '',
            include_wecom_transfer BOOLEAN NOT NULL DEFAULT TRUE,
            transfer_welcome_msg TEXT NOT NULL DEFAULT '',
            eligible_external_userids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            rows_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            row_stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            surface_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            pending_review_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            confirm_phrase TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT 'crm_console',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMPTZ NOT NULL,
            executed_result_id TEXT NOT NULL DEFAULT ''
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_owner_migration_previews_session ON owner_migration_previews (session_id, created_at DESC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_migration_results (
            result_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL DEFAULT '',
            preview_token TEXT NOT NULL DEFAULT '',
            scope_type TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL DEFAULT '',
            file_hash TEXT NOT NULL DEFAULT '',
            source_owner_userid TEXT NOT NULL,
            target_owner_userid TEXT NOT NULL,
            source_owner_display_name TEXT NOT NULL DEFAULT '',
            target_owner_display_name TEXT NOT NULL DEFAULT '',
            operator TEXT NOT NULL DEFAULT 'crm_console',
            preview_hash TEXT NOT NULL DEFAULT '',
            total_rows INTEGER NOT NULL DEFAULT 0,
            eligible_count INTEGER NOT NULL DEFAULT 0,
            wecom_success INTEGER NOT NULL DEFAULT 0,
            wecom_failed INTEGER NOT NULL DEFAULT 0,
            crm_updated INTEGER NOT NULL DEFAULT 0,
            include_wecom_transfer BOOLEAN NOT NULL DEFAULT TRUE,
            transfer_welcome_msg TEXT NOT NULL DEFAULT '',
            rows_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_owner_migration_results_preview ON owner_migration_results (preview_token)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_owner_migration_results_preview")
    op.execute("DROP INDEX IF EXISTS ix_owner_migration_previews_session")
    op.execute("DROP TABLE IF EXISTS owner_migration_results")
    op.execute("DROP TABLE IF EXISTS owner_migration_previews")
    op.execute("DROP TABLE IF EXISTS owner_migration_import_sessions")
