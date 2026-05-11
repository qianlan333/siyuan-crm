"""segments registry + campaigns + member exclusivity

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06

Adds the second-wave abstractions:

- ``segments`` — named filter view; SQL-backed; system_default | ai_generated;
  status draft/active/archived; cached headcount + sample preview
- ``segment_member_snapshots`` — periodic head/sample materialization (so
  Cloud Agent can read counts cheaply without re-running SQL)
- ``campaigns`` — multi-step engagement plan; anchor_mode = campaign_start_date
  | member_joined_at; review status pending/approved/started/paused/finished
- ``campaign_segments`` — which segments are part of this campaign + priority
  (for exclusivity tie-breaking)
- ``campaign_steps`` — per-segment sequence (day_offset, send_time,
  content_text, conditions)
- ``campaign_members`` — assignment table; UNIQUE(campaign_id, member_id) so
  any user appears at most once across all segments in one campaign — this
  is the system-level guarantee against cross-segment double-touch within
  a single campaign

All DDL uses ``IF NOT EXISTS`` so re-running on schema-bootstrapped DBs is
a no-op.
"""
from __future__ import annotations

from alembic import op


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_code TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT 'ai_generated',
            sql_query TEXT NOT NULL DEFAULT '',
            sql_params_json TEXT NOT NULL DEFAULT '{}',
            sql_dialect TEXT NOT NULL DEFAULT 'sqlite',
            status TEXT NOT NULL DEFAULT 'draft',
            version INTEGER NOT NULL DEFAULT 1,
            created_by_agent TEXT NOT NULL DEFAULT '',
            created_by_session TEXT NOT NULL DEFAULT '',
            cached_headcount INTEGER NOT NULL DEFAULT 0,
            cached_sample_json TEXT NOT NULL DEFAULT '[]',
            last_refreshed_at TEXT NOT NULL DEFAULT '',
            last_refresh_error TEXT NOT NULL DEFAULT '',
            usage_count INTEGER NOT NULL DEFAULT 0,
            tags_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_segments_status_source
        ON segments (status, source_type, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_segments_usage
        ON segments (usage_count DESC, last_refreshed_at DESC, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS segment_member_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_segment_member_snapshots_segment
        ON segment_member_snapshots (segment_id, captured_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_segment_member_snapshots_member
        ON segment_member_snapshots (member_id, captured_at DESC, id DESC)
        """
    )

    # ---------- Campaigns -----------------------------------------------

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_code TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            intent TEXT NOT NULL DEFAULT '',
            anchor_mode TEXT NOT NULL DEFAULT 'campaign_start_date',
            anchor_date TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            run_status TEXT NOT NULL DEFAULT 'draft',
            created_by_agent TEXT NOT NULL DEFAULT '',
            created_by_session TEXT NOT NULL DEFAULT '',
            trace_id TEXT NOT NULL DEFAULT '',
            owner_userid TEXT NOT NULL DEFAULT '',
            approval_token_hash TEXT NOT NULL DEFAULT '',
            approved_by TEXT NOT NULL DEFAULT '',
            approved_at TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            paused_at TEXT NOT NULL DEFAULT '',
            paused_reason TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            stats_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaigns_review
        ON campaigns (review_status, run_status, updated_at DESC, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaigns_run_status
        ON campaigns (run_status, anchor_date, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaigns_trace
        ON campaigns (trace_id, id DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            segment_id INTEGER NOT NULL,
            segment_code TEXT NOT NULL DEFAULT '',
            priority INTEGER NOT NULL DEFAULT 100,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_segments_unique
        ON campaign_segments (campaign_id, segment_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_segments_priority
        ON campaign_segments (campaign_id, priority DESC, id ASC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            campaign_segment_id INTEGER NOT NULL,
            step_index INTEGER NOT NULL DEFAULT 0,
            day_offset INTEGER NOT NULL DEFAULT 0,
            send_time TEXT NOT NULL DEFAULT '09:00',
            timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
            content_text TEXT NOT NULL DEFAULT '',
            content_payload_json TEXT NOT NULL DEFAULT '{}',
            stop_on_reply INTEGER NOT NULL DEFAULT 1,
            skip_if_recently_touched_days INTEGER NOT NULL DEFAULT 0,
            agent_run_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_steps_unique
        ON campaign_steps (campaign_segment_id, step_index)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_steps_due
        ON campaign_steps (campaign_id, day_offset ASC, step_index ASC)
        """
    )

    # 关键互斥保障表：一个 member 在一个 Campaign 里只能存在一行
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            campaign_segment_id INTEGER NOT NULL,
            segment_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            external_contact_id TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            anchor_date TEXT NOT NULL DEFAULT '',
            current_step_index INTEGER NOT NULL DEFAULT -1,
            next_due_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            stop_reason TEXT NOT NULL DEFAULT '',
            last_step_sent_at TEXT NOT NULL DEFAULT '',
            last_error_text TEXT NOT NULL DEFAULT '',
            retry_count INTEGER NOT NULL DEFAULT 0,
            trace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # ★ 系统级互斥：一个用户在同一个 Campaign 内只占一行
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_members_one_per_campaign
        ON campaign_members (campaign_id, member_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_members_due
        ON campaign_members (status, next_due_at, id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_members_segment
        ON campaign_members (campaign_segment_id, status, id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_members_external
        ON campaign_members (external_contact_id, campaign_id, id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_members_trace
        ON campaign_members (trace_id, id DESC)
        """
    )

    # 给 cloud_broadcast_plans 加 segment_id（选用） + campaign_id 关联
    bind = op.get_bind()
    if _is_postgres():
        for col_def in (
            "segment_id BIGINT",
            "campaign_id BIGINT",
        ):
            try:
                op.execute(f"ALTER TABLE cloud_broadcast_plans ADD COLUMN IF NOT EXISTS {col_def}")
            except Exception:
                pass
    else:
        from sqlalchemy import text

        for col_name, col_def in (
            ("segment_id", "segment_id INTEGER"),
            ("campaign_id", "campaign_id INTEGER"),
        ):
            rows = bind.execute(text("PRAGMA table_info(cloud_broadcast_plans)")).fetchall()
            if not any(r[1] == col_name for r in rows):
                op.execute(f"ALTER TABLE cloud_broadcast_plans ADD COLUMN {col_def}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS campaign_members")
    op.execute("DROP TABLE IF EXISTS campaign_steps")
    op.execute("DROP TABLE IF EXISTS campaign_segments")
    op.execute("DROP TABLE IF EXISTS campaigns")
    op.execute("DROP TABLE IF EXISTS segment_member_snapshots")
    op.execute("DROP TABLE IF EXISTS segments")
