from __future__ import annotations

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

from tests.automation_runtime_v2_test_helpers import count, seed_program, seed_task


def test_event_triggers_channel_questionnaire_payment_and_are_idempotent(next_pg_schema):
    program_id = seed_program("runtime_v2_events")
    seed_task(program_id, trigger_type="on_event", content_text="问卷事件", agent_config={"trigger_event_type": "questionnaire_submitted"})

    channel = process_event_payload(AutomationEventInput(event_type="channel_entered", source_type="test", source_id="channel-1", program_id=program_id, external_userid="wm_event_1"))
    assert channel["membership"]["current_stage"] == "operating"

    questionnaire = process_event_payload(AutomationEventInput(event_type="questionnaire_submitted", source_type="questionnaire", source_id="sub-1", program_id=program_id, external_userid="wm_event_1", payload_json={"answers": {"layer_key": "a"}}))
    assert questionnaire["membership"]["current_stage"] == "operating"
    assert questionnaire["counts"]["enqueued"] == 1

    payment = process_event_payload(AutomationEventInput(event_type="payment_succeeded", source_type="payment", source_id="order-1", program_id=program_id, external_userid="wm_event_1"))
    assert payment["membership"]["current_stage"] == "converted"

    process_event_payload(AutomationEventInput(event_type="payment_succeeded", source_type="payment", source_id="order-1", program_id=program_id, external_userid="wm_event_1"))
    assert count("automation_event_v2") == 3
