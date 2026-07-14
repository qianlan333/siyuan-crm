"""add questionnaire and radar runtime invariants.

Revision ID: 0102_questionnaire_radar_invariants
Revises: 0101_commerce_fulfillment_invariants
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "0102_questionnaire_radar_invariants"
down_revision = "0101_commerce_fulfillment_invariants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _questionnaire_columns()
    _radar_links_columns()
    _radar_click_events()


def _questionnaire_columns() -> None:
    statements = (
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS is_disabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS redirect_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS answer_display_mode TEXT NOT NULL DEFAULT 'all_in_one'",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS assessment_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS assessment_config JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_type TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_expires_at_ts BIGINT",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_day INTEGER",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_frequency INTEGER",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_remark TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS questionnaires ADD COLUMN IF NOT EXISTS external_push_custom_params JSONB NOT NULL DEFAULT '[]'::jsonb",
    )
    for statement in statements:
        op.execute(statement)


def _radar_links_columns() -> None:
    if not _has_table("radar_links"):
        return
    statements = (
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS original_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS preview_mode TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS file_name_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS mime_type_snapshot TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS file_size_snapshot BIGINT NOT NULL DEFAULT 0",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS pdf_processing_status TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS pdf_page_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS pdf_preview_error_code TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS pdf_preview_error_message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS auth_required BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS source_channel TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS campaign_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS staff_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS created_by TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE IF EXISTS radar_links ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
    )
    for statement in statements:
        op.execute(statement)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_radar_links_code ON radar_links (code) WHERE code <> ''")


def _radar_click_events() -> None:
    if not _has_table("radar_links"):
        return
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS radar_click_events (
            id BIGSERIAL PRIMARY KEY,
            link_id BIGINT NOT NULL REFERENCES radar_links(id) ON DELETE CASCADE,
            code TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT '',
            openid TEXT NOT NULL DEFAULT '',
            unionid TEXT NOT NULL DEFAULT '',
            external_userid TEXT NOT NULL DEFAULT '',
            target_type_snapshot TEXT NOT NULL DEFAULT '',
            person_id TEXT NOT NULL DEFAULT '',
            ip_hash TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            referer TEXT NOT NULL DEFAULT '',
            query_params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_channel TEXT NOT NULL DEFAULT '',
            campaign_id TEXT NOT NULL DEFAULT '',
            staff_id TEXT NOT NULL DEFAULT '',
            source_channel_snapshot TEXT NOT NULL DEFAULT '',
            campaign_id_snapshot TEXT NOT NULL DEFAULT '',
            staff_id_snapshot TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            ip TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = (
        "link_id BIGINT",
        "code TEXT NOT NULL DEFAULT ''",
        "stage TEXT NOT NULL DEFAULT ''",
        "openid TEXT NOT NULL DEFAULT ''",
        "unionid TEXT NOT NULL DEFAULT ''",
        "external_userid TEXT NOT NULL DEFAULT ''",
        "target_type_snapshot TEXT NOT NULL DEFAULT ''",
        "person_id TEXT NOT NULL DEFAULT ''",
        "ip_hash TEXT NOT NULL DEFAULT ''",
        "user_agent TEXT NOT NULL DEFAULT ''",
        "referer TEXT NOT NULL DEFAULT ''",
        "query_params_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "source_channel TEXT NOT NULL DEFAULT ''",
        "campaign_id TEXT NOT NULL DEFAULT ''",
        "staff_id TEXT NOT NULL DEFAULT ''",
        "source_channel_snapshot TEXT NOT NULL DEFAULT ''",
        "campaign_id_snapshot TEXT NOT NULL DEFAULT ''",
        "staff_id_snapshot TEXT NOT NULL DEFAULT ''",
        "error_code TEXT NOT NULL DEFAULT ''",
        "ip TEXT NOT NULL DEFAULT ''",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
    )
    for definition in columns:
        column_name = definition.split(" ", 1)[0]
        op.execute(f"ALTER TABLE IF EXISTS radar_click_events ADD COLUMN IF NOT EXISTS {column_name} {definition.split(' ', 1)[1]}")
    op.execute(
        """
        UPDATE radar_click_events event
        SET link_id = link.id
        FROM radar_links link
        WHERE event.link_id IS NULL
          AND event.code <> ''
          AND link.code = event.code
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'radar_click_events_link_id_fkey'
                  AND conrelid = 'radar_click_events'::regclass
            ) THEN
                ALTER TABLE radar_click_events
                ADD CONSTRAINT radar_click_events_link_id_fkey
                FOREIGN KEY (link_id) REFERENCES radar_links(id) ON DELETE CASCADE NOT VALID;
            END IF;
        END
        $$
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_radar_click_events_link_created ON radar_click_events (link_id, created_at DESC, id DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_radar_click_events_unionid_created ON radar_click_events (unionid, created_at DESC, id DESC) WHERE unionid <> ''")


def _has_table(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def downgrade() -> None:
    # Expand-only compatibility columns may predate Alembic on deployed databases.
    # A release rollback must retain them; destructive contraction requires a
    # separately proven ownership/removal window.
    op.execute("DROP INDEX IF EXISTS ix_radar_click_events_unionid_created")
    op.execute("DROP INDEX IF EXISTS ix_radar_click_events_link_created")
