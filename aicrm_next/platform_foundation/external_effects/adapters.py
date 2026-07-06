from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Protocol

import requests

from aicrm_next.shared.runtime_settings import runtime_bool, runtime_csv, runtime_setting

from .models import (
    AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
    GROUP_OPS_MESSAGE_LOOPBACK,
    GROUP_OPS_WEBHOOK_ACTION_LOOPBACK,
    PAYMENT_WECHAT_REFUND_REQUEST,
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    WEBHOOK_GENERIC_PUSH,
    WECOM_CONTACT_TAG_MARK,
    WECOM_CONTACT_TAG_UNMARK,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
    WECOM_WELCOME_MESSAGE_SEND,
    WECOM_PROFILE_UPDATE,
    ExternalEffectDispatchResult,
    ExternalEffectJob,
)
from .retry_policy import http_error_code

LOW_RISK_WEBHOOK_EFFECT_TYPES = frozenset(
    {
        WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        WEBHOOK_ORDER_PAID_PUSH,
        WEBHOOK_GENERIC_PUSH,
        AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
        GROUP_OPS_MESSAGE_LOOPBACK,
        GROUP_OPS_WEBHOOK_ACTION_LOOPBACK,
    }
)
WECOM_EFFECT_TYPES = (
    WECOM_CONTACT_TAG_MARK,
    WECOM_CONTACT_TAG_UNMARK,
    WECOM_WELCOME_MESSAGE_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_PROFILE_UPDATE,
)


class ExternalEffectAdapter(Protocol):
    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        ...


def _enabled(name: str) -> bool:
    return runtime_bool(name)


def _csv_env(name: str) -> set[str]:
    return runtime_csv(name)


def _runtime_present(*names: str) -> bool:
    return any(bool(runtime_setting(name, "")) for name in names)


def _normalized_wecom_execution_mode() -> tuple[str, str]:
    raw = runtime_setting("AICRM_WECOM_EXECUTION_MODE", "").strip().lower()
    if raw in {"disabled", "dry_run", "execute"}:
        return raw, "AICRM_WECOM_EXECUTION_MODE"
    if _enabled("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE"):
        return "execute", "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE"
    return "disabled", "default"


def _enabled_wecom_effect_types() -> tuple[list[str], str]:
    supported = set(WECOM_EFFECT_TYPES)
    configured = _csv_env("AICRM_WECOM_ENABLED_EFFECT_TYPES")
    if configured:
        return sorted(item for item in configured if item in supported), "AICRM_WECOM_ENABLED_EFFECT_TYPES"
    legacy = _csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")
    if legacy:
        return sorted(item for item in legacy if item in supported), "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES"
    return [], "default_empty"


def _configured_wecom_sender(fallback: str = "") -> str:
    raw = runtime_setting("AICRM_WECOM_DEFAULT_SENDER_USERID", "") or runtime_setting("AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS", "")
    candidates = [
        item.strip()
        for item in raw.replace("\n", ",").replace(" ", ",").split(",")
        if item.strip()
    ]
    return candidates[0] if candidates else str(fallback or "").strip()


def _safe_response_json_summary(response: Any) -> dict[str, Any]:
    parsed: Any = None
    parser = getattr(response, "json", None)
    if callable(parser):
        try:
            parsed = parser()
        except Exception:
            parsed = None
    if parsed is None:
        raw_text = str(getattr(response, "text", "") or "").strip()
        if raw_text.startswith("{") and raw_text.endswith("}"):
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = None
    if not isinstance(parsed, dict):
        return {}
    allowed_keys = {
        "ok",
        "mode",
        "batch_id",
        "received_count",
        "deduped_count",
        "accepted_count",
        "error",
        "detail",
    }
    summary = {key: parsed.get(key) for key in allowed_keys if key in parsed}
    batch_id = str(parsed.get("batch_id") or "").strip()
    if batch_id.startswith("agent_batch_"):
        summary["automation_agent_batch_id"] = batch_id
    return summary


def _target_unionid(payload: dict[str, Any]) -> str:
    return str(payload.get("target_unionid") or payload.get("unionid") or "").strip()


def _wecom_target_mismatch(job: ExternalEffectJob, payload: dict[str, Any], external_userid: str) -> bool:
    target_unionid = _target_unionid(payload)
    target_id = str(job.target_id or "").strip()
    if target_unionid:
        return target_id != target_unionid
    return not external_userid or target_id != external_userid


