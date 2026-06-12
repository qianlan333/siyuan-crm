#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from typing import Any


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

    sql = """
        WITH audience_rule AS (
            SELECT DISTINCT ON (program_id)
                program_id,
                payload_json,
                COALESCE((payload_json->'questionnaire_review'->>'enabled')::boolean, FALSE) AS questionnaire_review_enabled,
                NULLIF(payload_json->'questionnaire_review'->>'selected_questionnaire_id', '')::bigint AS selected_questionnaire_id
            FROM automation_program_config_block
            WHERE block_key = 'audience_entry_rule'
            ORDER BY program_id, updated_at DESC, id DESC
        )
        SELECT
            e.id AS event_id,
            e.external_userid,
            e.program_id,
            e.binding_id,
            se.id AS stage_entry_id,
            tp.id AS task_plan_id,
            bj.id AS broadcast_job_id,
            bj.sent_at,
            tp.task_id,
            ot.task_name
        FROM automation_event_v2 e
        INNER JOIN automation_stage_entry_v2 se
            ON se.source_event_id = e.id
           AND se.stage_code = 'operating'
           AND se.entry_reason = 'channel_entered'
        INNER JOIN audience_rule ar
            ON ar.program_id = e.program_id
           AND ar.questionnaire_review_enabled = TRUE
        LEFT JOIN automation_task_plan_v2 tp
            ON tp.stage_entry_id = se.id
        LEFT JOIN automation_operation_task ot
            ON ot.id = tp.task_id
        LEFT JOIN broadcast_jobs bj
            ON bj.id = tp.broadcast_job_id
        WHERE e.event_type = 'channel_entered'
          AND e.created_at >= NOW() - INTERVAL '24 hours'
          AND NOT EXISTS (
              SELECT 1
              FROM questionnaire_submissions qs
              WHERE NULLIF(COALESCE(qs.external_userid, ''), '') = NULLIF(COALESCE(e.external_userid, ''), '')
                AND (
                    COALESCE(ar.selected_questionnaire_id, 0) <= 0
                    OR qs.questionnaire_id = ar.selected_questionnaire_id
                )
              LIMIT 1
          )
          AND NOT EXISTS (
              SELECT 1
              FROM wechat_pay_orders wo
              WHERE NULLIF(COALESCE(wo.external_userid, ''), '') = NULLIF(COALESCE(e.external_userid, ''), '')
                AND (wo.status = 'paid' OR wo.trade_state = 'SUCCESS')
              LIMIT 1
          )
        ORDER BY e.created_at DESC, e.id DESC, tp.id DESC
    """
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = [dict(row) for row in cur.fetchall()]
    print(
        json.dumps(
            {
                "ok": True,
                "window": "last_24_hours",
                "description": "channel_entered operating stage entries in questionnaire-review programs without matching questionnaire/payment evidence",
                "count": len(rows),
                "rows": rows,
            },
            ensure_ascii=False,
            default=_json_default,
            indent=2,
        )
    )
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
