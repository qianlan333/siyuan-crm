from __future__ import annotations

import json
from typing import Any


def normalize_optional_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str) and "-" in value and ":" in value:
        return value
    ts = int(value)
    if ts > 10_000_000_000:
        ts = ts // 1000
    from datetime import datetime

    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def normalize_group_chat_record(payload: dict[str, Any], owner_userid: str | None = None, status: str = "active") -> dict[str, Any]:
    group_chat = payload.get("group_chat") or payload
    member_list = group_chat.get("member_list") or []
    manager_list = group_chat.get("admin_list") or []
    derived_owner = owner_userid or group_chat.get("owner") or (manager_list[0] if manager_list else "")
    return {
        "chat_id": group_chat.get("chat_id", ""),
        "group_name": group_chat.get("name", ""),
        "owner_userid": derived_owner or "",
        "notice": group_chat.get("notice", "") or "",
        "member_count": len(member_list),
        "status": status,
        "create_time": normalize_optional_timestamp(group_chat.get("create_time")) if group_chat.get("create_time") else "",
        "dismissed_at": normalize_optional_timestamp(group_chat.get("dismiss_time")) if group_chat.get("dismiss_time") else "",
        "raw_payload": json.dumps(payload, ensure_ascii=False),
    }
