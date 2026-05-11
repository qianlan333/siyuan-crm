"""automation_member segment columns + composite index

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-06

Materializes profile/behavior segmentation results onto ``automation_member`` so
the multi-dimensional 成员运营 page can filter at SQL level instead of
recomputing per-row at render time.

- ``profile_segment_key`` — 自然画像分层 key (e.g. 职场人/创业者/老板)
- ``behavior_tier_key`` — 行为画像分层 key (e.g. msg_lt_2 / msg_2_to_9 / msg_gte_10)
- ``segment_refreshed_at`` — last refresh timestamp for traceability
- composite index ``(current_audience_code, profile_segment_key, behavior_tier_key)``

All DDL uses ``IF NOT EXISTS`` / pre-checks so re-running on a database already
initialised from ``schema.sql`` (which already includes these columns) is a no-op.
"""
from __future__ import annotations

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if _is_postgres():
        row = bind.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c",
            {"t": table, "c": column},
        ).first()
        return bool(row)
    rows = bind.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    if _is_postgres():
        for column in ("profile_segment_key", "behavior_tier_key", "segment_refreshed_at"):
            if not _has_column("automation_member", column):
                op.execute(
                    f"ALTER TABLE automation_member ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )
    else:
        for column in ("profile_segment_key", "behavior_tier_key", "segment_refreshed_at"):
            if not _has_column("automation_member", column):
                op.execute(
                    f"ALTER TABLE automation_member ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_automation_member_segments
        ON automation_member (current_audience_code, profile_segment_key, behavior_tier_key)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_automation_member_segments")
    if _is_postgres():
        op.execute("ALTER TABLE automation_member DROP COLUMN IF EXISTS segment_refreshed_at")
        op.execute("ALTER TABLE automation_member DROP COLUMN IF EXISTS behavior_tier_key")
        op.execute("ALTER TABLE automation_member DROP COLUMN IF EXISTS profile_segment_key")
