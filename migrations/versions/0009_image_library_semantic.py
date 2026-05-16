"""image_library 增加语义字段 description / tags / category / ai_metadata

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-10

为图片素材库增加 4 个语义字段，支撑后续按场景标签筛选 + 外部 Skill 通过
MCP 自动打标 / 推荐：

- ``description`` (TEXT)：图片内容 + 适用沟通场景的自然语言描述
- ``tags`` (JSONB)：自由标签数组，如 ``["好评截图","信任建立"]``
- ``category`` (TEXT)：单值大类，如 ``"好评截图"`` / ``"产品案例"``
- ``ai_metadata`` (JSONB)：AI 分析的结构化扩展信息，schema 不约束

全部 nullable / 默认空，老数据零影响。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision: str = "0009"
down_revision: str | None = "0008"
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
    _add_column("image_library", "description TEXT NOT NULL DEFAULT ''", "description")
    _add_column(
        "image_library",
        "tags JSONB NOT NULL DEFAULT '[]'::jsonb",
        "tags",
    )
    _add_column("image_library", "category TEXT NOT NULL DEFAULT ''", "category")
    _add_column(
        "image_library",
        "ai_metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ai_metadata",
    )
    # category 单列索引：UI 一级分组高频读
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_library_category "
        "ON image_library (category) WHERE category <> ''"
    )
    # tags GIN：按标签筛选用 ?| / @> 操作符
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_library_tags_gin "
        "ON image_library USING GIN (tags)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_image_library_tags_gin")
    op.execute("DROP INDEX IF EXISTS idx_image_library_category")
    op.execute("ALTER TABLE image_library DROP COLUMN IF EXISTS ai_metadata")
    op.execute("ALTER TABLE image_library DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE image_library DROP COLUMN IF EXISTS tags")
    op.execute("ALTER TABLE image_library DROP COLUMN IF EXISTS description")
