from __future__ import annotations

from aicrm_next.automation_engine.audience_transition.domain import AudienceTransitionEvent
from aicrm_next.automation_engine.audience_transition.integration_gateway import (
    OperationTaskRealtimeTriggerGateway,
    admit_channel_contact_to_program_with_runtime,
)
from aicrm_next.automation_engine.audience_transition.application import trigger_realtime_operation_tasks_for_event
from aicrm_next.automation_engine.automation_program_admission import (
    AutomationAdmissionCommand,
    AutomationProgramAdmissionService,
    OperationTaskRealtimeTriggerService,
)


def test_channel_admission_gateway_uses_next_service(monkeypatch):
    calls: list[AutomationAdmissionCommand] = []

    def fake_admit(self, command: AutomationAdmissionCommand):
        calls.append(command)
        return {
            "admission_status": "accepted",
            "source_status": "next_command",
            "fallback_used": False,
            "real_external_call_executed": False,
        }

    monkeypatch.setattr(AutomationProgramAdmissionService, "admit", fake_admit)

    result = admit_channel_contact_to_program_with_runtime(
        program_id=1,
        channel_id=2,
        binding_id=3,
        external_contact_id=" ext-1 ",
        follow_user_userid="owner-1",
        trigger_payload={"state": "qr"},
        trigger_type="qrcode_enter",
    )

    assert result == {
        "admission_status": "accepted",
        "source_status": "next_command",
        "fallback_used": False,
        "real_external_call_executed": False,
    }
    assert calls == [
        AutomationAdmissionCommand(
            program_id=1,
            channel_id=2,
            binding_id=3,
            external_contact_id="ext-1",
            follow_user_userid="owner-1",
            trigger_payload={"state": "qr"},
            trigger_type="qrcode_enter",
        )
    ]


def test_realtime_trigger_service_uses_next_runner(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_run_audience_entered_operation_tasks(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "ran": 1,
            "enqueued_count": 1,
            "source_status": "next_command",
            "fallback_used": False,
            "real_external_call_executed": False,
        }

    monkeypatch.setattr(
        "aicrm_next.automation_engine.automation_program_admission.run_audience_entered_operation_tasks",
        fake_run_audience_entered_operation_tasks,
    )

    result = OperationTaskRealtimeTriggerService().trigger(
        AudienceTransitionEvent(
            member_id=42,
            external_userid="ext-42",
            program_id=1,
            source_channel_id=2,
            audience_entry_id=77,
            audience_code="operating",
            entry_reason="audience_entry_rule_passed",
            entry_source="program_admission",
            operator_id="qrcode_enter",
        )
    )

    assert result["source_status"] == "next_command"
    assert result["fallback_used"] is False
    assert result["real_external_call_executed"] is False
    assert calls == [
        {
            "member_id": 42,
            "audience_code": "operating",
            "audience_entry_id": 77,
            "operator_id": "qrcode_enter",
            "entry_source": "program_admission",
        }
    ]


def test_realtime_gateway_uses_next_service(monkeypatch):
    event = AudienceTransitionEvent(
        member_id=51,
        external_userid="ext-51",
        program_id=5,
        source_channel_id=6,
        audience_entry_id=88,
        audience_code="operating",
        entry_reason="audience_entry_rule_passed",
        entry_source="manual_stage_change",
        operator_id="operator-1",
    )
    calls: list[AudienceTransitionEvent] = []

    def fake_trigger(self, received_event: AudienceTransitionEvent):
        calls.append(received_event)
        return {
            "ok": True,
            "ran": 1,
            "source_status": "next_command",
            "fallback_used": False,
            "real_external_call_executed": False,
        }

    monkeypatch.setattr(OperationTaskRealtimeTriggerService, "trigger", fake_trigger)

    result = OperationTaskRealtimeTriggerGateway().trigger(event)

    assert result["source_status"] == "next_command"
    assert result["fallback_used"] is False
    assert result["real_external_call_executed"] is False
    assert calls == [event]


def test_realtime_trigger_normalizer_preserves_side_effect_plan():
    event = AudienceTransitionEvent(
        member_id=52,
        external_userid="ext-52",
        program_id=5,
        source_channel_id=6,
        audience_entry_id=89,
        audience_code="operating",
        entry_reason="audience_entry_rule_passed",
        entry_source="program_admission",
        operator_id="operator-1",
    )

    class FakeGateway:
        def trigger(self, received_event: AudienceTransitionEvent):
            assert received_event == event
            return {
                "ok": True,
                "ran": 1,
                "enqueued_count": 1,
                "results": [{"task_id": 7, "enqueued_count": 1}],
                "side_effect_plan": {
                    "planned": True,
                    "effect_type": "operation_task.broadcast_job",
                    "real_external_call_executed": False,
                },
            }

    result = trigger_realtime_operation_tasks_for_event(event, gateway=FakeGateway())

    assert result["realtime_operation_tasks_ran"] == 1
    assert result["realtime_operation_tasks_enqueued_count"] == 1
    assert result["side_effect_plan"] == {
        "planned": True,
        "effect_type": "operation_task.broadcast_job",
        "real_external_call_executed": False,
    }
