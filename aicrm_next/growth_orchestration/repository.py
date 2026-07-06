from __future__ import annotations

import os
from typing import Protocol

from sqlalchemy import text

from aicrm_next.shared.db_session import get_session_factory

from .dto import GrowthMember, GrowthProgram, GrowthTask, GrowthTouchpoint


class GrowthProgramRepository(Protocol):
    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]: ...

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]: ...

    def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTask]: ...

    def list_touchpoints(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTouchpoint]: ...


class EmptyGrowthProgramRepository:
    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]:
        return []

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]:
        return []

    def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTask]:
        return []

    def list_touchpoints(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTouchpoint]:
        return []


class InMemoryGrowthProgramRepository(EmptyGrowthProgramRepository):
    def __init__(
        self,
        items: list[GrowthProgram],
        members: list[GrowthMember] | None = None,
        tasks: list[GrowthTask] | None = None,
        touchpoints: list[GrowthTouchpoint] | None = None,
    ) -> None:
        self._items = list(items)
        self._members = list(members or [])
        self._tasks = list(tasks or [])
        self._touchpoints = list(touchpoints or [])

    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]:
        return self._items[offset : offset + limit]

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]:
        return self._members[offset : offset + limit]

    def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTask]:
        return self._tasks[offset : offset + limit]

    def list_touchpoints(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTouchpoint]:
        return self._touchpoints[offset : offset + limit]


class PostgresGrowthProgramRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def list_programs(self, *, limit: int = 50, offset: int = 0) -> list[GrowthProgram]:
        with self._session_factory() as session:
            rows = session.execute(text(GROWTH_PROGRAMS_SQL), {"limit": int(limit), "offset": int(offset)}).mappings().all()
        return [GrowthProgram(**dict(row)) for row in rows]

    def list_members(self, *, limit: int = 50, offset: int = 0) -> list[GrowthMember]:
        with self._session_factory() as session:
            rows = session.execute(text(GROWTH_MEMBERS_SQL), {"limit": int(limit), "offset": int(offset)}).mappings().all()
        return [GrowthMember(**dict(row)) for row in rows]

    def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTask]:
        with self._session_factory() as session:
            rows = session.execute(text(GROWTH_TASKS_SQL), {"limit": int(limit), "offset": int(offset)}).mappings().all()
        return [GrowthTask(**dict(row)) for row in rows]

    def list_touchpoints(self, *, limit: int = 50, offset: int = 0) -> list[GrowthTouchpoint]:
        with self._session_factory() as session:
            rows = session.execute(text(GROWTH_TOUCHPOINTS_SQL), {"limit": int(limit), "offset": int(offset)}).mappings().all()
        return [GrowthTouchpoint(**dict(row)) for row in rows]


def build_growth_program_repository() -> GrowthProgramRepository:
    if not str(os.getenv("DATABASE_URL") or "").strip():
        return EmptyGrowthProgramRepository()
    return PostgresGrowthProgramRepository()