def webhook_execution_settings() -> dict[str, Any]:
    return {
        "enabled": _enabled("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE"),
        "allowed_types": sorted(_csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")),
        "supported_types": sorted(LOW_RISK_WEBHOOK_EFFECT_TYPES),
    }


def wecom_execution_settings() -> dict[str, Any]:
    execution_mode, mode_source = _normalized_wecom_execution_mode()
    enabled_types, enabled_types_source = _enabled_wecom_effect_types()
    default_sender = _configured_wecom_sender()
    deprecated_settings_present = [
        key
        for key in (
            "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE",
            "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES",
            "AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS",
        )
        if runtime_setting(key, "")
    ]
    blocking_reasons: list[str] = []
    if execution_mode == "disabled":
        blocking_reasons.append("wecom_execution_disabled")
    if execution_mode == "execute" and not enabled_types:
        blocking_reasons.append("wecom_enabled_effect_types_empty")
    if execution_mode == "execute" and not _runtime_present("WECOM_CORP_ID"):
        blocking_reasons.append("wecom_corp_id_missing")
    if execution_mode == "execute" and not _runtime_present("WECOM_CONTACT_SECRET", "WECOM_SECRET"):
        blocking_reasons.append("wecom_contact_secret_missing")
    if execution_mode == "execute" and not default_sender:
        blocking_reasons.append("default_sender_userid_missing")
    return {
        "enabled": execution_mode == "execute" and not blocking_reasons,
        "execution_mode": execution_mode,
        "execution_mode_source": mode_source,
        "allowed_types": enabled_types,
        "enabled_effect_types": enabled_types,
        "enabled_effect_types_source": enabled_types_source,
        "allowed_target_external_userids": "all",
        "allowed_group_ops_webhook_keys": "all",
        "allowed_owner_userids": [default_sender] if default_sender else [],
        "allowed_group_chat_ids": "all",
        "supported_types": list(WECOM_EFFECT_TYPES),
        "corp_id_present": _runtime_present("WECOM_CORP_ID"),
        "contact_secret_present": _runtime_present("WECOM_CONTACT_SECRET", "WECOM_SECRET"),
        "default_sender_userid_present": bool(default_sender),
        "deprecated_settings_present": deprecated_settings_present,
        "blocking_reasons": blocking_reasons,
    }


def payment_execution_settings() -> dict[str, Any]:
    return {
        "enabled": _enabled("AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE"),
        "allowed_types": sorted(_csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")),
        "supported_types": [PAYMENT_WECHAT_REFUND_REQUEST],
    }


class DisabledAdapter:
    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        return ExternalEffectDispatchResult(
            status="failed_terminal",
            adapter_mode=job.execution_mode or "disabled",
            request_summary={"effect_type": job.effect_type, "target_type": job.target_type, "target_id": job.target_id},
            response_summary={"blocked": True, "real_external_call_executed": False},
            error_code="adapter_not_implemented",
            error_message="No External Effect Queue adapter is registered for this adapter_name.",
            real_external_call_executed=False,
        )


class WebhookAdapter:
    def __init__(self, http_post=None) -> None:
        self._http_post = http_post or requests.post

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        gate_error = self._execution_gate_error(job)
        if gate_error:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "shadow",
                request_summary={
                    "effect_type": job.effect_type,
                    "operation": job.operation,
                    "target_type": job.target_type,
                    "target_id": job.target_id,
                },
                response_summary={"blocked": True, "execution_gate": gate_error, "real_external_call_executed": False},
                error_code=gate_error,
                error_message="Webhook adapter execution is blocked by external effect execution gates.",
                real_external_call_executed=False,
            )

        payload = dict(job.payload_json or {})
        url = str(payload.get("webhook_url") or payload.get("target_url") or "").strip()
        body = self._request_body(payload)
        if not url:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode="execute",
                request_summary={"target_url_present": False, "effect_type": job.effect_type},
                response_summary={"real_external_call_executed": False},
                error_code="config_missing",
                error_message="webhook_url is required",
                real_external_call_executed=False,
            )
        if body is None:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode="execute",
                request_summary={"target_url_present": True, "effect_type": job.effect_type},
                response_summary={"real_external_call_executed": False},
                error_code="payload_invalid",
                error_message="webhook payload body must be a JSON object or array",
                real_external_call_executed=False,
            )
        timeout = float(runtime_setting("AICRM_EXTERNAL_EFFECT_WEBHOOK_TIMEOUT_SECONDS", "5") or "5")
        headers, signature_configured = self._headers(payload=payload, body=body)
        request_summary = {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_url_present": True,
            "timeout_seconds": timeout,
            "body_type": type(body).__name__,
            "signature_configured": signature_configured,
        }
        try:
            response = self._http_post(url, json=body, headers=headers, timeout=timeout)
        except requests.Timeout:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": True},
                error_code="timeout",
                error_message="webhook request timed out",
                real_external_call_executed=True,
            )
        except requests.RequestException as exc:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": True},
                error_code="network_error",
                error_message=str(exc),
                real_external_call_executed=True,
            )

        status_code = int(response.status_code)
        if 200 <= status_code < 300:
            status = "succeeded"
        elif status_code in {408, 429} or status_code >= 500:
            status = "failed_retryable"
        else:
            status = "failed_terminal"
        response_summary = {"status_code": status_code, "real_external_call_executed": True}
        response_json_summary = _safe_response_json_summary(response)
        if response_json_summary:
            response_summary["response_json"] = response_json_summary
            if response_json_summary.get("automation_agent_batch_id"):
                response_summary["automation_agent_batch_id"] = response_json_summary["automation_agent_batch_id"]
        return ExternalEffectDispatchResult(
            status=status,
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code="" if status == "succeeded" else http_error_code(status_code),
            error_message="" if status == "succeeded" else response.text[:500],
            real_external_call_executed=True,
        )

    def _execution_gate_error(self, job: ExternalEffectJob) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type == GROUP_OPS_MESSAGE_LOOPBACK:
            payload = dict(job.payload_json or {})
            if str(payload.get("execution_scope") or "").strip() != "test_loopback" or not payload.get("webhook_url"):
                return "group_ops_loopback_requires_test_receiver"
        if not _enabled("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE"):
            return "execution_disabled"
        if job.effect_type not in LOW_RISK_WEBHOOK_EFFECT_TYPES:
            return "unsupported_effect_type"
        allowed = _csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")
        if job.effect_type not in allowed:
            return "effect_type_not_allowed"
        return ""

    def _request_body(self, payload: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
        if "body" in payload:
            body = payload.get("body")
        elif "payload" in payload:
            body = payload.get("payload")
        else:
            body = {
                key: value
                for key, value in payload.items()
                if key not in {"webhook_url", "target_url", "signature_secret", "signing_secret"}
            }
        return body if isinstance(body, (dict, list)) else None

    def _headers(self, *, payload: dict[str, Any], body: dict[str, Any] | list[Any]) -> tuple[dict[str, str], bool]:
        headers = {"Content-Type": "application/json"}
        extra_headers = payload.get("headers")
        if isinstance(extra_headers, dict):
            for key, value in extra_headers.items():
                header_name = str(key or "").strip()
                if not header_name or any(sensitive in header_name.lower() for sensitive in ("authorization", "token", "secret", "cookie")):
                    continue
                headers[header_name] = str(value or "")
        secret = str(
            payload.get("signature_secret")
            or payload.get("signing_secret")
            or runtime_setting("AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET")
            or ""
        ).strip()
        if not secret:
            return headers, False
        canonical_body = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(secret.encode("utf-8"), canonical_body.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["X-AICRM-External-Effect-Signature"] = signature
        headers["X-AICRM-External-Effect-Signature-Alg"] = "hmac-sha256"
        return headers, True


class WeComPrivateMessageAdapter:
    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        external_userids = [str(item or "").strip() for item in list(payload.get("external_userids") or []) if str(item or "").strip()]
        owner_userid = str(payload.get("owner_userid") or payload.get("sender") or "").strip()
        sender_userid = _configured_wecom_sender(owner_userid)
        content_text = str(payload.get("content_text") or "").strip()
        gate_error = self._execution_gate_error(job=job, payload=payload, external_userids=external_userids, owner_userid=sender_userid)
        request_summary = {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "owner_userid": owner_userid,
            "sender_userid": sender_userid,
            "sender_binding_applied": bool(sender_userid and sender_userid != owner_userid),
            "target_unionid": _target_unionid(payload),
            "external_userid_count": len(external_userids),
            "content_text_length": len(content_text),
            "attachment_count": len(payload.get("attachments") or []) if isinstance(payload.get("attachments"), list) else 0,
            "business_type": job.business_type,
            "source": str(payload.get("source") or ""),
        }
        if gate_error:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary=request_summary,
                response_summary={"blocked": True, "execution_gate": gate_error, "real_external_call_executed": False, "wecom_send_executed": False},
                error_code=gate_error,
                error_message="WeCom private-message adapter execution is blocked by payload validation.",
                real_external_call_executed=False,
            )
        adapter_payload: dict[str, Any] = {
            "sender": sender_userid,
            "external_userids": external_userids,
        }
        if content_text:
            adapter_payload["text"] = {"content": content_text}
        attachments = payload.get("attachments")
        if isinstance(attachments, list) and attachments:
            adapter_payload["attachments"] = attachments
        try:
            from aicrm_next.integration_gateway.wecom_private_adapter import build_wecom_private_message_adapter

            result = build_wecom_private_message_adapter().create_private_message_task(
                adapter_payload,
                idempotency_key=job.idempotency_key or str(job.id),
            )
        except Exception as exc:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": True, "wecom_send_executed": False},
                error_code="adapter_exception",
                error_message=str(exc),
                real_external_call_executed=True,
            )
        side_effect_executed = bool(result.get("side_effect_executed"))
        ok = bool(result.get("ok"))
        error_code = str(result.get("error_code") or "").strip()
        response_summary = {
            "real_external_call_executed": side_effect_executed,
            "wecom_send_executed": side_effect_executed,
            "adapter_mode": str(result.get("mode") or ""),
            "exact_target_verified": bool(result.get("exact_target_verified")),
            "requested_external_userid_count": len(result.get("requested_external_userids") or external_userids),
            "wecom_msgid_present": bool(str(result.get("wecom_msgid") or "").strip()),
        }
        if ok:
            return ExternalEffectDispatchResult(
                status="succeeded",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary=response_summary,
                real_external_call_executed=side_effect_executed,
            )
        if not side_effect_executed:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary=response_summary,
                error_code=error_code or "adapter_blocked",
                error_message=str(result.get("error_message") or "WeCom private-message adapter blocked before external call."),
                real_external_call_executed=False,
            )
        retryable = error_code in {"external_call_unknown", "adapter_exception", "network_error", "timeout", "rate_limited"}
        return ExternalEffectDispatchResult(
            status="failed_retryable" if retryable else "failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code=error_code or "wecom_private_send_failed",
            error_message=str(result.get("error_message") or "WeCom private-message send failed."),
            real_external_call_executed=True,
        )

    def _execution_gate_error(
        self,
        *,
        job: ExternalEffectJob,
        payload: dict[str, Any],
        external_userids: list[str],
        owner_userid: str,
    ) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type != WECOM_MESSAGE_PRIVATE_SEND:
            return "unsupported_effect_type"
        if len(external_userids) != 1:
            return "single_target_required"
        if _wecom_target_mismatch(job, payload, external_userids[0]):
            return "target_mismatch"
        if str(payload.get("channel") or "").strip() != "wecom_private":
            return "channel_not_allowed"
        has_text = bool(str(payload.get("content_text") or "").strip())
        has_attachments = isinstance(payload.get("attachments"), list) and bool(payload.get("attachments"))
        if not has_text and not has_attachments:
            return "payload_invalid"
        return ""


