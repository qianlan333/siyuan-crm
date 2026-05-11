from __future__ import annotations

from wecom_ability_service import services
from wecom_ability_service.application.automation_engine import (
    AcknowledgeConversionBatchCommand,
    ApplyActivationWebhookCommand,
    GetCustomerMarketingProfileQuery,
    GetOutboundWebhookDeliveryCountsQuery,
    GetSignupConversionBatchQuery,
    GetSignupConversionConfigQuery,
    ListOutboundWebhookDeliveriesQuery,
    ListSignupConversionBatchesQuery,
    MarkEnrolledCommand,
    PreviewSignupConversionCustomerQuery,
    RecordConversionFeedbackCommand,
    RecomputeSignupConversionCustomersCommand,
    RetryOutboundWebhookDeliveryCommand,
    RunDueOutboundWebhookRetriesCommand,
    SaveSignupConversionConfigCommand,
    SetManualFollowupSegmentCommand,
    SyncAutomationMemberActivationCommand,
    UnmarkEnrolledCommand,
)
from wecom_ability_service.application.automation_engine import commands as automation_commands
from wecom_ability_service.application.automation_engine import queries as automation_queries
from wecom_ability_service.application.automation_engine.dto import (
    ActivationWebhookCommandDTO,
    ConversionBatchAckCommandDTO,
    ConversionFeedbackCommandDTO,
    CustomerMarketingProfileQueryDTO,
    ManualFollowupSegmentCommandDTO,
    MarkEnrolledCommandDTO,
    OutboundWebhookCountQueryDTO,
    OutboundWebhookListQueryDTO,
    OutboundWebhookRetryBatchCommandDTO,
    OutboundWebhookRetryCommandDTO,
    SignupConversionBatchDetailQueryDTO,
    SignupConversionBatchListQueryDTO,
    SignupConversionConfigCommandDTO,
    SignupConversionConfigQueryDTO,
    SignupConversionPreviewQueryDTO,
    SignupConversionRecomputeCommandDTO,
    UnmarkEnrolledCommandDTO,
)


def test_automation_application_api_is_importable():
    assert GetSignupConversionConfigQuery
    assert SaveSignupConversionConfigCommand
    assert PreviewSignupConversionCustomerQuery
    assert RecomputeSignupConversionCustomersCommand
    assert ListSignupConversionBatchesQuery
    assert GetSignupConversionBatchQuery
    assert GetOutboundWebhookDeliveryCountsQuery
    assert ListOutboundWebhookDeliveriesQuery
    assert RetryOutboundWebhookDeliveryCommand
    assert RunDueOutboundWebhookRetriesCommand
    assert ApplyActivationWebhookCommand
    assert SyncAutomationMemberActivationCommand
    assert RecordConversionFeedbackCommand
    assert AcknowledgeConversionBatchCommand
    assert GetCustomerMarketingProfileQuery
    assert MarkEnrolledCommand
    assert UnmarkEnrolledCommand
    assert SetManualFollowupSegmentCommand