GROWTH_PROGRAMS_SQL = """
WITH campaign_counts AS (
    SELECT
        campaign_id,
        COUNT(*)::int AS member_count,
        COUNT(*) FILTER (WHERE status NOT IN ('cancelled', 'failed', 'finished', 'stopped'))::int AS active_member_count,
        MAX(updated_at) AS last_member_activity_at
    FROM campaign_members
    GROUP BY campaign_id
),
campaign_task_counts AS (
    SELECT campaign_id, COUNT(*)::int AS task_count, MAX(updated_at) AS last_task_activity_at
    FROM campaign_steps
    GROUP BY campaign_id
),
group_counts AS (
    SELECT
        plan_id,
        COALESCE(SUM(internal_member_count_snapshot + external_member_count_snapshot), 0)::int AS member_count,
        COALESCE(SUM(internal_member_count_snapshot + external_member_count_snapshot) FILTER (WHERE status = 'active'), 0)::int AS active_member_count,
        MAX(COALESCE(removed_at, created_at)) AS last_member_activity_at
    FROM automation_group_ops_plan_groups
    GROUP BY plan_id
),
group_task_counts AS (
    SELECT plan_id, COUNT(*)::int AS task_count, MAX(updated_at) AS last_task_activity_at
    FROM automation_group_ops_plan_nodes
    GROUP BY plan_id
),
cloud_counts AS (
    SELECT
        plan_id,
        COUNT(*)::int AS member_count,
        COUNT(*) FILTER (WHERE send_status NOT IN ('failed', 'cancelled'))::int AS active_member_count,
        COALESCE(SUM(planned_message_count), 0)::int AS task_count,
        MAX(updated_at) AS last_activity_at
    FROM cloud_broadcast_plan_recipients
    GROUP BY plan_id
),
ai_audience_counts AS (
    SELECT
        package_id,
        COUNT(*)::int AS member_count,
        COUNT(*) FILTER (WHERE status = 'active')::int AS active_member_count,
        MAX(last_updated_at) AS last_member_activity_at
    FROM ai_audience_member_current
    GROUP BY package_id
),
programs AS (
    SELECT
        'campaign:' || c.campaign_code AS program_key,
        'campaign' AS program_type,
        COALESCE(c.display_name, '') AS title,
        COALESCE(NULLIF(c.run_status, ''), c.review_status, '') AS status,
        COALESCE(c.owner_userid, '') AS owner_userid,
        COALESCE(cc.member_count, 0)::int AS member_count,
        COALESCE(cc.active_member_count, 0)::int AS active_member_count,
        COALESCE(ct.task_count, 0)::int AS task_count,
        GREATEST(
            c.updated_at,
            COALESCE(cc.last_member_activity_at, c.updated_at),
            COALESCE(ct.last_task_activity_at, c.updated_at)
        ) AS last_activity_at,
        'campaigns' AS source_table,
        c.id::text AS source_id
    FROM campaigns c
    LEFT JOIN campaign_counts cc ON cc.campaign_id = c.id
    LEFT JOIN campaign_task_counts ct ON ct.campaign_id = c.id
    UNION ALL
    SELECT
        'group_ops:' || COALESCE(NULLIF(p.plan_code, ''), p.id::text) AS program_key,
        'group_ops' AS program_type,
        COALESCE(p.plan_name, '') AS title,
        COALESCE(p.status, '') AS status,
        COALESCE(p.owner_userid, '') AS owner_userid,
        COALESCE(gc.member_count, 0)::int AS member_count,
        COALESCE(gc.active_member_count, 0)::int AS active_member_count,
        COALESCE(gt.task_count, 0)::int AS task_count,
        GREATEST(
            p.updated_at,
            COALESCE(gc.last_member_activity_at, p.updated_at),
            COALESCE(gt.last_task_activity_at, p.updated_at)
        ) AS last_activity_at,
        'automation_group_ops_plans' AS source_table,
        p.id::text AS source_id
    FROM automation_group_ops_plans p
    LEFT JOIN group_counts gc ON gc.plan_id = p.id
    LEFT JOIN group_task_counts gt ON gt.plan_id = p.id
    WHERE p.archived_at IS NULL
    UNION ALL
    SELECT
        'cloud_plan:' || p.plan_id AS program_key,
        'cloud_plan' AS program_type,
        COALESCE(NULLIF(p.intent, ''), p.plan_id) AS title,
        COALESCE(p.status, '') AS status,
        COALESCE(p.operator, '') AS owner_userid,
        COALESCE(cc.member_count, 0)::int AS member_count,
        COALESCE(cc.active_member_count, 0)::int AS active_member_count,
        COALESCE(cc.task_count, 0)::int AS task_count,
        GREATEST(
            p.updated_at,
            COALESCE(cc.last_activity_at, p.updated_at)
        ) AS last_activity_at,
        'cloud_broadcast_plans' AS source_table,
        p.plan_id AS source_id
    FROM cloud_broadcast_plans p
    LEFT JOIN cloud_counts cc ON cc.plan_id = p.plan_id
    UNION ALL
    SELECT
        'ai_audience_package:' || p.package_key AS program_key,
        'ai_audience_package' AS program_type,
        COALESCE(p.name, '') AS title,
        COALESCE(p.status, '') AS status,
        '' AS owner_userid,
        COALESCE(aac.member_count, 0)::int AS member_count,
        COALESCE(aac.active_member_count, 0)::int AS active_member_count,
        0 AS task_count,
        GREATEST(p.updated_at, COALESCE(aac.last_member_activity_at, p.updated_at)) AS last_activity_at,
        'ai_audience_package' AS source_table,
        p.id::text AS source_id
    FROM ai_audience_package p
    LEFT JOIN ai_audience_counts aac ON aac.package_id = p.id
)
SELECT *
FROM programs
ORDER BY last_activity_at DESC NULLS LAST, program_key ASC
LIMIT :limit OFFSET :offset
"""


