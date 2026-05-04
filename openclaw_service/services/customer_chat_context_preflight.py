from __future__ import annotations

import os
from typing import Any

from openclaw_service.tools.registry import call_tool_by_name

TOOL_NAME = "get_customer_chat_context"

_REQUIRED_ENV_KEYS = (
    "CRM_API_BASE_URL",
    "CRM_API_TOKEN",
)

_OPTIONAL_ENV_KEYS = (
    "CRM_MCP_BEARER_TOKEN",
    "CRM_API_TIMEOUT_MS",
    "CRM_API_MAX_RETRIES",
    "CRM_API_RETRY_BACKOFF_SECONDS",
)


def validate_customer_chat_context_env() -> dict[str, Any]:
    required_env = {key: bool(str(os.getenv(key, "")).strip()) for key in _REQUIRED_ENV_KEYS}
    optional_env = {key: bool(str(os.getenv(key, "")).strip()) for key in _OPTIONAL_ENV_KEYS}
    missing_required = [key for key, present in required_env.items() if not present]
    return {
        "ok": not missing_required,
        "required_env": required_env,
        "optional_env": optional_env,
        "missing_required": missing_required,
    }


def run_customer_chat_context_preflight(
    external_userid: str,
    *,
    recent_message_limit: int = 5,
    timeline_limit: int = 5,
) -> dict[str, Any]:
    env_result = validate_customer_chat_context_env()
    if not env_result["ok"]:
        return {
            "ok": False,
            "external_userid": external_userid,
            "env": env_result,
            "tool_name": TOOL_NAME,
            "source_status": "error",
            "degraded": False,
            "warnings": [],
            "customer_present": False,
            "recent_messages_count": 0,
            "recent_timeline_events_count": 0,
            "sample_customer_fields": {},
            "error": f"missing required env: {', '.join(env_result['missing_required'])}",
        }

    try:
        context = call_tool_by_name(
            TOOL_NAME,
            {
                "external_userid": external_userid,
                "recent_message_limit": recent_message_limit,
                "timeline_limit": timeline_limit,
            },
        )
    except Exception as exc:
        return {
            "ok": False,
            "external_userid": external_userid,
            "env": env_result,
            "tool_name": TOOL_NAME,
            "source_status": "error",
            "degraded": False,
            "warnings": [],
            "customer_present": False,
            "recent_messages_count": 0,
            "recent_timeline_events_count": 0,
            "sample_customer_fields": {},
            "error": str(exc),
        }

    customer = context.get("customer") if isinstance(context, dict) else None
    recent_messages = context.get("recent_messages") if isinstance(context, dict) else []
    recent_timeline_events = context.get("recent_timeline_events") if isinstance(context, dict) else []
    source_status = str(context.get("source_status") or "error")
    degraded = bool(context.get("degraded"))
    warnings = context.get("warnings") if isinstance(context.get("warnings"), list) else []

    return {
        "ok": True,
        "external_userid": external_userid,
        "env": env_result,
        "tool_name": TOOL_NAME,
        "source_status": source_status,
        "degraded": degraded,
        "warnings": warnings,
        "customer_present": isinstance(customer, dict) and bool(customer),
        "recent_messages_count": len(recent_messages) if isinstance(recent_messages, list) else 0,
        "recent_timeline_events_count": len(recent_timeline_events) if isinstance(recent_timeline_events, list) else 0,
        "sample_customer_fields": _sample_customer_fields(customer),
        "error": "",
    }


def _sample_customer_fields(customer: Any) -> dict[str, str]:
    if not isinstance(customer, dict):
        return {}
    raw = customer.get("raw") if isinstance(customer.get("raw"), dict) else {}
    customer_name = (
        str(customer.get("name") or "").strip()
        or str(customer.get("customer_name") or "").strip()
        or str(raw.get("customer_name") or "").strip()
    )
    owner_userid = (
        str(customer.get("owner_userid") or "").strip()
        or str(raw.get("owner_userid") or "").strip()
    )
    external_userid = (
        str(customer.get("external_userid") or "").strip()
        or str(raw.get("external_userid") or "").strip()
    )
    return {
        "external_userid": external_userid,
        "customer_name": customer_name,
        "owner_userid": owner_userid,
    }
