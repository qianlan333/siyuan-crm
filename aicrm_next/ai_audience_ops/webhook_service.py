from __future__ import annotations

import hashlib
from typing import Any

from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WECOM_MESSAGE_PRIVATE_SEND
from aicrm_next.send_content.application import normalize_send_content_package
from aicrm_next.shared.runtime_settings import runtime_bool

from .repository import AudienceRepository, build_audience_repository, _json_dumps, _text


class AudienceInboundWebhookService:
    def __init__(
        self,
        repository: AudienceRepository | None = None,
        external_effects: ExternalEffectService | None = None,
    ):
        self._repo = repository or build_audience_repository()
        self._external_effects = external_effects or ExternalEffectService()

    def handle(self, package_key: str, payload: dict[str, Any], *, raw_body: bytes) -> dict[str, Any]:
        package = self._repo.get_package_by_key(package_key)
        if not package:
            return {"ok": False, "error": "package_not_found"}
        normalized = dict(payload or {})
        normalized["idempotency_key"] = self._idempotency_key(package, normalized)
        automation_send_plan = self._maybe_enqueue_automation_send_plan(package, normalized)
        external_effect_job_id = self._maybe_plan_action(package, normalized)
        recorded = self._repo.record_inbound_webhook(
            int(package["id"]),
            normalized,
            signature_valid=True,
            external_effect_job_id=external_effect_job_id,
        )
        return {
            "ok": True,
            "recorded": recorded,
            "automation_send_plan": automation_send_plan,
            "external_effect_job_id": external_effect_job_id,
            "record_only": external_effect_job_id is None and automation_send_plan is None,
            "real_external_call_executed": False,
        }

    def _idempotency_key(self, package: dict[str, Any], payload: dict[str, Any]) -> str:
        external_event_id = _text(payload.get("external_event_id"))
        if external_event_id:
            return f"ai_audience_inbound:{package['id']}:{external_event_id}"
        return f"ai_audience_inbound:{package['id']}:{hashlib.sha256(_json_dumps(payload).encode('utf-8')).hexdigest()}"

    def _maybe_plan_action(self, package: dict[str, Any], payload: dict[str, Any]) -> int | None:
        if not runtime_bool("AICRM_AI_AUDIENCE_INBOUND_ACTION_EXECUTE"):
            return None
        action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
        if _text(action.get("type")) != "send_private_message":
            return None
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        target = _text(action.get("target_external_userid"))
        sender = _text(action.get("sender_userid"))
        content = _text(message.get("text"))
        if not target or not sender or not content:
            return None
        job = self._external_effects.plan_effect(
            effect_type=WECOM_MESSAGE_PRIVATE_SEND,
            adapter_name="wecom_private_message",
            operation="send",
            target_type="external_user",
            target_id=target,
            payload={
                "channel": "wecom_private",
                "external_userids": [target],
                "owner_userid": sender,
                "content_text": content,
                "source": "ai_audience_inbound_webhook",
                **_test_scope(package),
            },
            payload_summary={
                "package_key": package.get("package_key"),
                "target_external_userid": target,
                "sender_userid": sender,
                "content_text_length": len(content),
            },
            business_type="ai_audience_inbound_webhook",
            business_id=_text(payload.get("external_event_id")),
            source_module="ai_audience_ops.webhook_service",
            idempotency_key=f"ai_audience_inbound_action:{package['id']}:{_text(payload.get('external_event_id'))}",
            execution_mode="execute",
            status="queued",
            context=CommandContext(actor_id="ai_audience_agent", actor_type="external_agent", source_route="ai_audience.inbound_webhook"),
        )
        return int(job.get("id") or 0) or None

    def _maybe_enqueue_automation_send_plan(self, package: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
        action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
        if _text(action.get("type")) != "enqueue_automation_send_plan":
            return None
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        content_package = message.get("content_package") if isinstance(message.get("content_package"), dict) else {}
        if not content_package:
            content_package = {"content_text": _text(message.get("text"))}
        normalized_package = normalize_send_content_package(content_package, text_enabled=True, require_body=True)
        target = _text(action.get("target_external_userid"))
        sender = _text(action.get("sender_userid"))
        external_event_id = _text(payload.get("external_event_id"))
        if not external_event_id or not target or not sender:
            return {"status": "skipped", "reason": "missing_required_action_fields"}
        from aicrm_next.cloud_orchestrator.repository import build_cloud_plan_repository

        return build_cloud_plan_repository().create_or_reuse_agent_send_plan(
            external_event_id=external_event_id,
            package_key=_text(package.get("package_key")),
            external_userid=target,
            owner_userid=sender,
            content_package=normalized_package,
            operator="automation_agent",
        )


def _test_scope(package: dict[str, Any]) -> dict[str, Any]:
    if _text(package.get("package_key")).startswith("prod_e2e_"):
        return {"is_test": True, "execution_scope": "test_loopback"}
    return {}