GROWTH_MEMBERS_SQL = """
WITH members AS (
    SELECT
        'campaign:' || c.campaign_code AS program_key,
        cm.unionid AS unionid,
        'step:' || cm.current_step_index::text AS current_stage,
        COALESCE(cm.status, '') AS status,
        COALESCE(c.owner_userid, '') AS owner_userid,
        COALESCE(cm.last_step_sent_at, cm.updated_at, cm.created_at) AS last_touch_at,
        cm.next_due_at AS next_task_at,
        'campaign_members' AS source_table,
        cm.id::text AS source_id
    FROM campaign_members cm
    JOIN campaigns c ON c.id = cm.campaign_id
    WHERE COALESCE(cm.unionid, '') <> ''
    UNION ALL
    SELECT
        'cloud_plan:' || r.plan_id AS program_key,
        r.unionid AS unionid,
        COALESCE(r.approval_status, '') AS current_stage,
        COALESCE(r.send_status, '') AS status,
        COALESCE(r.owner_userid, '') AS owner_userid,
        COALESCE(r.updated_at, r.created_at) AS last_touch_at,
        NULL::timestamptz AS next_task_at,
        'cloud_broadcast_plan_recipients' AS source_table,
        r.id::text AS source_id
    FROM cloud_broadcast_plan_recipients r
    WHERE COALESCE(r.unionid, '') <> ''
    UNION ALL
    SELECT
        'ai_audience_package:' || p.package_key AS program_key,
        m.unionid AS unionid,
        COALESCE(m.event_source_key, '') AS current_stage,
        COALESCE(m.status, '') AS status,
        COALESCE(m.owner_userid, '') AS owner_userid,
        COALESCE(m.last_seen_at, m.last_updated_at, m.updated_at, m.created_at) AS last_touch_at,
        NULL::timestamptz AS next_task_at,
        'ai_audience_member_current' AS source_table,
        m.id::text AS source_id
    FROM ai_audience_member_current m
    JOIN ai_audience_package p ON p.id = m.package_id
    WHERE COALESCE(m.unionid, '') <> ''
)
SELECT *
FROM members
ORDER BY last_touch_at DESC NULLS LAST, program_key ASC, unionid ASC
LIMIT :limit OFFSET :offset
"""


GROWTH_TASKS_SQL = """
WITH tasks AS (
    SELECT
        'broadcast_job:' || bj.id::text AS task_key,
        CASE
            WHEN bj.source_type IN ('campaign', 'cloud_plan', 'group_ops', 'ai_audience_package')
                THEN bj.source_type || ':' || bj.source_id
            WHEN COALESCE(bj.source_id, '') <> ''
                THEN 'broadcast:' || COALESCE(NULLIF(bj.source_type, ''), 'manual') || ':' || bj.source_id
            ELSE 'broadcast:' || COALESCE(NULLIF(bj.source_type, ''), 'manual') || ':' || bj.id::text
        END AS program_key,
        COALESCE(NULLIF(bj.content_type, ''), bj.source_type, 'broadcast') AS task_type,
        COALESCE(bj.status, '') AS status,
        COALESCE(bj.created_by, '') AS owner_userid,
        bj.scheduled_for AS scheduled_at,
        bj.sent_at AS completed_at,
        '' AS target_unionid,
        COALESCE(NULLIF(bj.target_count, 0), jsonb_array_length(COALESCE(bj.target_unionids_json, '[]'::jsonb)))::int AS target_count,
        COALESCE(bj.trace_id, '') AS trace_id,
        'broadcast_jobs' AS source_table,
        bj.id::text AS source_id
    FROM broadcast_jobs bj
    UNION ALL
    SELECT
        'external_effect_job:' || job.id::text AS task_key,
        CASE
            WHEN COALESCE(job.business_type, '') <> '' AND COALESCE(job.business_id, '') <> ''
                THEN job.business_type || ':' || job.business_id
            WHEN COALESCE(job.source_module, '') <> '' AND COALESCE(job.source_command_id, '') <> ''
                THEN job.source_module || ':' || job.source_command_id
            ELSE 'external_effect:' || job.id::text
        END AS program_key,
        COALESCE(NULLIF(job.operation, ''), job.effect_type, 'external_effect') AS task_type,
        COALESCE(job.status, '') AS status,
        COALESCE(job.actor_id, '') AS owner_userid,
        job.scheduled_at AS scheduled_at,
        job.executed_at AS completed_at,
        COALESCE(job.target_unionid, '') AS target_unionid,
        CASE WHEN COALESCE(job.target_unionid, '') <> '' THEN 1 ELSE 0 END AS target_count,
        COALESCE(job.trace_id, '') AS trace_id,
        'external_effect_job' AS source_table,
        job.id::text AS source_id
    FROM external_effect_job job
    UNION ALL
    SELECT
        'outbound_task:' || ot.id::text AS task_key,
        CASE
            WHEN COALESCE(ot.trace_id, '') <> '' THEN 'outbound_trace:' || ot.trace_id
            ELSE 'outbound_task:' || ot.id::text
        END AS program_key,
        COALESCE(NULLIF(ot.task_type, ''), 'outbound_task') AS task_type,
        COALESCE(ot.status, '') AS status,
        '' AS owner_userid,
        ot.created_at AS scheduled_at,
        ot.created_at AS completed_at,
        '' AS target_unionid,
        0 AS target_count,
        COALESCE(ot.trace_id, '') AS trace_id,
        'outbound_tasks' AS source_table,
        ot.id::text AS source_id
    FROM outbound_tasks ot
    WHERE NOT EXISTS (
        SELECT 1
        FROM broadcast_jobs bj
        WHERE bj.outbound_task_id = ot.id
    )
)
SELECT *
FROM tasks
ORDER BY scheduled_at DESC NULLS LAST, task_key ASC
LIMIT :limit OFFSET :offset
"""