class WeComGroupMessageExternalEffectAdapter:
    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        gate_error = self._execution_gate_error(job, payload)
        request_summary = self._request_summary(job, payload)
        if gate_error:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary=request_summary,
                response_summary={
                    "blocked": True,
                    "execution_gate": gate_error,
                    "real_external_call_executed": False,
                    "wecom_send_executed": False,
                },
                error_code=gate_error,
                error_message="WeCom group message adapter execution is blocked by payload validation.",
                real_external_call_executed=False,
            )

        wecom_payload = self._wecom_payload(payload)
        try:
            from aicrm_next.integration_gateway.wecom_group_adapter import build_wecom_group_message_adapter

            result = build_wecom_group_message_adapter().create_group_message_task(
                wecom_payload,
                idempotency_key=job.idempotency_key or job.trace_id or str(job.id),
            )
        except Exception as exc:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={"real_external_call_executed": True, "wecom_send_executed": False},
                error_code="network_error",
                error_message=str(exc),
                real_external_call_executed=True,
            )

        response_summary = {
            "adapter": result.get("adapter"),
            "mode": result.get("mode"),
            "operation": result.get("operation"),
            "audit_id": result.get("audit_id"),
            "requested_chat_count": int(result.get("requested_chat_count") or len(list(result.get("requested_chat_ids") or []))),
            "exact_target_required": bool(result.get("exact_target_required")),
            "exact_target_verified": bool(result.get("exact_target_verified")),
            "wecom_msgid_present": bool(str(result.get("wecom_msgid") or "").strip()),
            "real_external_call_executed": bool(result.get("side_effect_executed")),
            "wecom_send_executed": bool(result.get("side_effect_executed")),
        }
        if result.get("ok") and result.get("exact_target_verified") is True:
            return ExternalEffectDispatchResult(
                status="succeeded",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary=response_summary,
                real_external_call_executed=bool(result.get("side_effect_executed")),
            )
        error_code = str(result.get("error_code") or "wecom_group_message_failed").strip()
        return ExternalEffectDispatchResult(
            status="failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code=error_code,
            error_message=str(result.get("error_message") or error_code)[:500],
            real_external_call_executed=bool(result.get("side_effect_executed")),
        )

    def _request_summary(self, job: ExternalEffectJob, payload: dict[str, Any]) -> dict[str, Any]:
        chat_ids = self._chat_ids(payload)
        return {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "webhook_key": str(payload.get("webhook_key") or ""),
            "owner_userid": str(payload.get("owner_userid") or payload.get("sender") or ""),
            "chat_count": len(chat_ids),
            "mention_all": bool(payload.get("mention_all") or payload.get("is_mention_all")),
            "content_text_length": len(str(((payload.get("content_payload") or {}).get("text") or {}).get("content") or "")),
        }

    def _execution_gate_error(self, job: ExternalEffectJob, payload: dict[str, Any]) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type != WECOM_MESSAGE_GROUP_SEND:
            return "unsupported_effect_type"
        owner = _configured_wecom_sender(str(payload.get("owner_userid") or payload.get("sender") or "").strip())
        if not owner:
            return "owner_userid_missing"
        chat_ids = self._chat_ids(payload)
        if not chat_ids:
            return "group_chat_id_missing"
        content_payload = payload.get("content_payload")
        if not isinstance(content_payload, dict):
            return "payload_invalid"
        text = content_payload.get("text") if isinstance(content_payload.get("text"), dict) else {}
        attachments = content_payload.get("attachments") if isinstance(content_payload.get("attachments"), list) else []
        if not str(text.get("content") or "").strip() and not attachments:
            return "payload_invalid"
        return ""

    def _chat_ids(self, payload: dict[str, Any]) -> list[str]:
        return [str(item or "").strip() for item in list(payload.get("chat_ids") or []) if str(item or "").strip()]

    def _wecom_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        content_payload = dict(payload.get("content_payload") or {})
        result = dict(content_payload)
        result["sender"] = _configured_wecom_sender(
            str(payload.get("owner_userid") or payload.get("sender") or content_payload.get("sender") or "").strip()
        )
        result["chat_ids"] = self._chat_ids(payload)
        return result


