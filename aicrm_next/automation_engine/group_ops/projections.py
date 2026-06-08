from __future__ import annotations

from typing import Any

from .domain import binding_stats, clean_text, normalize_group_admin_userids


def plan_list_item(plan: dict[str, Any], *, groups: list[dict[str, Any]], owner_name: str = "") -> dict[str, Any]:
    stats = binding_stats(groups)
    return {
        "id": int(plan["id"]),
        "plan_code": clean_text(plan.get("plan_code")),
        "plan_name": clean_text(plan.get("plan_name")),
        "plan_type": clean_text(plan.get("plan_type")),
        "owner_userid": clean_text(plan.get("owner_userid")),
        "owner_name": owner_name or clean_text(plan.get("owner_name")),
        "bound_group_count": stats["bound_group_count"],
        "today_estimated_reach": stats["estimated_reach"],
        "status": clean_text(plan.get("status")),
    }


def group_asset_item(group: dict[str, Any], *, plan_name: str = "", bind_status: str = "unbound") -> dict[str, Any]:
    return {
        "chat_id": clean_text(group.get("chat_id")),
        "group_name": clean_text(group.get("group_name")),
        "owner_userid": clean_text(group.get("owner_userid")),
        "owner_name": clean_text(group.get("owner_name")),
        "admin_userids": normalize_group_admin_userids(group.get("admin_userids")),
        "plan_name": plan_name,
        "bind_status": bind_status,
    }