def test_services_automation_wrappers_route_through_application(monkeypatch):
    calls: dict[str, object] = {}

    class FakeGetSignupConversionConfigQuery:
        def __call__(self, dto):
            calls["get_signup_conversion_config"] = dto
            return {"kind": "get_signup_conversion_config"}

    class FakeSaveSignupConversionConfigCommand:
        def __call__(self, dto):
            calls["save_signup_conversion_config"] = dto
            return {"kind": "save_signup_conversion_config"}

    class FakePreviewSignupConversionCustomerQuery:
        def __call__(self, dto):
            calls["preview_signup_conversion_customer"] = dto
            return {"kind": "preview_signup_conversion_customer"}

    class FakeRecomputeSignupConversionCustomersCommand:
        def __call__(self, dto):
            calls["recompute_signup_conversion_customers"] = dto
            return {"kind": "recompute_signup_conversion_customers"}

    class FakeListSignupConversionBatchesQuery:
        def __call__(self, dto):
            calls["list_signup_conversion_batches"] = dto
            return {"kind": "list_signup_conversion_batches"}

    class FakeGetSignupConversionBatchQuery:
        def __call__(self, dto):
            calls["get_signup_conversion_batch"] = dto
            return {"kind": "get_signup_conversion_batch"}

    class FakeGetOutboundWebhookDeliveryCountsQuery:
        def __call__(self, dto):
            calls["get_outbound_webhook_delivery_counts"] = dto
            return {"failed": 2}

    class FakeListOutboundWebhookDeliveriesQuery:
        def __call__(self, dto=None, **kwargs):
            calls["list_outbound_webhook_deliveries"] = dto or kwargs
            return {"kind": "list_outbound_webhook_deliveries"}

    class FakeRetryOutboundWebhookDeliveryCommand:
        def __call__(self, dto):
            calls["retry_outbound_webhook_delivery"] = dto
            return {"kind": "retry_outbound_webhook_delivery"}

    class FakeRunDueOutboundWebhookRetriesCommand:
        def __call__(self, dto=None, **kwargs):
            calls["run_due_outbound_webhook_retries"] = dto or kwargs
            return {"kind": "run_due_outbound_webhook_retries"}

    class FakeApplyActivationWebhookCommand:
        def __call__(self, dto=None, **kwargs):
            calls["apply_activation_webhook"] = dto or kwargs
            return {"kind": "apply_activation_webhook"}

    class FakeRecordConversionFeedbackCommand:
        def __call__(self, dto):
            calls["record_conversion_feedback"] = dto
            return {"kind": "record_conversion_feedback"}

    class FakeAcknowledgeConversionBatchCommand:
        def __call__(self, dto):
            calls["ack_conversion_batch"] = dto
            return {"kind": "ack_conversion_batch"}

    class FakeGetCustomerMarketingProfileQuery:
        def __call__(self, dto):
            calls["get_customer_marketing_profile"] = dto
            return {"kind": "get_customer_marketing_profile"}

    class FakeMarkEnrolledCommand:
        def __call__(self, dto):
            calls["mark_enrolled"] = dto
            return {"kind": "mark_enrolled"}

    class FakeUnmarkEnrolledCommand:
        def __call__(self, dto):
            calls["unmark_enrolled"] = dto
            return {"kind": "unmark_enrolled"}

    class FakeSetManualFollowupSegmentCommand:
        def __call__(self, dto):
            calls["set_manual_followup_segment"] = dto
            return {"kind": "set_manual_followup_segment"}

    monkeypatch.setattr(automation_queries, "GetSignupConversionConfigQuery", FakeGetSignupConversionConfigQuery)
    monkeypatch.setattr(automation_commands, "SaveSignupConversionConfigCommand", FakeSaveSignupConversionConfigCommand)
    monkeypatch.setattr(
        automation_queries,
        "PreviewSignupConversionCustomerQuery",
        FakePreviewSignupConversionCustomerQuery,
    )
    monkeypatch.setattr(
        automation_commands,
        "RecomputeSignupConversionCustomersCommand",
        FakeRecomputeSignupConversionCustomersCommand,
    )
    monkeypatch.setattr(automation_queries, "ListSignupConversionBatchesQuery", FakeListSignupConversionBatchesQuery)
    monkeypatch.setattr(automation_queries, "GetSignupConversionBatchQuery", FakeGetSignupConversionBatchQuery)
    monkeypatch.setattr(
        automation_queries,
        "GetOutboundWebhookDeliveryCountsQuery",
        FakeGetOutboundWebhookDeliveryCountsQuery,
    )
    monkeypatch.setattr(
        automation_queries,
        "ListOutboundWebhookDeliveriesQuery",
        FakeListOutboundWebhookDeliveriesQuery,
    )
    monkeypatch.setattr(
        automation_commands,
        "RetryOutboundWebhookDeliveryCommand",
        FakeRetryOutboundWebhookDeliveryCommand,
    )
    monkeypatch.setattr(
        automation_commands,
        "RunDueOutboundWebhookRetriesCommand",
        FakeRunDueOutboundWebhookRetriesCommand,
    )
    monkeypatch.setattr(automation_commands, "ApplyActivationWebhookCommand", FakeApplyActivationWebhookCommand)
    monkeypatch.setattr(automation_commands, "RecordConversionFeedbackCommand", FakeRecordConversionFeedbackCommand)
    monkeypatch.setattr(automation_commands, "AcknowledgeConversionBatchCommand", FakeAcknowledgeConversionBatchCommand)
    monkeypatch.setattr(automation_queries, "GetCustomerMarketingProfileQuery", FakeGetCustomerMarketingProfileQuery)
    monkeypatch.setattr(automation_commands, "MarkEnrolledCommand", FakeMarkEnrolledCommand)
    monkeypatch.setattr(automation_commands, "UnmarkEnrolledCommand", FakeUnmarkEnrolledCommand)
    monkeypatch.setattr(automation_commands, "SetManualFollowupSegmentCommand", FakeSetManualFollowupSegmentCommand)

    assert services.get_signup_conversion_config() == {"kind": "get_signup_conversion_config"}
    assert services.save_signup_conversion_config({"enabled": True}) == {"kind": "save_signup_conversion_config"}
    assert services.preview_signup_conversion_customer(external_userid="wm_ext_001") == {
        "kind": "preview_signup_conversion_customer"
    }
    assert services.recompute_signup_conversion_customers(external_userid="wm_ext_001") == {
        "kind": "recompute_signup_conversion_customers"
    }
    assert services.list_signup_conversion_batches(limit=10) == {"kind": "list_signup_conversion_batches"}
    assert services.get_signup_conversion_batch(9) == {"kind": "get_signup_conversion_batch"}
    assert services.get_outbound_webhook_delivery_counts() == {"failed": 2}
    assert services.list_outbound_webhook_deliveries(event_type="signup") == {
        "kind": "list_outbound_webhook_deliveries"
    }
    assert services.retry_outbound_webhook_delivery(7) == {"kind": "retry_outbound_webhook_delivery"}
    assert services.run_due_outbound_webhook_retries(limit=3) == {"kind": "run_due_outbound_webhook_retries"}
    assert services.apply_activation_webhook(mobile="13800138000") == {"kind": "apply_activation_webhook"}
    assert services.record_conversion_feedback(
        feedback_type="manual_note",
        external_userid="wm_ext_001",
    ) == {"kind": "record_conversion_feedback"}
    assert services.ack_conversion_batch(5, acked_by="openclaw") == {"kind": "ack_conversion_batch"}
    assert services.get_customer_marketing_profile("wm_ext_001") == {"kind": "get_customer_marketing_profile"}
    assert services.mark_enrolled(external_userid="wm_ext_001") == {"kind": "mark_enrolled"}
    assert services.unmark_enrolled(external_userid="wm_ext_001") == {"kind": "unmark_enrolled"}
    assert services.set_manual_followup_segment(
        external_userid="wm_ext_001",
        followup_segment="focus",
    ) == {"kind": "set_manual_followup_segment"}

    assert isinstance(calls["get_signup_conversion_config"], SignupConversionConfigQueryDTO)
    assert isinstance(calls["save_signup_conversion_config"], SignupConversionConfigCommandDTO)
    assert isinstance(calls["preview_signup_conversion_customer"], SignupConversionPreviewQueryDTO)
    assert isinstance(calls["recompute_signup_conversion_customers"], SignupConversionRecomputeCommandDTO)
    assert isinstance(calls["list_signup_conversion_batches"], SignupConversionBatchListQueryDTO)
    assert isinstance(calls["get_signup_conversion_batch"], SignupConversionBatchDetailQueryDTO)
    assert isinstance(calls["get_outbound_webhook_delivery_counts"], OutboundWebhookCountQueryDTO)
    assert isinstance(calls["list_outbound_webhook_deliveries"], OutboundWebhookListQueryDTO)
    assert isinstance(calls["retry_outbound_webhook_delivery"], OutboundWebhookRetryCommandDTO)
    assert isinstance(calls["run_due_outbound_webhook_retries"], OutboundWebhookRetryBatchCommandDTO)
    assert isinstance(calls["apply_activation_webhook"], ActivationWebhookCommandDTO)
    assert isinstance(calls["record_conversion_feedback"], ConversionFeedbackCommandDTO)
    assert isinstance(calls["ack_conversion_batch"], ConversionBatchAckCommandDTO)
    assert isinstance(calls["get_customer_marketing_profile"], CustomerMarketingProfileQueryDTO)
    assert isinstance(calls["mark_enrolled"], MarkEnrolledCommandDTO)
    assert isinstance(calls["unmark_enrolled"], UnmarkEnrolledCommandDTO)
    assert isinstance(calls["set_manual_followup_segment"], ManualFollowupSegmentCommandDTO)

