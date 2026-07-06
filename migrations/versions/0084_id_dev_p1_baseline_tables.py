"""add id-dev P1 runtime baseline tables.

Revision ID: 0084_id_dev_p1_baseline_tables
Revises: 0083_create_marketing_automation_config_tables
"""

from __future__ import annotations

from alembic import op


revision = "0084_id_dev_p1_baseline_tables"
down_revision = "0083_create_marketing_automation_config_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS outbound_tasks ADD COLUMN IF NOT EXISTS task_type TEXT NOT NULL DEFAULT 'outbound_task'")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_tool_settings (
            tool_name TEXT PRIMARY KEY,
            tool_group TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            description_override TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            visible_in_console BOOLEAN NOT NULL DEFAULT TRUE,
            show_sample_args BOOLEAN NOT NULL DEFAULT FALSE,
            show_sample_output BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mcp_tool_settings_enabled_sort ON mcp_tool_settings (enabled, sort_order, tool_name)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wechat_shop_order_events (
            id BIGSERIAL PRIMARY KEY,
            event_type TEXT NOT NULL DEFAULT '',
            order_id TEXT NOT NULL DEFAULT '',
            wechat_create_time BIGINT,
            from_user_name TEXT NOT NULL DEFAULT '',
            to_user_name TEXT NOT NULL DEFAULT '',
            raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            process_status TEXT NOT NULL DEFAULT 'received',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_wechat_shop_order_events_source
        ON wechat_shop_order_events (event_type, order_id, wechat_create_time)
        WHERE event_type <> '' AND order_id <> '' AND wechat_create_time IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_wechat_shop_order_events_order_created
        ON wechat_shop_order_events (order_id, created_at DESC, id DESC)
        WHERE order_id <> ''
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_wechat_shop_order_events_created ON wechat_shop_order_events (created_at DESC, id DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_wechat_shop_order_events_created")
    op.execute("DROP INDEX IF EXISTS ix_wechat_shop_order_events_order_created")
    op.execute("DROP INDEX IF EXISTS ux_wechat_shop_order_events_source")
    op.execute("DROP TABLE IF EXISTS wechat_shop_order_events")
    op.execute("DROP INDEX IF EXISTS ix_mcp_tool_settings_enabled_sort")
    op.execute("DROP TABLE IF EXISTS mcp_tool_settings")
    op.execute("DROP TABLE IF EXISTS app_settings")
    op.execute("ALTER TABLE IF EXISTS outbound_tasks DROP COLUMN IF EXISTS task_type")
