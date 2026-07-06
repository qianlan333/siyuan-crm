"""automation agent webhook token and editable send url.

Revision ID: 0055_automation_agent_webhook_token_and_send_url
Revises: 0054_automation_agent_runtime_config
"""

from __future__ import annotations

from alembic import op


revision = "0055_automation_agent_webhook_token_and_send_url"
down_revision = "0054_automation_agent_runtime_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE automation_agent_runtime_config
        ADD COLUMN IF NOT EXISTS inbound_webhook_token TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE automation_agent_runtime_config
        ADD COLUMN IF NOT EXISTS send_webhook_url TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        UPDATE automation_agent_runtime_config
        SET inbound_webhook_token = 'agtok_' || md5(random()::text || clock_timestamp()::text || id::text)
        WHERE inbound_webhook_token = ''
        """
    )
    op.execute(
        """
        UPDATE automation_agent_runtime_config
        SET send_webhook_url = '/api/ai/audience/packages/' || bound_package_key || '/webhook'
        WHERE send_webhook_url = ''
          AND bound_package_key <> ''
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE automation_agent_runtime_config DROP COLUMN IF EXISTS send_webhook_url")
    op.execute("ALTER TABLE automation_agent_runtime_config DROP COLUMN IF EXISTS inbound_webhook_token")
