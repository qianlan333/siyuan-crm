#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any


QUESTIONNAIRE_ADMIN_READ_TABLES = (
    "questionnaires",
    "questionnaire_questions",
    "questionnaire_options",
    "questionnaire_score_rules",
    "questionnaire_submissions",
    "questionnaire_submission_answers",
)


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def _table_count(conn: Any, table: str) -> int:
    # Table names are fixed constants from QUESTIONNAIRE_ADMIN_READ_TABLES.
    row = conn.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    return int((row or {}).get("total") or 0)


def run_dry_run(database_url: str) -> dict[str, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - dependency availability is environment-specific
        raise RuntimeError("psycopg is required for questionnaire admin read dry-run") from exc

    with psycopg.connect(_psycopg_url(database_url), row_factory=dict_row) as conn:
        counts = {table: _table_count(conn, table) for table in QUESTIONNAIRE_ADMIN_READ_TABLES}
    return {
        "ok": True,
        "mode": "dry_run",
        "write_executed": False,
        "source_status": "next_read_model_dry_run",
        "tables": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run questionnaire admin read model readiness without writing data.")
    parser.add_argument("--database-url", required=True, help="Explicit PostgreSQL URL. Defaults are intentionally not used.")
    args = parser.parse_args()
    print(json.dumps(run_dry_run(args.database_url), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
