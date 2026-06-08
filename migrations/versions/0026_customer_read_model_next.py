"""customer read model next tables"""

from __future__ import annotations

from alembic import op


revision = "0026_customer_read_model_next"
down_revision = "0025_radar_pdf_preview_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_list_index_next (
            id BIGSERIAL PRIMARY KEY,
            person_id TEXT,
            external_userid TEXT NOT NULL,
            customer_name TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            owner_display_name TEXT NOT NULL DEFAULT '',
            remark TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            mobile TEXT,
            is_bound BOOLEAN NOT NULL DEFAULT false,
            binding_status TEXT NOT NULL DEFAULT 'unbound',
            tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            class_user_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_message_at TIMESTAMPTZ,
            last_touch_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_detail_snapshot_next (
            id BIGSERIAL PRIMARY KEY,
            person_id TEXT,
            external_userid TEXT NOT NULL,
            customer_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            binding_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            follow_users_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            marketing_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            marketing_profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            contact_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            sidebar_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_timeline_event_next (
            id BIGSERIAL PRIMARY KEY,
            event_id TEXT NOT NULL,
            person_id TEXT,
            external_userid TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            source_table TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_recent_message_next (
            id BIGSERIAL PRIMARY KEY,
            msgid TEXT NOT NULL,
            external_userid TEXT NOT NULL,
            msgtype TEXT NOT NULL DEFAULT 'text',
            content TEXT NOT NULL DEFAULT '',
            send_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            owner_userid TEXT,
            chat_type TEXT NOT NULL DEFAULT 'single',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for statement in [
        "CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_external_userid ON customer_list_index_next (external_userid)",
        "CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_owner_userid ON customer_list_index_next (owner_userid)",
        "CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_mobile ON customer_list_index_next (mobile)",
        "CREATE INDEX IF NOT EXISTS ix_customer_list_index_next_updated_at ON customer_list_index_next (updated_at)",
        "CREATE INDEX IF NOT EXISTS ix_customer_detail_snapshot_next_external_userid ON customer_detail_snapshot_next (external_userid)",
        "CREATE INDEX IF NOT EXISTS ix_customer_timeline_event_next_external_userid ON customer_timeline_event_next (external_userid)",
        "CREATE INDEX IF NOT EXISTS ix_customer_timeline_event_next_event_type ON customer_timeline_event_next (event_type)",
        "CREATE INDEX IF NOT EXISTS ix_customer_timeline_event_next_event_time ON customer_timeline_event_next (event_time)",
        "CREATE INDEX IF NOT EXISTS ix_customer_recent_message_next_external_userid ON customer_recent_message_next (external_userid)",
        "CREATE INDEX IF NOT EXISTS ix_customer_recent_message_next_send_time ON customer_recent_message_next (send_time)",
    ]:
        op.execute(statement)


def downgrade() -> None:
    for index_name in [
        "ix_customer_recent_message_next_send_time",
        "ix_customer_recent_message_next_external_userid",
        "ix_customer_timeline_event_next_event_time",
        "ix_customer_timeline_event_next_event_type",
        "ix_customer_timeline_event_next_external_userid",
        "ix_customer_detail_snapshot_next_external_userid",
        "ix_customer_list_index_next_updated_at",
        "ix_customer_list_index_next_mobile",
        "ix_customer_list_index_next_owner_userid",
        "ix_customer_list_index_next_external_userid",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
    op.execute("DROP TABLE IF EXISTS customer_recent_message_next")
    op.execute("DROP TABLE IF EXISTS customer_timeline_event_next")
    op.execute("DROP TABLE IF EXISTS customer_detail_snapshot_next")
    op.execute("DROP TABLE IF EXISTS customer_list_index_next")
