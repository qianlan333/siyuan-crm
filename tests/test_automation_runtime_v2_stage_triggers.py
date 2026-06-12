from __future__ import annotations

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

from tests.automation_runtime_v2_test_helpers import count, seed_program, seed_task


def test_stage_triggers_fire_once_when_stage_changes(next_pg_schema):
    program_id = seed_program("runtime_v2_stage")
    seed_task(program_id, trigger_type="audience_entered", target_stage="operating", content_text="进入运营")
    seed_task(program_id, trigger_type="on_enter_stage", target_stage="converted", content_text="成交")

    first = process_event_payload(AutomationEventInput(event_type="channel_entered", source_type="test", source_id="stage-channel", program_id=program_id, external_userid="wm_stage"))
    assert first["membership"]["current_stage"] == "operating"
    assert first["counts"]["enqueued"] == 1

    unchanged = process_event_payload(AutomationEventInput(event_type="questionnaire_submitted", source_type="questionnaire", source_id="stage-sub", program_id=program_id, external_userid="wm_stage"))
    assert unchanged["stage_entry"] is None
    assert count("automation_task_plan_v2") == 1

    converted = process_event_payload(AutomationEventInput(event_type="payment_succeeded", source_type="payment", source_id="stage-pay", program_id=program_id, external_userid="wm_stage"))
    assert converted["membership"]["current_stage"] == "converted"
    assert converted["counts"]["enqueued"] == 1
