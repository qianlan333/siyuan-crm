"""miniprogram library + attachments columns for broadcast/SOP

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-08

新建租户级小程序素材库 (miniprogram_library) 表，并为云编排群发计划
(cloud_broadcast_plans) 与 SOP 模板 (automation_sop_template) 增加
attachments_json / miniprograms_json 列，让 AI 群发、自动化工作流、SOP、
欢迎语、手动 user_ops 群发都能配置发送小程序卡片。

DDL 全部用 IF NOT EXISTS / 列存在性预检查，重复运行幂等。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return bool(row)


def _add_column(table: str, column_def: str, column_name: str) -> None:
    if not _has_column(table, column_name):
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS miniprogram_library (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            appid TEXT NOT NULL,
            pagepath TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            thumb_image_url TEXT NOT NULL DEFAULT '',
            thumb_image_base64 TEXT NOT NULL DEFAULT '',
            thumb_media_id TEXT NOT NULL DEFAULT '',
            thumb_media_id_expires_at TIMESTAMPTZ,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_miniprogram_library_enabled
        ON miniprogram_library (enabled, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_miniprogram_library_appid
        ON miniprogram_library (appid, id DESC)
        """
    )

    _add_column(
        "cloud_broadcast_plans",
        "attachments_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "attachments_json",
    )
    _add_column(
        "automation_sop_template",
        "miniprograms_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "miniprograms_json",
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_miniprogram_library_appid")
    op.execute("DROP INDEX IF EXISTS idx_miniprogram_library_enabled")
    op.execute("DROP TABLE IF EXISTS miniprogram_library")
    op.execute("ALTER TABLE cloud_broadcast_plans DROP COLUMN IF EXISTS attachments_json")
    op.execute("ALTER TABLE automation_sop_template DROP COLUMN IF EXISTS miniprograms_json")
