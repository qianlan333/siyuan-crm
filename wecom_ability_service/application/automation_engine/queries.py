from __future__ import annotations

from typing import Any

from ...domains.admin_config import service as admin_config_domain_service
from ...domains.marketing_automation import service as marketing_automation_domain_service
from ...domains.outbound_webhook import service as outbound_webhook_domain_service
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
    def __call__(
        self,
        dto: SignupConversionBatchListQueryDTO | None = None,
    ) -> SignupConversionBatchListResultDTO:
        effective_dto = dto or SignupConversionBatchListQueryDTO()
        kwargs = {
            "limit": int(effective_dto.limit),
            "cursor": str(effective_dto.cursor or ""),
        }
        if str(effective_dto.scenario_key or "").strip():
            kwargs["scenario_key"] = str(effective_dto.scenario_key or "").strip()
        return marketing_automation_domain_service.list_signup_conversion_batches(**kwargs)

    execute = __call__


class GetSignupConversionBatchQuery:
    def __call__(
        self,
        dto: SignupConversionBatchDetailQueryDTO,
    ) -> SignupConversionBatchDetailResultDTO:
        kwargs = {}
        if str(dto.scenario_key or "").strip():
            kwargs["scenario_key"] = str(dto.scenario_key or "").strip()
        return marketing_automation_domain_service.get_signup_conversion_batch(int(dto.batch_id), **kwargs)

    execute = __call__


class GetSignupConversionConfigQuery:
    def __call__(
        self,
        dto: SignupConversionConfigQueryDTO | None = None,
    ) -> SignupConversionConfigResultDTO:
        effective_dto = dto or SignupConversionConfigQueryDTO()
        kwargs = {}
        if str(effective_dto.automation_key or "").strip():
            kwargs["automation_key"] = str(effective_dto.automation_key or "").strip()
        return marketing_automation_domain_service.get_signup_conversion_config(**kwargs)

    execute = __call__


class PreviewSignupConversionCustomerQuery:
    def __call__(
        self,
        dto: SignupConversionPreviewQueryDTO,
    ) -> SignupConversionPreviewResultDTO:
        kwargs = {
            "persist": bool(dto.persist),
        }
        if str(dto.external_userid or "").strip():
            kwargs["external_userid"] = str(dto.external_userid or "").strip()
        if dto.person_id is not None:
            kwargs["person_id"] = int(dto.person_id)
        if str(dto.automation_key or "").strip():
            kwargs["automation_key"] = str(dto.automation_key or "").strip()
        return marketing_automation_domain_service.preview_signup_conversion_customer(**kwargs)

    execute = __call__


class ListAutomationConversionDispatchHistoryQuery:
    def __call__(
        self,
        *,
        status: str = "",
        limit: int = 50,
    ) -> dict[str, Any]:
        return admin_config_domain_service.list_automation_conversion_dispatch_history(
            status=str(status or "").strip(),
            limit=int(limit),
        )

    execute = __call__


class ListOutboundWebhookDeliveriesQuery:
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
        return outbound_webhook_domain_service.list_outbound_webhook_deliveries(
            event_type=str(effective_dto.event_type or "").strip(),
            status=str(effective_dto.status or "").strip(),
            limit=int(effective_dto.limit),
        )

    execute = __call__


class GetOutboundWebhookDeliveryCountsQuery:
    def __call__(
        self,
        dto: OutboundWebhookCountQueryDTO | None = None,
    ) -> OutboundWebhookCountResultDTO:
        del dto
        return outbound_webhook_domain_service.get_outbound_webhook_delivery_counts()

    execute = __call__


class GetCustomerMarketingProfileQuery:
    def __call__(
        self,
        dto: CustomerMarketingProfileQueryDTO,
    ) -> CustomerMarketingProfileResultDTO:
        kwargs = {
            "batch_context": dict(dto.batch_context or {}) if dto.batch_context else None,
        }
        if str(dto.scenario_key or "").strip():
            kwargs["scenario_key"] = str(dto.scenario_key or "").strip()
        return marketing_automation_domain_service.get_customer_marketing_profile(
            str(dto.external_userid or "").strip(),
            **kwargs,
        )

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
