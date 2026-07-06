"""radar pdf preview assets"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0025_radar_pdf_preview_assets"
down_revision = "0024_cloud_plan_approval"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    schema = None if bind.dialect.name == "sqlite" else "public"
    return inspect(bind).has_table(table, schema=schema)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS radar_links
        ADD COLUMN IF NOT EXISTS pdf_processing_status TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS pdf_page_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS pdf_preview_error_code TEXT NOT NULL DEFAULT '',
        ADD COLUMN IF NOT EXISTS pdf_preview_error_message TEXT NOT NULL DEFAULT ''
        """
    )
    link_reference = " REFERENCES radar_links(id) ON DELETE CASCADE" if _has_table("radar_links") else ""
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS radar_pdf_preview_assets (
            id BIGSERIAL PRIMARY KEY,
            media_item_id TEXT NOT NULL,
            radar_link_id BIGINT{link_reference},
            link_id BIGINT NOT NULL{link_reference},
            source_file_hash TEXT NOT NULL DEFAULT '',
            page_no INTEGER NOT NULL,
            page_count INTEGER NOT NULL DEFAULT 0,
            preview_mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
            preview_storage_key TEXT NOT NULL DEFAULT '',
            preview_data_base64 TEXT NOT NULL DEFAULT '',
            preview_public_url TEXT NOT NULL DEFAULT '',
            width INTEGER NOT NULL DEFAULT 0,
            height INTEGER NOT NULL DEFAULT 0,
            file_size BIGINT NOT NULL DEFAULT 0,
            render_dpi INTEGER NOT NULL DEFAULT 144,
            render_quality INTEGER NOT NULL DEFAULT 82,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (link_id, media_item_id, page_no)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_radar_pdf_preview_assets_link
        ON radar_pdf_preview_assets (link_id, media_item_id, page_no)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_radar_pdf_preview_assets_link")
    op.execute("DROP TABLE IF EXISTS radar_pdf_preview_assets")
    op.execute("ALTER TABLE IF EXISTS radar_links DROP COLUMN IF EXISTS pdf_preview_error_message")
    op.execute("ALTER TABLE IF EXISTS radar_links DROP COLUMN IF EXISTS pdf_preview_error_code")
    op.execute("ALTER TABLE IF EXISTS radar_links DROP COLUMN IF EXISTS pdf_page_count")
    op.execute("ALTER TABLE IF EXISTS radar_links DROP COLUMN IF EXISTS pdf_processing_status")
