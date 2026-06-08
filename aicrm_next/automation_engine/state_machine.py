from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from aicrm_next.shared.errors import ContractError

FOLLOWUP_TYPES = {"normal", "priority"}

POOL_DEFINITIONS = [
    {
        "pool_key": "new_user",
        "label": "新用户",
        "description": "新进入 CRM 且尚未打开体验课的用户。",
        "active_action_count": 0,
        "allow_broadcast": False,
    },
    {
        "pool_key": "unactivated_normal",
        "label": "未激活·普通",
        "description": "已打开体验但问卷分流为普通跟进，尚未激活。",
        "active_action_count": 1,
        "allow_broadcast": True,
    },
    {
        "pool_key": "unactivated_priority",
        "label": "未激活·重点",
        "description": "已打开体验且问卷或人工分流为重点跟进，尚未激活。",
        "active_action_count": 2,
        "allow_broadcast": True,
    },
    {
        "pool_key": "activated_normal",
        "label": "已激活·普通",
        "description": "已激活且普通跟进。",
        "active_action_count": 1,
        "allow_broadcast": True,
    },
    {
        "pool_key": "activated_priority",
        "label": "已激活·重点",
        "description": "已激活且重点跟进。",
        "active_action_count": 2,
        "allow_broadcast": True,
    },
    {
        "pool_key": "silent",
        "label": "静默池",
        "description": "当前只留存，不主动经营。",
        "active_action_count": 0,
        "allow_broadcast": False,
    },
    {
        "pool_key": "converted",
        "label": "已成交",
        "description": "人工确认成交后退出主动营销。",
        "active_action_count": 0,
        "allow_broadcast": False,
    },
    {
        "pool_key": "exited",
        "label": "已退出",
        "description": "已退出营销，不再进入主动营销。",
        "active_action_count": 0,
        "allow_broadcast": False,
    },
]

POOL_KEYS = [item["pool_key"] for item in POOL_DEFINITIONS]
POOL_LABELS = {item["pool_key"]: item["label"] for item in POOL_DEFINITIONS}
TERMINAL_POOLS = {"converted", "exited"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_valid_pool(pool_key: str) -> bool:
    return pool_key in POOL_KEYS


def normalize_followup_type(value: str | None, *, default: str = "normal") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized not in FOLLOWUP_TYPES:
        raise ContractError("followup_type must be normal or priority")
    return normalized


def effective_followup_type(member: dict[str, Any]) -> str:
    manual = str(member.get("manual_followup_type") or "").strip().lower()
    if manual:
        return normalize_followup_type(manual)
    return normalize_followup_type(str(member.get("questionnaire_followup_type") or member.get("followup_type") or "normal"))


def pool_for_member(member: dict[str, Any]) -> str:
    current = str(member.get("current_pool") or "new_user")
    if current in TERMINAL_POOLS or current == "silent":
        return current
    branch = effective_followup_type(member)
    if bool(member.get("activated")):
        return "activated_priority" if branch == "priority" else "activated_normal"
    if bool(member.get("trial_opened")):
        return "unactivated_priority" if branch == "priority" else "unactivated_normal"
    return "new_user"


def project_member(member: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(member)
    item["current_pool"] = pool_for_member(item)
    item["current_pool_label"] = POOL_LABELS.get(item["current_pool"], item["current_pool"])
    item["followup_type"] = effective_followup_type(item)
    item["trial_opened"] = bool(item.get("trial_opened"))
    item["activated"] = bool(item.get("activated"))
    item["converted"] = bool(item.get("converted"))
    item["exited"] = bool(item.get("exited"))
    item["silent"] = item["current_pool"] == "silent"
    item["can_manual_override"] = item["current_pool"] not in TERMINAL_POOLS
    item["can_confirm_conversion"] = item["current_pool"] not in TERMINAL_POOLS
    item["can_enter_silent"] = item["current_pool"] not in TERMINAL_POOLS and item["current_pool"] != "silent"
    item["can_exit_marketing"] = item["current_pool"] not in TERMINAL_POOLS
    item.setdefault("next_action", next_action_for_pool(item["current_pool"]))
    return item


def next_action_for_pool(pool_key: str) -> dict[str, str]:
    if pool_key.startswith("unactivated"):
        return {"type": "activation_nudge", "label": "提醒激活"}
    if pool_key.startswith("activated"):
        return {"type": "conversion_followup", "label": "成交跟进"}
    if pool_key == "new_user":
        return {"type": "wait_trial_opened", "label": "等待体验打开"}
    if pool_key == "silent":
        return {"type": "hold", "label": "静默留存"}
    return {"type": "none", "label": "停止主动经营"}


def transition_history(
    *,
    member: dict[str, Any],
    before_pool: str,
    after_pool: str,
    trigger: str,
    source: str,
    operator: str,
    reason: str,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": f"hist_{member['member_id']}_{len(member.get('history', [])) + 1}",
        "member_id": member["member_id"],
        "before_pool": before_pool,
        "after_pool": after_pool,
        "trigger": trigger,
        "source": source,
        "operator": operator,
        "reason": reason,
        "occurred_at": occurred_at or utc_now_iso(),
    }


def apply_transition(
    member: dict[str, Any],
    *,
    trigger: str,
    source: str = "fixture",
    operator: str = "system",
    reason: str = "",
    occurred_at: str | None = None,
    patch: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = deepcopy(member)
    before_pool = project_member(updated)["current_pool"]
    if before_pool in TERMINAL_POOLS and trigger not in {"confirm_conversion", "exit_marketing"}:
        history = transition_history(
            member=updated,
            before_pool=before_pool,
            after_pool=before_pool,
            trigger=trigger,
            source=source,
            operator=operator,
            reason=reason or "terminal_pool_noop",
            occurred_at=occurred_at,
        )
        updated.setdefault("warnings", []).append("terminal_pool_noop")
        updated.setdefault("history", []).append(history)
        return project_member(updated), history

    for key, value in (patch or {}).items():
        updated[key] = value

    if trigger == "confirm_conversion":
        updated["converted"] = True
        updated["exited"] = True
        updated["current_pool"] = "converted"
    elif trigger == "enter_silent":
        updated["silent"] = True
        updated["current_pool"] = "silent"
    elif trigger == "exit_marketing":
        updated["exited"] = True
        updated["current_pool"] = "exited"
    else:
        updated["current_pool"] = pool_for_member(updated)

    updated["latest_event_at"] = occurred_at or utc_now_iso()
    after_pool = project_member(updated)["current_pool"]
    history = transition_history(
        member=updated,
        before_pool=before_pool,
        after_pool=after_pool,
        trigger=trigger,
        source=source,
        operator=operator,
        reason=reason,
        occurred_at=occurred_at,
    )
    updated.setdefault("history", []).append(history)
    return project_member(updated), history
