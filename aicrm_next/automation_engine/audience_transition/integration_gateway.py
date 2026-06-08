from __future__ import annotations

from typing import Any

from .domain import AudienceTransitionEvent


class OperationTaskRealtimeTriggerGateway:
    """Boundary to the Next operation-task runtime and broadcast queue planner."""

    def trigger(self, event: AudienceTransitionEvent) -> dict[str, Any]:
        from aicrm_next.automation_engine.automation_program_admission import OperationTaskRealtimeTriggerService

        return OperationTaskRealtimeTriggerService().trigger(event)


def admit_channel_contact_to_program_with_runtime(
    *,
    program_id: int,
    channel_id: int,
    binding_id: int,
    external_contact_id: str,
    follow_user_userid: str = "",
    trigger_payload: dict[str, Any] | None = None,
    trigger_type: str = "qrcode_enter",
) -> dict[str, Any]:
    from aicrm_next.automation_engine.automation_program_admission import (
        AutomationAdmissionCommand,
        AutomationProgramAdmissionService,
    )

    return AutomationProgramAdmissionService().admit(
        AutomationAdmissionCommand(
            program_id=int(program_id),
            channel_id=int(channel_id),
            binding_id=int(binding_id),
            external_contact_id=str(external_contact_id or "").strip(),
            follow_user_userid=str(follow_user_userid or "").strip(),
            trigger_payload=dict(trigger_payload or {}),
            trigger_type=str(trigger_type or "qrcode_enter").strip() or "qrcode_enter",
        )
    )