class WeComWelcomeMessageAdapter:
    def __init__(self, adapter_factory=None) -> None:
        self._adapter_factory = adapter_factory

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        request_summary = self._request_summary(job, payload)
        gate_error = self._execution_gate_error(job, payload)
        if gate_error:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary=request_summary,
                response_summary={
                    "blocked": True,
                    "execution_gate": gate_error,
                    "real_external_call_executed": False,
                    "wecom_send_executed": False,
                },
                error_code=gate_error,
                error_message="WeCom welcome-message adapter execution is blocked by payload validation.",
                real_external_call_executed=False,
            )

        wecom_payload = self._wecom_payload(payload)
        try:
            adapter = self._build_adapter()
            result = adapter.send_welcome_msg(wecom_payload)
        except Exception as exc:
            return self._failure_result(exc, request_summary=request_summary)

        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary={
                "errcode": int(result.get("errcode") or 0) if isinstance(result, dict) else 0,
                "errmsg_present": bool(str((result or {}).get("errmsg") or "").strip()) if isinstance(result, dict) else False,
                "real_external_call_executed": True,
                "wecom_send_executed": True,
            },
            real_external_call_executed=True,
        )

    def _request_summary(self, job: ExternalEffectJob, payload: dict[str, Any]) -> dict[str, Any]:
        text_payload = payload.get("text") if isinstance(payload.get("text"), dict) else {}
        attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
        return {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "target_unionid": _target_unionid(payload),
            "external_userid": str(payload.get("external_userid") or ""),
            "follow_user_userid": str(payload.get("follow_user_userid") or ""),
            "welcome_code_present": bool(str(payload.get("welcome_code") or "").strip()),
            "text_length": len(str(text_payload.get("content") or "")),
            "attachment_count": len(attachments),
        }

    def _execution_gate_error(self, job: ExternalEffectJob, payload: dict[str, Any]) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type != WECOM_WELCOME_MESSAGE_SEND:
            return "unsupported_effect_type"
        external_userid = str(payload.get("external_userid") or "").strip()
        if _wecom_target_mismatch(job, payload, external_userid):
            return "target_mismatch"
        follow_user_userid = str(payload.get("follow_user_userid") or "").strip()
        if not follow_user_userid:
            return "owner_userid_missing"
        if not str(payload.get("welcome_code") or "").strip():
            return "welcome_code_missing"
        has_text = isinstance(payload.get("text"), dict) and bool(
            str((payload.get("text") or {}).get("content") or "").strip()
        )
        has_attachments = isinstance(payload.get("attachments"), list) and bool(payload.get("attachments"))
        if not has_text and not has_attachments:
            return "payload_invalid"
        return ""

    def _wecom_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"welcome_code": str(payload.get("welcome_code") or "").strip()}
        if isinstance(payload.get("text"), dict):
            result["text"] = dict(payload.get("text") or {})
        if isinstance(payload.get("attachments"), list) and payload.get("attachments"):
            result["attachments"] = list(payload.get("attachments") or [])
        return result

    def _build_adapter(self):
        if self._adapter_factory is not None:
            return self._adapter_factory()
        from aicrm_next.integration_gateway.wecom_channel_entry_client import (
            ProductionWeComAdapter,
            missing_wecom_config,
        )

        missing = missing_wecom_config()
        if missing:
            raise RuntimeError("missing_wecom_config:" + ",".join(missing))
        return ProductionWeComAdapter()

    def _failure_result(self, exc: Exception, *, request_summary: dict[str, Any]) -> ExternalEffectDispatchResult:
        error_code = "wecom_welcome_send_failed"
        error_message = str(exc)[:500]
        retryable = False
        response_summary: dict[str, Any] = {"real_external_call_executed": True, "wecom_send_executed": False}
        try:
            from aicrm_next.integration_gateway.wecom_channel_entry_client import WeComApiError

            if isinstance(exc, WeComApiError):
                payload = dict(exc.payload or {})
                errcode = int(payload.get("errcode") or 0)
                response_summary.update(
                    {
                        "errcode": errcode,
                        "errmsg_present": bool(str(payload.get("errmsg") or "").strip()),
                    }
                )
                error_code = f"wecom_error_{errcode}" if errcode else "network_error"
                error_message = str(payload.get("errmsg") or exc.message or exc)[:500]
                retryable = errcode in {-1, 42001, 45009, 45011} or errcode == 0
        except Exception:
            pass
        if error_message.startswith("missing_wecom_config:"):
            error_code = "config_missing"
            retryable = False
            response_summary["real_external_call_executed"] = False
        return ExternalEffectDispatchResult(
            status="failed_retryable" if retryable else "failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code=error_code,
            error_message=error_message,
            real_external_call_executed=bool(response_summary.get("real_external_call_executed")),
        )


