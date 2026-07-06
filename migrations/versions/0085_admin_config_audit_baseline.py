"""add admin config audit baseline tables.

Revision ID: 0085_admin_config_audit_baseline
Revises: 0084_id_dev_p1_baseline_tables
"""

from __future__ import annotations

from alembic import op


revision = "0085_admin_config_audit_baseline"
down_revision = "0084_id_dev_p1_baseline_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_operation_logs (
            id BIGSERIAL PRIMARY KEY,
            operator TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            target_type TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_operation_logs_target ON admin_operation_logs (target_type, target_id, id DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_operation_logs_created ON admin_operation_logs (created_at DESC, id DESC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id BIGSERIAL PRIMARY KEY,
            wecom_userid TEXT NOT NULL DEFAULT '',
            wecom_corpid TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            auth_source TEXT NOT NULL DEFAULT 'wecom_sso',
            last_login_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT NOT NULL DEFAULT '',
            login_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            admin_level TEXT NOT NULL DEFAULT 'admin'
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_admin_users_wecom_userid ON admin_users (wecom_userid) WHERE wecom_userid <> ''")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_user_roles (
            id BIGSERIAL PRIMARY KEY,
            admin_user_id BIGINT NOT NULL DEFAULT 0,
            role_code TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_admin_user_roles_user_role ON admin_user_roles (admin_user_id, role_code)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_login_audit (
            id BIGSERIAL PRIMARY KEY,
            admin_user_id BIGINT,
            login_type TEXT NOT NULL DEFAULT '',
            login_result TEXT NOT NULL DEFAULT '',
            ip TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_login_audit_user_created ON admin_login_audit (admin_user_id, created_at DESC, id DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_admin_login_audit_user_created")
    op.execute("DROP TABLE IF EXISTS admin_login_audit")
    op.execute("DROP INDEX IF EXISTS ux_admin_user_roles_user_role")
    op.execute("DROP TABLE IF EXISTS admin_user_roles")
    op.execute("DROP INDEX IF EXISTS ux_admin_users_wecom_userid")
    op.execute("DROP TABLE IF EXISTS admin_users")
    op.execute("DROP INDEX IF EXISTS ix_admin_operation_logs_created")
    op.execute("DROP INDEX IF EXISTS ix_admin_operation_logs_target")
    op.execute("DROP TABLE IF EXISTS admin_operation_logs")
