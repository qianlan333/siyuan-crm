from __future__ import annotations

from typing import Any

from . import _legacy_delegate
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
    """Wave 4 automation skeleton that delegates to ``domains.outbound_webhook.service.retry_outbound_webhook_delivery`` via ``_legacy_delegate`` while legacy customer-automation callers still invoke the command with a plain delivery id."""

    def __call__(
        self,
        dto: OutboundWebhookRetryCommandDTO | int,
    ) -> OutboundWebhookRetryResultDTO:
        effective_dto = (
            dto if isinstance(dto, OutboundWebhookRetryCommandDTO) else OutboundWebhookRetryCommandDTO(delivery_id=int(dto))
        )
        return _legacy_delegate.retry_outbound_webhook_delivery_legacy(effective_dto)

    execute = __call__


class RunDueOutboundWebhookRetriesCommand:
    """Wave 4 automation skeleton that delegates to ``domains.outbound_webhook.service.run_due_outbound_webhook_retries`` via ``_legacy_delegate`` for admin jobs and customer-automation retry runners that will cut over in later PRs."""

    def __call__(
        self,
        dto: OutboundWebhookRetryBatchCommandDTO | None = None,
        *,
        limit: int = 20,
        operator: str = "",
    ) -> OutboundWebhookRetryBatchResultDTO:
        effective_dto = dto or OutboundWebhookRetryBatchCommandDTO(limit=int(limit), operator=str(operator or "").strip())
        return _legacy_delegate.run_due_outbound_webhook_retries_legacy(effective_dto)

    execute = __call__


class SyncAutomationMemberActivationCommand:
    """Wave 4 automation skeleton that delegates to ``domains.automation_conversion.service.sync_member_activation`` via ``_legacy_delegate`` for activation webhook, callback, and questionnaire bridges that will cut over later."""

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
        return _legacy_delegate.sync_automation_member_activation_legacy(effective_dto)

    execute = __call__


class HandleQrcodeEnterFromCallbackCommand:
    """Wave 4 automation skeleton that delegates to ``domains.automation_conversion.service.handle_qrcode_enter_from_callback`` via ``_legacy_delegate`` for WeCom callback/background callers that cut over in PR 3."""

    def __call__(
        self,
        *,
        external_contact_id: str,
        phone: str = "",
        payload_json: dict[str, Any] | None = None,
        operator_id: str = "",
        send_welcome_message: bool = False,
    ) -> dict[str, Any]:
        return _legacy_delegate.handle_qrcode_enter_from_callback_legacy(
            external_contact_id=str(external_contact_id or "").strip(),
            phone=str(phone or "").strip(),
            payload_json=dict(payload_json or {}),
            operator_id=str(operator_id or "").strip(),
            send_welcome_message=bool(send_welcome_message),
        )

    execute = __call__


class ApplyActivationWebhookCommand:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.apply_activation_webhook`` via ``_legacy_delegate`` and then syncs the automation member projection via ``SyncAutomationMemberActivationCommand``; later PRs will move activation callers onto this formal owner."""

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
        result = _legacy_delegate.apply_activation_webhook_legacy(effective_dto)
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
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.save_signup_conversion_config`` via ``_legacy_delegate`` for admin config callers that will cut over in PR 2."""

    def __call__(
        self,
        dto: SignupConversionConfigCommandDTO,
    ) -> SignupConversionConfigCommandResultDTO:
        return _legacy_delegate.save_signup_conversion_config_legacy(dto)

    execute = __call__


class RecomputeSignupConversionCustomersCommand:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.recompute_signup_conversion_customers`` via ``_legacy_delegate`` for admin config recompute callers that will cut over in PR 2."""

    def __call__(
        self,
        dto: SignupConversionRecomputeCommandDTO,
    ) -> SignupConversionRecomputeResultDTO:
        return _legacy_delegate.recompute_signup_conversion_customers_legacy(dto)

    execute = __call__


class RecordConversionFeedbackCommand:
    """Wave 4 automation skeleton that delegates to ``domains.tasks.service.record_conversion_feedback`` via ``_legacy_delegate`` for MCP and admin-console callers that will cut over after the formal owner is stable."""

    def __call__(
        self,
        dto: ConversionFeedbackCommandDTO,
    ) -> ConversionFeedbackResultDTO:
        return _legacy_delegate.record_conversion_feedback_legacy(dto)

    execute = __call__


class AcknowledgeConversionBatchCommand:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.ack_conversion_batch`` via ``_legacy_delegate`` for MCP and admin jobs callers that will cut over later."""

    def __call__(
        self,
        dto: ConversionBatchAckCommandDTO,
    ) -> ConversionBatchAckResultDTO:
        return _legacy_delegate.acknowledge_conversion_batch_legacy(dto)

    execute = __call__


class MarkEnrolledCommand:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.mark_enrolled`` via ``_legacy_delegate`` for sidebar, admin-support, and MCP callers that will cut over in later PRs."""

    def __call__(self, dto: MarkEnrolledCommandDTO) -> MarkEnrolledResultDTO:
        return _legacy_delegate.mark_enrolled_legacy(dto)

    execute = __call__


class UnmarkEnrolledCommand:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.unmark_enrolled`` via ``_legacy_delegate`` for sidebar, admin-support, and MCP callers that will cut over in later PRs."""

    def __call__(self, dto: UnmarkEnrolledCommandDTO) -> UnmarkEnrolledResultDTO:
        return _legacy_delegate.unmark_enrolled_legacy(dto)

    execute = __call__


class SetManualFollowupSegmentCommand:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.set_manual_followup_segment`` via ``_legacy_delegate`` for sidebar and pulse-adjacent callers that will cut over in later PRs."""

    def __call__(
        self,
        dto: ManualFollowupSegmentCommandDTO,
    ) -> ManualFollowupSegmentResultDTO:
        return _legacy_delegate.set_manual_followup_segment_legacy(dto)

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
