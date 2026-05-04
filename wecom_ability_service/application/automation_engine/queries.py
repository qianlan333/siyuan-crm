from __future__ import annotations

from typing import Any

from . import _legacy_delegate
from .dto import (
    CustomerMarketingProfileQueryDTO,
    CustomerMarketingProfileResultDTO,
    OutboundWebhookCountQueryDTO,
    OutboundWebhookCountResultDTO,
    OutboundWebhookListQueryDTO,
    OutboundWebhookListResultDTO,
    SignupConversionBatchDetailQueryDTO,
    SignupConversionBatchDetailResultDTO,
    SignupConversionBatchListQueryDTO,
    SignupConversionBatchListResultDTO,
    SignupConversionConfigQueryDTO,
    SignupConversionConfigResultDTO,
    SignupConversionPreviewQueryDTO,
    SignupConversionPreviewResultDTO,
)


class ListSignupConversionBatchesQuery:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.list_signup_conversion_batches`` via ``_legacy_delegate`` for customer-automation readers and future admin callers."""

    def __call__(self, dto: SignupConversionBatchListQueryDTO | None = None) -> SignupConversionBatchListResultDTO:
        effective_dto = dto or SignupConversionBatchListQueryDTO()
        return _legacy_delegate.list_signup_conversion_batches_legacy(effective_dto)

    execute = __call__


class GetSignupConversionBatchQuery:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.get_signup_conversion_batch`` via ``_legacy_delegate`` for customer-automation readers and future retry/admin callers."""

    def __call__(self, dto: SignupConversionBatchDetailQueryDTO) -> SignupConversionBatchDetailResultDTO:
        return _legacy_delegate.get_signup_conversion_batch_legacy(dto)

    execute = __call__


class GetSignupConversionConfigQuery:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.get_signup_conversion_config`` via ``_legacy_delegate`` for admin config readers that will cut over in later PRs."""

    def __call__(
        self,
        dto: SignupConversionConfigQueryDTO | None = None,
    ) -> SignupConversionConfigResultDTO:
        return _legacy_delegate.get_signup_conversion_config_legacy(dto or SignupConversionConfigQueryDTO())

    execute = __call__


class PreviewSignupConversionCustomerQuery:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.preview_signup_conversion_customer`` via ``_legacy_delegate`` for admin config and sidebar readers that will cut over later."""

    def __call__(
        self,
        dto: SignupConversionPreviewQueryDTO,
    ) -> SignupConversionPreviewResultDTO:
        return _legacy_delegate.preview_signup_conversion_customer_legacy(dto)

    execute = __call__


class ListAutomationConversionDispatchHistoryQuery:
    """Wave 4 automation skeleton that delegates to ``domains.admin_config.service.list_automation_conversion_dispatch_history`` via ``_legacy_delegate`` for admin-config automation history readers in PR 2."""

    def __call__(
        self,
        *,
        status: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        return _legacy_delegate.list_automation_conversion_dispatch_history_legacy(
            status=str(status or "").strip(),
            limit=int(limit),
        )

    execute = __call__


class ListOutboundWebhookDeliveriesQuery:
    """Wave 4 automation skeleton that delegates to ``domains.outbound_webhook.service.list_outbound_webhook_deliveries`` via ``_legacy_delegate`` while Wave 1 callers still use the historical keyword-argument signature."""

    def __call__(
        self,
        dto: OutboundWebhookListQueryDTO | None = None,
        *,
        event_type: str = "",
        status: str = "",
        limit: int = 50,
    ) -> OutboundWebhookListResultDTO:
        effective_dto = dto or OutboundWebhookListQueryDTO(
            event_type=str(event_type or "").strip(),
            status=str(status or "").strip(),
            limit=int(limit),
        )
        return _legacy_delegate.list_outbound_webhook_deliveries_legacy(effective_dto)

    execute = __call__


class GetOutboundWebhookDeliveryCountsQuery:
    """Wave 4 automation skeleton that delegates to ``domains.outbound_webhook.service.get_outbound_webhook_delivery_counts`` via ``_legacy_delegate`` for admin jobs readers that will cut over in later PRs."""

    def __call__(
        self,
        dto: OutboundWebhookCountQueryDTO | None = None,
    ) -> OutboundWebhookCountResultDTO:
        del dto
        return _legacy_delegate.get_outbound_webhook_delivery_counts_legacy()

    execute = __call__


class GetCustomerMarketingProfileQuery:
    """Wave 4 automation skeleton that delegates to ``domains.marketing_automation.service.get_customer_marketing_profile`` via ``_legacy_delegate`` for sidebar and MCP readers that will cut over in later PRs."""

    def __call__(
        self,
        dto: CustomerMarketingProfileQueryDTO,
    ) -> CustomerMarketingProfileResultDTO:
        return _legacy_delegate.get_customer_marketing_profile_legacy(dto)

    execute = __call__


from .commands import (  # noqa: E402
    AcknowledgeConversionBatchCommand,
    ApplyActivationWebhookCommand,
    MarkEnrolledCommand,
    RecordConversionFeedbackCommand,
    RecomputeSignupConversionCustomersCommand,
    RetryOutboundWebhookDeliveryCommand,
    RunDueOutboundWebhookRetriesCommand,
    SaveSignupConversionConfigCommand,
    SetManualFollowupSegmentCommand,
    SyncAutomationMemberActivationCommand,
    UnmarkEnrolledCommand,
)


__all__ = [
    "AcknowledgeConversionBatchCommand",
    "ApplyActivationWebhookCommand",
    "GetCustomerMarketingProfileQuery",
    "GetOutboundWebhookDeliveryCountsQuery",
    "GetSignupConversionBatchQuery",
    "GetSignupConversionConfigQuery",
    "ListAutomationConversionDispatchHistoryQuery",
    "ListSignupConversionBatchesQuery",
    "ListOutboundWebhookDeliveriesQuery",
    "MarkEnrolledCommand",
    "PreviewSignupConversionCustomerQuery",
    "RecordConversionFeedbackCommand",
    "RecomputeSignupConversionCustomersCommand",
    "RunDueOutboundWebhookRetriesCommand",
    "RetryOutboundWebhookDeliveryCommand",
    "SaveSignupConversionConfigCommand",
    "SetManualFollowupSegmentCommand",
    "SyncAutomationMemberActivationCommand",
    "UnmarkEnrolledCommand",
]
