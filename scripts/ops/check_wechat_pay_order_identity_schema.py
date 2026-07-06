#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


TARGET_COLUMNS = ("payer_openid", "mobile_snapshot", "external_userid", "userid_snapshot", "respondent_key")


def main() -> int:
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print_json({"ok": False, "error": "DATABASE_URL required", "readonly": True})
        return 2
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'wechat_pay_orders'
              AND column_name = ANY(%s)
            ORDER BY column_name
            """,
            (list(TARGET_COLUMNS),),
        )
        columns = [str(row["column_name"]) for row in cur.fetchall() or []]
    print_json(
        {
            "ok": True,
            "readonly": True,
            "table": "public.wechat_pay_orders",
            "target_columns_present": columns,
            "final_schema_0065_applied": len(columns) == 0,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