GROWTH_TOUCHPOINTS_SQL = """
WITH touchpoints AS (
    SELECT
        'broadcast_job:' || bj.id::text AS touchpoint_key,
        CASE
            WHEN bj.source_type IN ('campaign', 'cloud_plan', 'group_ops', 'ai_audience_package')
                THEN bj.source_type || ':' || bj.source_id
            WHEN COALESCE(bj.source_id, '') <> ''
                THEN 'broadcast:' || COALESCE(NULLIF(bj.source_type, ''), 'manual') || ':' || bj.source_id
            ELSE 'broadcast:' || COALESCE(NULLIF(bj.source_type, ''), 'manual') || ':' || bj.id::text
        END AS program_key,
        '' AS unionid,
        COALESCE(NULLIF(bj.content_type, ''), bj.source_type, 'broadcast') AS touchpoint_type,
        COALESCE(bj.status, '') AS status,
        COALESCE(bj.sent_at, bj.claimed_at, bj.updated_at, bj.created_at) AS occurred_at,
        COALESCE(bj.trace_id, '') AS trace_id,
        'broadcast_jobs' AS source_table,
        bj.id::text AS source_id
    FROM broadcast_jobs bj
    UNION ALL
    SELECT
        'external_effect_job:' || job.id::text AS touchpoint_key,
        CASE
            WHEN COALESCE(job.business_type, '') <> '' AND COALESCE(job.business_id, '') <> ''
                THEN job.business_type || ':' || job.business_id
            WHEN COALESCE(job.source_module, '') <> '' AND COALESCE(job.source_command_id, '') <> ''
                THEN job.source_module || ':' || job.source_command_id
            ELSE 'external_effect:' || job.id::text
        END AS program_key,
        COALESCE(job.target_unionid, '') AS unionid,
        COALESCE(NULLIF(job.operation, ''), job.effect_type, 'external_effect') AS touchpoint_type,
        COALESCE(job.status, '') AS status,
        COALESCE(job.executed_at, job.locked_at, job.updated_at, job.created_at) AS occurred_at,
        COALESCE(job.trace_id, '') AS trace_id,
        'external_effect_job' AS source_table,
        job.id::text AS source_id
    FROM external_effect_job job
    UNION ALL
    SELECT
        'outbound_task:' || ot.id::text AS touchpoint_key,
        CASE
            WHEN COALESCE(ot.trace_id, '') <> '' THEN 'outbound_trace:' || ot.trace_id
            ELSE 'outbound_task:' || ot.id::text
        END AS program_key,
        '' AS unionid,
        COALESCE(NULLIF(ot.task_type, ''), 'outbound_task') AS touchpoint_type,
        COALESCE(ot.status, '') AS status,
        ot.created_at AS occurred_at,
        COALESCE(ot.trace_id, '') AS trace_id,
        'outbound_tasks' AS source_table,
        ot.id::text AS source_id
    FROM outbound_tasks ot
    WHERE NOT EXISTS (
        SELECT 1
        FROM broadcast_jobs bj
        WHERE bj.outbound_task_id = ot.id
    )
)
SELECT *
FROM touchpoints
ORDER BY occurred_at DESC NULLS LAST, touchpoint_key ASC
LIMIT :limit OFFSET :offset
"""