class WeComContactTagAdapter:
    def __init__(self, adapter_factory=None) -> None:
        self._adapter_factory = adapter_factory

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        request_summary = self._request_summary(job, payload)
        gate_error = self._execution_gate_error(job, payload)
        if gate_error:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary=request_summary,
                response_summary={
                    "blocked": True,
                    "execution_gate": gate_error,
                    "real_external_call_executed": False,
                    "wecom_tag_executed": False,
                },
                error_code=gate_error,
                error_message="WeCom contact-tag adapter execution is blocked by external effect gates.",
                real_external_call_executed=False,
            )

        try:
            adapter = self._build_adapter()
            result = adapter.mark_external_contact_tags(
                external_userid=str(payload.get("external_userid") or "").strip(),
                follow_user_userid=str(payload.get("follow_user_userid") or payload.get("userid") or "").strip(),
                add_tags=self._add_tags(job, payload),
                remove_tags=self._remove_tags(job, payload),
            )
        except Exception as exc:
            return self._failure_result(exc, request_summary=request_summary)

        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary={
                "errcode": int(result.get("errcode") or 0) if isinstance(result, dict) else 0,
                "errmsg_present": bool(str((result or {}).get("errmsg") or "").strip()) if isinstance(result, dict) else False,
                "real_external_call_executed": True,
                "wecom_tag_executed": True,
            },
            real_external_call_executed=True,
        )

    def _request_summary(self, job: ExternalEffectJob, payload: dict[str, Any]) -> dict[str, Any]:
        add_tags = self._add_tags(job, payload)
        remove_tags = self._remove_tags(job, payload)
        return {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "target_unionid": _target_unionid(payload),
            "external_userid": str(payload.get("external_userid") or ""),
            "follow_user_userid": str(payload.get("follow_user_userid") or payload.get("userid") or ""),
            "add_tag_count": len(add_tags),
            "remove_tag_count": len(remove_tags),
        }

    def _execution_gate_error(self, job: ExternalEffectJob, payload: dict[str, Any]) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type not in {WECOM_CONTACT_TAG_MARK, WECOM_CONTACT_TAG_UNMARK}:
            return "unsupported_effect_type"
        external_userid = str(payload.get("external_userid") or "").strip()
        if _wecom_target_mismatch(job, payload, external_userid):
            return "target_mismatch"
        follow_user_userid = str(payload.get("follow_user_userid") or payload.get("userid") or "").strip()
        if not follow_user_userid:
            return "owner_userid_missing"
        add_tags = self._add_tags(job, payload)
        remove_tags = self._remove_tags(job, payload)
        if not add_tags and not remove_tags:
            return "tag_ids_missing"
        if job.effect_type == WECOM_CONTACT_TAG_MARK and not add_tags:
            return "add_tags_missing"
        if job.effect_type == WECOM_CONTACT_TAG_UNMARK and not remove_tags:
            return "remove_tags_missing"
        return ""

    def _build_adapter(self):
        if self._adapter_factory is not None:
            return self._adapter_factory()
        from aicrm_next.integration_gateway.wecom_channel_entry_client import (
            ProductionWeComAdapter,
            missing_wecom_config,
        )

        missing = missing_wecom_config()
        if missing:
            raise RuntimeError("missing_wecom_config:" + ",".join(missing))
        return ProductionWeComAdapter()

    def _failure_result(self, exc: Exception, *, request_summary: dict[str, Any]) -> ExternalEffectDispatchResult:
        error_code = "wecom_tag_mark_failed"
        error_message = str(exc)[:500]
        retryable = False
        response_summary: dict[str, Any] = {"real_external_call_executed": True, "wecom_tag_executed": False}
        try:
            from aicrm_next.integration_gateway.wecom_channel_entry_client import WeComApiError

            if isinstance(exc, WeComApiError):
                payload = dict(exc.payload or {})
                errcode = int(payload.get("errcode") or 0)
                response_summary.update(
                    {
                        "errcode": errcode,
                        "errmsg_present": bool(str(payload.get("errmsg") or "").strip()),
                    }
                )
                error_code = f"wecom_error_{errcode}" if errcode else "network_error"
                error_message = str(payload.get("errmsg") or exc.message or exc)[:500]
                retryable = errcode in {-1, 42001, 45009, 45011} or errcode == 0
        except Exception:
            pass
        if error_message.startswith("missing_wecom_config:"):
            error_code = "config_missing"
            retryable = False
            response_summary["real_external_call_executed"] = False
        return ExternalEffectDispatchResult(
            status="failed_retryable" if retryable else "failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code=error_code,
            error_message=error_message,
            real_external_call_executed=bool(response_summary.get("real_external_call_executed")),
        )

    def _tags(self, value: Any) -> list[str]:
        return [str(item or "").strip() for item in list(value or []) if str(item or "").strip()]

    def _add_tags(self, job: ExternalEffectJob, payload: dict[str, Any]) -> list[str]:
        explicit = self._tags(payload.get("add_tags"))
        if explicit or job.effect_type != WECOM_CONTACT_TAG_MARK:
            return explicit
        return self._tags(payload.get("tag_ids"))

    def _remove_tags(self, job: ExternalEffectJob, payload: dict[str, Any]) -> list[str]:
        explicit = self._tags(payload.get("remove_tags"))
        if explicit or job.effect_type != WECOM_CONTACT_TAG_UNMARK:
            return explicit
        return self._tags(payload.get("tag_ids"))


