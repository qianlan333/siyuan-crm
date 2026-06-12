from __future__ import annotations

from datetime import datetime, timezone

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput
from aicrm_next.automation_runtime_v2.task_adapter import get_task
from aicrm_next.automation_runtime_v2.task_planner import run_due_scheduled_tasks

from tests.automation_runtime_v2_test_helpers import count, seed_program, seed_task


def test_scheduled_daily_and_stage_day_offset_are_idempotent(next_pg_schema):
    program_id = seed_program("runtime_v2_scheduled")
    seed_task(program_id, trigger_type="scheduled_daily", target_stage="operating", content_text="每日")
    seed_task(program_id, trigger_type="scheduled", target_stage="operating", content_text="第N天", agent_config={"schedule_type": "stage_day_offset"})
    process_event_payload(AutomationEventInput(event_type="channel_entered", source_type="test", source_id="sched-channel", program_id=program_id, external_userid="wm_sched"))

    result = run_due_scheduled_tasks(program_id=program_id, now=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc))
    assert result["counts"]["planned"] == 2
    assert result["counts"]["enqueued"] == 2
    assert count("automation_task_plan_v2") == 2

    again = run_due_scheduled_tasks(program_id=program_id, now=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc))
    assert again["counts"]["planned"] == 0
    assert count("broadcast_jobs") == 2


def test_legacy_scheduled_daily_day_offset_maps_to_stage_day_offset(next_pg_schema):
    program_id = seed_program("runtime_v2_scheduled_mapping")
    task_id = seed_task(
        program_id,
        trigger_type="scheduled_daily",
        target_stage="operating",
        audience_day_offset=2,
        content_text="第2天",
    )

    task = get_task(task_id)

    assert task
    assert task["runtime_v2"]["trigger_type"] == "scheduled"
    assert task["runtime_v2"]["schedule_type"] == "stage_day_offset"
    assert task["runtime_v2"]["target_stage"] == "operating"
    assert task["runtime_v2"]["day_offset"] == 2
    assert task["runtime_v2"]["send_time"] == "10:00"


def test_scheduled_api_accepts_now_and_commits_for_cross_connection_visibility(next_pg_schema, next_client):
    program_id = seed_program("runtime_v2_scheduled_api")
    seed_task(program_id, trigger_type="scheduled_daily", target_stage="operating", content_text="每日")
    seed_task(
        program_id,
        trigger_type="scheduled_daily",
        target_stage="operating",
        audience_day_offset=2,
        content_text="第2天",
    )
    process_event_payload(
        AutomationEventInput(
            event_type="channel_entered",
            source_type="test",
            source_id="sched-api-channel",
            program_id=program_id,
            external_userid="wm_sched_api",
        )
    )

    response = next_client.post(
        "/api/automation-runtime/v2/scheduled/run-due",
        json={"program_id": program_id, "now": "2026-06-11T10:00:00+00:00"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["planned"] == 2
    assert payload["counts"]["enqueued"] == 2
    assert count("automation_task_plan_v2") == 2
    assert count("broadcast_jobs") == 2

    again = next_client.post(
        "/api/automation-runtime/v2/scheduled/run-due",
        json={"program_id": program_id, "now": "2026-06-11T10:00:00+00:00"},
    )

    assert again.status_code == 200
    assert again.json()["counts"]["planned"] == 0
    assert count("automation_task_plan_v2") == 2
    assert count("broadcast_jobs") == 2
