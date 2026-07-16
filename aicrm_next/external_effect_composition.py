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
from .wecom_media_jobs import WeComMediaUploadAdapter
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
            "wecom_welcome_message": WeComWelcomeMessageAdapter(
                adapter_factory=provider_factory,
                material_resolver=_resolve_production_wecom_welcome_materials,
            ),
            "wecom_media_upload": WeComMediaUploadAdapter(),
            "wecom_tag": WeComContactTagAdapter(adapter_factory=provider_factory),
            "wecom_profile": WeComProfileUpdateAdapter(adapter_factory=provider_factory),
        }
    )


def _build_production_wecom_adapter():
    missing = wecom_channel_entry_client.missing_wecom_config()
    if missing:
        raise RuntimeError("missing_wecom_config:" + ",".join(missing))
    return wecom_channel_entry_client.ProductionWeComAdapter()


def _resolve_production_wecom_welcome_materials(attachments, *, resolver=None):
    if resolver is None:
        from .automation_engine.group_ops.material_resolver import PostgresGroupOpsMaterialResolver
        from .media_library.postgres_repo import PostgresMediaLibraryRepository
        from .shared.runtime import raw_database_url

        resolver = PostgresGroupOpsMaterialResolver(
            PostgresMediaLibraryRepository(raw_database_url()),
            real_upload_enabled=True,
        )

    resolved = []
    for item in list(attachments or []):
        if not isinstance(item, dict):
            raise ValueError("welcome attachments entries must be objects")
        material_id = item.get("material_id")
        if material_id in (None, ""):
            resolved.append(dict(item))
            continue
        try:
            material_id = int(material_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("welcome attachment material_id must be a positive integer") from exc
        if material_id <= 0:
            raise ValueError("welcome attachment material_id must be a positive integer")

        msgtype = str(item.get("msgtype") or "").strip().lower()
        package = {
            "image_library_ids": [material_id] if msgtype == "image" else [],
            "attachment_library_ids": [material_id] if msgtype == "file" else [],
            "miniprogram_library_ids": [material_id] if msgtype == "miniprogram" else [],
            "group_invite_library_ids": [material_id] if msgtype == "link" else [],
        }
        if msgtype not in {"image", "file", "miniprogram", "link"}:
            raise ValueError(f"unsupported welcome attachment msgtype: {msgtype or 'missing'}")
        nested_attachments, image_media_ids = resolver.resolve_content_package_materials(package)
        if msgtype == "image":
            media_id = str((image_media_ids or [""])[0] or "").strip()
            if not media_id:
                raise ValueError("welcome image material resolved without media_id")
            resolved.append({"msgtype": "image", "image": {"media_id": media_id}})
            continue

        nested = dict((nested_attachments or [{}])[0] or {})
        nested_payload = nested.get(msgtype) if isinstance(nested.get(msgtype), dict) else {}
        if msgtype == "file":
            media_id = str(nested_payload.get("media_id") or "").strip()
            if not media_id:
                raise ValueError("welcome file material resolved without media_id")
            resolved.append({"msgtype": "file", "file": {"media_id": media_id}})
            continue
        if msgtype == "link":
            title = str(nested_payload.get("title") or "").strip()
            url = str(nested_payload.get("url") or "").strip()
            if not title or not url:
                raise ValueError("welcome link material resolved with incomplete payload")
            link = {"title": title, "url": url}
            for field in ("desc", "picurl"):
                value = str(nested_payload.get(field) or "").strip()
                if value:
                    link[field] = value
            resolved.append({"msgtype": "link", "link": link})
            continue
        required = ("appid", "page", "title", "pic_media_id")
        if any(not str(nested_payload.get(field) or "").strip() for field in required):
            raise ValueError("welcome miniprogram material resolved with incomplete payload")
        resolved.append(
            {
                "msgtype": "miniprogram",
                "miniprogram": {
                    field: str(nested_payload.get(field) or "").strip()
                    for field in required
                },
            }
        )
    return resolved


def _build_wechat_pay_client():
    return wechat_pay_client.WeChatPayClient(wechat_pay_client.wechat_pay_client_config_from_env())


__all__ = [
    "build_external_effect_adapter_registry",
    "build_external_effect_continuation_registry",
]
