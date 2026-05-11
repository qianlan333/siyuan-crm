from __future__ import annotations

from typing import Any

from ...domains.automation_conversion import service as automation_conversion_domain_service
from ...domains.marketing_automation import service as marketing_automation_domain_service
from ...domains.outbound_webhook import service as outbound_webhook_domain_service
from ...domains.tasks import service as tasks_domain_service
from .dto import (
    ActivationWebhookCommandDTO,
    ActivationWebhookResultDTO,
    AutomationMemberActivationCommandDTO,
    AutomationMemberActivationResultDTO,
    ConversionBatchAckCommandDTO,
    ConversionBatchAckResultDTO,
    ConversionFeedbackCommandDTO,
    ConversionFeedbackResultDTO,
    ManualFollowupSegmentCommandDTO,
    ManualFollowupSegmentResultDTO,
    MarkEnrolledCommandDTO,
    MarkEnrolledResultDTO,
    OutboundWebhookRetryBatchCommandDTO,
    OutboundWebhookRetryBatchResultDTO,
    OutboundWebhookRetryCommandDTO,
    OutboundWebhookRetryResultDTO,
    SignupConversionConfigCommandDTO,
    SignupConversionConfigCommandResultDTO,
    SignupConversionRecomputeCommandDTO,
    SignupConversionRecomputeResultDTO,
    UnmarkEnrolledCommandDTO,
    UnmarkEnrolledResultDTO,
)


class RetryOutboundWebhookDeliveryCommand:
    def __call__(
        self,
        dto: OutboundWebhookRetryCommandDTO | int,
    ) -> OutboundWebhookRetryResultDTO:
        effective_dto = (
            dto if isinstance(dto, OutboundWebhookRetryCommandDTO) else OutboundWebhookRetryCommandDTO(delivery_id=int(dto))
        )
        return outbound_webhook_domain_service.retry_outbound_webhook_delivery(int(effective_dto.delivery_id))

    execute = __call__


class RunDueOutboundWebhookRetriesCommand:
    def __call__(
        self,
        dto: OutboundWebhookRetryBatchCommandDTO | None = None,
        *,
        limit: int = 20,
        operator: str = "",
    ) -> OutboundWebhookRetryBatchResultDTO:
        effective_dto = dto or OutboundWebhookRetryBatchCommandDTO(limit=int(limit), operator=str(operator or "").strip())
        return outbound_webhook_domain_service.run_due_outbound_webhook_retries(limit=int(effective_dto.limit))

    execute = __call__


class SyncAutomationMemberActivationCommand:
    def __call__(
        self,
        dto: AutomationMemberActivationCommandDTO | None = None,
        *,
        external_contact_id: str = "",
        phone: str = "",
        operator_id: str = "system",
    ) -> AutomationMemberActivationResultDTO:
        effective_dto = dto or AutomationMemberActivationCommandDTO(
            external_contact_id=str(external_contact_id or "").strip(),
            phone=str(phone or "").strip(),
            operator_id=str(operator_id or "system"),
        )
        return automation_conversion_domain_service.sync_member_activation(
            external_contact_id=str(effective_dto.external_contact_id or "").strip(),
            phone=str(effective_dto.phone or "").strip(),
            operator_id=str(effective_dto.operator_id or "system"),
        )

    execute = __call__


class HandleQrcodeEnterFromCallbackCommand:
    def __call__(
        self,
        *,
        external_contact_id: str,
        phone: str = "",
        payload_json: dict[str, Any] | None = None,
        operator_id: str = "",
        send_welcome_message: bool = False,
    ) -> dict[str, Any]:
        return automation_conversion_domain_service.handle_qrcode_enter_from_callback(
            external_contact_id=str(external_contact_id or "").strip(),
            phone=str(phone or "").strip(),
            payload_json=dict(payload_json or {}),
            operator_id=str(operator_id or "").strip(),
            send_welcome_message=bool(send_welcome_message),
        )

    execute = __call__


class ApplyActivationWebhookCommand:
    def __call__(
        self,
        dto: ActivationWebhookCommandDTO | None = None,
        *,
        mobile: str = "",
        activated_at: str = "",
        operator: str = "",
        source: str = "activation_webhook",
    ) -> ActivationWebhookResultDTO:
        effective_dto = dto or ActivationWebhookCommandDTO(
            mobile=str(mobile or "").strip(),
            activated_at=str(activated_at or "").strip(),
            operator=str(operator or "").strip(),
            source=str(source or "").strip() or "activation_webhook",
        )
        result = marketing_automation_domain_service.apply_activation_webhook(
            mobile=str(effective_dto.mobile or "").strip(),
            activated_at=str(effective_dto.activated_at or "").strip(),
            operator=str(effective_dto.operator or "").strip(),
            source=str(effective_dto.source or "").strip(),
        )
        SyncAutomationMemberActivationCommand()(
            AutomationMemberActivationCommandDTO(
                external_contact_id=str((result.get("customer") or {}).get("external_userid") or "").strip(),
                phone=str(effective_dto.mobile or "").strip(),
                operator_id=str(effective_dto.operator or "").strip() or "activation_webhook",
            )
        )
        return result

    execute = __call__


