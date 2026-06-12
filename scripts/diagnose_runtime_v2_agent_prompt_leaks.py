#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from typing import Any


PROMPT_MARKERS = [
    "{{",
    "你将收到以下资料",
    "你的唯一任务是",
    "最终只输出",
    "不要解释",
    "不要输出 JSON",
]


def _json_default(value: Any) -> str:
    return str(value)


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print(json.dumps({"ok": False, "error": "DATABASE_URL is required"}, ensure_ascii=False))
        return 2
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"psycopg import failed: {exc}"}, ensure_ascii=False))
        return 2
    marker_sql = " OR ".join(["content_summary ILIKE %s OR content_payload::text ILIKE %s" for _ in PROMPT_MARKERS])
    params: list[str] = []
    for marker in PROMPT_MARKERS:
        params.extend([f"%{marker}%", f"%{marker}%"])
    sql = f"""
        SELECT
            id AS job_id,
            sent_at,
            target_external_userids,
            content_payload->>'sender_userid' AS sender_userid,
            content_payload->>'task_id' AS task_id,
            content_payload->>'task_plan_id' AS task_plan_id,
            outbound_task_id,
            content_summary
        FROM broadcast_jobs
        WHERE source_type = 'automation_runtime_v2'
          AND content_payload->'rendered_content'->>'type' = 'agent_generated'
          AND created_at >= NOW() - INTERVAL '24 hours'
          AND ({marker_sql})
        ORDER BY created_at DESC, id DESC
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = [dict(row) for row in cur.fetchall()]
    print(json.dumps({"ok": True, "window": "last_24_hours", "count": len(rows), "rows": rows}, ensure_ascii=False, default=_json_default, indent=2))
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
