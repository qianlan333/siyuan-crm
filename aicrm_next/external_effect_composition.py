from __future__ import annotations

from .commerce.admin_transactions import apply_wechat_refund_result, mark_wechat_refund_request_failed
from .automation_agents.external_effect_continuation import AUTOMATION_AGENT_AUDIENCE_WEBHOOK_CONTINUATION
from .automation_agents.internal_webhook_adapter import AutomationAgentRoutingWebhookAdapter
from .external_push.external_effect_continuation import EXTERNAL_PUSH_DELIVERY_CONTINUATION
from .integration_gateway import (
    wechat_pay_client,
    wecom_channel_entry_client,
    wecom_group_adapter,
    wecom_private_adapter,
)
from .platform_foundation.external_effects.adapters import (
    ExternalEffectAdapterRegistry,
    WeChatPaymentAdapter,
    WeComContactTagAdapter,
    WeComGroupMessageExternalEffectAdapter,
    WeComPrivateMessageAdapter,
    WeComProfileUpdateAdapter,
    WeComWelcomeMessageAdapter,
    WebhookAdapter,
)
from .platform_foundation.external_effects.continuations import ExternalEffectContinuationRegistry
from .questionnaire.external_effect_continuation import QUESTIONNAIRE_CONTACT_TAGS_CONTINUATION


def build_external_effect_continuation_registry() -> ExternalEffectContinuationRegistry:
    return ExternalEffectContinuationRegistry(
        (
            QUESTIONNAIRE_CONTACT_TAGS_CONTINUATION,
            EXTERNAL_PUSH_DELIVERY_CONTINUATION,
            AUTOMATION_AGENT_AUDIENCE_WEBHOOK_CONTINUATION,
        )
    )


def build_external_effect_adapter_registry() -> ExternalEffectAdapterRegistry:
    provider_factory = _build_production_wecom_adapter
    generic_webhook_adapter = WebhookAdapter()
    return ExternalEffectAdapterRegistry(
        {
            "outbound_webhook": WebhookAdapter(),
            "webhook": AutomationAgentRoutingWebhookAdapter(generic_webhook_adapter),
            "wechat_payment": WeChatPaymentAdapter(
                client_factory=_build_wechat_pay_client,
                refund_result_sync=apply_wechat_refund_result,
                refund_failure_sync=mark_wechat_refund_request_failed,
            ),
            "wecom_private_message": WeComPrivateMessageAdapter(
                adapter_factory=wecom_private_adapter.build_wecom_private_message_adapter,
            ),
            "wecom_group_message": WeComGroupMessageExternalEffectAdapter(
                adapter_factory=wecom_group_adapter.build_wecom_group_message_adapter,
            ),
            "wecom_welcome_message": WeComWelcomeMessageAdapter(adapter_factory=provider_factory),
            "wecom_tag": WeComContactTagAdapter(adapter_factory=provider_factory),
            "wecom_profile": WeComProfileUpdateAdapter(adapter_factory=provider_factory),
        }
    )


def _build_production_wecom_adapter():
    missing = wecom_channel_entry_client.missing_wecom_config()
    if missing:
        raise RuntimeError("missing_wecom_config:" + ",".join(missing))
    return wecom_channel_entry_client.ProductionWeComAdapter()


def _build_wechat_pay_client():
    return wechat_pay_client.WeChatPayClient(wechat_pay_client.wechat_pay_client_config_from_env())


__all__ = [
    "build_external_effect_adapter_registry",
    "build_external_effect_continuation_registry",
]
