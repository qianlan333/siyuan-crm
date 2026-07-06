"""create customer status baseline tables.

Revision ID: 0081_create_customer_status_baseline_tables
Revises: 0080_create_contact_tags_mirror
"""

from __future__ import annotations

from alembic import op


revision = "0081_create_customer_status_baseline_tables"
down_revision = "0080_create_contact_tags_mirror"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS class_user_status_current (
            unionid TEXT PRIMARY KEY,
            owner_userid_snapshot TEXT NOT NULL DEFAULT '',
            customer_name_snapshot TEXT NOT NULL DEFAULT '',
            signup_status TEXT NOT NULL DEFAULT '',
            signup_label_name TEXT NOT NULL DEFAULT '',
            status_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source TEXT NOT NULL DEFAULT '',
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_class_user_status_current_owner ON class_user_status_current (owner_userid_snapshot) WHERE owner_userid_snapshot <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_class_user_status_current_status ON class_user_status_current (signup_status) WHERE signup_status <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_class_user_status_current_label ON class_user_status_current (signup_label_name) WHERE signup_label_name <> ''")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS class_user_status_history (
            id BIGSERIAL PRIMARY KEY,
            unionid TEXT NOT NULL DEFAULT '',
            owner_userid_snapshot TEXT NOT NULL DEFAULT '',
            customer_name_snapshot TEXT NOT NULL DEFAULT '',
            previous_signup_status TEXT NOT NULL DEFAULT '',
            signup_status TEXT NOT NULL DEFAULT '',
            signup_label_name TEXT NOT NULL DEFAULT '',
            status_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_class_user_status_history_unionid ON class_user_status_history (unionid) WHERE unionid <> ''")
    op.execute("CREATE INDEX IF NOT EXISTS ix_class_user_status_history_created_at ON class_user_status_history (created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS owner_role_map (
            userid TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            source TEXT NOT NULL DEFAULT '',
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_owner_role_map_active ON owner_role_map (active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_owner_role_map_display_name ON owner_role_map (display_name) WHERE display_name <> ''")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS owner_role_map")
    op.execute("DROP TABLE IF EXISTS class_user_status_history")
    op.execute("DROP TABLE IF EXISTS class_user_status_current")
