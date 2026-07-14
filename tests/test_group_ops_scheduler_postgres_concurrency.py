from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from threading import Barrier
from typing import Any

import psycopg
from psycopg.rows import dict_row

from aicrm_next.automation_engine.group_ops import scheduler


class _ConcurrentDueRepo:
    def list_plans(self, _filters: dict[str, Any]):
        return [
            {
                "id": 710,
                "plan_type": "standard",
                "status": "active",
                "owner_userid": "owner_concurrent",
                "created_at": "2026-07-12T08:00:00+08:00",
            }
        ], 1

    def list_bound_groups(self, _plan_id: int):
        return [
            {
                "chat_id": "chat_concurrent",
                "status": "active",
                "created_at": "2026-07-12T08:00:00+08:00",
            }
        ]

    def list_nodes(self, _plan_id: int):
        return [
            {
                "id": 711,
                "status": "active",
                "day_index": 1,
                "scheduled_time": "08:30",
                "action_title": "concurrent morning",
                "text_content": "concurrent hello",
                "attachments": [],
            }
        ]


def test_concurrent_group_ops_schedulers_create_exactly_one_external_effect(
    next_pg_schema,
    monkeypatch,
) -> None:
    barrier = Barrier(2)
    real_plan = scheduler.plan_group_ops_external_effect

    def synchronized_plan(**kwargs):
        barrier.wait(timeout=10)
        return real_plan(**kwargs)

    monkeypatch.setattr(scheduler, "plan_group_ops_external_effect", synchronized_plan)
    monkeypatch.setattr(scheduler, "resolve_group_ops_content_package_materials", lambda _payload: ([], []))

    def run_once(index: int):
        return scheduler.run_group_ops_due_scheduler(
            repo=_ConcurrentDueRepo(),
            now=datetime(2026, 7, 12, 1, 0, tzinfo=timezone.utc),
            operator=f"pytest-concurrent-{index}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        summaries = list(pool.map(run_once, (1, 2)))

    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT id, tenant_id, idempotency_key, effect_type, status
            FROM external_effect_job
            WHERE idempotency_key LIKE 'group_ops:710:node:711:due:%'
            """
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["tenant_id"] == "aicrm"
    assert rows[0]["effect_type"] == "wecom.message.group.send"
    assert sum(item["group_ops_external_effect_jobs"] for item in summaries) == 1
    assert sum(item["group_ops_reused_external_effect_jobs"] for item in summaries) == 1
    assert all(item["errors"] == [] for item in summaries)
