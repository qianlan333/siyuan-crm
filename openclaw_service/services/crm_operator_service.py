from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openclaw_service.integrations.crm.adapters.tags import TagsAdapter
from openclaw_service.integrations.crm.client import CrmApiClient
from openclaw_service.integrations.crm.config import CrmApiConfig
from openclaw_service.tools.registry import call_tool_by_name


def get_customer_context(
    external_userid: str,
    *,
    recent_message_limit: int = 20,
    timeline_limit: int = 20,
) -> dict[str, Any]:
    return call_tool_by_name(
        "get_customer_chat_context",
        {
            "external_userid": _require_value(external_userid, field_name="external_userid"),
            "recent_message_limit": recent_message_limit,
            "timeline_limit": timeline_limit,
        },
    )


def update_customer_tags(
    external_userid: str,
    *,
    userid: str,
    add_tags: Sequence[str] | None = None,
    remove_tags: Sequence[str] | None = None,
) -> dict[str, Any]:
    normalized_add_tags = _normalize_tags(add_tags, field_name="add_tags")
    normalized_remove_tags = _normalize_tags(remove_tags, field_name="remove_tags")
    if not normalized_add_tags and not normalized_remove_tags:
        raise ValueError("at least one of add_tags or remove_tags is required")

    config = CrmApiConfig.from_env()
    adapter = TagsAdapter(CrmApiClient(config))

    result: dict[str, Any] = {
        "ok": True,
        "external_userid": _require_value(external_userid, field_name="external_userid"),
        "userid": _require_value(userid, field_name="userid"),
        "add_tags": normalized_add_tags,
        "remove_tags": normalized_remove_tags,
        "results": {},
    }

    if normalized_add_tags:
        result["results"]["mark"] = _run_tag_operation(
            lambda: adapter.mark_tags(
                result["userid"],
                result["external_userid"],
                normalized_add_tags,
            )
        )

    if normalized_remove_tags:
        result["results"]["unmark"] = _run_tag_operation(
            lambda: adapter.unmark_tags(
                result["userid"],
                result["external_userid"],
                normalized_remove_tags,
            )
        )

    result["ok"] = all(operation["ok"] for operation in result["results"].values())
    return result


def _run_tag_operation(operation: Any) -> dict[str, Any]:
    try:
        payload = operation()
    except Exception as exc:  # pragma: no cover - exact exception type depends on CRM client path
        return {
            "ok": False,
            "error": str(exc),
            "error_type": exc.__class__.__name__,
        }
    return {
        "ok": True,
        "response": payload,
    }


def _require_value(value: str, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_tags(values: Sequence[str] | None, *, field_name: str) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        candidates = [values]
    else:
        candidates = list(values)

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        tag = str(item or "").strip()
        if not tag:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized
