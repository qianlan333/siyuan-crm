from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from flask import current_app

from ...db import get_db
from ...infra.json_utils import safe_json_loads as _json_loads
from ...application.class_user.commands import (
    ApplyClassUserStatusChangeCommand,
    ClearClassUserStatusCurrentCommand,
)
from ...application.class_user.dto import (
    ApplyClassUserStatusChangeCommandDTO,
    ClearClassUserStatusCurrentCommandDTO,
    GetClassUserStatusCurrentQueryDTO,
    GetClassUserStatusDefinitionQueryDTO,
)
from ...application.class_user.queries import (
    GetClassUserStatusCurrentQuery,
    GetClassUserStatusDefinitionQuery,
)
from ...infra.settings import get_setting
from ..automation_state.calculator import (
    calculate_marketing_state as _calculate_marketing_state,
    resolve_pool_key_for_customer as _shared_resolve_pool_key_for_customer,
    resolve_pool_reference_at as _shared_resolve_pool_reference_at,
    should_enter_silent_pool as _shared_should_enter_silent_pool,
)
from ..automation_state.state_defs import (
    FOLLOWUP_SEGMENT_FOCUS as SHARED_FOLLOWUP_SEGMENT_FOCUS,
    FOLLOWUP_SEGMENT_LABELS as SHARED_FOLLOWUP_SEGMENT_LABELS,
    FOLLOWUP_SEGMENT_NORMAL as SHARED_FOLLOWUP_SEGMENT_NORMAL,
    FOLLOWUP_SEGMENT_UNKNOWN as SHARED_FOLLOWUP_SEGMENT_UNKNOWN,
    FOCUS_POOL_KEYS as SHARED_FOCUS_POOL_KEYS,
    POOL_ACTIVE_FOCUS as SHARED_POOL_ACTIVE_FOCUS,
    POOL_ACTIVE_NORMAL as SHARED_POOL_ACTIVE_NORMAL,
    POOL_INACTIVE_FOCUS as SHARED_POOL_INACTIVE_FOCUS,
    POOL_INACTIVE_NORMAL as SHARED_POOL_INACTIVE_NORMAL,
    POOL_LABELS as SHARED_POOL_LABELS,
    POOL_NEW_USER as SHARED_POOL_NEW_USER,
    POOL_SILENT as SHARED_POOL_SILENT,
)
from ..archive import repo as archive_repo
from ..archive.service import extract_roomid_from_raw_payload, format_message_row, get_recent_messages_by_user
from ..group_chats.repo import get_group_chat_map
from ..questionnaire.service import get_questionnaire_detail
from ..tasks.service import dispatch_wecom_task  # noqa: F401 - legacy campaign dispatch monkeypatch seam
from .presenter import business_marketing_display
from ._repo_helpers import (
    _normalize_bool,
    _normalize_int,
    _normalized_json_text_list,
    _normalized_text,
    _nullable_timestamp_text,
)
from . import repo

DEFAULT_SCENARIO_KEY = "signup_conversion_v1"
DEFAULT_AUTOMATION_NAME = "自动化转化问卷初判"
DEFAULT_TARGET_EVENT = "signup_success"
DEFAULT_CHANNEL_TYPE = "text_message"
DEFAULT_CORE_THRESHOLD = 3
DEFAULT_TOP_THRESHOLD = 4
DEFAULT_DAY_START_HOUR = 9
DEFAULT_QUIET_HOUR_START = 23
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ENROLLED_SIGNUP_STATUS = "signed_999"
VALUE_SEGMENT_SCORING_VERSION = "signup_conversion_question_hits_v1"
_VALUE_SEGMENT_RANKS = {"unknown": 0, "normal": 1, "core": 2, "top": 3}
DEFAULT_AUTOMATION_OWNER_USERID = "HuangYouCan"

FOLLOWUP_SEGMENT_UNKNOWN = SHARED_FOLLOWUP_SEGMENT_UNKNOWN
FOLLOWUP_SEGMENT_NORMAL = SHARED_FOLLOWUP_SEGMENT_NORMAL
FOLLOWUP_SEGMENT_FOCUS = SHARED_FOLLOWUP_SEGMENT_FOCUS

POOL_STAGE = "pool"
POOL_NEW_USER = SHARED_POOL_NEW_USER
POOL_INACTIVE_NORMAL = SHARED_POOL_INACTIVE_NORMAL
POOL_INACTIVE_FOCUS = SHARED_POOL_INACTIVE_FOCUS
POOL_ACTIVE_NORMAL = SHARED_POOL_ACTIVE_NORMAL
POOL_ACTIVE_FOCUS = SHARED_POOL_ACTIVE_FOCUS
POOL_SILENT = SHARED_POOL_SILENT

DEFAULT_SILENT_THRESHOLD_DAYS = 7
DEFAULT_SILENT_THRESHOLD_DAYS_BY_POOL = {
    POOL_NEW_USER: DEFAULT_SILENT_THRESHOLD_DAYS,
    POOL_INACTIVE_NORMAL: DEFAULT_SILENT_THRESHOLD_DAYS,
    POOL_INACTIVE_FOCUS: DEFAULT_SILENT_THRESHOLD_DAYS,
    POOL_ACTIVE_NORMAL: DEFAULT_SILENT_THRESHOLD_DAYS,
    POOL_ACTIVE_FOCUS: DEFAULT_SILENT_THRESHOLD_DAYS,
}

_FOLLOWUP_SEGMENT_LABELS = SHARED_FOLLOWUP_SEGMENT_LABELS
_POOL_LABELS = SHARED_POOL_LABELS
_POOL_STAGE_KEYS = {f"{POOL_STAGE}/{pool_key}" for pool_key in _POOL_LABELS}
_ACTIONABLE_POOL_STAGE_KEYS = {
    f"{POOL_STAGE}/{POOL_INACTIVE_FOCUS}",
    f"{POOL_STAGE}/{POOL_ACTIVE_FOCUS}",
}
_SILENT_ELIGIBLE_POOL_KEYS = set(DEFAULT_SILENT_THRESHOLD_DAYS_BY_POOL)

_EXIT_SIGNUP_PREFIXES = ("signed_",)
_HIGH_INTENT_TAG_KEYWORDS = ("高意向", "待跟进", "已报价", "课程安排", "想报名")
_VALUE_SEGMENT_LABELS = {"unknown": "未知", "top": "Top", "core": "Core", "normal": "普通"}
_PHASE_LABELS = {
    "awaiting_trigger": "待触发",
    "waiting_openclaw": "待 OpenClaw 处理",
    "blocked_after_2300": "自动启动时间窗外",
    "exited_signup_success": "已确认成交，退出全部营销",
}
_CUSTOMER_MARKETING_STATE_LABELS = {
    (POOL_STAGE, POOL_NEW_USER): _POOL_LABELS[POOL_NEW_USER],
    (POOL_STAGE, POOL_INACTIVE_NORMAL): _POOL_LABELS[POOL_INACTIVE_NORMAL],
    (POOL_STAGE, POOL_INACTIVE_FOCUS): _POOL_LABELS[POOL_INACTIVE_FOCUS],
    (POOL_STAGE, POOL_ACTIVE_NORMAL): _POOL_LABELS[POOL_ACTIVE_NORMAL],
    (POOL_STAGE, POOL_ACTIVE_FOCUS): _POOL_LABELS[POOL_ACTIVE_FOCUS],
    (POOL_STAGE, POOL_SILENT): _POOL_LABELS[POOL_SILENT],
    ("converted", "enrolled"): "已确认成交",
}
_ROUTER_ALLOWED_STAGE_KEYS = set(_ACTIONABLE_POOL_STAGE_KEYS)
_ROUTER_TERMINAL_DISPATCH_STATUSES = {"dispatched", "acked", "cancelled", "converted_before_dispatch"}
_ROUTER_BLOCKED_DISPATCH_STATUS = "blocked_quiet_hours"
_ROUTER_PENDING_DISPATCH_STATUS = "pending"
_OPENCLAW_ACKABLE_DISPATCH_STATUSES = {"pending", "dispatched", "acked"}
_POOL_SENDABLE_POOL_KEYS = {
    POOL_NEW_USER,
    POOL_INACTIVE_NORMAL,
    POOL_INACTIVE_FOCUS,
    POOL_ACTIVE_NORMAL,
    POOL_ACTIVE_FOCUS,
}


def _get_class_user_status_definition(signup_status: str) -> dict[str, Any] | None:
    return GetClassUserStatusDefinitionQuery()(
        GetClassUserStatusDefinitionQueryDTO(signup_status=str(signup_status or "").strip())
    )


def _get_class_user_status_current(external_userid: str) -> dict[str, Any] | None:
    return GetClassUserStatusCurrentQuery()(
        GetClassUserStatusCurrentQueryDTO(external_userid=str(external_userid or "").strip())
    )


