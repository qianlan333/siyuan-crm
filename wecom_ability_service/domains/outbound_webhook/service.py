from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import requests
from flask import current_app

from ...infra.settings import DEFAULT_OPENCLAW_WEBHOOK_URL, get_setting
from . import repo


outbound_webhook_logger = logging.getLogger("outbound_webhook")

STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_RETRY_SCHEDULED = "retry_scheduled"
STATUS_EXHAUSTED = "exhausted"

EVENT_OPENCLAW_FOCUS_MESSAGE = "openclaw_focus_message"
EVENT_QUESTIONNAIRE_SUBMIT = "questionnaire_submit"

_EVENT_CONFIGS = {
    EVENT_OPENCLAW_FOCUS_MESSAGE: {
        "url_key": "OPENCLAW_WEBHOOK_URL",
        "url_fallback_keys": ("OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL",),
        "default_url": DEFAULT_OPENCLAW_WEBHOOK_URL,
        "token_key": "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN",
        "timeout_key": "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS",
        "default_timeout": 10,
    },
    EVENT_QUESTIONNAIRE_SUBMIT: {
        "url_key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_URL",
        "token_key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN",
        "timeout_key": "QUESTIONNAIRE_SUBMIT_WEBHOOK_TIMEOUT_SECONDS",
        "default_timeout": 10,
    },
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _truncate_text(value: Any, *, maximum: int) -> str:
    text = _normalized_text(value)
    if len(text) <= maximum:
        return text
    return f"{text[:maximum]}..."


def _setting_text(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _setting_int(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def _setting_bool(key: str, *, default: bool) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _event_config(event_type: str) -> dict[str, Any]:
    normalized = _normalized_text(event_type)
    config = _EVENT_CONFIGS.get(normalized)
    if not config:
        raise ValueError("unsupported outbound webhook event_type")
    return config


def _event_webhook_url(config: dict[str, Any]) -> str:
    primary_key = str(config["url_key"])
    fallback_keys = [str(item) for item in (config.get("url_fallback_keys") or ()) if _normalized_text(item)]
    default_url = _normalized_text(config.get("default_url"))

    primary_setting = get_setting(primary_key)
    if primary_setting is not None:
        return _normalized_text(primary_setting)

    primary_config = _normalized_text(current_app.config.get(primary_key, ""))
    for fallback_key in fallback_keys:
        fallback_setting = get_setting(fallback_key)
        if fallback_setting is not None:
            fallback_value = _normalized_text(fallback_setting)
            if fallback_value:
                return fallback_value
            break

    if primary_config and (not default_url or primary_config != default_url):
        return primary_config

    for fallback_key in fallback_keys:
        fallback_config = _normalized_text(current_app.config.get(fallback_key, ""))
        if fallback_config:
            return fallback_config

    return primary_config


def _retry_enabled() -> bool:
    return _setting_bool("OUTBOUND_WEBHOOK_RETRY_ENABLED", default=True)


def _retry_max_attempts() -> int:
    return _setting_int("OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS", default=3, minimum=1)


def _retry_interval_seconds() -> int:
    return _setting_int("OUTBOUND_WEBHOOK_RETRY_INTERVAL_SECONDS", default=60, minimum=1)


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_retry_at(now_text: str) -> str:
    base = datetime.strptime(now_text, "%Y-%m-%d %H:%M:%S")
    return (base + timedelta(seconds=_retry_interval_seconds())).strftime("%Y-%m-%d %H:%M:%S")


def _response_body_summary(response: requests.Response) -> str:
    body_text = ""
    try:
        body_text = response.text
    except Exception:
        body_text = ""
    return _truncate_text(body_text, maximum=1000)


def _payload_summary(payload: dict[str, Any]) -> str:
    return _truncate_text(_json_dumps(payload), maximum=1000)


def _request_headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if _normalized_text(token):
        headers["Authorization"] = f"Bearer {_normalized_text(token)}"
    return headers


def _delivery_snapshot(delivery: dict[str, Any]) -> dict[str, Any]:
    payload = _json_loads(delivery.get("payload_json"), default={})
    return {
        "id": int(delivery.get("id") or 0),
        "event_type": _normalized_text(delivery.get("event_type")),
        "source_key": _normalized_text(delivery.get("source_key")),
        "source_id": _normalized_text(delivery.get("source_id")),
        "target_url": _normalized_text(delivery.get("target_url")),
        "payload": payload if isinstance(payload, dict) else {},
        "payload_summary": _normalized_text(delivery.get("payload_summary")),
        "token_configured": bool(delivery.get("token_configured")),
        "status": _normalized_text(delivery.get("status")),
        "attempt_count": int(delivery.get("attempt_count") or 0),
        "max_attempts": int(delivery.get("max_attempts") or 0),
        "response_status_code": delivery.get("response_status_code"),
        "response_body_summary": _normalized_text(delivery.get("response_body_summary")),
        "last_error": _normalized_text(delivery.get("last_error")),
        "last_attempted_at": _normalized_text(delivery.get("last_attempted_at")),
        "next_retry_at": _normalized_text(delivery.get("next_retry_at")),
        "created_at": _normalized_text(delivery.get("created_at")),
        "updated_at": _normalized_text(delivery.get("updated_at")),
    }


def _attempt_delivery(delivery: dict[str, Any]) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service._attempt_delivery(delivery)


def send_outbound_webhook(
    *,
    event_type: str,
    payload: dict[str, Any],
    source_key: str = "",
    source_id: str = "",
) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service.send_outbound_webhook(
        event_type=event_type,
        payload=payload,
        source_key=source_key,
        source_id=source_id,
    )


def retry_outbound_webhook_delivery(delivery_id: int) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service.retry_outbound_webhook_delivery(delivery_id)


def run_due_outbound_webhook_retries(*, limit: int = 20) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service.run_due_outbound_webhook_retries(limit=limit)


def list_outbound_webhook_deliveries(
    *,
    event_type: str = "",
    status: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service.list_outbound_webhook_deliveries(
        event_type=event_type,
        status=status,
        limit=limit,
    )


def get_outbound_webhook_delivery_counts() -> dict[str, int]:
    from . import message_dispatch_service

    return message_dispatch_service.get_outbound_webhook_delivery_counts()
