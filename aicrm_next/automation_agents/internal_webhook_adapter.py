from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from aicrm_next.platform_foundation.external_effects.adapters import ExternalEffectAdapter, WebhookAdapter
from aicrm_next.platform_foundation.external_effects.models import (
    WEBHOOK_GENERIC_PUSH,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)
from aicrm_next.shared.runtime import runtime_setting

from .application import AutomationAgentWebhookService


_AGENT_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_AGENT_WEBHOOK_PATH_PATTERN = re.compile(r"^/api/ai/agents/([^/]+)/audience-webhook$")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_CANONICAL_FIRST_PARTY_ORIGINS = {
    ("https", "www.youcangogogo.com", 443),
    ("https", "id-dev.youcangogogo.com", 443),
}


def _origin(value: str) -> tuple[str, str, int] | None:
    parsed = urlparse(value)
    scheme = str(parsed.scheme or "").lower()
    host = str(parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return None
    try:
        port = int(parsed.port or (443 if scheme == "https" else 80))
    except ValueError:
        return None
    return scheme, host, port


def _first_party_webhook_origin(raw: str) -> bool:
    parsed = urlparse(raw)
    if not parsed.scheme and not parsed.netloc:
        return raw.startswith("/")
    candidate = _origin(raw)
    if candidate is None:
        return False
    if candidate[1] in _LOOPBACK_HOSTS:
        return True
    configured = {
        origin
        for name in ("AICRM_PUBLIC_BASE_URL", "AICRM_AUTH_ISSUER")
        if (origin := _origin(str(runtime_setting(name, "") or "").strip())) is not None
    }
    return candidate in (_CANONICAL_FIRST_PARTY_ORIGINS | configured)


def automation_agent_code_from_webhook_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or not _first_party_webhook_origin(raw):
        return ""
    match = _AGENT_WEBHOOK_PATH_PATTERN.fullmatch(urlparse(raw).path)
    if not match:
        return ""
    agent_code = unquote(match.group(1)).strip()
    return agent_code if _AGENT_CODE_PATTERN.fullmatch(agent_code) else ""


class AutomationAgentRoutingWebhookAdapter:
    """Route the exact first-party Agent webhook in-process.

    Other webhook targets retain the public-HTTPS/SSRF policy of WebhookAdapter.
    This keeps first-party loopback traffic out of the network without creating a
    general localhost exception.
    """

    def __init__(
        self,
        fallback: ExternalEffectAdapter | None = None,
        *,
        service_factory: Callable[[], AutomationAgentWebhookService] | None = None,
    ) -> None:
        self._fallback = fallback or WebhookAdapter()
        self._service_factory = service_factory or AutomationAgentWebhookService

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        target_url = str(payload.get("webhook_url") or payload.get("target_url") or "").strip()
        agent_code = automation_agent_code_from_webhook_url(target_url)
        if job.effect_type != WEBHOOK_GENERIC_PUSH or not agent_code:
            return self._fallback.dispatch(job)

        request_summary = {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": "automation_agent_audience_webhook",
            "agent_code_present": True,
            "dispatch_path": "in_process_service",
        }
        if job.execution_mode != "execute":
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "disabled",
                request_summary=request_summary,
                response_summary={"blocked": True, "real_external_call_executed": False},
                error_code="shadow_only",
                error_message="Automation Agent internal webhook execution is disabled for this job mode.",
                real_external_call_executed=False,
            )

        body = payload.get("body")
        if not isinstance(body, (dict, list)):
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": False},
                error_code="payload_invalid",
                error_message="Automation Agent webhook body must be a JSON object or array.",
                real_external_call_executed=False,
            )

        headers = dict(payload.get("headers") or {}) if isinstance(payload.get("headers"), dict) else {}
        raw_body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            response, status_code = self._service_factory().handle(
                agent_code,
                body,
                raw_body=raw_body,
                headers=headers,
            )
        except Exception as exc:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": False},
                error_code="automation_agent_internal_dispatch_failed",
                error_message=type(exc).__name__,
                real_external_call_executed=False,
            )

        response_summary = {
            key: response.get(key)
            for key in ("ok", "mode", "received_count", "deduped_count", "accepted_count", "error")
            if key in response
        }
        batch_id = str(response.get("batch_id") or "").strip()
        if batch_id.startswith("agent_batch_"):
            response_summary["automation_agent_batch_id"] = batch_id
        response_summary.update(
            {
                "http_status": int(status_code),
                "internal_service_call_executed": True,
                "internal_side_effect_executed": True,
                "real_external_call_executed": False,
            }
        )
        succeeded = 200 <= int(status_code) < 300 and bool(response.get("ok"))
        return ExternalEffectDispatchResult(
            status="succeeded" if succeeded else "failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code="" if succeeded else str(response.get("error") or "automation_agent_webhook_rejected"),
            error_message="" if succeeded else "Automation Agent internal webhook rejected the request.",
            real_external_call_executed=False,
            provider_result_received=True,
        )


__all__ = ["AutomationAgentRoutingWebhookAdapter", "automation_agent_code_from_webhook_url"]
