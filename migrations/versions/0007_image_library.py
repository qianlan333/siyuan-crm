"""image_library + 关联 miniprogram_library / campaign_steps 用上图片素材库

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-08

新建租户级图片素材库 (image_library) 表，集中管理所有"可被复用的图片"，
覆盖小程序卡片缩略图 / campaign 群发配图 / 自动化欢迎语配图等。
- ``source`` ∈ {upload, url, base64}：决定用 ``data_base64`` / ``source_url`` 哪个字段
- ``thumb_media_id`` + ``thumb_media_id_expires_at`` 缓存企微素材 id（与
  miniprogram_library 同套机制），过期重传

同时给 ``miniprogram_library`` 加 ``thumb_image_id BIGINT`` 关联到
image_library；保留旧 ``thumb_image_url`` / ``thumb_image_base64`` 字段
兼容老数据，运行期 service 层优先读 thumb_image_id 命中的素材。

DDL 全部 IF NOT EXISTS / 列存在性预检查，重复运行幂等。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision: str = "0007"
down_revision: str | None = "0006"
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
        CREATE TABLE IF NOT EXISTS image_library (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            file_name TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'upload',
            source_url TEXT NOT NULL DEFAULT '',
            data_base64 TEXT NOT NULL DEFAULT '',
            mime_type TEXT NOT NULL DEFAULT 'image/png',
            file_size INTEGER NOT NULL DEFAULT 0,
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
        CREATE INDEX IF NOT EXISTS idx_image_library_enabled
        ON image_library (enabled, updated_at DESC, id DESC)
        """
    )

    # miniprogram_library 加 thumb_image_id 关联（不强制 FK 避免删除连环约束）
    _add_column("miniprogram_library", "thumb_image_id BIGINT", "thumb_image_id")


def downgrade() -> None:
    op.execute("ALTER TABLE miniprogram_library DROP COLUMN IF EXISTS thumb_image_id")
    op.execute("DROP INDEX IF EXISTS idx_image_library_enabled")
    op.execute("DROP TABLE IF EXISTS image_library")
