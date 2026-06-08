from __future__ import annotations

from typing import Any

from .state_machine import POOL_DEFINITIONS, project_member


def pool_summary(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = {pool["pool_key"]: 0 for pool in POOL_DEFINITIONS}
    for member in members:
        counts[project_member(member)["current_pool"]] += 1
    return [{**pool, "count": counts[pool["pool_key"]]} for pool in POOL_DEFINITIONS]


def overview_cards(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected = [project_member(member) for member in members]
    return [
        {"key": "total", "label": "自动化成员总数", "value": len(projected)},
        {"key": "new_user", "label": "新用户", "value": sum(item["current_pool"] == "new_user" for item in projected)},
        {"key": "unactivated", "label": "未激活", "value": sum(item["current_pool"].startswith("unactivated") for item in projected)},
        {"key": "activated", "label": "已激活", "value": sum(item["current_pool"].startswith("activated") for item in projected)},
        {"key": "priority", "label": "重点跟进", "value": sum(item["followup_type"] == "priority" for item in projected)},
        {"key": "silent", "label": "静默池", "value": sum(item["current_pool"] == "silent" for item in projected)},
        {"key": "converted", "label": "已成交", "value": sum(item["current_pool"] == "converted" for item in projected)},
        {"key": "exited", "label": "已退出", "value": sum(item["current_pool"] == "exited" for item in projected)},
    ]


def member_matches_filters(member: dict[str, Any], filters: dict[str, Any]) -> bool:
    item = project_member(member)
    pool = str(filters.get("pool") or filters.get("current_pool") or "").strip()
    followup_type = str(filters.get("followup_type") or "").strip()
    owner_userid = str(filters.get("owner_userid") or "").strip()
    keyword = str(filters.get("keyword") or "").strip()
    if pool and pool != item.get("current_pool"):
        return False
    if followup_type and followup_type != item.get("followup_type"):
        return False
    if owner_userid and owner_userid != item.get("owner_userid"):
        return False
    if keyword:
        haystack = " ".join(
            str(item.get(key) or "")
            for key in ["member_id", "person_id", "external_userid", "mobile", "customer_name", "owner_userid"]
        )
        if keyword not in haystack:
            return False
    return True


def execution_record_projection(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "record_type": record.get("record_type", "automation_conversion"),
        "member_id": record.get("member_id", ""),
        "trigger": record.get("trigger", ""),
        "status": record.get("status", "succeeded"),
        "status_label": record.get("status_label", "已记录"),
        "delivery_status": record.get("delivery_status", "fake"),
        "payload_preview": record.get("payload_preview", {}),
        "created_at": record.get("created_at", ""),
    }
