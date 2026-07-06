from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.growth_orchestration.application import (
    list_growth_members,
    list_growth_programs,
    list_growth_tasks,
    list_growth_touchpoints,
)
from aicrm_next.growth_orchestration.dto import GrowthMember, GrowthProgram, GrowthTask, GrowthTouchpoint
from aicrm_next.growth_orchestration.repository import (
    GROWTH_MEMBERS_SQL,
    GROWTH_PROGRAMS_SQL,
    GROWTH_TASKS_SQL,
    GROWTH_TOUCHPOINTS_SQL,
    InMemoryGrowthProgramRepository,
)
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_growth_orchestration_programs_api_returns_empty_without_database(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.get("/api/admin/growth-orchestration/programs")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.json() == {"ok": True, "items": [], "limit": 50, "offset": 0}

    members = client.get("/api/admin/growth-orchestration/members")
    assert members.status_code == 200
    assert members.json() == {"ok": True, "items": [], "limit": 50, "offset": 0}

    tasks = client.get("/api/admin/growth-orchestration/tasks")
    assert tasks.status_code == 200
    assert tasks.json() == {"ok": True, "items": [], "limit": 50, "offset": 0}

    touchpoints = client.get("/api/admin/growth-orchestration/touchpoints")
    assert touchpoints.status_code == 200
    assert touchpoints.json() == {"ok": True, "items": [], "limit": 50, "offset": 0}


def test_growth_orchestration_programs_application_lists_all_active_program_types() -> None:
    repo = InMemoryGrowthProgramRepository(
        [
            GrowthProgram(
                program_key="campaign:c-1",
                program_type="campaign",
                title="Campaign",
                status="running",
                owner_userid="owner-1",
                member_count=10,
                active_member_count=8,
                task_count=3,
                source_table="campaigns",
                source_id="1",
            ),
            GrowthProgram(
                program_key="group_ops:g-1",
                program_type="group_ops",
                title="Group Ops",
                status="active",
                owner_userid="owner-2",
                member_count=20,
                active_member_count=20,
                task_count=5,
                source_table="automation_group_ops_plans",
                source_id="2",
            ),
            GrowthProgram(
                program_key="cloud_plan:plan-3",
                program_type="cloud_plan",
                title="Cloud Plan",
                status="active",
                member_count=7,
                active_member_count=6,
                task_count=4,
                source_table="cloud_broadcast_plans",
                source_id="plan-3",
            ),
            GrowthProgram(
                program_key="ai_audience_package:pkg",
                program_type="ai_audience_package",
                title="AI Audience",
                status="active",
                member_count=11,
                active_member_count=10,
                source_table="ai_audience_package",
                source_id="4",
            ),
        ]
    )

    payload = list_growth_programs(repo=repo)

    assert {item["program_type"] for item in payload["items"]} == {
        "campaign",
        "group_ops",
        "cloud_plan",
        "ai_audience_package",
    }
    assert {item["source_table"] for item in payload["items"]} == {
        "campaigns",
        "automation_group_ops_plans",
        "cloud_broadcast_plans",
        "ai_audience_package",
    }


def test_growth_orchestration_members_application_is_unionid_only() -> None:
    repo = InMemoryGrowthProgramRepository(
        items=[],
        members=[
            GrowthMember(
                program_key="campaign:c-1",
                unionid="union-1",
                current_stage="step:1",
                status="pending",
                owner_userid="owner-1",
                source_table="campaign_members",
                source_id="1",
            ),
            GrowthMember(
                program_key="cloud_plan:p-1",
                unionid="union-2",
                current_stage="approved",
                status="queued",
                owner_userid="owner-2",
                source_table="cloud_broadcast_plan_recipients",
                source_id="2",
            ),
            GrowthMember(
                program_key="ai_audience_package:pkg",
                unionid="union-3",
                current_stage="refresh",
                status="active",
                owner_userid="owner-3",
                source_table="ai_audience_member_current",
                source_id="3",
            ),
        ],
    )

    payload = list_growth_members(repo=repo)

    assert [item["unionid"] for item in payload["items"]] == ["union-1", "union-2", "union-3"]
    assert {item["source_table"] for item in payload["items"]} == {
        "campaign_members",
        "cloud_broadcast_plan_recipients",
        "ai_audience_member_current",
    }


def test_growth_orchestration_tasks_and_touchpoints_use_active_execution_sources() -> None:
    repo = InMemoryGrowthProgramRepository(
        items=[],
        tasks=[
            GrowthTask(
                task_key="broadcast_job:1",
                program_key="campaign:c-1",
                task_type="text",
                status="queued",
                owner_userid="owner-1",
                target_count=3,
                trace_id="trace-1",
                source_table="broadcast_jobs",
                source_id="1",
            ),
            GrowthTask(
                task_key="external_effect_job:2",
                program_key="campaign:c-1",
                task_type="send_private_message",
                status="planned",
                target_unionid="union-1",
                target_count=1,
                trace_id="trace-2",
                source_table="external_effect_job",
                source_id="2",
            ),
            GrowthTask(
                task_key="outbound_task:3",
                program_key="outbound_trace:trace-3",
                task_type="broadcast_job/wecom_private",
                status="created",
                trace_id="trace-3",
                source_table="outbound_tasks",
                source_id="3",
            ),
        ],
        touchpoints=[
            GrowthTouchpoint(
                touchpoint_key="external_effect_job:2",
                program_key="campaign:c-1",
                unionid="union-1",
                touchpoint_type="send_private_message",
                status="succeeded",
                trace_id="trace-2",
                source_table="external_effect_job",
                source_id="2",
            )
        ],
    )

    tasks = list_growth_tasks(repo=repo)
    touchpoints = list_growth_touchpoints(repo=repo)

    assert {item["source_table"] for item in tasks["items"]} == {
        "broadcast_jobs",
        "external_effect_job",
        "outbound_tasks",
    }
    assert touchpoints["items"][0]["unionid"] == "union-1"
    assert touchpoints["items"][0]["source_table"] == "external_effect_job"


def test_growth_orchestration_program_sql_uses_only_active_unionid_safe_sources() -> None:
    assert "automation_workflow" not in GROWTH_PROGRAMS_SQL
    assert "automation_program" not in GROWTH_PROGRAMS_SQL
    assert "automation_membership_v2" not in GROWTH_PROGRAMS_SQL
    assert "automation_task_plan_v2" not in GROWTH_PROGRAMS_SQL
    assert "external_userid" not in GROWTH_PROGRAMS_SQL
    assert "cloud_broadcast_plans" in GROWTH_PROGRAMS_SQL
    assert "campaigns" in GROWTH_PROGRAMS_SQL
    assert "external_user_id" not in GROWTH_MEMBERS_SQL
    assert "external_userid" not in GROWTH_MEMBERS_SQL
    assert "automation_group_ops_plan_member" not in GROWTH_MEMBERS_SQL
    assert "automation_membership_v2" not in GROWTH_MEMBERS_SQL
    assert "automation_task_plan_v2" not in GROWTH_TASKS_SQL
    assert "automation_task_plan_v2" not in GROWTH_TOUCHPOINTS_SQL
    assert "automation_membership_v2" not in GROWTH_TASKS_SQL
    assert "automation_membership_v2" not in GROWTH_TOUCHPOINTS_SQL
    assert "external_userid" not in GROWTH_TASKS_SQL
    assert "external_userid" not in GROWTH_TOUCHPOINTS_SQL
    assert "broadcast_jobs" in GROWTH_TASKS_SQL
    assert "external_effect_job" in GROWTH_TASKS_SQL
    assert "outbound_tasks" in GROWTH_TASKS_SQL