def _apply_class_user_status_change(
    *,
    external_userid: str,
    signup_status: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> dict[str, Any]:
    return ApplyClassUserStatusChangeCommand()(
        ApplyClassUserStatusChangeCommandDTO(
            external_userid=str(external_userid or "").strip(),
            signup_status=str(signup_status or "").strip(),
            set_by_userid=str(set_by_userid or "").strip(),
            customer_name_snapshot=str(customer_name_snapshot or "").strip(),
            owner_userid_snapshot=str(owner_userid_snapshot or "").strip(),
            mobile_snapshot=str(mobile_snapshot or "").strip(),
        )
    )


def _clear_class_user_status_current(
    *,
    external_userid: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> None:
    return ClearClassUserStatusCurrentCommand()(
        ClearClassUserStatusCurrentCommandDTO(
            external_userid=str(external_userid or "").strip(),
            set_by_userid=str(set_by_userid or "").strip(),
            customer_name_snapshot=str(customer_name_snapshot or "").strip(),
            owner_userid_snapshot=str(owner_userid_snapshot or "").strip(),
            mobile_snapshot=str(mobile_snapshot or "").strip(),
        )
    )
_FOCUS_POOL_KEYS = set(SHARED_FOCUS_POOL_KEYS)

automation_webhook_logger = logging.getLogger("automation_webhook")
logger = logging.getLogger(__name__)


def _get_active_owner_role(userid: str) -> dict[str, Any]:
    owner_role = dict(repo.get_owner_role_item(_normalized_text(userid)) or {})
    if not owner_role or not bool(owner_role.get("active")):
        return {}
    return owner_role


def _normalize_option_id_list(value: Any) -> list[int]:
    raw_value = value
    if isinstance(value, str):
        raw_value = _json_loads(value, default=None)
    if not isinstance(raw_value, list):
        raise ValueError("hit_option_ids_json must be an array")
    result: list[int] = []
    seen: set[int] = set()
    for item in raw_value:
        option_id = _normalize_int(item, "hit_option_ids_json item", minimum=1)
        if option_id in seen:
            continue
        seen.add(int(option_id))
        result.append(int(option_id))
    if not result:
        raise ValueError("hit_option_ids_json must contain at least one option id")
    return result


def _validate_timezone(value: Any) -> str:
    timezone = _normalized_text(value) or DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone is invalid") from exc
    return timezone


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = _normalized_text(value)
    if not text:
        return None
    import re as _re
    text = _re.sub(r"[+-]\d{2}(:\d{2})?$", "", text).rstrip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_silent_threshold_days_by_pool() -> dict[str, int]:
    return {key: int(value) for key, value in DEFAULT_SILENT_THRESHOLD_DAYS_BY_POOL.items()}


def _normalize_silent_threshold_days_by_pool(value: Any) -> dict[str, int]:
    result = _default_silent_threshold_days_by_pool()
    raw_value = _json_loads(value, default={})
    if not isinstance(raw_value, dict):
        return result
    for pool_key in DEFAULT_SILENT_THRESHOLD_DAYS_BY_POOL:
        if pool_key not in raw_value:
            continue
        threshold = _normalize_int(
            raw_value.get(pool_key),
            f"silent_threshold_days_by_pool.{pool_key}",
            minimum=1,
        )
        assert threshold is not None
        result[pool_key] = int(threshold)
    return result


def _normalize_followup_segment(
    value: Any,
    *,
    allow_unknown: bool = True,
) -> str:
    normalized = _normalized_text(value).lower()
    alias_map = {
        "unknown": FOLLOWUP_SEGMENT_UNKNOWN,
        "unclassified": FOLLOWUP_SEGMENT_UNKNOWN,
        "normal": FOLLOWUP_SEGMENT_NORMAL,
        "普通": FOLLOWUP_SEGMENT_NORMAL,
        "普通跟进": FOLLOWUP_SEGMENT_NORMAL,
        "focus": FOLLOWUP_SEGMENT_FOCUS,
        "core": FOLLOWUP_SEGMENT_FOCUS,
        "top": FOLLOWUP_SEGMENT_FOCUS,
        "高意向": FOLLOWUP_SEGMENT_FOCUS,
        "重点": FOLLOWUP_SEGMENT_FOCUS,
        "重点跟进": FOLLOWUP_SEGMENT_FOCUS,
    }
    if not normalized:
        return FOLLOWUP_SEGMENT_UNKNOWN if allow_unknown else FOLLOWUP_SEGMENT_NORMAL
    mapped = alias_map.get(normalized, normalized if normalized in _FOLLOWUP_SEGMENT_LABELS else "")
    if mapped:
        return mapped
    return FOLLOWUP_SEGMENT_UNKNOWN if allow_unknown else FOLLOWUP_SEGMENT_NORMAL


def _followup_segment_label(segment: Any) -> str:
    normalized = _normalize_followup_segment(segment)
    return _FOLLOWUP_SEGMENT_LABELS.get(normalized, _FOLLOWUP_SEGMENT_LABELS[FOLLOWUP_SEGMENT_UNKNOWN])


def _followup_segment_from_value_segment(value_segment: Any) -> str:
    normalized = _normalized_text(value_segment).lower()
    if normalized in {"core", "top"}:
        return FOLLOWUP_SEGMENT_FOCUS
    if normalized == "normal":
        return FOLLOWUP_SEGMENT_NORMAL
    return FOLLOWUP_SEGMENT_UNKNOWN


def _pool_label(pool_key: Any) -> str:
    return _POOL_LABELS.get(_normalized_text(pool_key), "")


def _pool_stage_key(pool_key: Any) -> str:
    normalized_pool_key = _normalized_text(pool_key)
    if not normalized_pool_key:
        return ""
    return f"{POOL_STAGE}/{normalized_pool_key}"


def _pool_segment_from_pool_key(pool_key: Any) -> str:
    normalized_pool_key = _normalized_text(pool_key)
    if normalized_pool_key in {POOL_INACTIVE_FOCUS, POOL_ACTIVE_FOCUS}:
        return FOLLOWUP_SEGMENT_FOCUS
    if normalized_pool_key in {POOL_INACTIVE_NORMAL, POOL_ACTIVE_NORMAL}:
        return FOLLOWUP_SEGMENT_NORMAL
    return FOLLOWUP_SEGMENT_UNKNOWN


def _resolve_pool_key_for_customer(
    *,
    has_questionnaire_submission: bool,
    trial_opened: bool,
    activated: bool,
    followup_segment: str,
) -> str:
    return _shared_resolve_pool_key_for_customer(
        has_questionnaire_submission=has_questionnaire_submission,
        trial_opened=trial_opened,
        activated=activated,
        current_segment=_normalize_followup_segment(followup_segment, allow_unknown=False),
    )


def _resolve_silent_threshold_days(config: dict[str, Any], *, pool_key: str) -> int:
    thresholds = _normalize_silent_threshold_days_by_pool(config.get("silent_threshold_days_by_pool"))
    return int(thresholds.get(_normalized_text(pool_key)) or DEFAULT_SILENT_THRESHOLD_DAYS)


def _resolve_manual_followup_segment(
    *,
    existing_state: dict[str, Any] | None,
    state_payload_overrides: dict[str, Any] | None,
) -> str:
    override_payload = dict(state_payload_overrides or {})
    override_value = override_payload.get("manual_followup_segment")
    if override_value is None:
        override_value = override_payload.get("manual_followup_judgement")
    if override_value is not None:
        normalized = _normalize_followup_segment(override_value)
        return "" if normalized == FOLLOWUP_SEGMENT_UNKNOWN else normalized
    existing_payload = dict((existing_state or {}).get("state_payload") or {})
    normalized = _normalize_followup_segment(
        existing_payload.get("manual_followup_segment") or existing_payload.get("manual_followup_judgement")
    )
    return "" if normalized == FOLLOWUP_SEGMENT_UNKNOWN else normalized


def _should_enter_silent_pool(*, entered_at: str, threshold_days: int, now_text: str) -> bool:
    return _shared_should_enter_silent_pool(
        entered_at=entered_at,
        silent_threshold_days=threshold_days,
        now=now_text,
    )


def _resolve_pool_reference_at(
    *,
    pool_key: str,
    trial_opened_at: str,
    submission_at: str,
    activation_at: str,
    message_at: str,
    fallback_now: str,
) -> str:
    return _shared_resolve_pool_reference_at(
        pool_key=pool_key,
        trial_opened_at=trial_opened_at,
        submission_at=submission_at,
        activation_at=activation_at,
        last_message_at=message_at,
        now=fallback_now,
    )


def _default_config_payload(*, automation_key: str = DEFAULT_SCENARIO_KEY) -> dict[str, Any]:
    return {
        "automation_key": automation_key,
        "automation_name": DEFAULT_AUTOMATION_NAME,
        "target_event": DEFAULT_TARGET_EVENT,
        "channel_type": DEFAULT_CHANNEL_TYPE,
        "enabled": True,
        "questionnaire_id": None,
        "questionnaire_missing": False,
        "missing_questionnaire_id": None,
        "core_threshold": DEFAULT_CORE_THRESHOLD,
        "top_threshold": DEFAULT_TOP_THRESHOLD,
        "day_start_hour": DEFAULT_DAY_START_HOUR,
        "quiet_hour_start": DEFAULT_QUIET_HOUR_START,
        "timezone": DEFAULT_TIMEZONE,
        "silent_threshold_days_by_pool": _default_silent_threshold_days_by_pool(),
        "question_rules": [],
        "configured": False,
        "created_at": "",
        "updated_at": "",
}


def _format_auto_start_window(day_start_hour: int, quiet_hour_start: int) -> str:
    return f"{int(day_start_hour):02d}:00 - {int(quiet_hour_start):02d}:00"


def _is_within_auto_start_window(*, hour: int, day_start_hour: int, quiet_hour_start: int) -> bool:
    normalized_hour = int(hour)
    return int(day_start_hour) <= normalized_hour < int(quiet_hour_start)


def _segment_rank(segment: str) -> int:
    return _VALUE_SEGMENT_RANKS.get(_normalized_text(segment), 0)


def _questionnaire_lookup_optional(
    questionnaire_id: int,
) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[int, dict[int, dict[str, Any]]]] | None:
    questionnaire = get_questionnaire_detail(int(questionnaire_id))
    if not questionnaire:
        return None
    question_map: dict[int, dict[str, Any]] = {}
    option_map: dict[int, dict[int, dict[str, Any]]] = {}
    for question in questionnaire.get("questions") or []:
        question_id = int(question["id"])
        question_map[question_id] = dict(question)
        option_map[question_id] = {int(option["id"]): dict(option) for option in question.get("options") or []}
    return questionnaire, question_map, option_map


def _questionnaire_lookup(questionnaire_id: int) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[int, dict[int, dict[str, Any]]]]:
    lookup = _questionnaire_lookup_optional(int(questionnaire_id))
    if not lookup:
        raise ValueError("questionnaire not found")
    return lookup


def _questionnaire_has_required_mobile_question(questionnaire: dict[str, Any]) -> bool:
    for question in questionnaire.get("questions") or []:
        if _normalized_text(question.get("type")) != "mobile":
            continue
        if _normalize_bool(question.get("required"), default=False):
            return True
    return False


