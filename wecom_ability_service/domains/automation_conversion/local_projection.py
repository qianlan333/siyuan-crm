from __future__ import annotations

from typing import Any

POOL_PENDING_QUESTIONNAIRE = "pending_questionnaire"
POOL_OPERATING = "operating"
POOL_CONVERTED = "converted"
POOL_WON = POOL_CONVERTED
POOL_REMOVED = "removed"
POOL_NO_REPLY = "no_reply"
POOL_HUMAN_REPLY = "human_reply"

POOL_LABELS = {
    POOL_PENDING_QUESTIONNAIRE: "未填问卷人群",
    POOL_OPERATING: "运营中人群",
    POOL_CONVERTED: "已转化人群",
    POOL_REMOVED: "已移出",
    POOL_NO_REPLY: "不回复池",
    POOL_HUMAN_REPLY: "人工回复池",
}

MANUAL_SEND_ALLOWED_POOLS = {
    POOL_PENDING_QUESTIONNAIRE,
    POOL_OPERATING,
    POOL_CONVERTED,
}

FOCUS_SEND_ALLOWED_POOLS = {
    POOL_OPERATING,
}

STAGE_BY_POOL = {
    POOL_PENDING_QUESTIONNAIRE: "pending_questionnaire_followup",
    POOL_OPERATING: "operating_followup",
    POOL_CONVERTED: "converted",
    POOL_REMOVED: "removed",
    POOL_NO_REPLY: "no_reply_waiting",
    POOL_HUMAN_REPLY: "human_reply_waiting",
}

TARGET_BY_POOL = {
    POOL_PENDING_QUESTIONNAIRE: "submit_questionnaire",
    POOL_OPERATING: "followup",
    POOL_CONVERTED: "post_deal",
    POOL_REMOVED: "none",
    POOL_NO_REPLY: "no_action",
    POOL_HUMAN_REPLY: "manual_reply",
}

STAGE_LABELS = {
    "pending_questionnaire_followup": "等待提交问卷",
    "operating_followup": "运营中跟进",
    "converted": "已转化",
    "removed": "已移出",
    "no_reply_waiting": "不回复待观察",
    "human_reply_waiting": "等待人工回复",
}

TARGET_LABELS = {
    "submit_questionnaire": "推动提交问卷",
    "followup": "运营跟进",
    "post_deal": "成交后维护",
    "none": "无",
    "no_action": "不自动处理",
    "manual_reply": "转人工回复",
}

STAGE_DEFINITIONS = (
    {"pool": POOL_PENDING_QUESTIONNAIRE, "route_key": "pending-questionnaire", "label": "未填问卷人群", "description": "尚未完成问卷采集，等待提交问卷。"},
    {"pool": POOL_OPERATING, "route_key": "operating", "label": "运营中人群", "description": "问卷已提交后的统一运营主人群。"},
    {"pool": POOL_CONVERTED, "route_key": "converted", "label": "已转化人群", "description": "人工确认转化后进入成交后运营。"},
)

SPECIAL_STAGE_DEFINITIONS = (
    {"pool": POOL_NO_REPLY, "route_key": "no-reply", "label": "不回复池", "description": "路由判断为无需回复时，仅记录结果，不触发后续动作。"},
    {"pool": POOL_HUMAN_REPLY, "route_key": "human-reply", "label": "人工回复池", "description": "路由判断需人工接管时进入该池，等待人工处理。"},
)

ROUTE_KEY_TO_POOL = {
    item["route_key"]: item["pool"] for item in (*STAGE_DEFINITIONS, *SPECIAL_STAGE_DEFINITIONS)
}
ROUTE_KEY_TO_POOL.update(
    {
        "new-user": POOL_PENDING_QUESTIONNAIRE,
        "inactive-normal": POOL_OPERATING,
        "inactive-focus": POOL_OPERATING,
        "active-normal": POOL_OPERATING,
        "active-focus": POOL_OPERATING,
        "silent": POOL_OPERATING,
        "won": POOL_CONVERTED,
    }
)
POOL_TO_STAGE_DEF = {item["pool"]: item for item in (*STAGE_DEFINITIONS, *SPECIAL_STAGE_DEFINITIONS)}


def _text(value: Any) -> str:
    return str(value or "").strip()


def pool_label(pool: Any) -> str:
    return POOL_LABELS.get(_text(pool), _text(pool) or "未设置")


def stage_from_pool(pool: Any) -> str:
    return STAGE_BY_POOL.get(_text(pool), "removed")


def stage_label(stage: Any) -> str:
    return STAGE_LABELS.get(_text(stage), _text(stage) or "未设置")


def target_from_pool(pool: Any) -> str:
    return TARGET_BY_POOL.get(_text(pool), "none")


def target_label(target: Any) -> str:
    return TARGET_LABELS.get(_text(target), _text(target) or "无")


def button_state(*, current_pool: Any, in_pool: Any) -> dict[str, Any]:
    normalized_current_pool = _text(current_pool)
    in_pool_bool = bool(in_pool)
    won = normalized_current_pool == POOL_WON
    ai_enabled = normalized_current_pool not in {POOL_REMOVED, POOL_NO_REPLY, POOL_HUMAN_REPLY}
    return {
        "put_in_pool": {"enabled": (not in_pool_bool) and (not won)},
        "remove_from_pool": {"enabled": in_pool_bool and not won},
        "set_focus": {"enabled": in_pool_bool and not won},
        "set_normal": {"enabled": in_pool_bool and not won},
        "mark_won": {"enabled": in_pool_bool and not won},
        "unmark_won": {"enabled": won},
        "push_openclaw": {"enabled": ai_enabled},
        "ai_push": {"enabled": ai_enabled},
    }


def manual_send_allowed_route_keys() -> set[str]:
    return {definition["route_key"] for definition in STAGE_DEFINITIONS if definition["pool"] in MANUAL_SEND_ALLOWED_POOLS}


def manual_send_stage_definition(route_key: str) -> dict[str, Any]:
    normalized_route_key = _text(route_key)
    pool = ROUTE_KEY_TO_POOL.get(normalized_route_key)
    if not pool:
        raise ValueError("invalid stage")
    if pool not in MANUAL_SEND_ALLOWED_POOLS:
        raise ValueError("focus stage must use focus send batches")
    return dict(POOL_TO_STAGE_DEF.get(pool) or {})


def focus_send_stage_definition(route_key: str) -> dict[str, Any]:
    normalized_route_key = _text(route_key)
    pool = ROUTE_KEY_TO_POOL.get(normalized_route_key)
    if not pool:
        raise ValueError("invalid stage")
    if pool not in FOCUS_SEND_ALLOWED_POOLS:
        raise ValueError("stage does not support focus send batches")
    return dict(POOL_TO_STAGE_DEF.get(pool) or {})
