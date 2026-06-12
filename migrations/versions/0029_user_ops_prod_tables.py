"""create User Ops production tables.

Revision ID: 0029_user_ops_prod_tables
Revises: 0028_owner_excel_sessions
"""

from __future__ import annotations

from alembic import op


revision = "0029_user_ops_prod_tables"
down_revision = "0028_owner_excel_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_ops_pool_current_next (
            id INTEGER PRIMARY KEY,
            person_id VARCHAR(80),
            mobile VARCHAR(32),
            external_userid VARCHAR(128),
            customer_name VARCHAR(255) NOT NULL DEFAULT '',
            owner_userid VARCHAR(128),
            owner_display_name VARCHAR(255) NOT NULL DEFAULT '',
            class_term_no VARCHAR(80),
            class_term_label VARCHAR(255) NOT NULL DEFAULT '',
            source_type VARCHAR(80) NOT NULL DEFAULT 'lead_pool',
            activation_bucket VARCHAR(40) NOT NULL DEFAULT 'pending_input',
            activation_bucket_label VARCHAR(80) NOT NULL DEFAULT '激活待录入',
            is_mobile_bound BOOLEAN NOT NULL DEFAULT FALSE,
            auto_do_not_disturb_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_external_userid "
        "ON user_ops_pool_current_next (external_userid)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_mobile "
        "ON user_ops_pool_current_next (mobile)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_owner_userid "
        "ON user_ops_pool_current_next (owner_userid)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_class_term_no "
        "ON user_ops_pool_current_next (class_term_no)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_pool_current_next_activation_bucket "
        "ON user_ops_pool_current_next (activation_bucket)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_ops_do_not_disturb_next (
            id BIGSERIAL PRIMARY KEY,
            external_userid VARCHAR(128),
            mobile VARCHAR(32),
            source_type VARCHAR(40) NOT NULL DEFAULT 'manual',
            reason_code VARCHAR(80) NOT NULL DEFAULT 'manual_set',
            reason_text TEXT NOT NULL DEFAULT '运营设置',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by VARCHAR(128) NOT NULL DEFAULT 'fixture-admin',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_dnd_next_external_userid "
        "ON user_ops_do_not_disturb_next (external_userid)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_dnd_next_mobile "
        "ON user_ops_do_not_disturb_next (mobile)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_dnd_next_active_reason "
        "ON user_ops_do_not_disturb_next (is_active, reason_code)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_ops_send_records_next (
            id BIGSERIAL PRIMARY KEY,
            record_key VARCHAR(80) NOT NULL UNIQUE,
            task_type VARCHAR(80) NOT NULL DEFAULT 'user_ops_batch_send',
            outbound_task_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            task_results_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_count INTEGER NOT NULL DEFAULT 0,
            eligible_count INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            skipped_reasons_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            include_do_not_disturb BOOLEAN NOT NULL DEFAULT FALSE,
            content_preview TEXT NOT NULL DEFAULT '',
            image_count INTEGER NOT NULL DEFAULT 0,
            sender_userids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            filter_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            operator VARCHAR(128) NOT NULL DEFAULT 'fixture-admin',
            status VARCHAR(40) NOT NULL DEFAULT 'created',
            status_label VARCHAR(80) NOT NULL DEFAULT '已创建任务',
            last_status_sync_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_ops_send_records_next_record_key "
        "ON user_ops_send_records_next (record_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_send_records_next_created_at "
        "ON user_ops_send_records_next (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_ops_send_records_next_status "
        "ON user_ops_send_records_next (status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_ops_send_records_next_status")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_send_records_next_created_at")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_send_records_next_record_key")
    op.execute("DROP TABLE IF EXISTS user_ops_send_records_next")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_dnd_next_active_reason")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_dnd_next_mobile")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_dnd_next_external_userid")
    op.execute("DROP TABLE IF EXISTS user_ops_do_not_disturb_next")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_pool_current_next_activation_bucket")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_pool_current_next_class_term_no")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_pool_current_next_owner_userid")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_pool_current_next_mobile")
    op.execute("DROP INDEX IF EXISTS ix_user_ops_pool_current_next_external_userid")
    op.execute("DROP TABLE IF EXISTS user_ops_pool_current_next")