def _serialize_question_rule(
    row: dict[str, Any],
    *,
    question_map: dict[int, dict[str, Any]] | None = None,
    option_map: dict[int, dict[int, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    questionnaire_question_id = int(row.get("question_id") or row.get("questionnaire_question_id") or 0)
    hit_option_ids = [
        int(option_id)
        for option_id in _json_loads(row.get("answer_match_value_json") or row.get("hit_option_ids_json"), default=[])
        if str(option_id).strip()
    ]
    question = (question_map or {}).get(questionnaire_question_id, {})
    available_options = (option_map or {}).get(questionnaire_question_id, {})
    return {
        "id": int(row.get("id") or 0),
        "questionnaire_id": _normalize_int(row.get("questionnaire_id"), "questionnaire_id", allow_none=True),
        "questionnaire_question_id": questionnaire_question_id,
        "question_title": _normalized_text(question.get("title")) or _normalized_text(row.get("rule_name")),
        "question_type": _normalized_text(question.get("type")),
        "hit_option_ids_json": hit_option_ids,
        "hit_options": [
            {"id": option_id, "option_text": _normalized_text(available_options.get(option_id, {}).get("option_text"))}
            for option_id in hit_option_ids
        ],
        "sort_order": int(row.get("sort_order") or 0),
    }


def list_signup_conversion_question_rules(*, automation_key: str = DEFAULT_SCENARIO_KEY) -> list[dict[str, Any]]:
    config_row = repo.get_marketing_automation_config(automation_key)
    if not config_row:
        return []
    payload = _json_loads(config_row.get("config_payload_json"), default={})
    questionnaire_id = _normalize_int(payload.get("questionnaire_id"), "questionnaire_id", allow_none=True)
    question_map: dict[int, dict[str, Any]] = {}
    option_map: dict[int, dict[int, dict[str, Any]]] = {}
    if questionnaire_id:
        lookup = _questionnaire_lookup_optional(int(questionnaire_id))
        if not lookup:
            return []
        _, question_map, option_map = lookup
    return [
        _serialize_question_rule(item, question_map=question_map, option_map=option_map)
        for item in repo.list_marketing_automation_question_rules(int(config_row["id"]))
    ]


def get_signup_conversion_config(*, automation_key: str = DEFAULT_SCENARIO_KEY) -> dict[str, Any]:
    defaults = _default_config_payload(automation_key=automation_key)
    row = repo.get_marketing_automation_config(automation_key)
    if not row:
        return defaults
    payload = _json_loads(row.get("config_payload_json"), default={})
    questionnaire_id = _normalize_int(payload.get("questionnaire_id"), "questionnaire_id", allow_none=True)
    questionnaire_lookup = _questionnaire_lookup_optional(int(questionnaire_id)) if questionnaire_id else None
    questionnaire_missing = bool(questionnaire_id and questionnaire_lookup is None)
    result = {
        "automation_key": _normalized_text(row.get("automation_key")) or automation_key,
        "automation_name": _normalized_text(row.get("automation_name")) or DEFAULT_AUTOMATION_NAME,
        "target_event": _normalized_text(row.get("target_event")) or DEFAULT_TARGET_EVENT,
        "channel_type": _normalized_text(row.get("channel_type")) or DEFAULT_CHANNEL_TYPE,
        "enabled": _normalized_text(row.get("status")).lower() == "active",
        "questionnaire_id": None if questionnaire_missing else questionnaire_id,
        "questionnaire_missing": questionnaire_missing,
        "missing_questionnaire_id": questionnaire_id if questionnaire_missing else None,
        "core_threshold": _normalize_int(payload.get("core_threshold"), "core_threshold", default=DEFAULT_CORE_THRESHOLD),
        "top_threshold": _normalize_int(payload.get("top_threshold"), "top_threshold", default=DEFAULT_TOP_THRESHOLD),
        "day_start_hour": _normalize_int(
            payload.get("day_start_hour"),
            "day_start_hour",
            default=DEFAULT_DAY_START_HOUR,
            minimum=0,
            maximum=23,
        ),
        "quiet_hour_start": _normalize_int(
            row.get("do_not_start_after_hour"),
            "quiet_hour_start",
            default=DEFAULT_QUIET_HOUR_START,
            minimum=0,
            maximum=23,
        ),
        "timezone": _validate_timezone(payload.get("timezone") or DEFAULT_TIMEZONE),
        "silent_threshold_days_by_pool": _normalize_silent_threshold_days_by_pool(payload.get("silent_threshold_days_by_pool")),
        "question_rules": list_signup_conversion_question_rules(automation_key=automation_key),
        "configured": True,
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }
    return result


def _normalize_question_rules(
    rules: Any,
    *,
    questionnaire_id: int,
    question_map: dict[int, dict[str, Any]],
    option_map: dict[int, dict[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise ValueError("question_rules must be an array")
    if not rules:
        raise ValueError("question_rules must contain at least one item")
    normalized_rules: list[dict[str, Any]] = []
    seen_question_ids: set[int] = set()
    for index, item in enumerate(rules, start=1):
        if not isinstance(item, dict):
            raise ValueError("question rule must be an object")
        question_id = _normalize_int(item.get("questionnaire_question_id"), "questionnaire_question_id", minimum=1)
        assert question_id is not None
        if question_id in seen_question_ids:
            raise ValueError("question_rules cannot contain duplicate questionnaire_question_id")
        seen_question_ids.add(question_id)
        question = question_map.get(int(question_id))
        if not question:
            raise ValueError(f"question {question_id} does not belong to questionnaire {questionnaire_id}")
        if _normalized_text(question.get("type")) not in {"single_choice", "multi_choice"}:
            raise ValueError(f"question {question_id} does not support option matching")
        available_options = option_map.get(int(question_id), {})
        hit_option_ids = _normalize_option_id_list(item.get("hit_option_ids_json"))
        invalid_option_ids = [option_id for option_id in hit_option_ids if option_id not in available_options]
        if invalid_option_ids:
            raise ValueError(f"option {invalid_option_ids[0]} does not belong to question {question_id}")
        sort_order = _normalize_int(item.get("sort_order"), "sort_order", default=index, minimum=1)
        assert sort_order is not None
        normalized_rules.append(
            {
                "questionnaire_question_id": int(question_id),
                "hit_option_ids_json": hit_option_ids,
                "sort_order": int(sort_order),
                "rule_code": f"question-{question_id}",
                "rule_name": _normalized_text(question.get("title")) or f"question-{question_id}",
                "rule_payload": {"questionnaire_id": int(questionnaire_id)},
            }
        )
    normalized_rules.sort(key=lambda item: (item["sort_order"], item["questionnaire_question_id"]))
    return normalized_rules


def save_signup_conversion_config(
    payload: dict[str, Any],
    *,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    enforce_required_mobile_question: bool = False,
) -> dict[str, Any]:
    existing = get_signup_conversion_config(automation_key=automation_key)
    raw_payload = payload or {}
    questionnaire_id = _normalize_int(
        raw_payload.get("questionnaire_id", existing.get("questionnaire_id")),
        "questionnaire_id",
        minimum=1,
    )
    assert questionnaire_id is not None
    core_threshold = _normalize_int(
        raw_payload.get("core_threshold", existing.get("core_threshold")),
        "core_threshold",
        default=DEFAULT_CORE_THRESHOLD,
        minimum=0,
    )
    top_threshold = _normalize_int(
        raw_payload.get("top_threshold", existing.get("top_threshold")),
        "top_threshold",
        default=DEFAULT_TOP_THRESHOLD,
        minimum=0,
    )
    assert core_threshold is not None
    assert top_threshold is not None
    if top_threshold < core_threshold:
        raise ValueError("top_threshold must be >= core_threshold")
    quiet_hour_start = _normalize_int(
        raw_payload.get("quiet_hour_start", existing.get("quiet_hour_start")),
        "quiet_hour_start",
        default=DEFAULT_QUIET_HOUR_START,
        minimum=0,
        maximum=23,
    )
    day_start_hour = _normalize_int(
        raw_payload.get("day_start_hour", existing.get("day_start_hour")),
        "day_start_hour",
        default=DEFAULT_DAY_START_HOUR,
        minimum=0,
        maximum=23,
    )
    assert quiet_hour_start is not None
    assert day_start_hour is not None
    if int(day_start_hour) >= int(quiet_hour_start):
        raise ValueError("day_start_hour must be < quiet_hour_start")
    timezone = _validate_timezone(raw_payload.get("timezone", existing.get("timezone")))
    silent_threshold_days_by_pool = _normalize_silent_threshold_days_by_pool(
        raw_payload.get("silent_threshold_days_by_pool", existing.get("silent_threshold_days_by_pool"))
    )
    enabled = _normalize_bool(raw_payload.get("enabled", existing.get("enabled")), default=True)
    questionnaire, question_map, option_map = _questionnaire_lookup(int(questionnaire_id))
    if enforce_required_mobile_question and not _questionnaire_has_required_mobile_question(questionnaire):
        raise ValueError("selected questionnaire must contain a required mobile question")
    question_rules = _normalize_question_rules(
        raw_payload.get("question_rules", existing.get("question_rules")),
        questionnaire_id=int(questionnaire_id),
        question_map=question_map,
        option_map=option_map,
    )
    db = get_db()
    try:
        row = repo.upsert_marketing_automation_config(
            automation_key=automation_key,
            automation_name=DEFAULT_AUTOMATION_NAME,
            target_event=DEFAULT_TARGET_EVENT,
            channel_type=DEFAULT_CHANNEL_TYPE,
            status="active" if enabled else "disabled",
            do_not_start_after_hour=int(quiet_hour_start),
            config_payload={
                "questionnaire_id": int(questionnaire_id),
                "core_threshold": int(core_threshold),
                "top_threshold": int(top_threshold),
                "day_start_hour": int(day_start_hour),
                "timezone": timezone,
                "silent_threshold_days_by_pool": silent_threshold_days_by_pool,
            },
        )
        repo.replace_marketing_automation_question_rules(
            automation_config_id=int(row["id"]),
            questionnaire_id=int(questionnaire_id),
            rules=question_rules,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_signup_conversion_config(automation_key=automation_key)


def _matched_question_rule_items(
    config: dict[str, Any],
    *,
    matched_question_ids: list[int],
) -> list[dict[str, Any]]:
    matched_question_id_set = {
        int(question_id)
        for question_id in matched_question_ids
        if str(question_id).strip()
    }
    if not matched_question_id_set:
        return []
    items: list[dict[str, Any]] = []
    for rule in config.get("question_rules") or []:
        question_id = int(rule.get("questionnaire_question_id") or 0)
        if question_id <= 0 or question_id not in matched_question_id_set:
            continue
        items.append(
            {
                "questionnaire_question_id": question_id,
                "question_title": _normalized_text(rule.get("question_title")),
                "hit_option_ids_json": [
                    int(option_id)
                    for option_id in rule.get("hit_option_ids_json") or []
                    if str(option_id).strip()
                ],
                "hit_options": [dict(item) for item in rule.get("hit_options") or [] if isinstance(item, dict)],
                "sort_order": int(rule.get("sort_order") or 0),
            }
        )
    return items


def _preview_ineligible_reason(marketing_state: dict[str, Any]) -> str:
    if bool(marketing_state.get("eligible_for_conversion")):
        return ""
    return (
        _normalized_text(marketing_state.get("exit_reason"))
        or _normalized_text(marketing_state.get("sub_stage"))
        or "not_eligible"
    )


def _setting_text(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _setting_int(key: str, *, default: int) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    value = _normalize_int(raw_value, key, default=default, minimum=1)
    assert value is not None
    return int(value)


def _bearer_headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    normalized_token = _normalized_text(token)
    if normalized_token:
        headers["Authorization"] = f"Bearer {normalized_token}"
    return headers


def _match_active_dnd_reasons(
    item: dict[str, Any],
    *,
    dnd_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    external_userid = _normalized_text(item.get("external_userid"))
    mobile = _normalized_text(item.get("mobile"))
    reasons: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in dnd_rows:
        row_external_userid = _normalized_text(row.get("external_userid"))
        row_mobile = _normalized_text(row.get("mobile"))
        if external_userid and row_external_userid == external_userid:
            pass
        elif mobile and row_mobile == mobile:
            pass
        else:
            continue
        reason_key = (
            _normalized_text(row.get("source_type")),
            _normalized_text(row.get("reason_code")),
            _normalized_text(row.get("reason_text")),
        )
        if reason_key in seen:
            continue
        seen.add(reason_key)
        reasons.append(
            {
                "source_type": reason_key[0],
                "reason_code": reason_key[1],
                "reason_text": reason_key[2],
            }
        )
    return reasons


def _pool_send_selection(*, owner_userid: str, pool_key: str) -> list[dict[str, Any]]:
    normalized_owner_userid = _normalized_text(owner_userid) or DEFAULT_AUTOMATION_OWNER_USERID
    rows = repo.list_pool_batch_send_candidates(pool_key)
    dnd_rows = repo.list_active_do_not_disturb_rows(
        external_userids=[_normalized_text(item.get("external_userid")) for item in rows],
        mobiles=[_normalized_text(item.get("person_mobile")) for item in rows],
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        state_payload = _json_loads(row.get("state_payload_json"), default={})
        if not isinstance(state_payload, dict):
            state_payload = {}
        final_owner_userid = (
            _normalized_text(row.get("contact_owner_userid"))
            or _normalized_text(state_payload.get("pool_owner_userid"))
            or DEFAULT_AUTOMATION_OWNER_USERID
        )
        if final_owner_userid != normalized_owner_userid:
            continue
        item = {
            "id": int(row.get("marketing_state_id") or 0),
            "person_id": _normalize_int(row.get("person_id"), "person_id", allow_none=True),
            "external_userid": _normalized_text(row.get("external_userid")),
            "customer_name": _normalized_text(row.get("customer_name")) or _normalized_text(row.get("external_userid")),
            "owner_userid": final_owner_userid,
            "owner_display_name": _normalized_text(row.get("owner_display_name")) or final_owner_userid,
            "mobile": _normalized_text(row.get("person_mobile")) or _normalized_text(state_payload.get("mobile")),
            "entered_at": _normalized_text(row.get("entered_at")),
            "last_activation_at": _normalized_text(row.get("last_activation_at")),
            "pool_key": _normalized_text(state_payload.get("pool_key")) or _normalized_text(pool_key),
            "pool_label": _normalized_text(state_payload.get("pool_label")) or _pool_label(pool_key),
        }
        dnd_reasons = _match_active_dnd_reasons(item, dnd_rows=dnd_rows)
        item["do_not_disturb"] = bool(dnd_reasons)
        item["do_not_disturb_reasons"] = dnd_reasons
        items.append(item)
    return items


def _validate_send_owner_userid(owner_userid: str) -> tuple[str, dict[str, Any]]:
    normalized_owner_userid = _normalized_text(owner_userid) or DEFAULT_AUTOMATION_OWNER_USERID
    owner_role = _get_active_owner_role(normalized_owner_userid)
    if not owner_role:
        raise ValueError("owner_userid is invalid")
    return normalized_owner_userid, owner_role


def _build_pool_send_plan(
    *,
    owner_userid: str,
    pool_key: str,
    apply_frequency_budget: bool = True,
    budget_channels: tuple[str, ...] = ("wecom_private",),
    budget_program_codes: tuple[str, ...] = (DEFAULT_SCENARIO_KEY,),
) -> dict[str, Any]:
    matched_items = _pool_send_selection(owner_userid=owner_userid, pool_key=pool_key)
    skipped_by_reason: dict[str, int] = {}
    eligible_items: list[dict[str, Any]] = []
    for item in matched_items:
        skip_reason = ""
        if not _normalized_text(item.get("external_userid")):
            skip_reason = "missing_external_userid"
        elif not _normalized_text(item.get("owner_userid")):
            skip_reason = "missing_owner_userid"
        elif bool(item.get("do_not_disturb")):
            skip_reason = "do_not_disturb"
        if skip_reason:
            skipped_by_reason[skip_reason] = skipped_by_reason.get(skip_reason, 0) + 1
            continue
        eligible_items.append(item)
    budget_skip_details: list[dict[str, Any]] = []
    if apply_frequency_budget and eligible_items:
        try:
            from .frequency_budget_service import annotate_eligible_items_with_budget

            eligible_items, skipped_by_reason, budget_skip_details = (
                annotate_eligible_items_with_budget(
                    eligible_items=eligible_items,
                    pool_keys=(pool_key,) if pool_key else (),
                    program_codes=budget_program_codes,
                    channels=budget_channels,
                    skipped_by_reason=skipped_by_reason,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("frequency budget filter failed, fail-open: %s", exc)
    owner_buckets = []
    if eligible_items:
        owner_buckets.append(
            {
                "owner_userid": _normalized_text(owner_userid),
                "owner_display_name": eligible_items[0].get("owner_display_name") or _normalized_text(owner_userid),
                "count": len(eligible_items),
            }
        )
    return {
        "matched_items": matched_items,
        "eligible_items": eligible_items,
        "matched_count": len(matched_items),
        "eligible_count": len(eligible_items),
        "skipped_count": len(matched_items) - len(eligible_items),
        "skipped_by_reason": skipped_by_reason,
        "budget_skip_details": budget_skip_details,
        "owner_buckets": owner_buckets,
    }


def _build_openclaw_focus_message_webhook_payload(
    *,
    external_userid: str,
    recent_message_limit: int = 10,
) -> dict[str, Any]:
    from ..admin_console.customer_profile_service import (
        get_customer_messages_payload,
        get_customer_profile_payload,
        get_customer_profile_tags_payload,
        get_customer_questionnaire_answers_payload,
    )

    marketing_profile = get_openclaw_customer_marketing_profile(
        external_userid=external_userid,
        recent_message_limit=max(1, min(int(recent_message_limit), 20)),
    )
    profile_payload = get_customer_profile_payload(external_userid=external_userid) or {}
    tags_payload = get_customer_profile_tags_payload(external_userid=external_userid)
    questionnaire_payload = get_customer_questionnaire_answers_payload(external_userid=external_userid)
    messages_payload = get_customer_messages_payload(external_userid=external_userid, limit=recent_message_limit)
    profile = dict(profile_payload.get("profile") or {})
    marketing_state = dict(marketing_profile.get("marketing_state") or {})
    return {
        "external_userid": _normalized_text(external_userid),
        "owner_userid": _normalized_text((marketing_profile.get("owner") or {}).get("owner_userid")) or DEFAULT_AUTOMATION_OWNER_USERID,
        "current_pool": _normalized_text(marketing_state.get("pool_key")),
        "current_pool_label": _normalized_text(marketing_state.get("pool_label")),
        "current_stage": _normalized_text(marketing_state.get("stage_key")),
        "activated": bool(marketing_state.get("activated")),
        "last_activation_at": _normalized_text(marketing_state.get("last_activation_at")),
        "customer_profile": {
            "customer_name": _normalized_text(profile.get("customer_name")),
            "mobile": _normalized_text(profile.get("mobile")),
            "unionid": _normalized_text(profile.get("unionid")),
        },
        "questionnaire_summary": {
            "count": int(questionnaire_payload.get("count") or 0),
            "answers": list(questionnaire_payload.get("answers") or []),
        },
        "tags": list(tags_payload.get("tags") or []),
        "recent_messages": list(messages_payload.get("messages") or []),
        "marketing_profile": marketing_profile,
    }


def _post_json_webhook(
    *,
    url: str,
    token: str = "",
    payload: dict[str, Any],
    timeout: int = 10,
) -> requests.Response:
    # Routes through the shared retry/breaker client so any single misbehaving
    # marketing webhook can't hammer the upstream and trip cascades; raises
    # OutboundHttpError instead of requests.RequestException, which existing
    # callers already catch as the bare ``Exception`` superclass.
    from ...infra.http_client import get_outbound_client

    client = get_outbound_client(
        "marketing_automation_webhook",
        timeout=float(max(int(timeout), 1)),
        retry_max=2,
    )
    return client.post(
        url,
        json=payload,
        headers=_bearer_headers(token),
    )


def get_customer_trial_opening_fact(
    *,
    external_userid: str = "",
    person_id: int | None = None,
) -> dict[str, Any]:
    target = _resolve_customer_marketing_state_target(external_userid=external_userid, person_id=person_id)
    fact = repo.get_explicit_trial_opening_fact(
        external_userids=target.get("external_userids") or [],
        mobile=_normalized_text(target.get("mobile")),
    )
    if not fact:
        return {
            "trial_opened": False,
            "mobile": _normalized_text(target.get("mobile")),
            "external_userid": _normalized_text(target.get("external_userid")),
            "opened_at": "",
            "source": "",
            "owner_userid": "",
        }
    return {
        "trial_opened": True,
        "mobile": _normalized_text(fact.get("mobile")),
        "external_userid": _normalized_text(fact.get("external_userid")),
        "opened_at": _normalized_text(fact.get("updated_at")) or _normalized_text(fact.get("created_at")),
        "source": _normalized_text(fact.get("source_type")),
        "owner_userid": _normalized_text(fact.get("owner_userid")),
        "customer_name": _normalized_text(fact.get("customer_name")),
        "current_status": _normalized_text(fact.get("current_status")) or "lead_trial",
    }


def upsert_customer_trial_opening_fact(
    *,
    mobile: str = "",
    external_userid: str = "",
    person_id: int | None = None,
    customer_name: str = "",
    owner_userid: str = "",
    source: str = "automation_conversion",
    opened_at: str = "",
) -> dict[str, Any]:
    target = {}
    if _normalized_text(external_userid) or person_id is not None:
        target = _resolve_customer_marketing_state_target(external_userid=external_userid, person_id=person_id)
    final_mobile = _normalized_text(mobile) or _normalized_text(target.get("mobile"))
    final_external_userid = _normalized_text(external_userid) or _normalized_text(target.get("external_userid"))
    if not final_mobile and not final_external_userid:
        raise ValueError("mobile or external_userid is required")
    base = repo.load_customer_marketing_base(final_external_userid) if final_external_userid else {}
    saved = repo.upsert_explicit_trial_opening_fact(
        mobile=final_mobile,
        external_userid=final_external_userid,
        customer_name=_normalized_text(customer_name) or _normalized_text(base.get("customer_name")),
        owner_userid=_normalized_text(owner_userid) or _normalized_text(base.get("owner_userid")) or DEFAULT_AUTOMATION_OWNER_USERID,
        source_type=_normalized_text(source) or "automation_conversion",
        opened_at=_normalized_text(opened_at),
    )
    return {
        "trial_opened": True,
        "mobile": _normalized_text(saved.get("mobile")),
        "external_userid": _normalized_text(saved.get("external_userid")),
        "opened_at": _normalized_text(saved.get("updated_at")) or _normalized_text(saved.get("created_at")),
        "source": _normalized_text(saved.get("source_type")),
        "owner_userid": _normalized_text(saved.get("owner_userid")),
        "customer_name": _normalized_text(saved.get("customer_name")),
        "current_status": _normalized_text(saved.get("current_status")) or "lead_trial",
    }


def send_pool_private_message(
    *,
    owner_userid: str,
    pool_key: str,
    content: str = "",
    confirm: bool = False,
    operator: str = "",
    images: list[dict[str, Any]] | None = None,
    image_media_ids: list[str] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    attachment_library_ids: list[int] | None = None,
    trace_id: str = "",
    source_kind: str = "manual_pool_send",
    source_id: str = "",
) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service.send_pool_private_message(
        owner_userid=owner_userid,
        pool_key=pool_key,
        content=content,
        confirm=confirm,
        operator=operator,
        images=images,
        image_media_ids=image_media_ids,
        attachments=attachments,
        attachment_library_ids=attachment_library_ids,
        trace_id=trace_id,
        source_kind=source_kind,
        source_id=source_id,
    )


def trigger_openclaw_focus_message_webhook(
    *,
    external_userid: str,
    recent_message_limit: int = 10,
) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service.trigger_openclaw_focus_message_webhook(
        external_userid=external_userid,
        recent_message_limit=recent_message_limit,
    )


def process_inbound_messages_for_openclaw(messages: list[dict[str, Any]]) -> dict[str, Any]:
    from . import message_dispatch_service

    return message_dispatch_service.process_inbound_messages_for_openclaw(messages)


def apply_activation_webhook(
    *,
    mobile: str,
    activated_at: str = "",
    operator: str = "",
    source: str = "activation_webhook",
) -> dict[str, Any]:
    normalized_mobile = _normalized_text(mobile)
    if not normalized_mobile:
        raise ValueError("mobile is required")
    identity = repo.resolve_customer_identity_by_mobile(normalized_mobile) or {}
    normalized_external_userid = _normalized_text(identity.get("external_userid"))
    if not normalized_external_userid:
        raise LookupError("customer not found by mobile")
    signal_at = _normalized_text(activated_at) or _iso_now()
    source_row = repo.upsert_activation_webhook_source(
        mobile=normalized_mobile,
        signal_at=signal_at,
        import_batch_id=_normalized_text(source) or "activation_webhook",
        created_by=_normalized_text(operator) or "activation_webhook",
    )
    marketing_state = evaluate_customer_marketing_state(external_userid=normalized_external_userid)
    automation_webhook_logger.info(
        "activation webhook applied mobile=%s external_userid=%s stage_key=%s signal_at=%s",
        normalized_mobile,
        normalized_external_userid,
        _normalized_text(marketing_state.get("stage_key")),
        signal_at,
    )
    return {
        "ok": True,
        "mobile": normalized_mobile,
        "external_userid": normalized_external_userid,
        "owner_userid": _normalized_text(identity.get("owner_userid")),
        "activated_at": signal_at,
        "activation_source": source_row,
        "marketing_state": marketing_state,
    }


def preview_signup_conversion_customer(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    normalized_person_id = _normalize_int(person_id, "person_id", allow_none=True)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid and normalized_person_id is None:
        raise ValueError("external_userid or person_id is required")

    config = get_signup_conversion_config(automation_key=automation_key)
    marketing_state_lookup: dict[str, Any]
    if normalized_person_id is not None:
        marketing_state_lookup = {"person_id": int(normalized_person_id)}
    else:
        marketing_state_lookup = {"external_userid": normalized_external_userid}

    marketing_state = evaluate_customer_marketing_state(
        automation_key=automation_key,
        persist=persist,
        **marketing_state_lookup,
    )

    value_segment_lookup: dict[str, Any]
    if marketing_state.get("person_id") is not None:
        value_segment_lookup = {"person_id": int(marketing_state["person_id"])}
    else:
        value_segment_lookup = {"external_userid": _normalized_text(marketing_state.get("external_userid")) or normalized_external_userid}
    value_segment = evaluate_customer_value_segment(
        automation_key=automation_key,
        persist=persist,
        **value_segment_lookup,
    )

    matched_question_ids = [
        int(question_id)
        for question_id in value_segment.get("matched_question_ids_json") or []
        if str(question_id).strip()
    ]
    matched_questions = _matched_question_rule_items(config, matched_question_ids=matched_question_ids)
    current_stage = _normalized_text(marketing_state.get("stage_key"))
    current_segment = _normalize_followup_segment(marketing_state.get("current_segment"))
    display = business_marketing_display(
        main_stage=marketing_state.get("main_stage"),
        sub_stage=marketing_state.get("sub_stage"),
        segment=current_segment,
        eligible_for_conversion=marketing_state.get("eligible_for_conversion"),
        ineligible_reason=_preview_ineligible_reason(marketing_state),
    )
    return {
        "automation_key": automation_key,
        "resolved_customer": {
            "person_id": marketing_state.get("person_id"),
            "external_userid": _normalized_text(marketing_state.get("external_userid"))
            or _normalized_text(value_segment.get("external_userid")),
            "mobile": _normalized_text(((marketing_state.get("state_payload") or {}).get("mobile"))),
            "bound_external_userids": list(marketing_state.get("bound_external_userids") or []),
        },
        "config_snapshot": {
            "enabled": bool(config.get("enabled")),
            "configured": bool(config.get("configured")),
            "questionnaire_id": _normalize_int(config.get("questionnaire_id"), "questionnaire_id", allow_none=True),
            "core_threshold": int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD),
            "top_threshold": int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD),
            "day_start_hour": int(config.get("day_start_hour") or DEFAULT_DAY_START_HOUR),
            "quiet_hour_start": int(config.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START),
            "timezone": _normalized_text(config.get("timezone")) or DEFAULT_TIMEZONE,
            "silent_threshold_days_by_pool": _normalize_silent_threshold_days_by_pool(
                config.get("silent_threshold_days_by_pool")
            ),
        },
        "summary": {
            "current_stage": current_stage,
            "current_stage_label": _normalized_text(marketing_state.get("stage_label")),
            "current_stage_display": display["stage_label"],
            "current_pool": _normalized_text(marketing_state.get("pool_key")),
            "current_pool_label": _normalized_text(marketing_state.get("pool_label")),
            "current_segment": current_segment,
            "current_segment_label": _followup_segment_label(current_segment),
            "current_segment_display": display["segment_label"],
            "matched_question_ids": matched_question_ids,
            "matched_questions": matched_questions,
            "hit_count": int(value_segment.get("hit_count") or 0),
            "eligible": bool(marketing_state.get("eligible_for_conversion")),
            "eligible_for_conversion": bool(marketing_state.get("eligible_for_conversion")),
            "eligibility_display": display["eligibility_label"],
            "ineligible_reason": _preview_ineligible_reason(marketing_state),
            "ineligible_reason_display": display["ineligible_reason_label"],
        },
        "marketing_state": marketing_state,
        "value_segment": value_segment,
    }


def _normalize_recompute_targets(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    external_userids: list[Any] | None = None,
    person_ids: list[Any] | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add_external(value: Any) -> None:
        normalized = _normalized_text(value)
        if not normalized:
            return
        key = ("external_userid", normalized)
        if key in seen:
            return
        seen.add(key)
        targets.append({"external_userid": normalized, "person_id": None})

    def _add_person(value: Any) -> None:
        normalized = _normalize_int(value, "person_id", allow_none=True)
        if normalized is None:
            return
        key = ("person_id", str(int(normalized)))
        if key in seen:
            return
        seen.add(key)
        targets.append({"external_userid": "", "person_id": int(normalized)})

    _add_external(external_userid)
    _add_person(person_id)
    if external_userids:
        for item in external_userids:
            _add_external(item)
    if person_ids:
        for item in person_ids:
            _add_person(item)
    if not targets:
        raise ValueError("external_userid or person_id is required")
    return targets


def recompute_signup_conversion_customers(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    external_userids: list[Any] | None = None,
    person_ids: list[Any] | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    targets = _normalize_recompute_targets(
        external_userid=external_userid,
        person_id=person_id,
        external_userids=external_userids,
        person_ids=person_ids,
    )
    items: list[dict[str, Any]] = []
    for target in targets:
        preview = preview_signup_conversion_customer(
            external_userid=_normalized_text(target.get("external_userid")),
            person_id=_normalize_int(target.get("person_id"), "person_id", allow_none=True),
            automation_key=automation_key,
            persist=persist,
        )
        preview["history_refresh"] = {
            "marketing_state_history_written": bool((preview.get("marketing_state") or {}).get("history_written")),
            "value_segment_history_written": bool((preview.get("value_segment") or {}).get("history_written")),
        }
        items.append(preview)
    result = {
        "automation_key": automation_key,
        "mode": "single" if len(items) == 1 else "batch",
        "count": len(items),
        "items": items,
    }
    if len(items) == 1:
        result["item"] = items[0]
    return result



def _is_signup_success(signup_status: str) -> bool:
    normalized = _normalized_text(signup_status).lower()
    return any(normalized.startswith(prefix) for prefix in _EXIT_SIGNUP_PREFIXES)


def _latest_timestamp(*values: Any) -> str:
    candidates = [_normalized_text(value) for value in values if _normalized_text(value)]
    return max(candidates) if candidates else ""


def _serialize_current_customer_marketing_state(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = _json_loads(row.get("state_payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    stored_external_userid = _normalized_text(row.get("external_userid"))
    resolved_external_userid = _normalized_text(payload.get("resolved_external_userid"))
    if not resolved_external_userid:
        resolved_external_userid = stored_external_userid
    bound_external_userids = _normalized_json_text_list(payload.get("bound_external_userids"))
    if not bound_external_userids and resolved_external_userid:
        bound_external_userids = [resolved_external_userid]
    person_id = _normalize_int(
        row.get("person_id") if row.get("person_id") not in (None, "") else payload.get("person_id"),
        "person_id",
        allow_none=True,
    )
    main_stage = _normalized_text(row.get("main_stage"))
    sub_stage = _normalized_text(row.get("sub_stage"))
    stage_key = f"{main_stage}/{sub_stage}" if main_stage and sub_stage else main_stage or sub_stage
    pool_key = sub_stage if main_stage == POOL_STAGE else _normalized_text(payload.get("pool_key"))
    current_segment = _normalize_followup_segment(
        payload.get("followup_segment") or payload.get("current_segment") or _pool_segment_from_pool_key(pool_key)
    )
    return {
        "id": int(row.get("id") or 0),
        "person_id": person_id,
        "storage_external_userid": stored_external_userid,
        "external_userid": resolved_external_userid,
        "bound_external_userids": bound_external_userids,
        "main_stage": main_stage,
        "sub_stage": sub_stage,
        "stage_key": stage_key,
        "stage_label": _CUSTOMER_MARKETING_STATE_LABELS.get((main_stage, sub_stage), ""),
        "pool_key": pool_key,
        "pool_label": _pool_label(pool_key) if pool_key else "",
        "current_segment": current_segment,
        "current_segment_label": _followup_segment_label(current_segment),
        "openclaw_eligible": bool(payload.get("openclaw_eligible"))
        if "openclaw_eligible" in payload
        else stage_key in _ACTIONABLE_POOL_STAGE_KEYS,
        "activated": _normalize_bool(row.get("activated")),
        "converted": _normalize_bool(row.get("converted")),
        "eligible_for_conversion": _normalize_bool(row.get("eligible_for_conversion")),
        "lifecycle_status": _normalized_text(row.get("lifecycle_status")),
        "last_activation_at": _normalized_text(row.get("last_activation_at")),
        "last_conversion_marked_at": _normalized_text(row.get("last_conversion_marked_at")),
        "last_message_at": _normalized_text(row.get("last_message_at")),
        "last_batch_id": _normalize_int(row.get("last_batch_id"), "last_batch_id", allow_none=True),
        "last_batch_status": _normalized_text(row.get("last_batch_status")),
        "last_batch_window_start": _normalized_text(row.get("last_batch_window_start")),
        "last_batch_window_end": _normalized_text(row.get("last_batch_window_end")),
        "last_trigger_message_at": _normalized_text(row.get("last_trigger_message_at")),
        "entered_at": _normalized_text(row.get("entered_at")),
        "exited_at": _normalized_text(row.get("exited_at")),
        "exit_reason": _normalized_text(row.get("exit_reason")),
        "state_payload": payload,
        "updated_at": _normalized_text(row.get("updated_at")),
        "created_at": _normalized_text(row.get("created_at")),
    }


def _customer_marketing_state_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "person_id": _normalize_int(row.get("person_id"), "person_id", allow_none=True),
        "storage_external_userid": _normalized_text(row.get("storage_external_userid")),
        "external_userid": _normalized_text(row.get("external_userid")),
        "bound_external_userids": _normalized_json_text_list(row.get("bound_external_userids")),
        "main_stage": _normalized_text(row.get("main_stage")),
        "sub_stage": _normalized_text(row.get("sub_stage")),
        "activated": bool(row.get("activated")),
        "converted": bool(row.get("converted")),
        "eligible_for_conversion": bool(row.get("eligible_for_conversion")),
        "lifecycle_status": _normalized_text(row.get("lifecycle_status")),
        "last_activation_at": _normalized_text(row.get("last_activation_at")),
        "last_conversion_marked_at": _normalized_text(row.get("last_conversion_marked_at")),
        "last_message_at": _normalized_text(row.get("last_message_at")),
        "last_batch_id": _normalize_int(row.get("last_batch_id"), "last_batch_id", allow_none=True),
        "last_batch_status": _normalized_text(row.get("last_batch_status")),
        "last_batch_window_start": _normalized_text(row.get("last_batch_window_start")),
        "last_batch_window_end": _normalized_text(row.get("last_batch_window_end")),
        "last_trigger_message_at": _normalized_text(row.get("last_trigger_message_at")),
        "entered_at": _normalized_text(row.get("entered_at")),
        "exited_at": _normalized_text(row.get("exited_at")),
        "exit_reason": _normalized_text(row.get("exit_reason")),
        "state_payload": row.get("state_payload") or {},
    }


def _resolve_customer_marketing_state_target(
    *,
    external_userid: str,
    person_id: int | None,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_person_id = _normalize_int(person_id, "person_id", allow_none=True)
    external_userids: list[str] = []
    mobile = ""
    if normalized_person_id is not None:
        external_userids = repo.list_external_userids_by_person(int(normalized_person_id))
        mobile = repo.get_person_mobile(int(normalized_person_id))
        if not mobile and not external_userids:
            raise LookupError("person not found")
    elif normalized_external_userid:
        binding = repo.get_binding_snapshot_for_external_userid(normalized_external_userid) or {}
        if binding:
            normalized_person_id = int(binding["person_id"])
            external_userids = repo.list_external_userids_by_person(int(normalized_person_id))
            mobile = _normalized_text(binding.get("mobile")) or repo.get_person_mobile(int(normalized_person_id))
        elif repo.has_live_external_userid(normalized_external_userid):
            external_userids = [normalized_external_userid]
            mobile = repo.get_signal_mobile_for_external_userid(normalized_external_userid)
        else:
            mobile = repo.get_signal_mobile_for_external_userid(normalized_external_userid)
    else:
        raise ValueError("external_userid or person_id is required")

    deduped_external_userids: list[str] = []
    seen_external_userids: set[str] = set()
    for item in external_userids or ([normalized_external_userid] if normalized_external_userid else []):
        normalized_item = _normalized_text(item)
        if not normalized_item or normalized_item in seen_external_userids:
            continue
        seen_external_userids.add(normalized_item)
        deduped_external_userids.append(normalized_item)

    primary_external_userid = deduped_external_userids[0] if deduped_external_userids else ""
    return {
        "person_id": normalized_person_id,
        "external_userid": primary_external_userid,
        "external_userids": deduped_external_userids,
        "mobile": _normalized_text(mobile),
    }


def _latest_converted_signal(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        signup_status = _normalized_text(row.get("signup_status"))
        if not _is_signup_success(signup_status):
            continue
        signal_at = _normalized_text(row.get("set_at")) or _latest_timestamp(
            row.get("updated_at"),
            row.get("created_at"),
        )
        candidates.append(
            {
                "external_userid": _normalized_text(row.get("external_userid")),
                "signup_status": signup_status,
                "signal_at": signal_at,
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item["signal_at"],
            item["external_userid"],
        ),
        reverse=True,
    )
    return candidates[0]


def _latest_activation_signal(
    *,
    lead_pool_rows: list[dict[str, Any]],
    activation_source_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for row in lead_pool_rows:
        if _normalized_text(row.get("huangxiaocan_activation_state")) != "activated":
            continue
        candidates.append(
            {
                "signal_source": "lead_pool_current",
                "external_userid": _normalized_text(row.get("external_userid")),
                "mobile": _normalized_text(row.get("mobile")),
                "signal_at": _latest_timestamp(row.get("updated_at"), row.get("created_at")),
            }
        )
    if activation_source_row and _normalize_bool(activation_source_row.get("is_active"), default=True):
        if _normalized_text(activation_source_row.get("activation_state")) == "activated":
            candidates.append(
                {
                    "signal_source": "huangxiaocan_activation_source",
                    "external_userid": "",
                    "mobile": _normalized_text(activation_source_row.get("mobile")),
                    "signal_at": _latest_timestamp(
                        activation_source_row.get("updated_at"),
                        activation_source_row.get("created_at"),
                    ),
                }
            )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item["signal_at"],
            item["signal_source"],
            item["external_userid"],
        ),
        reverse=True,
    )
    return candidates[0]


def evaluate_customer_marketing_state(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    state_payload_overrides: dict[str, Any] | None = None,
    history_change_reason: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    target = _resolve_customer_marketing_state_target(external_userid=external_userid, person_id=person_id)
    stored_external_userid = _normalized_text(target.get("external_userid"))
    existing = _serialize_current_customer_marketing_state(
        repo.get_customer_marketing_state_current(
            external_userid=stored_external_userid,
            person_id=target.get("person_id"),
        )
    )
    config = get_signup_conversion_config(automation_key=automation_key)
    value_segment = evaluate_customer_value_segment(
        external_userid=stored_external_userid,
        person_id=target.get("person_id"),
        automation_key=automation_key,
        persist=False,
    )
    submission_id = _normalize_int(value_segment.get("submission_id"), "submission_id", allow_none=True)
    submission_at = _normalized_text(((value_segment.get("source_payload") or {}).get("latest_submission_submitted_at")))
    hit_count = int(value_segment.get("hit_count") or 0)
    questionnaire_segment = _normalized_text(value_segment.get("segment")) or "unknown"
    questionnaire_followup_segment = _followup_segment_from_value_segment(questionnaire_segment)
    manual_followup_segment = _resolve_manual_followup_segment(
        existing_state=existing,
        state_payload_overrides=state_payload_overrides,
    )
    has_questionnaire_submission = submission_id is not None

    class_status_rows = repo.list_class_status_rows(target.get("external_userids") or [])
    converted_signal = _latest_converted_signal(class_status_rows)
    lead_pool_rows = repo.list_user_ops_lead_pool_rows_for_marketing_state(
        external_userids=target.get("external_userids") or [],
        mobile=_normalized_text(target.get("mobile")),
    )
    trial_opening_fact = repo.get_explicit_trial_opening_fact(
        external_userids=target.get("external_userids") or [],
        mobile=_normalized_text(target.get("mobile")),
    )
    activation_source_row = repo.get_huangxiaocan_activation_source_by_mobile(_normalized_text(target.get("mobile")))
    activation_signal = _latest_activation_signal(
        lead_pool_rows=lead_pool_rows,
        activation_source_row=activation_source_row,
    )
    activated = activation_signal is not None
    converted = converted_signal is not None
    last_activation_at = _normalized_text((activation_signal or {}).get("signal_at"))
    last_conversion_marked_at = _normalized_text((converted_signal or {}).get("signal_at"))
    last_message_at = repo.get_latest_message_at_for_external_userids(target.get("external_userids") or [])
    has_external_userid = bool(target.get("external_userids"))
    trial_opened = trial_opening_fact is not None
    trial_opened_at = _normalized_text((trial_opening_fact or {}).get("updated_at")) or _normalized_text((trial_opening_fact or {}).get("created_at"))
    trial_opened_source = _normalized_text((trial_opening_fact or {}).get("source_type"))
    trial_opened_external_userid = _normalized_text((trial_opening_fact or {}).get("external_userid"))
    now_text = _iso_now()
    existing_stage_key = _normalized_text((existing or {}).get("stage_key"))
    existing_payload = dict((existing or {}).get("state_payload") or {})
    preview_base_pool_key = _resolve_pool_key_for_customer(
        has_questionnaire_submission=has_questionnaire_submission,
        trial_opened=trial_opened,
        activated=activated,
        followup_segment=(
            manual_followup_segment
            or (questionnaire_followup_segment if questionnaire_followup_segment != FOLLOWUP_SEGMENT_UNKNOWN else FOLLOWUP_SEGMENT_NORMAL)
            or FOLLOWUP_SEGMENT_UNKNOWN
        ),
    )
    silent_threshold_days = _resolve_silent_threshold_days(config, pool_key=preview_base_pool_key)
    override_payload = dict(state_payload_overrides or {})
    force_base_entered_at = ""
    override_manual_segment = _normalize_followup_segment(override_payload.get("manual_followup_segment"))
    if override_manual_segment in {FOLLOWUP_SEGMENT_NORMAL, FOLLOWUP_SEGMENT_FOCUS}:
        force_base_entered_at = _normalized_text(override_payload.get("manual_followup_segment_at")) or now_text
    calculated_state = _calculate_marketing_state(
        has_questionnaire_submission=has_questionnaire_submission,
        questionnaire_segment=(
            questionnaire_followup_segment
            if questionnaire_followup_segment != FOLLOWUP_SEGMENT_UNKNOWN
            else FOLLOWUP_SEGMENT_NORMAL
        ),
        manual_segment=manual_followup_segment,
        trial_opened=trial_opened,
        activated=activated,
        converted=converted,
        has_external_userid=has_external_userid,
        submission_at=submission_at,
        trial_opened_at=trial_opened_at,
        activation_at=last_activation_at,
        last_message_at=last_message_at,
        silent_threshold_days=silent_threshold_days,
        existing_stage_key=existing_stage_key,
        existing_entered_at=_normalized_text((existing or {}).get("entered_at")),
        existing_state_payload=existing_payload,
        now=now_text,
        converted_at=last_conversion_marked_at,
        force_base_entered_at=force_base_entered_at,
    )

    followup_segment = _normalized_text(calculated_state.get("current_segment")) or FOLLOWUP_SEGMENT_UNKNOWN
    followup_segment_source = _normalized_text(calculated_state.get("current_segment_source")) or "awaiting_questionnaire"
    base_pool_key = _normalized_text(calculated_state.get("base_pool_key"))
    base_entered_at = _normalized_text(calculated_state.get("base_entered_at"))
    final_pool_key = _normalized_text(calculated_state.get("pool_key"))
    main_stage = _normalized_text(calculated_state.get("main_stage"))
    sub_stage = _normalized_text(calculated_state.get("sub_stage"))
    lifecycle_status = _normalized_text(calculated_state.get("lifecycle_status"))
    eligible_for_conversion = bool(calculated_state.get("eligible_for_conversion"))
    exit_reason = _normalized_text(calculated_state.get("exit_reason"))
    stage_key = _normalized_text(calculated_state.get("stage_key"))
    entered_at = _normalized_text(calculated_state.get("entered_at"))
    exited_at = _normalized_text(calculated_state.get("exited_at"))
    openclaw_eligible = bool(calculated_state.get("openclaw_eligible"))
    state_payload = {
        "person_id": target.get("person_id"),
        "mobile": _normalized_text(target.get("mobile")),
        "resolved_external_userid": _normalized_text(target.get("external_userid")),
        "bound_external_userids": sorted(_normalized_json_text_list(target.get("external_userids") or [])),
        "activated_signal_source": _normalized_text((activation_signal or {}).get("signal_source")),
        "activated_signal_external_userid": _normalized_text((activation_signal or {}).get("external_userid")),
        "converted_external_userid": _normalized_text((converted_signal or {}).get("external_userid")),
        "converted_signup_status": _normalized_text((converted_signal or {}).get("signup_status")),
        "trial_opened": trial_opened,
        "trial_opened_at": trial_opened_at,
        "trial_opened_source": trial_opened_source,
        "trial_opened_external_userid": trial_opened_external_userid,
        "pool_key": final_pool_key,
        "pool_label": _pool_label(final_pool_key),
        "followup_segment": followup_segment,
        "followup_segment_label": _followup_segment_label(followup_segment),
        "followup_segment_source": followup_segment_source,
        "manual_followup_segment": manual_followup_segment,
        "manual_followup_segment_label": _normalized_text(existing_payload.get("manual_followup_segment_label")),
        "manual_followup_segment_source": _normalized_text(existing_payload.get("manual_followup_segment_source")),
        "manual_followup_segment_operator": _normalized_text(existing_payload.get("manual_followup_segment_operator")),
        "manual_followup_segment_at": _normalized_text(existing_payload.get("manual_followup_segment_at")),
        "questionnaire_submission_id": submission_id,
        "questionnaire_submitted_at": submission_at,
        "questionnaire_hit_count": hit_count,
        "questionnaire_segment": questionnaire_segment,
        "questionnaire_matched_question_ids": list(value_segment.get("matched_question_ids_json") or []),
        "pool_owner_userid": _normalized_text(existing_payload.get("pool_owner_userid")) or DEFAULT_AUTOMATION_OWNER_USERID,
        "openclaw_eligible": openclaw_eligible,
        "silent_threshold_days": int(silent_threshold_days),
        "base_pool_key": base_pool_key,
        "base_pool_label": _pool_label(base_pool_key),
        "base_pool_entered_at": base_entered_at,
    }
    if final_pool_key == POOL_SILENT:
        state_payload.update(
            {
                "silent_base_pool_key": base_pool_key,
                "silent_base_pool_label": _pool_label(base_pool_key),
                "silent_base_pool_entered_at": base_entered_at,
                "silent_triggered_at": entered_at,
            }
        )
    if state_payload_overrides:
        state_payload.update(dict(state_payload_overrides))
    result = {
        "person_id": target.get("person_id"),
        "storage_external_userid": stored_external_userid,
        "external_userid": _normalized_text(target.get("external_userid")),
        "bound_external_userids": state_payload["bound_external_userids"],
        "main_stage": main_stage,
        "sub_stage": sub_stage,
        "stage_key": stage_key,
        "stage_label": _CUSTOMER_MARKETING_STATE_LABELS.get((main_stage, sub_stage), ""),
        "pool_key": final_pool_key if main_stage == POOL_STAGE else "",
        "pool_label": _pool_label(final_pool_key) if main_stage == POOL_STAGE else "",
        "current_segment": _normalize_followup_segment(followup_segment),
        "current_segment_label": _followup_segment_label(followup_segment),
        "openclaw_eligible": openclaw_eligible,
        "activated": activated,
        "converted": converted,
        "eligible_for_conversion": eligible_for_conversion,
        "lifecycle_status": lifecycle_status,
        "last_activation_at": last_activation_at,
        "last_conversion_marked_at": last_conversion_marked_at,
        "last_message_at": last_message_at,
        "last_batch_id": (existing or {}).get("last_batch_id"),
        "last_batch_status": _normalized_text((existing or {}).get("last_batch_status")),
        "last_batch_window_start": _normalized_text((existing or {}).get("last_batch_window_start")),
        "last_batch_window_end": _normalized_text((existing or {}).get("last_batch_window_end")),
        "last_trigger_message_at": _normalized_text((existing or {}).get("last_trigger_message_at")) or last_message_at,
        "entered_at": entered_at,
        "exited_at": exited_at,
        "exit_reason": exit_reason,
        "state_payload": state_payload,
    }

    if not persist:
        result["history_written"] = False
        return result

    existing_snapshot = _customer_marketing_state_snapshot(existing or {}) if existing else None
    result_snapshot = _customer_marketing_state_snapshot(result)
    history_written = False
    db = get_db()
    dispatch_external_userid = _normalized_text((existing or {}).get("storage_external_userid")) or stored_external_userid
    try:
        if existing_snapshot != result_snapshot:
            repo.insert_customer_marketing_state_history(
                external_userid=stored_external_userid,
                person_id=target.get("person_id"),
                automation_key=automation_key,
                main_stage=main_stage,
                sub_stage=sub_stage,
                activated=activated,
                converted=converted,
                eligible_for_conversion=eligible_for_conversion,
                batch_id=result.get("last_batch_id"),
                lifecycle_status=lifecycle_status,
                exit_reason=exit_reason,
                last_activation_at=last_activation_at,
                last_conversion_marked_at=last_conversion_marked_at,
                last_message_at=last_message_at,
                change_reason="initial_compute" if not existing else (_normalized_text(history_change_reason) or "state_changed"),
                state_payload=state_payload,
            )
            history_written = True
        current = repo.upsert_customer_marketing_state_current(
            external_userid=stored_external_userid,
            person_id=target.get("person_id"),
            automation_key=automation_key,
            main_stage=main_stage,
            sub_stage=sub_stage,
            activated=activated,
            converted=converted,
            eligible_for_conversion=eligible_for_conversion,
            lifecycle_status=lifecycle_status,
            last_activation_at=last_activation_at,
            last_conversion_marked_at=last_conversion_marked_at,
            last_message_at=last_message_at,
            last_batch_id=result.get("last_batch_id"),
            last_batch_status=result.get("last_batch_status", ""),
            last_batch_window_start=result.get("last_batch_window_start", ""),
            last_batch_window_end=result.get("last_batch_window_end", ""),
            last_trigger_message_at=result.get("last_trigger_message_at", ""),
            entered_at=_nullable_timestamp_text(entered_at),
            exited_at=_nullable_timestamp_text(exited_at),
            exit_reason=exit_reason,
            state_payload=state_payload,
        )
        if (
            existing_stage_key
            and existing_stage_key != stage_key
            and dispatch_external_userid
            and not (stage_key == "converted/enrolled" and _normalized_text(history_change_reason) == "mark_enrolled")
        ):
            _cancel_dispatches_for_pool_change(
                external_userid=dispatch_external_userid,
                previous_stage_key=existing_stage_key,
                current_stage_key=stage_key,
                automation_key=automation_key,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    serialized = _serialize_current_customer_marketing_state(current) or result
    serialized["history_written"] = history_written
    return serialized




def _blocked_phase_label(day_start_hour: int, quiet_hour_start: int) -> str:
    return f"{_format_auto_start_window(day_start_hour, quiet_hour_start)} 外不启动"


def _build_state_payload(
    base: dict[str, Any],
    *,
    existing_state: dict[str, Any] | None,
    batch_context: dict[str, Any] | None,
) -> dict[str, Any]:
    now_text = _iso_now()
    if _is_signup_success(_normalized_text(base.get("signup_status"))):
        entered_at = _normalized_text((existing_state or {}).get("entered_at"))
        return {
            "marketing_phase": "exited_signup_success",
            "phase_label": _PHASE_LABELS["exited_signup_success"],
            "phase_reason": f"signup_status={_normalized_text(base.get('signup_status')) or 'unknown'}",
            "lifecycle_status": "exited",
            "last_batch_id": (existing_state or {}).get("last_batch_id"),
            "last_batch_status": _normalized_text((existing_state or {}).get("last_batch_status")),
            "last_batch_window_start": _normalized_text((existing_state or {}).get("last_batch_window_start")),
            "last_batch_window_end": _normalized_text((existing_state or {}).get("last_batch_window_end")),
            "last_trigger_message_at": _normalized_text((existing_state or {}).get("last_trigger_message_at"))
            or _normalized_text(base.get("last_customer_text_at"))
            or _normalized_text(base.get("last_message_at")),
            "entered_at": entered_at or now_text,
            "exited_at": now_text,
            "exit_reason": "signup_success",
            "source_payload": {
                "signup_status": _normalized_text(base.get("signup_status")),
                "last_customer_text_at": _normalized_text(base.get("last_customer_text_at")),
            },
        }

    if batch_context:
        existing_is_active = _normalized_text((existing_state or {}).get("lifecycle_status")) == "active"
        if bool(batch_context.get("blocked_after_quiet_hour")) and not existing_is_active:
            return {
                "marketing_phase": "blocked_after_2300",
                "phase_label": _blocked_phase_label(
                    int(batch_context.get("day_start_hour") or DEFAULT_DAY_START_HOUR),
                    int(batch_context.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START),
                ),
                "phase_reason": "window_start_outside_auto_start_window",
                "lifecycle_status": "blocked",
                "last_batch_id": batch_context.get("batch_id"),
                "last_batch_status": _normalized_text(batch_context.get("batch_status")),
                "last_batch_window_start": _normalized_text(batch_context.get("window_start")),
                "last_batch_window_end": _normalized_text(batch_context.get("window_end")),
                "last_trigger_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
                "entered_at": now_text,
                "exited_at": "",
                "exit_reason": "",
                "source_payload": {
                    "batch_id": batch_context.get("batch_id"),
                    "eligible_message_count": int(batch_context.get("customer_text_count") or 0),
                },
            }
        return {
            "marketing_phase": "waiting_openclaw",
            "phase_label": _PHASE_LABELS["waiting_openclaw"],
            "phase_reason": "pending_text_message_batch",
            "lifecycle_status": "active",
            "last_batch_id": batch_context.get("batch_id"),
            "last_batch_status": _normalized_text(batch_context.get("batch_status")),
            "last_batch_window_start": _normalized_text(batch_context.get("window_start")),
            "last_batch_window_end": _normalized_text(batch_context.get("window_end")),
            "last_trigger_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
            "entered_at": _normalized_text((existing_state or {}).get("entered_at")) or now_text,
            "exited_at": "",
            "exit_reason": "",
            "source_payload": {
                "batch_id": batch_context.get("batch_id"),
                "eligible_message_count": int(batch_context.get("customer_text_count") or 0),
            },
        }

    if existing_state and _normalized_text(existing_state.get("lifecycle_status")) in {"active", "blocked"}:
        return {
            "marketing_phase": _normalized_text(existing_state.get("marketing_phase")),
            "phase_label": _normalized_text(existing_state.get("phase_label"))
            or _PHASE_LABELS.get(_normalized_text(existing_state.get("marketing_phase")), ""),
            "phase_reason": _normalized_text(existing_state.get("phase_reason")),
            "lifecycle_status": _normalized_text(existing_state.get("lifecycle_status")),
            "last_batch_id": existing_state.get("last_batch_id"),
            "last_batch_status": _normalized_text(existing_state.get("last_batch_status")),
            "last_batch_window_start": _normalized_text(existing_state.get("last_batch_window_start")),
            "last_batch_window_end": _normalized_text(existing_state.get("last_batch_window_end")),
            "last_trigger_message_at": _normalized_text(existing_state.get("last_trigger_message_at")),
            "entered_at": _normalized_text(existing_state.get("entered_at")),
            "exited_at": _normalized_text(existing_state.get("exited_at")),
            "exit_reason": _normalized_text(existing_state.get("exit_reason")),
            "source_payload": _json_loads(existing_state.get("source_payload_json"), default={}),
        }

    return {
        "marketing_phase": "awaiting_trigger",
        "phase_label": _PHASE_LABELS["awaiting_trigger"],
        "phase_reason": "awaiting_pending_batch",
        "lifecycle_status": "idle",
        "last_batch_id": None,
        "last_batch_status": "",
        "last_batch_window_start": "",
        "last_batch_window_end": "",
        "last_trigger_message_at": _normalized_text(base.get("last_customer_text_at")),
        "entered_at": "",
        "exited_at": "",
        "exit_reason": "",
        "source_payload": {
            "signup_status": _normalized_text(base.get("signup_status")),
            "last_customer_text_at": _normalized_text(base.get("last_customer_text_at")),
        },
    }



def _persist_marketing_state(
    base: dict[str, Any],
    *,
    scenario_key: str,
    batch_context: dict[str, Any] | None,
) -> dict[str, Any]:
    existing = repo.get_marketing_state_current(_normalized_text(base.get("external_userid")), scenario_key=scenario_key)
    payload = _build_state_payload(base, existing_state=existing, batch_context=batch_context)
    row = repo.upsert_marketing_state_current(
        scenario_key=scenario_key,
        external_userid=_normalized_text(base.get("external_userid")),
        marketing_phase=_normalized_text(payload.get("marketing_phase")),
        phase_label=_normalized_text(payload.get("phase_label")),
        phase_reason=_normalized_text(payload.get("phase_reason")),
        lifecycle_status=_normalized_text(payload.get("lifecycle_status")),
        last_batch_id=payload.get("last_batch_id"),
        last_batch_status=_normalized_text(payload.get("last_batch_status")),
        last_batch_window_start=_normalized_text(payload.get("last_batch_window_start")),
        last_batch_window_end=_normalized_text(payload.get("last_batch_window_end")),
        last_trigger_message_at=_normalized_text(payload.get("last_trigger_message_at")),
        entered_at=_normalized_text(payload.get("entered_at")),
        exited_at=_normalized_text(payload.get("exited_at")),
        exit_reason=_normalized_text(payload.get("exit_reason")),
        source_payload=payload.get("source_payload") or {},
    )
    row["source_payload"] = _json_loads(row.get("source_payload_json"), default={})
    return row


def get_customer_marketing_profile(
    external_userid: str,
    *,
    scenario_key: str = DEFAULT_SCENARIO_KEY,
    batch_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    base = repo.load_customer_marketing_base(normalized_external_userid)
    if not _normalized_text(base.get("external_userid")):
        raise LookupError("customer not found")
    preview = preview_signup_conversion_customer(
        external_userid=normalized_external_userid,
        automation_key=scenario_key,
        persist=False,
    )
    marketing_state = dict(preview.get("marketing_state") or {})
    summary = dict(preview.get("summary") or {})
    value_segment = dict(preview.get("value_segment") or {})
    current_stage = _normalized_text(marketing_state.get("stage_key"))
    if current_stage == "converted/enrolled":
        marketing_phase = "exited_signup_success"
        phase_reason = "manual_or_status_conversion"
        lifecycle_status = "exited"
    elif current_stage == _pool_stage_key(POOL_SILENT):
        marketing_phase = "silent_record"
        phase_reason = "silent_pool"
        lifecycle_status = "silent"
    elif batch_context and bool(marketing_state.get("openclaw_eligible")):
        if bool(batch_context.get("blocked_after_quiet_hour")):
            marketing_phase = "blocked_after_2300"
            phase_reason = "window_start_outside_auto_start_window"
            lifecycle_status = "blocked"
        else:
            marketing_phase = "waiting_openclaw"
            phase_reason = "pending_text_message_batch"
            lifecycle_status = "active"
    else:
        marketing_phase = "awaiting_trigger"
        phase_reason = "pool_waiting_followup"
        lifecycle_status = "idle"
    return {
        "scenario_key": scenario_key,
        "external_userid": normalized_external_userid,
        "marketing_state": {
            "marketing_phase": marketing_phase,
            "phase_label": (
                _blocked_phase_label(
                    int((batch_context or {}).get("day_start_hour") or DEFAULT_DAY_START_HOUR),
                    int((batch_context or {}).get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START),
                )
                if marketing_phase == "blocked_after_2300"
                else _PHASE_LABELS.get(marketing_phase, marketing_phase)
            ),
            "phase_reason": phase_reason,
            "lifecycle_status": lifecycle_status,
            "last_batch_id": _normalize_int((batch_context or {}).get("batch_id"), "batch_id", allow_none=True),
            "last_batch_status": _normalized_text((batch_context or {}).get("batch_status")),
            "last_batch_window_start": _normalized_text((batch_context or {}).get("window_start")),
            "last_batch_window_end": _normalized_text((batch_context or {}).get("window_end")),
            "last_trigger_message_at": _normalized_text((batch_context or {}).get("latest_customer_message_at"))
            or _normalized_text(marketing_state.get("last_message_at")),
            "entered_at": _normalized_text(marketing_state.get("entered_at")),
            "exited_at": _normalized_text(marketing_state.get("exited_at")),
            "exit_reason": _normalized_text(marketing_state.get("exit_reason")),
            "updated_at": _normalized_text(marketing_state.get("updated_at")) or _iso_now(),
        },
        "summary": {
            "current_stage": _normalized_text(summary.get("current_stage")),
            "current_stage_display": _normalized_text(summary.get("current_stage_display")),
            "current_pool": _normalized_text(summary.get("current_pool")),
            "current_pool_label": _normalized_text(summary.get("current_pool_label")),
            "current_segment": _normalize_followup_segment(summary.get("current_segment")),
            "current_segment_label": _normalized_text(summary.get("current_segment_label"))
            or _followup_segment_label(summary.get("current_segment")),
            "current_segment_display": _normalized_text(summary.get("current_segment_display"))
            or _followup_segment_label(summary.get("current_segment")),
            "matched_question_ids": list(summary.get("matched_question_ids") or []),
            "matched_questions": list(summary.get("matched_questions") or []),
            "hit_count": int(summary.get("hit_count") or 0),
            "eligible": bool(summary.get("eligible")),
            "eligible_for_conversion": bool(summary.get("eligible_for_conversion")),
            "eligibility_display": _normalized_text(summary.get("eligibility_display"))
            or ("会" if bool(summary.get("eligible")) else "不会"),
            "ineligible_reason": _normalized_text(summary.get("ineligible_reason")),
            "ineligible_reason_display": _normalized_text(summary.get("ineligible_reason_display")),
        },
        "value_segment": {
            "value_segment": _normalize_followup_segment(summary.get("current_segment")),
            "segment_label": _followup_segment_label(summary.get("current_segment")),
            "score": int(summary.get("hit_count") or 0),
            "score_breakdown": {
                "question_hit_count": int(summary.get("hit_count") or 0),
                "matched_question_ids": list(summary.get("matched_question_ids") or []),
                "submission_id": value_segment.get("submission_id"),
            },
            "is_core": _normalize_followup_segment(summary.get("current_segment")) == FOLLOWUP_SEGMENT_FOCUS,
            "is_top": False,
            "updated_at": _normalized_text(value_segment.get("evaluated_at")) or _normalized_text(value_segment.get("updated_at")),
        },
    }


def _load_formatted_batch(batch_id: int) -> dict[str, Any] | None:
    result = archive_repo.get_message_batch(batch_id, limit=500, cursor="")
    if not result:
        return None
    batch, rows, safe_limit, cursor_text = result
    page_rows = list(rows[:safe_limit])
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in page_rows])
    next_cursor = str(page_rows[-1]["batch_item_id"]) if len(rows) > safe_limit and page_rows else ""
    return {
        "batch": dict(batch),
        "messages": [format_message_row(row, group_map=group_map) for row in page_rows],
        "paging": {"limit": safe_limit, "cursor": cursor_text, "next_cursor": next_cursor},
    }


def _build_batch_context(
    batch: dict[str, Any],
    messages: list[dict[str, Any]],
    external_userid: str,
    *,
    day_start_hour: int,
    quiet_hour_start: int,
) -> dict[str, Any]:
    customer_messages = [item for item in messages if _normalized_text(item.get("external_userid")) == external_userid]
    customer_text_messages = [
        item
        for item in customer_messages
        if _normalized_text(item.get("msgtype")).lower() == "text" and _normalized_text(item.get("from")) == external_userid
    ]
    latest_customer_message_at = max((_normalized_text(item.get("send_time")) for item in customer_text_messages), default="")
    window_start = _normalized_text(batch.get("window_start"))
    window_start_dt = _parse_timestamp(window_start)
    blocked_outside_auto_start_window = bool(
        window_start_dt is not None
        and not _is_within_auto_start_window(
            hour=int(window_start_dt.hour),
            day_start_hour=int(day_start_hour),
            quiet_hour_start=int(quiet_hour_start),
        )
    )
    return {
        "batch_id": int(batch.get("id") or 0),
        "batch_status": _normalized_text(batch.get("status")),
        "window_start": window_start,
        "window_end": _normalized_text(batch.get("window_end")),
        "blocked_after_quiet_hour": blocked_outside_auto_start_window,
        "blocked_outside_auto_start_window": blocked_outside_auto_start_window,
        "day_start_hour": int(day_start_hour),
        "quiet_hour_start": int(quiet_hour_start),
        "latest_customer_message_at": latest_customer_message_at,
        "customer_text_count": len(customer_text_messages),
        "candidate_messages": customer_text_messages,
    }


def _router_now(*, timezone: str) -> datetime:
    return datetime.now(ZoneInfo(_validate_timezone(timezone)))


def _router_quiet_hours_blocked(*, config: dict[str, Any]) -> bool:
    day_start_hour = int(config.get("day_start_hour") or DEFAULT_DAY_START_HOUR)
    quiet_hour_start = int(config.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START)
    timezone = _normalized_text(config.get("timezone")) or DEFAULT_TIMEZONE
    return not _is_within_auto_start_window(
        hour=int(_router_now(timezone=timezone).hour),
        day_start_hour=day_start_hour,
        quiet_hour_start=quiet_hour_start,
    )


def _serialize_dispatch_log(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = row.get("dispatch_payload")
    if not isinstance(payload, dict):
        payload = _json_loads(row.get("dispatch_payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    result = dict(row)
    result["dispatch_payload"] = payload
    return result


def _routing_reason_from_preview(
    preview: dict[str, Any],
    *,
    dispatch_status: str = "",
    default_reason: str = "",
) -> str:
    normalized_dispatch_status = _normalized_text(dispatch_status)
    if normalized_dispatch_status == _ROUTER_BLOCKED_DISPATCH_STATUS:
        return _ROUTER_BLOCKED_DISPATCH_STATUS
    if _normalized_text(default_reason):
        return _normalized_text(default_reason)
    config_snapshot = dict(preview.get("config_snapshot") or {})
    summary = dict(preview.get("summary") or {})
    current_stage = _candidate_preview_stage(preview)
    current_segment = _candidate_preview_segment(preview)
    if not bool(config_snapshot.get("enabled")):
        return "automation_disabled"
    if not bool(summary.get("eligible_for_conversion")):
        return _normalized_text(summary.get("ineligible_reason")) or "not_eligible"
    if current_stage == "converted/enrolled":
        return "enrolled"
    if current_stage == _pool_stage_key(POOL_NEW_USER):
        return "awaiting_questionnaire"
    if current_stage == _pool_stage_key(POOL_SILENT):
        return "silent_pool"
    if current_stage not in _ROUTER_ALLOWED_STAGE_KEYS:
        return "pool_not_openclaw_target"
    if current_segment != FOLLOWUP_SEGMENT_FOCUS:
        return "pool_not_focus_followup"
    return "eligible_by_router"


def _message_sender_role(message: dict[str, Any], *, external_userid: str, owner_userid: str) -> str:
    sender = _normalized_text(message.get("from")) or _normalized_text(message.get("sender"))
    if sender and sender == external_userid:
        return "customer"
    if sender and owner_userid and sender == owner_userid:
        return "staff"
    return "unknown"


def _build_recent_text_message_summary(
    external_userid: str,
    *,
    owner_userid: str,
    limit: int,
) -> dict[str, Any]:
    def _summarize_text(value: Any, *, max_length: int = 80) -> str:
        normalized = " ".join(_normalized_text(value).split())
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"

    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return {
            "latest_at": "",
            "latest_customer_message_at": "",
            "latest_customer_message_summary": "",
            "latest_staff_message_at": "",
            "latest_staff_message_summary": "",
            "count": 0,
            "customer_message_count": 0,
            "staff_message_count": 0,
            "sample_size": 0,
            "samples": [],
            "summary_text": "",
        }
    safe_limit = max(1, min(int(limit), 50))
    messages = get_recent_messages_by_user(
        normalized_external_userid,
        limit=max(safe_limit, 10),
        chat_type="private",
        group_chat_map_loader=get_group_chat_map,
    )
    text_items: list[dict[str, Any]] = []
    for item in messages:
        if _normalized_text(item.get("msgtype")).lower() != "text":
            continue
        content = _normalized_text(item.get("content"))
        if not content:
            continue
        text_items.append(
            {
                "send_time": _normalized_text(item.get("send_time")),
                "sender_role": _message_sender_role(
                    item,
                    external_userid=normalized_external_userid,
                    owner_userid=_normalized_text(owner_userid),
                ),
                "content": content,
            }
        )
    preview_items = text_items[:safe_limit]
    latest_customer_message = next(
        (item for item in preview_items if _normalized_text(item.get("sender_role")) == "customer"),
        {},
    )
    latest_staff_message = next(
        (item for item in preview_items if _normalized_text(item.get("sender_role")) == "staff"),
        {},
    )
    samples = [
        {
            "send_time": _normalized_text(item.get("send_time")),
            "sender_role": _normalized_text(item.get("sender_role")),
            "excerpt": _summarize_text(item.get("content")),
        }
        for item in preview_items[:2]
    ]
    summary_parts: list[str] = []
    if latest_customer_message:
        summary_parts.append(f"customer:{_summarize_text(latest_customer_message.get('content'))}")
    if latest_staff_message:
        summary_parts.append(f"staff:{_summarize_text(latest_staff_message.get('content'))}")
    return {
        "latest_at": _normalized_text((preview_items[0] if preview_items else {}).get("send_time")),
        "latest_customer_message_at": _normalized_text(latest_customer_message.get("send_time")),
        "latest_customer_message_summary": _summarize_text(latest_customer_message.get("content")),
        "latest_staff_message_at": _normalized_text(latest_staff_message.get("send_time")),
        "latest_staff_message_summary": _summarize_text(latest_staff_message.get("content")),
        "count": len(text_items),
        "customer_message_count": sum(1 for item in text_items if _normalized_text(item.get("sender_role")) == "customer"),
        "staff_message_count": sum(1 for item in text_items if _normalized_text(item.get("sender_role")) == "staff"),
        "sample_size": len(samples),
        "samples": samples,
        "summary_text": " | ".join(summary_parts),
    }


def _build_openclaw_customer_marketing_profile(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    batch_id: int | None = None,
    dispatch_status: str = "",
    routing_reason: str = "",
    recent_message_limit: int = 3,
) -> dict[str, Any]:
    preview = preview_signup_conversion_customer(
        external_userid=external_userid,
        person_id=person_id,
        automation_key=automation_key,
    )
    resolved_customer = dict(preview.get("resolved_customer") or {})
    resolved_external_userid = _normalized_text(resolved_customer.get("external_userid")) or _normalized_text(external_userid)
    base = repo.load_customer_marketing_base(resolved_external_userid) if resolved_external_userid else {}
    marketing_state = dict(preview.get("marketing_state") or {})
    value_segment = dict(preview.get("value_segment") or {})
    summary = dict(preview.get("summary") or {})
    owner_userid = (
        _normalized_text(base.get("owner_userid"))
        or _normalized_text(((marketing_state.get("state_payload") or {}).get("pool_owner_userid")))
        or DEFAULT_AUTOMATION_OWNER_USERID
    )
    routing = {
        "reason": _routing_reason_from_preview(
            preview,
            dispatch_status=dispatch_status,
            default_reason=routing_reason,
        ),
        "dispatch_status": _normalized_text(dispatch_status),
        "batch_id": _normalize_int(batch_id, "batch_id", allow_none=True),
        "stage_key": _normalized_text(summary.get("current_stage")),
        "segment": _normalize_followup_segment(summary.get("current_segment")),
        "hit_count": int(summary.get("hit_count") or 0),
        "eligible_for_conversion": bool(summary.get("eligible_for_conversion")),
        "ineligible_reason": _normalized_text(summary.get("ineligible_reason")),
    }
    return {
        "external_userid": resolved_external_userid,
        "person_id": _normalize_int(resolved_customer.get("person_id"), "person_id", allow_none=True),
        "customer": {
            "external_userid": resolved_external_userid,
            "person_id": _normalize_int(resolved_customer.get("person_id"), "person_id", allow_none=True),
            "customer_name": _normalized_text(base.get("customer_name")) or resolved_external_userid,
            "mobile": _normalized_text(resolved_customer.get("mobile")) or _normalized_text(base.get("mobile")),
            "signup_status": _normalized_text(base.get("signup_status")),
            "signup_label_name": _normalized_text(base.get("signup_label_name")),
            "is_bound": bool(base.get("is_bound")),
            "tags": _dedupe_tag_names(base),
        },
        "owner": {
            "owner_userid": owner_userid,
            "owner_display_name": _normalized_text(base.get("owner_display_name")) or owner_userid,
        },
        "marketing_state": {
            "main_stage": _normalized_text(marketing_state.get("main_stage")),
            "sub_stage": _normalized_text(marketing_state.get("sub_stage")),
            "stage_key": _normalized_text(marketing_state.get("stage_key")),
            "stage_label": _normalized_text(marketing_state.get("stage_label")),
            "pool_key": _normalized_text(marketing_state.get("pool_key")),
            "pool_label": _normalized_text(marketing_state.get("pool_label")),
            "eligible_for_conversion": bool(marketing_state.get("eligible_for_conversion")),
            "exit_reason": _normalized_text(marketing_state.get("exit_reason")),
            "activated": bool(marketing_state.get("activated")),
            "converted": bool(marketing_state.get("converted")),
            "last_activation_at": _normalized_text(marketing_state.get("last_activation_at")),
            "last_conversion_marked_at": _normalized_text(marketing_state.get("last_conversion_marked_at")),
            "last_message_at": _normalized_text(marketing_state.get("last_message_at")),
        },
        "value_segment": {
            "segment": _normalize_followup_segment(summary.get("current_segment")),
            "segment_label": _followup_segment_label(summary.get("current_segment")),
            "hit_count": int(value_segment.get("hit_count") or 0),
            "matched_question_ids": list(summary.get("matched_question_ids") or []),
            "matched_questions": list(summary.get("matched_questions") or []),
            "submission_id": _normalize_int(value_segment.get("submission_id"), "submission_id", allow_none=True),
            "evaluated_at": _normalized_text(value_segment.get("evaluated_at")),
            "is_core": _normalize_followup_segment(summary.get("current_segment")) == FOLLOWUP_SEGMENT_FOCUS,
            "is_top": False,
        },
        "routing": routing,
        "recent_text_summary": _build_recent_text_message_summary(
            resolved_external_userid,
            owner_userid=owner_userid,
            limit=recent_message_limit,
        ),
    }


def _serialize_conversion_batch_meta(batch: dict[str, Any]) -> dict[str, Any]:
    batch_id = int(batch.get("id") or 0)
    return {
        "id": batch_id,
        "batch_id": batch_id,
        "status": _normalized_text(batch.get("status")),
        "window_start": _normalized_text(batch.get("window_start")),
        "window_end": _normalized_text(batch.get("window_end")),
        "message_count": int(batch.get("message_count") or 0),
        "acked_at": _normalized_text(batch.get("acked_at")),
    }


def _build_openclaw_batch_candidate(
    item: dict[str, Any],
    *,
    batch_id: int,
    automation_key: str,
    recent_message_limit: int,
) -> dict[str, Any]:
    external_userid = _normalized_text(item.get("external_userid"))
    dispatch_status = _normalized_text(item.get("dispatch_status"))
    profile = _build_openclaw_customer_marketing_profile(
        external_userid=external_userid,
        automation_key=automation_key,
        batch_id=batch_id,
        dispatch_status=dispatch_status,
        routing_reason=_normalized_text(item.get("trigger_reason")),
        recent_message_limit=recent_message_limit,
    )
    return {
        "external_userid": external_userid,
        "customer_name": _normalized_text(item.get("customer_name")),
        "owner_userid": _normalized_text(item.get("owner_userid")),
        "dispatch_status": dispatch_status,
        "candidate_message_count": int(item.get("candidate_message_count") or 0),
        "latest_customer_message_at": _normalized_text(item.get("latest_customer_message_at")),
        "routing": dict(profile.get("routing") or {}),
        "marketing_profile": profile,
        "dispatch_log": _serialize_dispatch_log(item.get("dispatch_log")),
    }


def get_openclaw_customer_marketing_profile(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    recent_message_limit: int = 3,
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    return _build_openclaw_customer_marketing_profile(
        external_userid=external_userid,
        person_id=person_id,
        automation_key=automation_key,
        recent_message_limit=recent_message_limit,
    )


def get_conversion_batch(
    batch_id: int,
    *,
    recent_message_limit: int = 3,
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any] | None:
    detail = route_signup_conversion_batch_candidates(batch_id, scenario_key=automation_key)
    if not detail:
        return None
    batch = _serialize_conversion_batch_meta(dict(detail.get("batch") or {}))
    candidates = [
        _build_openclaw_batch_candidate(
            dict(item),
            batch_id=int(batch.get("batch_id") or 0),
            automation_key=automation_key,
            recent_message_limit=recent_message_limit,
        )
        for item in detail.get("candidates") or []
        if isinstance(item, dict)
    ]
    return {
        "automation_key": automation_key,
        "batch": batch,
        "candidate_count": len(candidates),
        "blocked_count": int(detail.get("blocked_count") or 0),
        "skipped_count": int(detail.get("skipped_count") or 0),
        "quiet_hours_blocked": bool(detail.get("quiet_hours_blocked")),
        "candidates": candidates,
        "skipped_customers": list(detail.get("skipped_customers") or []),
    }


def get_pending_conversion_batches(
    *,
    limit: int = 20,
    cursor: str = "",
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    raw_batches = list_signup_conversion_batches(
        limit=limit,
        cursor=cursor,
        scenario_key=automation_key,
    )
    items: list[dict[str, Any]] = []
    for row in raw_batches.get("items") or []:
        if int(row.get("candidate_count") or 0) <= 0:
            continue
        preview_items = []
        for item in row.get("candidates_preview") or []:
            preview_items.append(
                {
                    "external_userid": _normalized_text(item.get("external_userid")),
                    "customer_name": _normalized_text(item.get("customer_name")),
                    "owner_userid": _normalized_text(item.get("owner_userid")),
                    "main_stage": _normalized_text(item.get("current_stage")).split("/", 1)[0],
                    "sub_stage": _normalized_text(item.get("current_stage")).split("/", 1)[1]
                    if "/" in _normalized_text(item.get("current_stage"))
                    else "",
                    "segment": _normalized_text(item.get("value_segment")) or "unknown",
                    "hit_count": int(item.get("score") or 0),
                    "reason": "pending_text_message_batch",
                    "dispatch_status": _normalized_text(item.get("dispatch_status")) or _ROUTER_PENDING_DISPATCH_STATUS,
                }
            )
        items.append(
            {
                "id": int(row.get("id") or 0),
                "batch_id": int(row.get("id") or 0),
                "status": _normalized_text(row.get("status")),
                "window_start": _normalized_text(row.get("window_start")),
                "window_end": _normalized_text(row.get("window_end")),
                "message_count": int(row.get("message_count") or 0),
                "candidate_count": int(row.get("candidate_count") or 0),
                "candidates_preview": preview_items,
            }
        )
    return {
        "automation_key": automation_key,
        "items": items,
        "count": len(items),
        "filters": dict(raw_batches.get("filters") or {}),
        "next_cursor": _normalized_text(raw_batches.get("next_cursor")),
    }


def ack_conversion_batch(
    batch_id: int,
    *,
    acked_by: str = "",
    ack_note: str = "",
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any] | None:
    detail = route_signup_conversion_batch_candidates(int(batch_id), scenario_key=automation_key)
    if not detail:
        return None
    batch = _serialize_conversion_batch_meta(dict(detail.get("batch") or {}))
    existing_logs = {
        _normalized_text(item.get("external_userid")): _serialize_dispatch_log(item)
        for item in repo.list_conversion_dispatch_logs(batch_id=int(batch_id))
    }
    acked_at = _iso_now()
    normalized_acked_by = _normalized_text(acked_by) or "openclaw"
    normalized_ack_note = _normalized_text(ack_note)
    updated_logs: list[dict[str, Any]] = []
    acknowledged_count = 0
    db = get_db()
    try:
        for candidate in detail.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            external_userid = _normalized_text(candidate.get("external_userid"))
            if not external_userid:
                continue
            existing = existing_logs.get(external_userid) or {}
            existing_status = _normalized_text(existing.get("dispatch_status"))
            if existing_status == "acked" and _normalized_text(existing.get("acked_at")):
                updated_logs.append(existing)
                continue
            if existing_status and existing_status not in _OPENCLAW_ACKABLE_DISPATCH_STATUSES:
                continue
            payload = dict(existing.get("dispatch_payload") or {})
            payload.update(
                {
                    "acked_by": normalized_acked_by,
                    "ack_note": normalized_ack_note,
                    "ack_source": "ack_conversion_batch",
                }
            )
            row = repo.upsert_conversion_dispatch_log(
                automation_key=automation_key,
                batch_id=int(batch_id),
                external_userid=external_userid,
                dispatch_status="acked",
                dispatch_channel=_normalized_text(existing.get("dispatch_channel")) or DEFAULT_CHANNEL_TYPE,
                dispatch_payload=payload,
                dispatch_note=normalized_ack_note or f"acked by {normalized_acked_by}",
                dispatched_at=_normalized_text(existing.get("dispatched_at")) or acked_at,
                acked_at=acked_at,
            )
            acknowledged_count += 1
            updated_logs.append(_serialize_dispatch_log(row))
        db.commit()
    except Exception:
        db.rollback()
        raise
    if not updated_logs:
        updated_logs = [
            _serialize_dispatch_log(item)
            for item in repo.list_conversion_dispatch_logs(batch_id=int(batch_id))
            if _normalized_text(item.get("dispatch_status")) == "acked"
        ]
    return {
        "automation_key": automation_key,
        "batch": batch,
        "batch_id": int(batch.get("batch_id") or 0),
        "acknowledged_count": acknowledged_count,
        "dispatch_logs": updated_logs,
        "acked_at": acked_at if acknowledged_count else _normalized_text((updated_logs[0] if updated_logs else {}).get("acked_at")),
        "acked_by": normalized_acked_by,
        "ack_note": normalized_ack_note,
    }




# === Re-exports for backward compatibility (modules split off) ===
from .value_segment_service import (  # noqa: E402,F401
    _compute_submission_hit_result,
    _compute_value_segment,
    _dedupe_tag_names,
    _normalize_answer_option_ids,
    _persist_value_segment,
    _resolve_latest_value_segment_submission,
    _resolve_value_segment_target,
    _serialize_current_customer_value_segment,
    _value_segment_config_ready,
    evaluate_customer_value_segment,
)
from .enrollment_service import (  # noqa: E402,F401
    _build_class_user_snapshot_for_conversion,
    _cancel_dispatches_for_pool_change,
    _cancel_pending_conversion_dispatches,
    _list_pending_conversion_candidate_batch_ids,
    _normalize_conversion_source,
    _normalize_enrolled_signup_status,
    _restore_signup_status_for_unmark,
    mark_enrolled,
    set_manual_followup_segment,
    unmark_enrolled,
)
from .router_dispatch_service import (  # noqa: E402,F401
    _build_disabled_batch_result,
    _candidate_preview_segment,
    _candidate_preview_stage,
    _candidate_skip_entry,
    _ensure_router_dispatch_log,
    get_signup_conversion_batch,
    list_signup_conversion_batches,
    route_signup_conversion_batch_candidates,
)
