from __future__ import annotations

from ...domains.admin_config import service as admin_config_domain_service
from ...domains.automation_conversion import service as automation_conversion_domain_service
from ...domains.marketing_automation import service as marketing_automation_domain_service
from ...domains.outbound_webhook import service as outbound_webhook_domain_service
from ...domains.tasks import service as tasks_domain_service
from .dto import (
    ActivationWebhookCommandDTO,
    AutomationMemberActivationCommandDTO,
    ConversionBatchAckCommandDTO,
    ConversionFeedbackCommandDTO,
    CustomerMarketingProfileQueryDTO,
    ManualFollowupSegmentCommandDTO,
    MarkEnrolledCommandDTO,
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


def list_signup_conversion_batches_legacy(dto: SignupConversionBatchListQueryDTO) -> dict:
    kwargs = {
        "limit": int(dto.limit),
        "cursor": str(dto.cursor or ""),
    }
    if str(dto.scenario_key or "").strip():
        kwargs["scenario_key"] = str(dto.scenario_key or "").strip()
    return marketing_automation_domain_service.list_signup_conversion_batches(**kwargs)


def get_signup_conversion_batch_legacy(dto: SignupConversionBatchDetailQueryDTO) -> dict | None:
    kwargs = {}
    if str(dto.scenario_key or "").strip():
        kwargs["scenario_key"] = str(dto.scenario_key or "").strip()
    return marketing_automation_domain_service.get_signup_conversion_batch(int(dto.batch_id), **kwargs)


def get_signup_conversion_config_legacy(dto: SignupConversionConfigQueryDTO) -> dict:
    kwargs = {}
    if str(dto.automation_key or "").strip():
        kwargs["automation_key"] = str(dto.automation_key or "").strip()
    return marketing_automation_domain_service.get_signup_conversion_config(**kwargs)


def list_automation_conversion_dispatch_history_legacy(*, status: str = "", limit: int = 50) -> dict:
    return admin_config_domain_service.list_automation_conversion_dispatch_history(
        status=str(status or "").strip(),
        limit=int(limit),
    )


def save_signup_conversion_config_legacy(dto: SignupConversionConfigCommandDTO) -> dict:
    kwargs = {
        "enforce_required_mobile_question": bool(dto.enforce_required_mobile_question),
    }
    if str(dto.automation_key or "").strip():
        kwargs["automation_key"] = str(dto.automation_key or "").strip()
    return marketing_automation_domain_service.save_signup_conversion_config(
        dict(dto.payload or {}),
        **kwargs,
    )


def preview_signup_conversion_customer_legacy(dto: SignupConversionPreviewQueryDTO) -> dict:
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


def recompute_signup_conversion_customers_legacy(dto: SignupConversionRecomputeCommandDTO) -> dict:
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


def list_outbound_webhook_deliveries_legacy(dto: OutboundWebhookListQueryDTO) -> dict:
    return outbound_webhook_domain_service.list_outbound_webhook_deliveries(
        event_type=str(dto.event_type or "").strip(),
        status=str(dto.status or "").strip(),
        limit=int(dto.limit),
    )


def get_outbound_webhook_delivery_counts_legacy() -> dict:
    return outbound_webhook_domain_service.get_outbound_webhook_delivery_counts()


def retry_outbound_webhook_delivery_legacy(dto: OutboundWebhookRetryCommandDTO) -> dict:
    return outbound_webhook_domain_service.retry_outbound_webhook_delivery(int(dto.delivery_id))


def run_due_outbound_webhook_retries_legacy(dto: OutboundWebhookRetryBatchCommandDTO) -> dict:
    return outbound_webhook_domain_service.run_due_outbound_webhook_retries(limit=int(dto.limit))


def sync_automation_member_activation_legacy(dto: AutomationMemberActivationCommandDTO) -> dict:
    return automation_conversion_domain_service.sync_member_activation(
        external_contact_id=str(dto.external_contact_id or "").strip(),
        phone=str(dto.phone or "").strip(),
        operator_id=str(dto.operator_id or "system"),
    )


def handle_qrcode_enter_from_callback_legacy(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
    send_welcome_message: bool = False,
) -> dict:
    return automation_conversion_domain_service.handle_qrcode_enter_from_callback(
        external_contact_id=str(external_contact_id or "").strip(),
        phone=str(phone or "").strip(),
        payload_json=dict(payload_json or {}),
        operator_id=str(operator_id or "").strip(),
        send_welcome_message=bool(send_welcome_message),
    )


def apply_activation_webhook_legacy(dto: ActivationWebhookCommandDTO) -> dict:
    return marketing_automation_domain_service.apply_activation_webhook(
        mobile=str(dto.mobile or "").strip(),
        activated_at=str(dto.activated_at or "").strip(),
        operator=str(dto.operator or "").strip(),
        source=str(dto.source or "").strip(),
    )


def record_conversion_feedback_legacy(dto: ConversionFeedbackCommandDTO) -> dict:
    return tasks_domain_service.record_conversion_feedback(
        feedback_type=str(dto.feedback_type or "").strip(),
        external_userid=str(dto.external_userid or "").strip(),
        chat_id=str(dto.chat_id or "").strip(),
        actor=str(dto.actor or "").strip(),
        feedback_payload=dict(dto.feedback_payload or {}) if dto.feedback_payload else None,
    )


def acknowledge_conversion_batch_legacy(dto: ConversionBatchAckCommandDTO) -> dict | None:
    kwargs = {
        "acked_by": str(dto.acked_by or "").strip(),
        "ack_note": str(dto.ack_note or "").strip(),
    }
    if str(dto.automation_key or "").strip():
        kwargs["automation_key"] = str(dto.automation_key or "").strip()
    return marketing_automation_domain_service.ack_conversion_batch(int(dto.batch_id), **kwargs)


def get_customer_marketing_profile_legacy(dto: CustomerMarketingProfileQueryDTO) -> dict:
    kwargs = {
        "batch_context": dict(dto.batch_context or {}) if dto.batch_context else None,
    }
    if str(dto.scenario_key or "").strip():
        kwargs["scenario_key"] = str(dto.scenario_key or "").strip()
    return marketing_automation_domain_service.get_customer_marketing_profile(
        str(dto.external_userid or "").strip(),
        **kwargs,
    )


def mark_enrolled_legacy(dto: MarkEnrolledCommandDTO) -> dict:
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


def unmark_enrolled_legacy(dto: UnmarkEnrolledCommandDTO) -> dict:
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


def set_manual_followup_segment_legacy(dto: ManualFollowupSegmentCommandDTO) -> dict:
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


__all__ = [
    "acknowledge_conversion_batch_legacy",
    "apply_activation_webhook_legacy",
    "get_customer_marketing_profile_legacy",
    "get_outbound_webhook_delivery_counts_legacy",
    "get_signup_conversion_batch_legacy",
    "get_signup_conversion_config_legacy",
    "handle_qrcode_enter_from_callback_legacy",
    "list_outbound_webhook_deliveries_legacy",
    "list_signup_conversion_batches_legacy",
    "mark_enrolled_legacy",
    "preview_signup_conversion_customer_legacy",
    "recompute_signup_conversion_customers_legacy",
    "record_conversion_feedback_legacy",
    "retry_outbound_webhook_delivery_legacy",
    "run_due_outbound_webhook_retries_legacy",
    "save_signup_conversion_config_legacy",
    "set_manual_followup_segment_legacy",
    "sync_automation_member_activation_legacy",
    "unmark_enrolled_legacy",
]
