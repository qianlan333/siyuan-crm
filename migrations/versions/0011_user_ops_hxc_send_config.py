"""user_ops_hxc_send_config — 激活漏斗看板发送人白名单.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_ops_hxc_send_config (
            id              BIGSERIAL PRIMARY KEY,
            sender_userid   TEXT NOT NULL UNIQUE,
            display_name    TEXT NOT NULL DEFAULT '',
            priority        INTEGER NOT NULL DEFAULT 100,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS user_ops_hxc_send_config")