class WeComProfileUpdateAdapter:
    def __init__(self, adapter_factory=None) -> None:
        self._adapter_factory = adapter_factory

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        request_summary = self._request_summary(job, payload)
        gate_error = self._execution_gate_error(job, payload)
        if gate_error:
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary=request_summary,
                response_summary={
                    "blocked": True,
                    "execution_gate": gate_error,
                    "real_external_call_executed": False,
                    "wecom_profile_update_executed": False,
                },
                error_code=gate_error,
                error_message="WeCom profile-update adapter execution is blocked by external effect gates.",
                real_external_call_executed=False,
            )

        wecom_payload = {
            "userid": str(payload.get("follow_user_userid") or payload.get("userid") or "").strip(),
            "external_userid": str(payload.get("external_userid") or "").strip(),
        }
        for key in ("remark", "description", "remark_company"):
            value = str(payload.get(key) or "").strip()
            if value:
                wecom_payload[key] = value
        remark_mobiles = [str(item or "").strip() for item in list(payload.get("remark_mobiles") or []) if str(item or "").strip()]
        if remark_mobiles:
            wecom_payload["remark_mobiles"] = remark_mobiles
        try:
            result = self._build_adapter().update_external_contact_remark(wecom_payload)
        except Exception as exc:
            return self._failure_result(exc, request_summary=request_summary)

        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary={
                "errcode": int(result.get("errcode") or 0) if isinstance(result, dict) else 0,
                "errmsg_present": bool(str((result or {}).get("errmsg") or "").strip()) if isinstance(result, dict) else False,
                "real_external_call_executed": True,
                "wecom_profile_update_executed": True,
            },
            real_external_call_executed=True,
        )

    def _request_summary(self, job: ExternalEffectJob, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "target_unionid": _target_unionid(payload),
            "external_userid": str(payload.get("external_userid") or ""),
            "follow_user_userid": str(payload.get("follow_user_userid") or payload.get("userid") or ""),
            "remark_present": bool(str(payload.get("remark") or "").strip()),
            "description_present": bool(str(payload.get("description") or "").strip()),
        }

    def _execution_gate_error(self, job: ExternalEffectJob, payload: dict[str, Any]) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type != WECOM_PROFILE_UPDATE:
            return "unsupported_effect_type"
        external_userid = str(payload.get("external_userid") or "").strip()
        if _wecom_target_mismatch(job, payload, external_userid):
            return "target_mismatch"
        follow_user_userid = str(payload.get("follow_user_userid") or payload.get("userid") or "").strip()
        if not follow_user_userid:
            return "owner_userid_missing"
        if not any(str(payload.get(key) or "").strip() for key in ("remark", "description", "remark_company")) and not payload.get("remark_mobiles"):
            return "profile_update_payload_missing"
        return ""

    def _build_adapter(self):
        if self._adapter_factory is not None:
            return self._adapter_factory()
        from aicrm_next.integration_gateway.wecom_channel_entry_client import (
            ProductionWeComAdapter,
            missing_wecom_config,
        )

        missing = missing_wecom_config()
        if missing:
            raise RuntimeError("missing_wecom_config:" + ",".join(missing))
        return ProductionWeComAdapter()

    def _failure_result(self, exc: Exception, *, request_summary: dict[str, Any]) -> ExternalEffectDispatchResult:
        error_code = "wecom_profile_update_failed"
        error_message = str(exc)[:500]
        retryable = False
        response_summary: dict[str, Any] = {"real_external_call_executed": True, "wecom_profile_update_executed": False}
        try:
            from aicrm_next.integration_gateway.wecom_channel_entry_client import WeComApiError

            if isinstance(exc, WeComApiError):
                payload = dict(exc.payload or {})
                errcode = int(payload.get("errcode") or 0)
                response_summary.update(
                    {
                        "errcode": errcode,
                        "errmsg_present": bool(str(payload.get("errmsg") or "").strip()),
                    }
                )
                error_code = f"wecom_error_{errcode}" if errcode else "network_error"
                error_message = str(payload.get("errmsg") or exc.message or exc)[:500]
                retryable = errcode in {-1, 42001, 45009, 45011} or errcode == 0
        except Exception:
            pass
        if error_message.startswith("missing_wecom_config:"):
            error_code = "config_missing"
            retryable = False
            response_summary["real_external_call_executed"] = False
        return ExternalEffectDispatchResult(
            status="failed_retryable" if retryable else "failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary=response_summary,
            error_code=error_code,
            error_message=error_message,
            real_external_call_executed=bool(response_summary.get("real_external_call_executed")),
        )


