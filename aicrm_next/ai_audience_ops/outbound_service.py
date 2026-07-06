from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_GENERIC_PUSH

from .repository import AudienceRepository, build_audience_repository, _text


class AudienceOutboundService:
    def __init__(
        self,
        repository: AudienceRepository | None = None,
        external_effects: ExternalEffectService | None = None,
    ):
        self._repo = repository or build_audience_repository()
        self._external_effects = external_effects or ExternalEffectService()

    def plan_for_member_event(self, member_event_id: int) -> dict[str, Any]:
        event = self._repo.get_member_event(int(member_event_id))
        if not event:
            return {"ok": False, "error": "member_event_not_found", "real_external_call_executed": False}
        run_id = int(event.get("run_id") or 0)
        if run_id > 0 and _text(event.get("event_type")) == "entered":
            return self.plan_for_run(run_id)
        package = self._repo.get_package(int(event["package_id"]))
        if not package:
            return {"ok": False, "error": "package_not_found", "real_external_call_executed": False}
        subscriptions = self._repo.list_subscriptions(
            int(package["id"]),
            active_only=True,
            trigger_event_type=_text(event.get("event_type")),
        )
        planned: list[dict[str, Any]] = []
        seen_targets: set[tuple[str, str, str]] = set()
        for subscription in subscriptions:
            if _text(subscription.get("target_type")) != "webhook":
                continue
            target_key = (
                _text(subscription.get("trigger_event_type")),
                _text(subscription.get("target_type")),
                _text(subscription.get("webhook_url")),
            )
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            payload = self._payload(package=package, member_event=event, subscription=subscription)
            target_hash = hashlib.sha256(f"{target_key[1]}:{target_key[2]}".encode("utf-8")).hexdigest()[:16]
            job = self._external_effects.plan_effect(
                effect_type=WEBHOOK_GENERIC_PUSH,
                adapter_name="webhook",
                operation="post",
                target_type="webhook",
                target_id=str(subscription["id"]),
                payload=payload,
                payload_summary={
                    "package_key": package.get("package_key"),
                    "member_event_id": int(event["id"]),
                    "trigger_event_type": event.get("event_type"),
                    "webhook_url_present": bool(subscription.get("webhook_url")),
                },
                business_type="ai_audience_member_event",
                business_id=str(event["id"]),
                source_module="ai_audience_ops.outbound_service",
                source_event_id=_text(event.get("internal_event_id")),
                risk_level="medium",
                requires_approval=bool(subscription.get("requires_approval")),
                execution_mode=_text(subscription.get("execution_mode")) or "execute",
                max_attempts=int(subscription.get("max_attempts") or 5),
                idempotency_key=f"ai_audience_outbound:{package['id']}:{event['id']}:{event.get('event_type')}:{target_hash}",
                status="queued",
                context=CommandContext(
                    actor_id="ai_audience_outbound",
                    actor_type="system",
                    source_route="ai_audience.member_event",
                    request_id=str(event["id"]),
                ),
            )
            planned.append(job)
        return {
            "ok": True,
            "member_event_id": int(event["id"]),
            "planned_count": len(planned),
            "external_effect_jobs": planned,
            "real_external_call_executed": False,
        }

    def plan_for_run(self, run_id: int) -> dict[str, Any]:
        entered_events = self._repo.list_member_events_for_run(int(run_id), event_type="entered")
        if not entered_events:
            return {"ok": True, "run_id": int(run_id), "planned_count": 0, "external_effect_jobs": [], "real_external_call_executed": False}
        package_id = int(entered_events[0]["package_id"])
        package = self._repo.get_package(package_id)
        if not package:
            return {"ok": False, "error": "package_not_found", "real_external_call_executed": False}
        subscriptions = self._repo.list_subscriptions(
            package_id,
            active_only=True,
            trigger_event_type="entered",
        )
        external_userids = sorted({_text(event.get("external_userid")) for event in entered_events if _text(event.get("external_userid"))})
        planned: list[dict[str, Any]] = []
        seen_targets: set[tuple[str, str, str]] = set()
        for subscription in subscriptions:
            if _text(subscription.get("target_type")) != "webhook":
                continue
            target_key = (
                "entered",
                _text(subscription.get("target_type")),
                _text(subscription.get("webhook_url")),
            )
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            target_hash = hashlib.sha256(f"{target_key[1]}:{target_key[2]}".encode("utf-8")).hexdigest()[:16]
            idempotency_key = f"ai_audience_outbound_run:{package_id}:{int(run_id)}:entered:{target_hash}"
            payload = self._run_payload(
                package=package,
                run_id=int(run_id),
                external_userids=external_userids,
                subscription=subscription,
                idempotency_key=idempotency_key,
            )
            job = self._external_effects.plan_effect(
                effect_type=WEBHOOK_GENERIC_PUSH,
                adapter_name="webhook",
                operation="post",
                target_type="webhook",
                target_id=str(subscription["id"]),
                payload=payload,
                payload_summary={
                    "package_key": package.get("package_key"),
                    "run_id": int(run_id),
                    "trigger_event_type": "entered",
                    "external_userid_count": len(external_userids),
                    "webhook_url_present": bool(subscription.get("webhook_url")),
                },
                business_type="ai_audience_package_run",
                business_id=str(run_id),
                source_module="ai_audience_ops.outbound_service",
                source_event_id="",
                risk_level="medium",
                requires_approval=bool(subscription.get("requires_approval")),
                execution_mode=_text(subscription.get("execution_mode")) or "execute",
                max_attempts=int(subscription.get("max_attempts") or 5),
                idempotency_key=idempotency_key,
                status="queued",
                context=CommandContext(
                    actor_id="ai_audience_outbound",
                    actor_type="system",
                    source_route="ai_audience.refresh_run",
                    request_id=str(run_id),
                ),
            )
            planned.append(job)
        return {
            "ok": True,
            "run_id": int(run_id),
            "planned_count": len(planned),
            "external_effect_jobs": planned,
            "real_external_call_executed": False,
        }

    def _payload(self, *, package: dict[str, Any], member_event: dict[str, Any], subscription: dict[str, Any]) -> dict[str, Any]:
        member = {
            "identity_type": member_event.get("identity_type"),
            "identity_value": member_event.get("identity_value"),
            "person_id": member_event.get("person_id"),
            "external_userid": member_event.get("external_userid"),
            "mobile_hash": member_event.get("mobile_hash"),
            "owner_userid": member_event.get("owner_userid"),
        }
        body = {
            "event_type": f"audience.member.{member_event.get('event_type')}",
            "package_key": package.get("package_key"),
            "package_name": package.get("name"),
            "member_event_id": int(member_event["id"]),
            "member": member,
            "payload": member_event.get("payload_json") or {},
            "idempotency_key": member_event.get("idempotency_key"),
        }
        headers = subscription.get("headers_json") if isinstance(subscription.get("headers_json"), dict) else {}
        return {
            "webhook_url": subscription.get("webhook_url"),
            "signing_secret": subscription.get("signing_secret"),
            "headers": headers,
            "body": body,
        }

    def _run_payload(
        self,
        *,
        package: dict[str, Any],
        run_id: int,
        external_userids: list[str],
        subscription: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        body = list(external_userids)
        secret = _text(subscription.get("signing_secret"))
        headers = {
            "X-AICRM-Package-Key": _text(package.get("package_key")),
            "X-AICRM-Event-Type": "audience.incremental.entered",
            "X-AICRM-Refresh-Run-Id": str(int(run_id)),
            "X-AICRM-Idempotency-Key": idempotency_key,
        }
        if secret:
            headers["X-AICRM-Signature"] = _signature(secret, body)
        return {
            "webhook_url": subscription.get("webhook_url"),
            "signing_secret": secret,
            "headers": headers,
            "body": body,
            **_test_scope(package),
        }


def _signature(secret: str, body: list[str]) -> str:
    canonical_body = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode("utf-8"), canonical_body.encode("utf-8"), hashlib.sha256).hexdigest()


def _test_scope(package: dict[str, Any]) -> dict[str, Any]:
    package_key = _text(package.get("package_key"))
    if not package_key.startswith("prod_e2e_"):
        return {}
    return {"is_test": True, "execution_scope": "test_loopback"}
