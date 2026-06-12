#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

import psycopg


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


DDL = """
ALTER TABLE automation_channel
ADD COLUMN IF NOT EXISTS assignment_mode TEXT NOT NULL DEFAULT 'single_owner';

ALTER TABLE automation_channel
ADD COLUMN IF NOT EXISTS assignment_strategy TEXT NOT NULL DEFAULT 'ratio';

ALTER TABLE automation_channel
ADD COLUMN IF NOT EXISTS overflow_policy TEXT NOT NULL DEFAULT 'least_loaded';

ALTER TABLE automation_channel
ADD COLUMN IF NOT EXISTS assignment_config_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS automation_channel_assignee (
  id BIGSERIAL PRIMARY KEY,
  channel_id BIGINT NOT NULL REFERENCES automation_channel(id) ON DELETE CASCADE,
  staff_id TEXT NOT NULL,
  display_name_snapshot TEXT NOT NULL DEFAULT '',
  priority INTEGER NOT NULL DEFAULT 0,
  ratio_percent INTEGER,
  max_scans_24h INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(channel_id, staff_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_assignee_active
ON automation_channel_assignee(channel_id, status, priority, id);

CREATE TABLE IF NOT EXISTS automation_channel_assignment_event (
  id BIGSERIAL PRIMARY KEY,
  channel_id BIGINT NOT NULL REFERENCES automation_channel(id) ON DELETE CASCADE,
  assignee_staff_id TEXT NOT NULL DEFAULT '',
  strategy TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'assigned',
  external_contact_id TEXT NOT NULL DEFAULT '',
  wecom_user_id TEXT NOT NULL DEFAULT '',
  source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  converted_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_channel_assignment_24h
ON automation_channel_assignment_event(channel_id, assignee_staff_id, assigned_at DESC);

CREATE INDEX IF NOT EXISTS idx_channel_assignment_external
ON automation_channel_assignment_event(channel_id, external_contact_id);
"""


def main() -> int:
    with psycopg.connect(_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'automation_channel'
                  AND column_name IN (
                    'assignment_mode',
                    'assignment_strategy',
                    'overflow_policy',
                    'assignment_config_json'
                  )
                ORDER BY column_name
                """
            )
            columns = {row[0] for row in cur.fetchall()}
            cur.execute(
                """
                SELECT to_regclass('public.automation_channel_assignee'),
                       to_regclass('public.automation_channel_assignment_event')
                """
            )
            tables = cur.fetchone()
            cur.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE indexname IN (
                    'idx_channel_assignee_active',
                    'idx_channel_assignment_24h',
                    'idx_channel_assignment_external'
                )
                """
            )
            indexes = {row[0] for row in cur.fetchall()}
        conn.commit()

    required_columns = {
        "assignment_mode",
        "assignment_strategy",
        "overflow_policy",
        "assignment_config_json",
    }
    required_indexes = {
        "idx_channel_assignee_active",
        "idx_channel_assignment_24h",
        "idx_channel_assignment_external",
    }
    ok = (
        required_columns.issubset(columns)
        and tables == ("automation_channel_assignee", "automation_channel_assignment_event")
        and required_indexes.issubset(indexes)
    )
    print(
        {
            "ok": ok,
            "columns": sorted(columns),
            "tables": list(tables or ()),
            "indexes": sorted(indexes),
        }
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