class WeChatPaymentAdapter:
    def __init__(self, client_factory=None, refund_result_sync=None, refund_failure_sync=None) -> None:
        self._client_factory = client_factory
        self._refund_result_sync = refund_result_sync
        self._refund_failure_sync = refund_failure_sync

    def dispatch(self, job: ExternalEffectJob) -> ExternalEffectDispatchResult:
        payload = dict(job.payload_json or {})
        request_payload = dict(payload.get("request_payload") or {})
        request_summary = self._request_summary(job, payload, request_payload)
        out_refund_no = str(request_payload.get("out_refund_no") or payload.get("out_refund_no") or job.target_id or "").strip()
        gate_error = self._execution_gate_error(job, payload, request_payload)
        if gate_error:
            sync_result = self._mark_refund_failed(
                out_refund_no,
                error_code=gate_error,
                error_message="WeChat payment refund execution is blocked by external effect gates.",
                response_payload={"blocked": True, "execution_gate": gate_error, "real_external_call_executed": False},
            )
            return ExternalEffectDispatchResult(
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary=request_summary,
                response_summary={
                    "blocked": True,
                    "execution_gate": gate_error,
                    "real_external_call_executed": False,
                    "wechat_refund_executed": False,
                    "refund_failure_synced": bool(sync_result.get("ok")),
                },
                error_code=gate_error,
                error_message="WeChat payment refund execution is blocked by external effect gates.",
                real_external_call_executed=False,
            )

        try:
            provider_payload = self._build_client().create_refund(request_payload)
        except Exception as exc:
            return self._failure_result(exc, request_summary=request_summary, out_refund_no=out_refund_no)

        refund_payload = {
            **dict(provider_payload or {}),
            "out_trade_no": str(payload.get("out_trade_no") or request_payload.get("out_trade_no") or ""),
            "transaction_id": str(payload.get("transaction_id") or request_payload.get("transaction_id") or ""),
            "out_refund_no": str((provider_payload or {}).get("out_refund_no") or out_refund_no),
            "refund_status": str((provider_payload or {}).get("status") or (provider_payload or {}).get("refund_status") or "PROCESSING"),
            "amount": dict(request_payload.get("amount") or {}),
        }
        try:
            sync_result = self._apply_refund_result(refund_payload)
        except Exception as exc:
            return ExternalEffectDispatchResult(
                status="failed_retryable",
                adapter_mode="execute",
                request_summary=request_summary,
                response_summary={
                    "real_external_call_executed": True,
                    "wechat_refund_executed": True,
                    "refund_result_sync_failed": True,
                    "provider_status": str(refund_payload.get("refund_status") or ""),
                    "refund_id_present": bool(str(refund_payload.get("refund_id") or "").strip()),
                },
                error_code="network_error",
                error_message=f"wechat refund created but local result sync failed: {str(exc)[:400]}",
                real_external_call_executed=True,
            )

        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary={
                "real_external_call_executed": True,
                "wechat_refund_executed": True,
                "refund_result_synced": True,
                "provider_status": str(refund_payload.get("refund_status") or ""),
                "refund_id_present": bool(str(refund_payload.get("refund_id") or "").strip()),
                "order_refund_status": str(sync_result.get("order_refund_status") or "") if isinstance(sync_result, dict) else "",
            },
            real_external_call_executed=True,
        )

    def _request_summary(self, job: ExternalEffectJob, payload: dict[str, Any], request_payload: dict[str, Any]) -> dict[str, Any]:
        amount = request_payload.get("amount") if isinstance(request_payload.get("amount"), dict) else {}
        return {
            "effect_type": job.effect_type,
            "operation": job.operation,
            "target_type": job.target_type,
            "target_id": job.target_id,
            "out_trade_no": str(payload.get("out_trade_no") or request_payload.get("out_trade_no") or ""),
            "out_refund_no": str(request_payload.get("out_refund_no") or payload.get("out_refund_no") or ""),
            "transaction_id_present": bool(str(payload.get("transaction_id") or request_payload.get("transaction_id") or "").strip()),
            "refund_amount_total": self._int_value(amount.get("refund")),
            "order_amount_total": self._int_value(amount.get("total")),
            "notify_url_present": bool(str(request_payload.get("notify_url") or "").strip()),
        }

    def _int_value(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _execution_gate_error(self, job: ExternalEffectJob, payload: dict[str, Any], request_payload: dict[str, Any]) -> str:
        if job.execution_mode in {"disabled", "shadow", "plan_only", "execute_dryrun"}:
            return "shadow_only"
        if job.effect_type != PAYMENT_WECHAT_REFUND_REQUEST or job.operation != "refund_request":
            return "unsupported_effect_type"
        if not _enabled("AICRM_EXTERNAL_EFFECT_PAYMENT_EXECUTE"):
            return "payment_execution_disabled"
        allowed_types = _csv_env("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")
        if job.effect_type not in allowed_types:
            return "effect_type_not_allowed"
        out_refund_no = str(request_payload.get("out_refund_no") or payload.get("out_refund_no") or "").strip()
        if not out_refund_no or out_refund_no != str(job.target_id or "").strip():
            return "target_mismatch"
        if not str(request_payload.get("transaction_id") or payload.get("transaction_id") or "").strip():
            return "transaction_id_missing"
        amount = request_payload.get("amount") if isinstance(request_payload.get("amount"), dict) else {}
        try:
            refund_amount = int(amount.get("refund") or 0)
            order_amount = int(amount.get("total") or 0)
        except (TypeError, ValueError):
            return "payload_invalid"
        if refund_amount <= 0 or order_amount <= 0 or refund_amount > order_amount:
            return "payload_invalid"
        return ""

    def _build_client(self):
        if self._client_factory is not None:
            return self._client_factory()
        from aicrm_next.integration_gateway.wechat_pay_client import WeChatPayClient, wechat_pay_client_config_from_env

        return WeChatPayClient(wechat_pay_client_config_from_env())

    def _apply_refund_result(self, refund_payload: dict[str, Any]) -> dict[str, Any]:
        if self._refund_result_sync is not None:
            return dict(self._refund_result_sync(refund_payload) or {})
        from aicrm_next.commerce.admin_transactions import apply_wechat_refund_result

        return dict(apply_wechat_refund_result(refund_payload) or {})

    def _mark_refund_failed(self, out_refund_no: str, *, error_code: str, error_message: str, response_payload: dict[str, Any]) -> dict[str, Any]:
        if not out_refund_no:
            return {"ok": False, "reason": "out_refund_no_missing"}
        try:
            if self._refund_failure_sync is not None:
                return dict(
                    self._refund_failure_sync(
                        out_refund_no,
                        error_code=error_code,
                        error_message=error_message,
                        response_payload=response_payload,
                    )
                    or {}
                )
            from aicrm_next.commerce.admin_transactions import mark_wechat_refund_request_failed

            return dict(
                mark_wechat_refund_request_failed(
                    out_refund_no,
                    error_code=error_code,
                    error_message=error_message,
                    response_payload=response_payload,
                )
                or {}
            )
        except Exception as exc:
            return {"ok": False, "reason": "refund_failure_sync_failed", "error": str(exc)[:200]}

    def _failure_result(self, exc: Exception, *, request_summary: dict[str, Any], out_refund_no: str) -> ExternalEffectDispatchResult:
        status_code = getattr(exc, "status_code", None)
        provider_payload = dict(getattr(exc, "payload", {}) or {})
        error_message = str(exc)[:500]
        if status_code is None and ("required" in error_message or "failed to load WeChat Pay" in error_message):
            error_code = "config_missing"
            real_external_call_executed = False
        else:
            error_code = http_error_code(status_code)
            real_external_call_executed = True
        retryable = error_code in {"network_error", "timeout", "http_408", "http_429", "http_5xx"}
        sync_result: dict[str, Any] = {}
        if not retryable:
            sync_result = self._mark_refund_failed(
                out_refund_no,
                error_code=error_code,
                error_message=error_message,
                response_payload={
                    "provider_payload": provider_payload,
                    "real_external_call_executed": real_external_call_executed,
                },
            )
        return ExternalEffectDispatchResult(
            status="failed_retryable" if retryable else "failed_terminal",
            adapter_mode="execute",
            request_summary=request_summary,
            response_summary={
                "status_code": status_code,
                "provider_payload_present": bool(provider_payload),
                "real_external_call_executed": real_external_call_executed,
                "wechat_refund_executed": False,
                "refund_failure_synced": bool(sync_result.get("ok")) if sync_result else False,
            },
            error_code=error_code,
            error_message=error_message,
            real_external_call_executed=real_external_call_executed,
        )


class ExternalEffectAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ExternalEffectAdapter] = {
            "outbound_webhook": WebhookAdapter(),
            "webhook": WebhookAdapter(),
            "wechat_payment": WeChatPaymentAdapter(),
            "wecom_private_message": WeComPrivateMessageAdapter(),
            "wecom_group_message": WeComGroupMessageExternalEffectAdapter(),
            "wecom_welcome_message": WeComWelcomeMessageAdapter(),
            "wecom_tag": WeComContactTagAdapter(),
            "wecom_profile": WeComProfileUpdateAdapter(),
        }
        self._disabled = DisabledAdapter()

    def get(self, adapter_name: str) -> ExternalEffectAdapter:
        return self._adapters.get(str(adapter_name or "").strip(), self._disabled)


DEFAULT_ADAPTER_REGISTRY = ExternalEffectAdapterRegistry()