class SaveSignupConversionConfigCommand:
    def __call__(
        self,
        dto: SignupConversionConfigCommandDTO,
    ) -> SignupConversionConfigCommandResultDTO:
        kwargs = {
            "enforce_required_mobile_question": bool(dto.enforce_required_mobile_question),
        }
        if str(dto.automation_key or "").strip():
            kwargs["automation_key"] = str(dto.automation_key or "").strip()
        return marketing_automation_domain_service.save_signup_conversion_config(
            dict(dto.payload or {}),
            **kwargs,
        )

    execute = __call__


class RecomputeSignupConversionCustomersCommand:
    def __call__(
        self,
        dto: SignupConversionRecomputeCommandDTO,
    ) -> SignupConversionRecomputeResultDTO:
        kwargs = {
            "persist": bool(dto.persist),
            "external_userids": list(dto.external_userids or []),
            "person_ids": list(dto.person_ids or []),
        }
        if str(dto.external_userid or "").strip():
            kwargs["external_userid"] = str(dto.external_userid or "").strip()
        if dto.person_id is not None:
            kwargs["person_id"] = int(dto.person_id)
        if str(dto.automation_key or "").strip():
            kwargs["automation_key"] = str(dto.automation_key or "").strip()
        return marketing_automation_domain_service.recompute_signup_conversion_customers(**kwargs)

    execute = __call__


class RecordConversionFeedbackCommand:
    def __call__(
        self,
        dto: ConversionFeedbackCommandDTO,
    ) -> ConversionFeedbackResultDTO:
        return tasks_domain_service.record_conversion_feedback(
            feedback_type=str(dto.feedback_type or "").strip(),
            external_userid=str(dto.external_userid or "").strip(),
            chat_id=str(dto.chat_id or "").strip(),
            actor=str(dto.actor or "").strip(),
            feedback_payload=dict(dto.feedback_payload or {}) if dto.feedback_payload else None,
        )

    execute = __call__


class AcknowledgeConversionBatchCommand:
    def __call__(
        self,
        dto: ConversionBatchAckCommandDTO,
    ) -> ConversionBatchAckResultDTO:
        kwargs = {
            "acked_by": str(dto.acked_by or "").strip(),
            "ack_note": str(dto.ack_note or "").strip(),
        }
        if str(dto.automation_key or "").strip():
            kwargs["automation_key"] = str(dto.automation_key or "").strip()
        return marketing_automation_domain_service.ack_conversion_batch(int(dto.batch_id), **kwargs)

    execute = __call__


class MarkEnrolledCommand:
    def __call__(self, dto: MarkEnrolledCommandDTO) -> MarkEnrolledResultDTO:
        kwargs = {
            "external_userid": str(dto.external_userid or "").strip(),
            "owner_userid": str(dto.owner_userid or "").strip(),
            "operator": str(dto.operator or "").strip(),
            "source": str(dto.source or "").strip() or "manual",
        }
        if str(dto.signup_status or "").strip():
            kwargs["signup_status"] = str(dto.signup_status or "").strip()
        if str(dto.automation_key or "").strip():
            kwargs["automation_key"] = str(dto.automation_key or "").strip()
        return marketing_automation_domain_service.mark_enrolled(**kwargs)

    execute = __call__


class UnmarkEnrolledCommand:
    def __call__(self, dto: UnmarkEnrolledCommandDTO) -> UnmarkEnrolledResultDTO:
        kwargs = {
            "external_userid": str(dto.external_userid or "").strip(),
            "owner_userid": str(dto.owner_userid or "").strip(),
            "operator": str(dto.operator or "").strip(),
            "source": str(dto.source or "").strip() or "manual",
        }
        if str(dto.restore_signup_status or "").strip():
            kwargs["restore_signup_status"] = str(dto.restore_signup_status or "").strip()
        if str(dto.automation_key or "").strip():
            kwargs["automation_key"] = str(dto.automation_key or "").strip()
        return marketing_automation_domain_service.unmark_enrolled(**kwargs)

    execute = __call__


class SetManualFollowupSegmentCommand:
    def __call__(
        self,
        dto: ManualFollowupSegmentCommandDTO,
    ) -> ManualFollowupSegmentResultDTO:
        kwargs = {
            "external_userid": str(dto.external_userid or "").strip(),
            "followup_segment": str(dto.followup_segment or "").strip(),
            "owner_userid": str(dto.owner_userid or "").strip(),
            "operator": str(dto.operator or "").strip(),
            "source": str(dto.source or "").strip() or "manual",
        }
        if str(dto.automation_key or "").strip():
            kwargs["automation_key"] = str(dto.automation_key or "").strip()
        return marketing_automation_domain_service.set_manual_followup_segment(**kwargs)

    execute = __call__


__all__ = [
    "AcknowledgeConversionBatchCommand",
    "ApplyActivationWebhookCommand",
    "HandleQrcodeEnterFromCallbackCommand",
    "MarkEnrolledCommand",
    "RecordConversionFeedbackCommand",
    "RecomputeSignupConversionCustomersCommand",
    "RetryOutboundWebhookDeliveryCommand",
    "RunDueOutboundWebhookRetriesCommand",
    "SaveSignupConversionConfigCommand",
    "SetManualFollowupSegmentCommand",
    "SyncAutomationMemberActivationCommand",
    "UnmarkEnrolledCommand",
]
