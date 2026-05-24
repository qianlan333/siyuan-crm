from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ...db import get_db
from ...infra.settings import (
    get_setting,
)
from ...infra.wecom_runtime import get_app_runtime_client, get_contact_runtime_client  # noqa: F401 - service_seams monkeypatch path
from ...wecom_client import WeComClientError
from ..automation_state.renderer import business_pool_label
from ..automation_state.state_defs import (
    FOLLOWUP_SEGMENT_FOCUS as SHARED_FOLLOWUP_SEGMENT_FOCUS,
    FOLLOWUP_SEGMENT_NORMAL as SHARED_FOLLOWUP_SEGMENT_NORMAL,
)
from ..attachment_library import _normalize_id_list as _normalize_attachment_ids
from ..marketing_automation.service import get_signup_conversion_config, save_signup_conversion_config
from ..outbound_webhook.service import EVENT_OPENCLAW_FOCUS_MESSAGE, send_outbound_webhook
from ..questionnaire.service import get_questionnaire_detail, list_questionnaires
from ..tasks.service import dispatch_wecom_task  # noqa: F401 - legacy monkeypatch seam
from .message_activity_client import query_message_activity_counts  # noqa: F401 - legacy monkeypatch seam
from . import local_projection
from . import repo
from .private_message_dispatch import _dispatch_private_message_batch  # noqa: F401
from .provider import load_channel_provider

DEFAULT_OWNER_STAFF_ID = "HuangYouCan"
DEFAULT_CHANNEL_CODE = "default_qrcode"
DEFAULT_CHANNEL_NAME = "默认渠道二维码"
AI_PUSH_SCENE_SIDEBAR_SCRIPT = "sidebar_script"
AI_PUSH_COOLDOWN_SECONDS = 30
FOCUS_SEND_INTERVAL_SECONDS = 20
TOUCH_PROGRAM_SIGNUP_CONVERSION = "signup_conversion_v1"
TOUCH_SURFACE_STAGE_MANUAL_SEND = "stage_manual_send"
TOUCH_SURFACE_FOCUS_SEND = "focus_send"
MESSAGE_ACTIVITY_SYNC_SOURCE_MANUAL = "manual"
MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED = "scheduled"
ACTIVE_FOCUS_MESSAGE_THRESHOLD = 15
ACTIVE_MESSAGE_MIN_THRESHOLD = 2
REPLY_MONITOR_TRIGGER_TYPE = "reply_monitor"
REPLY_MONITOR_STATUS_PENDING = "pending"
REPLY_MONITOR_STATUS_DEFERRED = "deferred_quiet_hours"
REPLY_MONITOR_STATUS_DISPATCHED = "dispatched"
REPLY_MONITOR_STATUS_FAILED = "failed"
REPLY_MONITOR_STATUS_PAUSED = "paused"
REPLY_MONITOR_DEFAULT_QUIET_HOURS_START = "23:00"
REPLY_MONITOR_DEFAULT_QUIET_HOURS_END = "09:00"
REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS = 30
DEEPSEEK_SETTING_KEYS = (
    "DEEPSEEK_ENABLED",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_ROUTER_MODEL",
    "DEEPSEEK_EXECUTION_MODEL",
    "DEEPSEEK_REASONER_MODEL",
    "DEEPSEEK_TIMEOUT_SECONDS",
)
CHANNEL_STATUS_NOT_GENERATED = "not_generated"
CHANNEL_STATUS_CONFIGURED = "configured"
CHANNEL_STATUS_ACTIVE = "active"


def _program_default_channel_code(program_id: int | None = None) -> str:
    normalized_program_id = int(program_id or 0)
    return f"program_{normalized_program_id}_default_qrcode" if normalized_program_id > 0 else DEFAULT_CHANNEL_CODE


def _lead_qr_from_channel(channel: dict[str, Any] | None) -> dict[str, Any]:
    channel = dict(channel or {})
    qr_url = _normalized_text(channel.get("qr_url"))
    if not qr_url:
        return {}
    return {
        "channel_id": int(channel.get("id") or 0),
        "channel_name": _normalized_text(channel.get("channel_name")),
        "qr_url": qr_url,
        "status": _normalized_text(channel.get("status")),
        "owner_staff_id": _normalized_text(channel.get("owner_staff_id")),
    }


def resolve_lead_channel_for_program(
    program_id: int | None,
    *,
    channel_id: int | None = None,
) -> dict[str, Any] | None:
    normalized_channel_id = int(channel_id or 0)
    if normalized_channel_id > 0:
        channel = repo.get_channel_by_id(normalized_channel_id)
        if channel and _normalized_text(channel.get("qr_url")):
            return channel
    normalized_program_id = int(program_id or 0)
    if normalized_program_id <= 0:
        return None
    channels = repo.list_channels_by_program(normalized_program_id, include_inactive=True)
    preferred = next(
        (
            channel
            for channel in channels
            if _normalized_text(channel.get("qr_url"))
            and _normalized_text(channel.get("status")) in {"active", "configured"}
        ),
        None,
    )
    if preferred:
        return preferred
    fallback = next((channel for channel in channels if _normalized_text(channel.get("qr_url"))), None)
    if fallback:
        return fallback
    return repo.get_default_channel(program_id=normalized_program_id, allow_legacy_fallback=True)


def list_product_lead_plan_options() -> list[dict[str, Any]]:
    from . import program_repo

    options = [
        {
            "program_id": 0,
            "program_name": "不配置引流计划",
            "status": "",
            "channel_id": None,
            "channel_name": "",
            "qr_url": "",
            "selectable": True,
        }
    ]
    for program in program_repo.list_program_rows(include_archived=False):
        status = _normalized_text(program.get("status"))
        if status not in {"active", "draft", "paused"}:
            continue
        qr = _lead_qr_from_channel(resolve_lead_channel_for_program(int(program.get("id") or 0)))
        options.append(
            {
                "program_id": int(program.get("id") or 0),
                "program_name": _normalized_text(program.get("program_name")) or _normalized_text(program.get("program_code")),
                "status": status,
                "channel_id": qr.get("channel_id"),
                "channel_name": qr.get("channel_name", ""),
                "qr_url": qr.get("qr_url", ""),
                "selectable": bool(qr.get("qr_url")),
            }
        )
    return options


def list_product_lead_channel_options() -> list[dict[str, Any]]:
    options = [
        {
            "channel_id": 0,
            "channel_name": "不配置引流渠道码",
            "channel_code": "",
            "program_id": None,
            "program_name": "",
            "status": "",
            "qr_url": "",
            "selectable": True,
        }
    ]
    for channel in repo.list_product_lead_channels():
        program_name = _normalized_text(channel.get("program_name")) or _normalized_text(channel.get("program_code"))
        options.append(
            {
                "channel_id": int(channel.get("id") or 0),
                "channel_name": _normalized_text(channel.get("channel_name")) or _normalized_text(channel.get("channel_code")),
                "channel_code": _normalized_text(channel.get("channel_code")),
                "program_id": int(channel.get("program_id") or 0) or None,
                "program_name": program_name,
                "status": _normalized_text(channel.get("status")),
                "qr_url": _normalized_text(channel.get("qr_url")),
                "selectable": bool(_normalized_text(channel.get("qr_url"))),
            }
        )
    return options


POOL_WON = local_projection.POOL_WON
POOL_REMOVED = local_projection.POOL_REMOVED
POOL_NO_REPLY = local_projection.POOL_NO_REPLY
POOL_HUMAN_REPLY = local_projection.POOL_HUMAN_REPLY
POOL_PENDING_QUESTIONNAIRE = local_projection.POOL_PENDING_QUESTIONNAIRE
POOL_OPERATING = local_projection.POOL_OPERATING
POOL_CONVERTED = local_projection.POOL_CONVERTED

POOL_NEW_USER = POOL_PENDING_QUESTIONNAIRE
POOL_INACTIVE_NORMAL = POOL_OPERATING
POOL_INACTIVE_FOCUS = POOL_OPERATING
POOL_ACTIVE_NORMAL = POOL_OPERATING
POOL_ACTIVE_FOCUS = POOL_OPERATING
POOL_SILENT = POOL_OPERATING

FOLLOWUP_NORMAL = SHARED_FOLLOWUP_SEGMENT_NORMAL
FOLLOWUP_FOCUS = SHARED_FOLLOWUP_SEGMENT_FOCUS

QUESTIONNAIRE_PENDING = "pending"
QUESTIONNAIRE_SUBMITTED = "submitted"

DECISION_SOURCE_QUESTIONNAIRE = "questionnaire"
DECISION_SOURCE_MANUAL = "manual"
DECISION_SOURCE_SYSTEM = "system"

SOURCE_TYPE_MANUAL = "manual"
SOURCE_TYPE_QRCODE = "qrcode"
SOURCE_TYPE_WECOM_CUSTOMER_ACQUISITION = "wecom_customer_acquisition"
SOURCE_TYPE_IMPORT = "import"
SOURCE_TYPE_QUESTIONNAIRE = "questionnaire"
SOURCE_TYPE_SYSTEM = "system"

ACTION_LABELS = {
    "put_in_pool": "放入自动化转化池",
    "remove_from_pool": "移除自动化转化池",
    "set_focus": "转化为重点跟进",
    "set_normal": "转化为普通跟进",
    "mark_won": "确认已成交",
    "unmark_won": "移除已成交",
    "push_openclaw": "一键自动化写话术",
    "message_activity_sync": "消息活跃同步",
    "reply_monitor_capture": "自动接话扫描",
    "reply_monitor_dispatch": "自动接话触发",
    "router_apply_pool": "龙虾异步回调改池",
    "qrcode_welcome_sent": "扫码欢迎语已发送",
    "qrcode_welcome_failed": "扫码欢迎语发送失败",
    "qrcode_entry_tag_applied": "扫码渠道标签已打上",
    "qrcode_entry_tag_failed": "扫码渠道标签打标失败",
}

POOL_LABELS = local_projection.POOL_LABELS
MANUAL_SEND_ALLOWED_POOLS = local_projection.MANUAL_SEND_ALLOWED_POOLS
STAGE_BY_POOL = local_projection.STAGE_BY_POOL
TARGET_BY_POOL = local_projection.TARGET_BY_POOL
STAGE_LABELS = local_projection.STAGE_LABELS
TARGET_LABELS = local_projection.TARGET_LABELS
STAGE_DEFINITIONS = local_projection.STAGE_DEFINITIONS
ROUTE_KEY_TO_POOL = local_projection.ROUTE_KEY_TO_POOL
POOL_TO_STAGE_DEF = local_projection.POOL_TO_STAGE_DEF
MESSAGE_ACTIVITY_SYNC_POOLS = (
    POOL_OPERATING,
)
FOCUS_SEND_ALLOWED_POOLS = local_projection.FOCUS_SEND_ALLOWED_POOLS
SOP_V1_ALLOWED_POOLS = (
    POOL_PENDING_QUESTIONNAIRE,
    POOL_OPERATING,
    POOL_CONVERTED,
)
SOP_V1_DEFAULT_SEND_TIME = "09:00"
SOP_V1_DEFAULT_TIMEZONE = "Asia/Shanghai"
SOP_RUN_SKIPPED_REASON_LABELS = {
    "moved_out_of_pool": "成员已移出当前池子",
    "already_processed_today": "当天这个 day 已处理过",
    "no_template": "当天没有对应模板",
    "template_disabled": "对应 day 模板已禁用",
    "template_empty": "对应 day 模板内容为空",
    "missing_external_userid": "缺少 external_userid",
    "send_time_not_reached": "当前还未到发送时间",
}
SOP_BATCH_STATUS_LABELS = {
    "finished": "已完成",
    "running": "执行中",
    "pending": "待执行",
    "failed": "失败",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = _normalized_text(value)
    if not text:
        return None
    import re as _re
    text = _re.sub(r"[+-]\d{2}(:\d{2})?$", "", text).rstrip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _setting_bool_text(key: str, *, default: bool) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _setting_int_value(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def _setting_text_value(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _phone_last4(phone: Any) -> str:
    text = _normalized_text(phone)
    return text[-4:] if len(text) >= 4 else ""


def _phone_prefix3(phone: Any) -> str:
    text = _normalized_text(phone)
    return text[:3] if len(text) >= 3 else ""


def _phone_match_key(phone: Any) -> str:
    text = _normalized_text(phone)
    if len(text) < 7:
        return ""
    return f"{text[:3]}_{text[-4:]}"


def default_owner_staff_id() -> str:
    return DEFAULT_OWNER_STAFF_ID


def _pool_label(pool: str) -> str:
    shared_label = business_pool_label(pool)
    if shared_label:
        return shared_label
    return local_projection.pool_label(pool)


def _auto_start_window_payload(config: dict[str, Any]) -> dict[str, Any]:
    day_start_hour = int(config.get("day_start_hour") or 9)
    quiet_hour_start = int(config.get("quiet_hour_start") or 23)
    timezone = _normalized_text(config.get("timezone")) or "Asia/Shanghai"
    return {
        "day_start_hour": day_start_hour,
        "quiet_hour_start": quiet_hour_start,
        "timezone": timezone,
        "label": f"{day_start_hour:02d}:00 - {quiet_hour_start:02d}:00",
        "description": f"按 {timezone} 时区，只有 {day_start_hour:02d}:00 - {quiet_hour_start:02d}:00 之间允许自动启动。",
    }

def _focus_send_stage_definition(route_key: str) -> dict[str, Any]:
    return local_projection.focus_send_stage_definition(route_key)




def _stage_from_pool(pool: str) -> str:
    return local_projection.stage_from_pool(pool)


def _stage_label(stage: str) -> str:
    return local_projection.stage_label(stage)


def _target_from_pool(pool: str) -> str:
    return local_projection.target_from_pool(pool)


def _target_label(target: str) -> str:
    return local_projection.target_label(target)


def _follow_type_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {"normal": "普通跟进", "focus": "重点跟进"}.get(normalized, "未定")


def _normalized_follow_type_value(value: Any, *, default: str = "") -> str:
    normalized = _normalized_text(value)
    if normalized in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
        return normalized
    return default


def _resolved_follow_type_for_member(
    member: dict[str, Any] | None,
    questionnaire: dict[str, Any] | None,
    *,
    default: str = "",
) -> str:
    serialized_member = _serialize_member(member or {})
    if _normalized_text(serialized_member.get("decision_source")) == DECISION_SOURCE_MANUAL:
        manual_follow_type = _normalized_follow_type_value(serialized_member.get("follow_type"))
        if manual_follow_type:
            return manual_follow_type
    questionnaire_follow_type = _normalized_follow_type_value((questionnaire or {}).get("resolved_follow_type"))
    if questionnaire_follow_type:
        return questionnaire_follow_type
    return _normalized_follow_type_value(serialized_member.get("follow_type"), default=default)


def _resolved_decision_source_for_member(member: dict[str, Any] | None, questionnaire: dict[str, Any] | None) -> str:
    serialized_member = _serialize_member(member or {})
    if (
        _normalized_text(serialized_member.get("decision_source")) == DECISION_SOURCE_MANUAL
        and _normalized_follow_type_value(serialized_member.get("follow_type"))
    ):
        return DECISION_SOURCE_MANUAL
    if (
        _normalized_text((questionnaire or {}).get("questionnaire_status")) == QUESTIONNAIRE_SUBMITTED
        and _normalized_follow_type_value((questionnaire or {}).get("resolved_follow_type"))
    ):
        return DECISION_SOURCE_QUESTIONNAIRE
    return DECISION_SOURCE_SYSTEM


def _questionnaire_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {QUESTIONNAIRE_PENDING: "待提交", QUESTIONNAIRE_SUBMITTED: "已提交"}.get(normalized, "待提交")


def _decision_source_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        DECISION_SOURCE_MANUAL: "人工改判",
        DECISION_SOURCE_QUESTIONNAIRE: "问卷初判",
        DECISION_SOURCE_SYSTEM: "系统",
    }.get(normalized, "系统")


def _automation_action_label(value: str) -> str:
    normalized = _normalized_text(value)
    return ACTION_LABELS.get(normalized, normalized or "未知操作")


def _serialize_member(member: dict[str, Any]) -> dict[str, Any]:
    serialized = {
        "id": int(member.get("id") or 0) if member.get("id") not in (None, "") else 0,
        "external_contact_id": _normalized_text(member.get("external_contact_id")),
        "phone": _normalized_text(member.get("phone")),
        "master_customer_id": member.get("master_customer_id"),
        "owner_staff_id": _normalized_text(member.get("owner_staff_id")),
        "in_pool": _normalize_bool(member.get("in_pool")),
        "current_pool": _normalized_text(member.get("current_pool")) or POOL_REMOVED,
        "follow_type": _normalized_follow_type_value(member.get("follow_type")),
        "questionnaire_status": _normalized_text(member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING,
        "decision_source": _normalized_text(member.get("decision_source")) or DECISION_SOURCE_SYSTEM,
        "source_type": _normalized_text(member.get("source_type")) or SOURCE_TYPE_SYSTEM,
        "source_channel_id": member.get("source_channel_id"),
        "last_active_pool": _normalized_text(member.get("last_active_pool")),
        "joined_at": _normalized_text(member.get("joined_at")),
        "last_ai_push_at": _normalized_text(member.get("last_ai_push_at")),
        "ai_cooldown_until": _normalized_text(member.get("ai_cooldown_until")),
        "current_audience_code": _normalized_text(member.get("current_audience_code")),
        "current_audience_entered_at": _normalized_text(member.get("current_audience_entered_at")),
        "created_at": _normalized_text(member.get("created_at")),
        "updated_at": _normalized_text(member.get("updated_at")),
    }
    serialized["current_stage"] = _stage_from_pool(serialized["current_pool"])
    serialized["current_stage_label"] = _stage_label(serialized["current_stage"])
    serialized["current_target"] = _target_from_pool(serialized["current_pool"])
    serialized["current_target_label"] = _target_label(serialized["current_target"])
    serialized["current_pool_label"] = _pool_label(serialized["current_pool"])
    serialized["follow_type_label"] = _follow_type_label(serialized["follow_type"])
    serialized["questionnaire_status_label"] = _questionnaire_status_label(serialized["questionnaire_status"])
    serialized["decision_source_label"] = _decision_source_label(serialized["decision_source"])
    return serialized


def _member_snapshot(member: dict[str, Any]) -> dict[str, Any]:
    serialized = _serialize_member(member)
    return {
        "id": serialized["id"],
        "external_contact_id": serialized["external_contact_id"],
        "phone": serialized["phone"],
        "owner_staff_id": serialized["owner_staff_id"],
        "in_pool": serialized["in_pool"],
        "current_pool": serialized["current_pool"],
        "follow_type": serialized["follow_type"],
        "questionnaire_status": serialized["questionnaire_status"],
        "decision_source": serialized["decision_source"],
        "source_type": serialized["source_type"],
        "source_channel_id": serialized["source_channel_id"],
        "last_active_pool": serialized["last_active_pool"],
        "joined_at": serialized["joined_at"],
        "last_ai_push_at": serialized["last_ai_push_at"],
        "ai_cooldown_until": serialized["ai_cooldown_until"],
        "current_audience_code": serialized["current_audience_code"],
        "current_audience_entered_at": serialized["current_audience_entered_at"],
    }


def _question_answer_text(answer_row: dict[str, Any]) -> str:
    option_texts = _json_loads(answer_row.get("selected_option_texts_snapshot"), default=[])
    if isinstance(option_texts, list):
        normalized = [text for text in (_normalized_text(item) for item in option_texts) if text]
        if normalized:
            return " / ".join(normalized)
    text_value = _normalized_text(answer_row.get("text_value"))
    return text_value or "未填写"


def _resolve_lookup(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_phone = _normalized_text(phone)
    if not normalized_external_contact_id and normalized_phone:
        normalized_external_contact_id = repo.find_latest_external_contact_id_by_phone(normalized_phone)
    person_id = repo.lookup_person_id_by_external_contact_id(normalized_external_contact_id) or repo.lookup_person_id_by_phone(normalized_phone)
    return {
        "external_contact_id": normalized_external_contact_id,
        "phone": normalized_phone,
        "master_customer_id": person_id,
        "external_contact_ids": repo.list_external_contact_ids_by_person_id(person_id) if person_id else ([normalized_external_contact_id] if normalized_external_contact_id else []),
    }


def _load_profile(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    from ..admin_console.customer_profile_repo import load_customer_base_profile

    profile = load_customer_base_profile(external_userid=external_contact_id, mobile=phone) or {}
    return {
        "external_contact_id": _normalized_text(profile.get("external_userid")) or _normalized_text(external_contact_id),
        "phone": _normalized_text(profile.get("mobile")) or _normalized_text(phone),
        "customer_name": _normalized_text(profile.get("customer_name")),
        "owner_staff_id": _normalized_text(profile.get("owner_userid")) or _normalized_text(profile.get("owner_display_name")),
        "owner_display_name": _normalized_text(profile.get("owner_display_name")) or _normalized_text(profile.get("owner_userid")),
        "unionid": _normalized_text(profile.get("unionid")),
    }


def _latest_questionnaire_context(external_contact_ids: list[str], phone: str) -> dict[str, Any]:
    def _submitted_context(
        submission: dict[str, Any],
        *,
        questionnaire_id: int | None,
        matched_question_ids: list[int] | None = None,
        matched_questions: list[str] | None = None,
        resolved_follow_type: str = "",
    ) -> dict[str, Any]:
        answer_rows = repo.list_questionnaire_submission_answers(int(submission["id"]))
        answers = [
            {
                "question": _normalized_text(row.get("question_title_snapshot")) or f"问题 {int(row.get('question_id') or 0)}",
                "answer": _question_answer_text(row),
            }
            for row in answer_rows
        ]
        return {
            "questionnaire_status": QUESTIONNAIRE_SUBMITTED,
            "resolved_follow_type": _normalized_follow_type_value(resolved_follow_type),
            "hit_count": len(matched_question_ids or []),
            "matched_question_ids": list(matched_question_ids or []),
            "matched_questions": list(matched_questions or []),
            "answers": answers,
            "submitted_at": _normalized_text(submission.get("submitted_at")),
            "questionnaire_id": questionnaire_id,
            "submission_id": int(submission["id"]),
        }

    settings = get_signup_conversion_config()
    questionnaire_id = settings.get("questionnaire_id")
    if not questionnaire_id:
        any_submission = repo.get_latest_any_questionnaire_submission(
            external_contact_ids=external_contact_ids,
            phone=phone,
        )
        if any_submission:
            return _submitted_context(
                any_submission,
                questionnaire_id=int(any_submission.get("questionnaire_id") or 0) or None,
            )
        return {
            "questionnaire_status": QUESTIONNAIRE_PENDING,
            "resolved_follow_type": "",
            "hit_count": 0,
            "matched_question_ids": [],
            "matched_questions": [],
            "answers": [],
            "submitted_at": "",
            "questionnaire_id": None,
        }
    submission = repo.get_latest_questionnaire_submission(
        questionnaire_id=int(questionnaire_id),
        external_contact_ids=external_contact_ids,
        phone=phone,
    )
    if not submission:
        any_submission = repo.get_latest_any_questionnaire_submission(
            external_contact_ids=external_contact_ids,
            phone=phone,
        )
        if any_submission:
            return _submitted_context(
                any_submission,
                questionnaire_id=int(any_submission.get("questionnaire_id") or 0) or None,
            )
        return {
            "questionnaire_status": QUESTIONNAIRE_PENDING,
            "resolved_follow_type": "",
            "hit_count": 0,
            "matched_question_ids": [],
            "matched_questions": [],
            "answers": [],
            "submitted_at": "",
            "questionnaire_id": int(questionnaire_id),
        }
    answer_rows = repo.list_questionnaire_submission_answers(int(submission["id"]))
    answer_option_map = {
        int(row.get("question_id") or 0): {
            int(option_id)
            for option_id in _json_loads(row.get("selected_option_ids"), default=[])
            if str(option_id).strip()
        }
        for row in answer_rows
    }
    matched_questions: list[str] = []
    matched_question_ids: list[int] = []
    for rule in settings.get("question_rules") or []:
        question_id = int(rule.get("questionnaire_question_id") or 0)
        if question_id <= 0:
            continue
        selected_option_ids = answer_option_map.get(question_id, set())
        hit_option_ids = {
            int(option_id)
            for option_id in rule.get("hit_option_ids_json") or []
            if str(option_id).strip()
        }
        if selected_option_ids and hit_option_ids and selected_option_ids.intersection(hit_option_ids):
            matched_question_ids.append(question_id)
            matched_questions.append(_normalized_text(rule.get("question_title")) or f"问题 {question_id}")
    return _submitted_context(
        submission,
        questionnaire_id=int(questionnaire_id),
        matched_question_ids=matched_question_ids,
        matched_questions=matched_questions,
        resolved_follow_type=FOLLOWUP_FOCUS if len(matched_question_ids) >= int(settings.get("core_threshold") or 0) else FOLLOWUP_NORMAL,
    )


def resolve_member_questionnaire_truth(
    *,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
    member: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = _latest_questionnaire_context(
        [_normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)],
        _normalized_text(phone),
    )
    if resolved.get("questionnaire_id") is not None or member is None:
        return resolved
    fallback_member = _serialize_member(member)
    return {
        "questionnaire_status": _normalized_text(fallback_member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING,
        "resolved_follow_type": _normalized_follow_type_value(fallback_member.get("follow_type")),
        "hit_count": 0,
        "matched_question_ids": [],
        "matched_questions": [],
        "answers": [],
        "submitted_at": "",
        "questionnaire_id": None,
    }


def _build_live_context(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    lookup = _resolve_lookup(external_contact_id=external_contact_id, phone=phone)
    profile = _load_profile(lookup["external_contact_id"], lookup["phone"])
    resolved_external_contact_id = _normalized_text(profile.get("external_contact_id")) or lookup["external_contact_id"]
    resolved_phone = _normalized_text(profile.get("phone")) or lookup["phone"]
    external_contact_ids = list(dict.fromkeys([item for item in lookup["external_contact_ids"] + [resolved_external_contact_id] if _normalized_text(item)]))
    questionnaire = resolve_member_questionnaire_truth(external_contact_ids=external_contact_ids, phone=resolved_phone)
    return {
        "lookup": {**lookup, "external_contact_ids": external_contact_ids},
        "profile": profile,
        "questionnaire": questionnaire,
    }


def recompute_pool(member: dict[str, Any], context: dict[str, Any], *, action: str = "") -> str:
    current_pool = _normalized_text(member.get("current_pool"))
    if current_pool == POOL_WON and action != "unmark_won":
        return POOL_WON
    if current_pool in {POOL_NO_REPLY, POOL_HUMAN_REPLY} and action not in {
        "put_in_pool",
        "set_focus",
        "set_normal",
        "mark_won",
        "unmark_won",
        "remove_from_pool",
    }:
        return current_pool
    if not _normalize_bool(member.get("in_pool")):
        return POOL_REMOVED
    questionnaire_status = _normalized_text(member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING
    if questionnaire_status != QUESTIONNAIRE_SUBMITTED:
        return POOL_PENDING_QUESTIONNAIRE
    return POOL_OPERATING


def _member_payload_from_context(
    existing: dict[str, Any] | None,
    context: dict[str, Any],
    *,
    source_type: str = "",
    source_channel_id: int | None = None,
    in_pool: bool | None = None,
) -> dict[str, Any]:
    existing_row = _serialize_member(existing or {})
    profile = context["profile"]
    questionnaire = context["questionnaire"]
    lookup = context["lookup"]
    resolved_follow_type = _resolved_follow_type_for_member(existing_row, questionnaire)
    base_payload = {
        "external_contact_id": _normalized_text(profile.get("external_contact_id")) or existing_row.get("external_contact_id") or lookup.get("external_contact_id"),
        "phone": _normalized_text(profile.get("phone")) or existing_row.get("phone") or lookup.get("phone"),
        "master_customer_id": lookup.get("master_customer_id") or existing_row.get("master_customer_id"),
        "owner_staff_id": _normalized_text(existing_row.get("owner_staff_id")) or _normalized_text(profile.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
        "in_pool": existing_row.get("in_pool") if in_pool is None else bool(in_pool),
        "current_pool": existing_row.get("current_pool") or POOL_REMOVED,
        "follow_type": resolved_follow_type,
        "questionnaire_status": _normalized_text(questionnaire.get("questionnaire_status")) or existing_row.get("questionnaire_status") or QUESTIONNAIRE_PENDING,
        "decision_source": _resolved_decision_source_for_member(existing_row, questionnaire),
        "source_type": _normalized_text(source_type) or existing_row.get("source_type") or SOURCE_TYPE_SYSTEM,
        "source_channel_id": source_channel_id if source_channel_id is not None else existing_row.get("source_channel_id"),
        "last_active_pool": _normalized_text(existing_row.get("last_active_pool")),
        "joined_at": _normalized_text(existing_row.get("joined_at")),
        "updated_at": _normalized_text(existing_row.get("updated_at")),
        "last_ai_push_at": _normalized_text(existing_row.get("last_ai_push_at")),
        "ai_cooldown_until": _normalized_text(existing_row.get("ai_cooldown_until")),
        "current_audience_code": _normalized_text(existing_row.get("current_audience_code")),
        "current_audience_entered_at": _normalized_text(existing_row.get("current_audience_entered_at")),
    }
    return base_payload


def _substantive_member_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    tracked_fields = (
        "external_contact_id",
        "phone",
        "master_customer_id",
        "owner_staff_id",
        "in_pool",
        "current_pool",
        "follow_type",
        "questionnaire_status",
        "decision_source",
        "source_type",
        "source_channel_id",
        "last_active_pool",
        "joined_at",
        "last_ai_push_at",
        "ai_cooldown_until",
        "current_audience_code",
        "current_audience_entered_at",
    )
    return any(before.get(field) != after.get(field) for field in tracked_fields)


def _sync_sop_progress_for_transition(before: dict[str, Any], after: dict[str, Any]) -> None:
    before_pool = _normalized_text(before.get("current_pool")) if _normalize_bool(before.get("in_pool")) else ""
    after_pool = _normalized_text(after.get("current_pool")) if _normalize_bool(after.get("in_pool")) else ""
    if after_pool not in SOP_V1_ALLOWED_POOLS:
        return
    if before_pool == after_pool and int(before.get("id") or 0) == int(after.get("id") or 0):
        return
    _upsert_sop_progress_entry(
        member_id=int(after.get("id") or 0),
        pool_key=after_pool,
        entered_at=_normalized_text(after.get("updated_at")) or _iso_now(),
    )


def _sync_sop_progress_for_transition_non_blocking(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    try:
        _sync_sop_progress_for_transition(before, after)
        get_db().commit()
        return {"attempted": True, "ok": True, "error": ""}
    except Exception as exc:
        get_db().rollback()
        current_app.logger.exception(
            "automation conversion sop progress sync failed member_id=%s before_pool=%s after_pool=%s",
            int(after.get("id") or 0),
            _normalized_text(before.get("current_pool")),
            _normalized_text(after.get("current_pool")),
        )
        return {"attempted": True, "ok": False, "error": str(exc)}


def _persist_member(member: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    audience_sync_result: dict[str, Any] = {}
    try:
        before = _serialize_member(member or {})
        if member and member.get("id"):
            saved = repo.update_member(int(member["id"]), payload)
        else:
            saved = repo.insert_member(payload)
        from .workflow_runtime import sync_conversion_member_audience

        audience_sync_result = sync_conversion_member_audience(saved)
        saved = repo.get_member_by_id(int(saved["id"])) or saved
        db.commit()
    except Exception:
        db.rollback()
        raise
    if bool(audience_sync_result.get("updated")):
        try:
            from .operation_task_service import run_audience_entered_operation_tasks

            run_audience_entered_operation_tasks(
                member_id=int(audience_sync_result.get("member_id") or 0),
                audience_code=_normalized_text(audience_sync_result.get("audience_code")),
                audience_entry_id=int(audience_sync_result.get("audience_entry_id") or 0),
                operator_id="audience_entered",
            )
        except Exception:
            try:
                get_db().rollback()
            except Exception:
                pass
            try:
                current_app.logger.exception(
                    "automation operation task audience-entered trigger failed member_id=%s audience=%s",
                    audience_sync_result.get("member_id"),
                    audience_sync_result.get("audience_code"),
                )
            except Exception:
                pass
    _sync_sop_progress_for_transition_non_blocking(before, _serialize_member(saved))
    return repo.get_member_by_id(int(saved["id"])) or saved


def _write_event(
    *,
    member_id: int,
    action: str,
    operator_type: str,
    operator_id: str,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    remark: str = "",
) -> dict[str, Any]:
    db = get_db()
    try:
        saved = repo.insert_event(
            member_id=int(member_id),
            action=action,
            operator_type=operator_type,
            operator_id=operator_id,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            remark=remark,
        )
        db.commit()
        return saved
    except Exception:
        db.rollback()
        raise


def _send_channel_welcome_message(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    welcome_message = _normalized_text(channel.get("welcome_message"))
    payload = _json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    welcome_code = ""
    for key in ("WelcomeCode", "welcome_code", "welcomeCode"):
        welcome_code = _normalized_text(payload.get(key))
        if welcome_code:
            break
    if not welcome_message:
        return {"attempted": False, "sent": False, "reason": "not_configured"}
    if not welcome_code:
        return {"attempted": False, "sent": False, "reason": "welcome_code_missing"}
    serialized_member = _serialize_member(member)
    request_payload: dict[str, Any] = {
        "welcome_code": welcome_code,
        "text": {"content": welcome_message},
    }
    welcome_library_ids: list[int] = []
    raw_library_ids = channel.get("welcome_miniprogram_library_ids") or []
    if isinstance(raw_library_ids, str):
        try:
            import json as _json

            raw_library_ids = _json.loads(raw_library_ids)
        except (ValueError, TypeError):
            raw_library_ids = []
    for value in raw_library_ids or []:
        try:
            welcome_library_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if welcome_library_ids:
        from .. import miniprogram_library as _miniprogram_library

        welcome_attachments: list[dict[str, Any]] = []
        for lid in welcome_library_ids:
            welcome_attachments.append(
                _miniprogram_library.materialize_miniprogram_attachment(lid)
            )
        if welcome_attachments:
            request_payload["attachments"] = welcome_attachments
    try:
        raw_attachment_ids = channel.get("welcome_attachment_library_ids") or []
        if raw_attachment_ids:
            from .. import attachment_library as _attachment_library

            welcome_attachments = list(request_payload.get("attachments") or [])
            for aid in _attachment_library._normalize_id_list(raw_attachment_ids):
                welcome_attachments.append(_attachment_library.materialize_file_attachment(aid))
            if len(welcome_attachments) > 9:
                raise ValueError("welcome message supports at most 9 attachments")
            if welcome_attachments:
                request_payload["attachments"] = welcome_attachments
    except (ValueError, RuntimeError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {"attempted": True, "sent": False, "error": str(exc)}
    try:
        wecom_result = get_contact_runtime_client().send_welcome_msg(request_payload)
    except (WeComClientError, AttributeError, ValueError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {"attempted": True, "sent": False, "error": str(exc)}

    _write_event(
        member_id=int(member["id"]),
        action="qrcode_welcome_sent",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(serialized_member),
        after_snapshot=_member_snapshot(serialized_member),
        remark="official_send_welcome_msg",
    )
    return {
        "attempted": True,
        "sent": True,
        "via": "send_welcome_msg",
        "wecom_result": dict(wecom_result or {}),
    }


def _touch_member_from_sources(
    member: dict[str, Any],
    *,
    action: str,
    operator_type: str = "system",
    operator_id: str = "system",
    persist_event: bool = False,
) -> dict[str, Any]:
    serialized_before = _serialize_member(member)
    context = _build_live_context(serialized_before["external_contact_id"], serialized_before["phone"])
    next_payload = _member_payload_from_context(member, {**context, "settings": get_signup_conversion_config()})
    next_payload["joined_at"] = serialized_before.get("joined_at") or _iso_now()
    next_payload["current_pool"] = recompute_pool(next_payload, {**context, "settings": get_signup_conversion_config()}, action=action)
    if not _substantive_member_changed(serialized_before, next_payload):
        return member
    saved = _persist_member(member, next_payload)
    if persist_event:
        _write_event(
            member_id=int(saved["id"]),
            action=action,
            operator_type=operator_type,
            operator_id=operator_id,
            before_snapshot=_member_snapshot(serialized_before),
            after_snapshot=_member_snapshot(saved),
        )
    return saved


def refresh_expired_silent_members() -> dict[str, Any]:
    return {"refreshed_count": 0}



def _inactive_follow_type_from_member(before: dict[str, Any]) -> tuple[str, str, bool]:
    manual_preserved = (
        _normalized_text(before.get("decision_source")) == DECISION_SOURCE_MANUAL
        and _normalized_text(before.get("follow_type")) in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}
    )
    if manual_preserved:
        return _normalized_text(before.get("follow_type")), _normalized_text(before.get("decision_source")) or DECISION_SOURCE_MANUAL, True
    questionnaire = resolve_member_questionnaire_truth(
        external_contact_ids=[_normalized_text(before.get("external_contact_id"))] if _normalized_text(before.get("external_contact_id")) else [],
        phone=_normalized_text(before.get("phone")),
        member=before,
    )
    next_follow_type = _resolved_follow_type_for_member(before, questionnaire, default=FOLLOWUP_NORMAL)
    next_decision_source = _resolved_decision_source_for_member(before, questionnaire)
    return next_follow_type, next_decision_source, False


def _questionnaire_rule_editor_question(question: dict[str, Any]) -> dict[str, Any] | None:
    question_type = _normalized_text(question.get("type"))
    if question_type not in {"single_choice", "multi_choice"}:
        return None
    options = [
        {
            "id": int(option.get("id") or 0),
            "option_text": _normalized_text(option.get("option_text")) or f"选项 {int(option.get('id') or 0)}",
        }
        for option in question.get("options") or []
        if int(option.get("id") or 0) > 0
    ]
    return {
        "id": int(question.get("id") or 0),
        "title": _normalized_text(question.get("title")) or f"问题 {int(question.get('id') or 0)}",
        "type": question_type,
        "options": options,
    }


def _build_questionnaire_rule_catalog(questionnaires: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for item in questionnaires:
        questionnaire_id = int(item.get("id") or 0)
        if questionnaire_id <= 0:
            continue
        try:
            detail = get_questionnaire_detail(questionnaire_id)
        except Exception:
            detail = None
        if not detail:
            continue
        catalog[str(questionnaire_id)] = {
            "id": questionnaire_id,
            "title": _normalized_text(detail.get("title")) or _normalized_text(detail.get("name")) or f"问卷 #{questionnaire_id}",
            "is_disabled": _normalize_bool(detail.get("is_disabled")),
            "questions": [
                editor_question
                for question in detail.get("questions") or []
                for editor_question in [_questionnaire_rule_editor_question(question)]
                if editor_question
            ],
        }
    return catalog

def get_settings_payload(*, program_id: int | None = None) -> dict[str, Any]:
    config = get_signup_conversion_config()
    normalized_program_id = int(program_id or 0) or None
    channel = repo.get_default_channel(program_id=normalized_program_id) or {}
    provider = load_channel_provider()
    questionnaires = list_questionnaires()
    questionnaire_rule_catalog = _build_questionnaire_rule_catalog(questionnaires)
    questionnaire = None
    questionnaire_missing = bool(config.get("questionnaire_missing"))
    questionnaire_id = config.get("questionnaire_id") or config.get("missing_questionnaire_id")
    if questionnaire_id not in (None, ""):
        if not questionnaire_missing:
            try:
                questionnaire = get_questionnaire_detail(int(questionnaire_id))
            except Exception:
                questionnaire = None
                questionnaire_missing = True
            else:
                questionnaire_missing = not bool(questionnaire)
    rule_editor_questionnaire_id = (
        _normalized_text(config.get("questionnaire_id"))
        if not questionnaire_missing and config.get("questionnaire_id") not in (None, "")
        else ""
    )
    selected_catalog_item = questionnaire_rule_catalog.get(rule_editor_questionnaire_id)
    return {
        "questionnaires": questionnaires,
        "selected_questionnaire": questionnaire,
        "questionnaire_missing": questionnaire_missing,
        "missing_questionnaire_id": int(questionnaire_id) if questionnaire_missing and questionnaire_id not in (None, "") else None,
        "config": config,
        "questionnaire_rule_catalog": questionnaire_rule_catalog,
        "rule_editor": {
            "selected_questionnaire_id": rule_editor_questionnaire_id,
            "selected_questionnaire": selected_catalog_item,
            "rules": list(config.get("question_rules") or []) if not questionnaire_missing else [],
            "rules_invalidated": questionnaire_missing,
        },
        "default_channel": {
            "program_id": normalized_program_id,
            "channel_code": _normalized_text(channel.get("channel_code")) or DEFAULT_CHANNEL_CODE,
            "channel_name": _normalized_text(channel.get("channel_name")) or DEFAULT_CHANNEL_NAME,
            "qr_url": _normalized_text(channel.get("qr_url")),
            "qr_ticket": _normalized_text(channel.get("qr_ticket")),
            "scene_value": _normalized_text(channel.get("scene_value")),
            "welcome_message": _normalized_text(channel.get("welcome_message")),
            "welcome_attachment_library_ids": _normalize_attachment_ids(channel.get("welcome_attachment_library_ids")),
            "auto_accept_friend": _normalize_bool(channel.get("auto_accept_friend")),
            "entry_tag_id": _normalized_text(channel.get("entry_tag_id")),
            "entry_tag_name": _normalized_text(channel.get("entry_tag_name")),
            "entry_tag_group_name": _normalized_text(channel.get("entry_tag_group_name")),
            "owner_staff_id": _normalized_text(channel.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
            "status": _normalized_text(channel.get("status")) or CHANNEL_STATUS_NOT_GENERATED,
            "field_statuses": _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(channel.get("status")) or CHANNEL_STATUS_NOT_GENERATED,
                welcome_message=_normalized_text(channel.get("welcome_message")),
                welcome_attachment_library_ids=_normalize_attachment_ids(channel.get("welcome_attachment_library_ids")),
                auto_accept_friend=_normalize_bool(channel.get("auto_accept_friend")),
                entry_tag_name=_normalized_text(channel.get("entry_tag_name")),
            ),
        },
        "default_owner_staff_id": DEFAULT_OWNER_STAFF_ID,
        "provider_available": provider is not None,
        "message_activity_sync": _message_activity_sync_status_payload(),
        "reply_monitor": _reply_monitor_status_payload(),
    }


def _coerce_legacy_settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = dict(payload or {})

    if "question_rules" not in normalized_payload and "question_rules_json" in normalized_payload:
        raw_question_rules = normalized_payload.get("question_rules_json")
        normalized_payload["question_rules"] = _json_loads(
            raw_question_rules,
            default=raw_question_rules,
        )

    if "silent_threshold_days_by_pool" not in normalized_payload:
        legacy_threshold_keys = {
            "silent_threshold_new_user": "new_user",
            "silent_threshold_inactive_normal": "inactive_normal",
            "silent_threshold_inactive_focus": "inactive_focus",
            "silent_threshold_active_normal": "active_normal",
            "silent_threshold_active_focus": "active_focus",
        }
        legacy_thresholds = {
            pool_key: normalized_payload.get(legacy_key)
            for legacy_key, pool_key in legacy_threshold_keys.items()
            if legacy_key in normalized_payload
        }
        if legacy_thresholds:
            normalized_payload["silent_threshold_days_by_pool"] = legacy_thresholds

    return normalized_payload


def save_settings(payload: dict[str, Any], *, program_id: int | None = None) -> dict[str, Any]:
    normalized_payload = _coerce_legacy_settings_payload(payload or {})
    normalized_program_id = int(program_id or normalized_payload.get("program_id") or 0) or None
    config_payload = {
        "enabled": _normalize_bool(normalized_payload.get("enabled", True)),
        "questionnaire_id": normalized_payload.get("questionnaire_id"),
        "core_threshold": normalized_payload.get("core_threshold"),
        "top_threshold": normalized_payload.get("top_threshold", normalized_payload.get("core_threshold")),
        "day_start_hour": normalized_payload.get("day_start_hour"),
        "quiet_hour_start": normalized_payload.get("quiet_hour_start"),
        "timezone": normalized_payload.get("timezone"),
        "silent_threshold_days_by_pool": normalized_payload.get("silent_threshold_days_by_pool"),
        "question_rules": normalized_payload.get("question_rules"),
    }
    save_signup_conversion_config(config_payload, enforce_required_mobile_question=True)
    existing = repo.get_default_channel(program_id=normalized_program_id) or {}
    entry_tag_payload = _effective_channel_entry_tag_payload(normalized_payload, existing)
    next_channel_name = _normalized_text(normalized_payload.get("channel_name")) or _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    next_welcome_message = (
        _normalized_text(normalized_payload.get("welcome_message"))
        if "welcome_message" in normalized_payload
        else _normalized_text(existing.get("welcome_message"))
    )
    next_auto_accept_friend = (
        _normalize_bool(normalized_payload.get("auto_accept_friend"))
        if "auto_accept_friend" in normalized_payload
        else _normalize_bool(existing.get("auto_accept_friend"))
    )
    current_channel_name = _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    current_welcome_message = _normalized_text(existing.get("welcome_message"))
    current_auto_accept_friend = _normalize_bool(existing.get("auto_accept_friend"))
    channel_settings_changed = (
        next_channel_name != current_channel_name
        or next_welcome_message != current_welcome_message
        or next_auto_accept_friend != current_auto_accept_friend
        or entry_tag_payload["entry_tag_id"] != _normalized_text(existing.get("entry_tag_id"))
        or entry_tag_payload["entry_tag_name"] != _normalized_text(existing.get("entry_tag_name"))
        or entry_tag_payload["entry_tag_group_name"] != _normalized_text(existing.get("entry_tag_group_name"))
    )
    repo.save_channel(
        {
            "program_id": normalized_program_id,
            "channel_code": _program_default_channel_code(normalized_program_id),
            "channel_name": next_channel_name,
            "qr_url": _normalized_text(normalized_payload.get("qr_url")) or _normalized_text(existing.get("qr_url")),
            "qr_ticket": _normalized_text(normalized_payload.get("qr_ticket")) or _normalized_text(existing.get("qr_ticket")),
            "scene_value": _normalized_text(normalized_payload.get("scene_value")) or _normalized_text(existing.get("scene_value")),
            "welcome_message": next_welcome_message,
            "auto_accept_friend": next_auto_accept_friend,
            "entry_tag_id": entry_tag_payload["entry_tag_id"],
            "entry_tag_name": entry_tag_payload["entry_tag_name"],
            "entry_tag_group_name": entry_tag_payload["entry_tag_group_name"],
            "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
            "status": (
                CHANNEL_STATUS_CONFIGURED
                if channel_settings_changed
                else (
                    _normalized_text(normalized_payload.get("channel_status"))
                    or _normalized_text(existing.get("status"))
                    or CHANNEL_STATUS_CONFIGURED
                )
            ),
        }
    )
    get_db().commit()
    return get_settings_payload(program_id=normalized_program_id)


def _resolve_existing_member(external_contact_id: str = "", phone: str = "") -> dict[str, Any] | None:
    from . import member_state_service

    return member_state_service._resolve_existing_member(
        external_contact_id=external_contact_id,
        phone=phone,
    )


def get_member_detail(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.get_member_detail(
        external_contact_id=external_contact_id,
        phone=phone,
    )


def _button_state(member: dict[str, Any]) -> dict[str, Any]:
    return local_projection.button_state(
        current_pool=_normalized_text(member.get("current_pool")),
        in_pool=bool(member.get("in_pool")),
    )


def _mutate_member(
    *,
    external_contact_id: str = "",
    phone: str = "",
    action: str,
    operator_id: str,
    operator_type: str = "user",
    include_detail: bool = True,
    mutate,
) -> dict[str, Any]:
    from . import member_state_service

    return member_state_service._mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action=action,
        operator_id=operator_id,
        operator_type=operator_type,
        include_detail=include_detail,
        mutate=mutate,
    )


def apply_router_target_pool(
    *,
    external_contact_id: str = "",
    phone: str = "",
    target_pool: str,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.apply_router_target_pool(
        external_contact_id=external_contact_id,
        phone=phone,
        target_pool=target_pool,
        operator_id=operator_id,
        operator_type=operator_type,
    )


def put_in_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.put_in_pool(
        external_contact_id=external_contact_id,
        phone=phone,
        operator_id=operator_id,
    )


def remove_from_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.remove_from_pool(
        external_contact_id=external_contact_id,
        phone=phone,
        operator_id=operator_id,
    )


def set_follow_type(*, external_contact_id: str = "", phone: str = "", follow_type: str, operator_id: str = "") -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.set_follow_type(
        external_contact_id=external_contact_id,
        phone=phone,
        follow_type=follow_type,
        operator_id=operator_id,
    )


def mark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.mark_won(
        external_contact_id=external_contact_id,
        phone=phone,
        operator_id=operator_id,
    )


def unmark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.unmark_won(
        external_contact_id=external_contact_id,
        phone=phone,
        operator_id=operator_id,
    )


def _build_openclaw_payload(member: dict[str, Any]) -> dict[str, Any]:
    from ..admin_console.customer_profile_service import (
        get_customer_messages_payload,
        get_customer_profile_tags_payload,
        get_customer_questionnaire_answers_payload,
    )

    serialized = _serialize_member(member)
    external_contact_id = serialized["external_contact_id"]
    phone = serialized["phone"]
    tags_payload = get_customer_profile_tags_payload(external_userid=external_contact_id) if external_contact_id else {"tags": []}
    questionnaire_payload = get_customer_questionnaire_answers_payload(external_userid=external_contact_id, mobile=phone)
    messages_payload = get_customer_messages_payload(external_userid=external_contact_id, mobile=phone, limit=20)
    return {
        "externalContactId": external_contact_id,
        "currentPool": serialized["current_pool"],
        "currentStage": serialized["current_stage"],
        "currentTarget": serialized["current_target"],
        "tags": [(_normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))) for item in tags_payload.get("tags") or []],
        "questionnaire": {
            "status": serialized["questionnaire_status"],
            "answers": [
                {
                    "question": _normalized_text(item.get("question")),
                    "answer": _normalized_text(item.get("answer")),
                }
                for item in (questionnaire_payload.get("answers") or [])
            ],
        },
        "recentChats": [
            {
                "role": "customer" if _normalized_text(item.get("sender")) == external_contact_id else "staff",
                "time": _normalized_text(item.get("send_time")),
                "content": _normalized_text(item.get("content")),
            }
            for item in messages_payload.get("messages") or []
        ][:20],
    }


def push_openclaw(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        raise LookupError("automation member not found")
    serialized = _serialize_member(member)
    if serialized["current_pool"] == POOL_REMOVED:
        raise ValueError("removed member cannot push openclaw")
    cooldown_until = _parse_timestamp(serialized["ai_cooldown_until"])
    now = datetime.now()
    if cooldown_until and cooldown_until > now:
        remaining_seconds = max(1, int((cooldown_until - now).total_seconds()))
        repo.insert_ai_push_log(
            member_id=int(serialized["id"]),
            scene=AI_PUSH_SCENE_SIDEBAR_SCRIPT,
            request_payload={"memberId": str(serialized["id"])},
            status="cooldown_blocked",
            error_message=f"cooldown:{remaining_seconds}",
            pushed_at=_iso_now(),
            cooldown_until=serialized["ai_cooldown_until"],
        )
        get_db().commit()
        return {"accepted": False, "status": "cooldown_blocked", "remaining_seconds": remaining_seconds}
    payload = _build_openclaw_payload(member)
    delivery = send_outbound_webhook(
        event_type=EVENT_OPENCLAW_FOCUS_MESSAGE,
        payload=payload,
        source_key="automation_member",
        source_id=str(serialized["id"]),
    )
    now_text = _iso_now()
    if delivery.get("ok"):
        cooldown_until_text = (datetime.now() + timedelta(seconds=AI_PUSH_COOLDOWN_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
        updated = _persist_member(
            member,
            {
                **serialized,
                "last_ai_push_at": now_text,
                "ai_cooldown_until": cooldown_until_text,
            },
        )
        repo.insert_ai_push_log(
            member_id=int(serialized["id"]),
            scene=AI_PUSH_SCENE_SIDEBAR_SCRIPT,
            request_payload=payload,
            status="accepted",
            request_id=str(((delivery.get("delivery") or {}).get("id") or "")),
            pushed_at=now_text,
            cooldown_until=cooldown_until_text,
        )
        get_db().commit()
        return {
            "accepted": True,
            "status": "accepted",
            "member": _serialize_member(updated),
            "cooldown_until": cooldown_until_text,
        }
    repo.insert_ai_push_log(
        member_id=int(serialized["id"]),
        scene=AI_PUSH_SCENE_SIDEBAR_SCRIPT,
        request_payload=payload,
        status="failed",
        request_id=str(((delivery.get("delivery") or {}).get("id") or "")),
        error_message=_normalized_text(delivery.get("reason")),
        pushed_at=now_text,
        cooldown_until="",
    )
    get_db().commit()
    return {"accepted": False, "status": "failed", "error": _normalized_text(delivery.get("reason")) or "openclaw webhook failed"}


def get_overview_payload() -> dict[str, Any]:
    refresh_expired_silent_members()
    counts = repo.get_overview_counts()
    metrics_map = {_normalized_text(item.get("current_pool")): item for item in repo.get_stage_metrics()}
    message_activity_sync = _message_activity_sync_status_payload()
    reply_monitor = _reply_monitor_status_payload()
    config = get_signup_conversion_config()
    cards = [
        {"key": "in_pool_total", "label": "在池总人数", "value": counts["in_pool_total"], "description": "当前仍在自动化池里的成员数量。"},
        {"key": "today_joined", "label": "今日入池", "value": counts["today_joined"], "description": "今天新进入自动化池的成员数量。"},
        {"key": "questionnaire_pending", "label": "未填问卷人群", "value": counts["questionnaire_pending"], "description": "已入池但还没提交问卷。"},
        {"key": "operating_total", "label": "运营中人群", "value": counts["operating_total"], "description": "问卷提交后的统一运营人群。"},
        {"key": "converted_total", "label": "已转化人群", "value": counts["converted_total"], "description": "确认转化后的成员数量。"},
    ]
    stage_columns = []
    for definition in STAGE_DEFINITIONS:
        metric = metrics_map.get(definition["pool"], {})
        stage_columns.append(
            {
                "route_key": definition["route_key"],
                "pool": definition["pool"],
                "label": definition["label"],
                "description": definition["description"],
                "total_count": int(metric.get("total_count") or 0),
                "focus_count": int(metric.get("focus_count") or 0),
                "normal_count": int(metric.get("normal_count") or 0),
                "today_new_count": int(metric.get("today_new_count") or 0),
            }
        )
    return {
        "cards": cards,
        "stage_columns": stage_columns,
        "counts": counts,
        "message_activity_sync": message_activity_sync,
        "reply_monitor": reply_monitor,
        "auto_start_window": _auto_start_window_payload(config),
    }


def get_stage_detail_payload(*, route_key: str, keyword: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    refresh_expired_silent_members()
    pool = ROUTE_KEY_TO_POOL.get(_normalized_text(route_key))
    if not pool:
        raise ValueError("invalid stage")
    definition = POOL_TO_STAGE_DEF[pool]
    metrics_map = {_normalized_text(item.get("current_pool")): item for item in repo.get_stage_metrics()}
    metric = metrics_map.get(pool, {})
    rows = repo.list_stage_members(current_pool=pool, keyword=keyword, limit=limit, offset=offset)
    customers = []
    for row in rows:
        serialized = _serialize_member(row)
        profile = _load_profile(serialized["external_contact_id"], serialized["phone"])
        customers.append(
            {
                "member_id": serialized["id"],
                "external_userid": serialized["external_contact_id"],
                "customer_name": _normalized_text(profile.get("customer_name")) or "",
                "owner_display_name": _normalized_text(profile.get("owner_display_name"))
                or _normalized_text(profile.get("owner_staff_id"))
                or serialized["owner_staff_id"],
                "owner_userid": _normalized_text(profile.get("owner_staff_id")) or serialized["owner_staff_id"],
                "mobile": serialized["phone"],
                "last_touch_at": serialized["updated_at"] or serialized["joined_at"],
                "current_stage_label": serialized["current_stage_label"],
                "current_target_label": serialized["current_target_label"],
            }
        )
    total = repo.count_stage_members(current_pool=pool, keyword=keyword)
    return {
        "stage": {
            "pool": pool,
            "route_key": definition["route_key"],
            "label": definition["label"],
            "description": definition["description"],
            "total_count": int(metric.get("total_count") or 0),
            "focus_count": int(metric.get("focus_count") or 0),
            "normal_count": int(metric.get("normal_count") or 0),
            "today_new_count": int(metric.get("today_new_count") or 0),
        },
        "filters": {"keyword": _normalized_text(keyword)},
        "customers": customers,
        "pagination": {
            "total": int(total),
            "offset": int(offset),
            "limit": int(limit),
            "has_prev": int(offset) > 0,
            "has_next": int(offset) + int(limit) < int(total),
            "prev_offset": max(int(offset) - int(limit), 0),
            "next_offset": int(offset) + int(limit),
        },
    }


def _has_existing_touch_delivery(*, touch_surface: str, rule_key: str, external_contact_id: str) -> bool:
    normalized_surface = _normalized_text(touch_surface)
    normalized_rule_key = _normalized_text(rule_key)
    normalized_external_contact_id = _normalized_text(external_contact_id)
    if not normalized_surface or not normalized_rule_key or not normalized_external_contact_id:
        return False
    existing_delivery = repo.get_active_touch_delivery(
        program_code=TOUCH_PROGRAM_SIGNUP_CONVERSION,
        touch_surface=normalized_surface,
        rule_key=normalized_rule_key,
        external_contact_id=normalized_external_contact_id,
    )
    if existing_delivery:
        return True
    if normalized_surface == TOUCH_SURFACE_FOCUS_SEND:
        return repo.has_historical_focus_send_delivery(
            rule_key=normalized_rule_key,
            external_contact_id=normalized_external_contact_id,
        )
    if normalized_surface == TOUCH_SURFACE_STAGE_MANUAL_SEND:
        return repo.has_historical_stage_manual_send_delivery(
            rule_key=normalized_rule_key,
            external_contact_id=normalized_external_contact_id,
        )
    return False


def _event_payloads(member_id: int, limit: int = 10) -> list[dict[str, Any]]:
    return [repo.deserialize_event_row(row) for row in repo.list_recent_events(member_id, limit=limit)]


def get_debug_payload(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_phone = _normalized_text(phone)
    if not normalized_external_contact_id and not normalized_phone:
        empty_member = _serialize_member({})
        return {
            "lookup": {"external_contact_id": "", "phone": ""},
            "member_exists": False,
            "member": empty_member,
            "profile": {
                "customer_name": "未命名客户",
                "owner_staff_id": "",
                "owner_display_name": "",
                "external_contact_id": "",
                "phone": "",
                "unionid": "",
            },
            "questionnaire": {
                "status": QUESTIONNAIRE_PENDING,
                "status_label": _questionnaire_status_label(QUESTIONNAIRE_PENDING),
                "hit_count": 0,
                "matched_questions": [],
                "submitted_at": "",
            },
            "current_pool": empty_member["current_pool"],
            "current_stage": empty_member["current_stage"],
            "current_target": empty_member["current_target"],
            "manual_override_preferred": False,
            "recent_events": [],
        }
    detail = get_member_detail(external_contact_id=external_contact_id, phone=phone)
    member = detail["member"]
    events = _event_payloads(int(member["id"]), 10) if detail["member_exists"] and int(member["id"] or 0) > 0 else []
    return {
        "lookup": {"external_contact_id": _normalized_text(external_contact_id), "phone": _normalized_text(phone)},
        "member_exists": detail["member_exists"],
        "member": member,
        "profile": detail["profile"],
        "questionnaire": detail["questionnaire"],
        "current_pool": member["current_pool"],
        "current_stage": member["current_stage"],
        "current_target": member["current_target"],
        "manual_override_preferred": member["decision_source"] == DECISION_SOURCE_MANUAL,
        "recent_events": events,
    }


def sync_member_from_questionnaire_submission(
    *,
    external_contact_id: str = "",
    phone: str = "",
    questionnaire_id: int | None = None,
    operator_id: str = "system",
) -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.sync_member_from_questionnaire_submission(
        external_contact_id=external_contact_id,
        phone=phone,
        questionnaire_id=questionnaire_id,
        operator_id=operator_id,
    )


def sync_member_activation(*, external_contact_id: str = "", phone: str = "", operator_id: str = "system") -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.sync_member_activation(
        external_contact_id=external_contact_id,
        phone=phone,
        operator_id=operator_id,
    )


def _extract_channel_scene(payload_json: dict[str, Any]) -> str:
    from . import member_state_service

    return member_state_service._extract_channel_scene(payload_json)


def _extract_welcome_code(payload_json: dict[str, Any]) -> str:
    from . import member_state_service

    return member_state_service._extract_welcome_code(payload_json)


def _send_channel_welcome_message(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    from . import member_state_service

    return member_state_service._send_channel_welcome_message(
        member=member,
        channel=channel,
        payload_json=payload_json,
        operator_id=operator_id,
    )


def _apply_channel_entry_tag(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    operator_id: str = "",
) -> dict[str, Any]:
    from . import member_state_service

    return member_state_service._apply_channel_entry_tag(
        member=member,
        channel=channel,
        operator_id=operator_id,
    )


def handle_qrcode_enter_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
    follow_user_userid: str = "",
    send_welcome_message: bool = False,
) -> dict[str, Any]:
    from . import member_state_service

    return member_state_service.handle_qrcode_enter_from_callback(
        external_contact_id=external_contact_id,
        phone=phone,
        payload_json=payload_json,
        operator_id=operator_id,
        follow_user_userid=follow_user_userid,
        send_welcome_message=send_welcome_message,
    )


# === Re-exports for backward compatibility (modules split off) ===
# These imports are at the end to avoid circular imports with sub-services.
# F401 is intentionally suppressed here because this module is a legacy facade.

from .sop_service import (  # noqa: E402,F401
    _upsert_sop_progress_entry,
    _validate_sop_pool_key,
    delete_sop_v1_template_day,
    ensure_sop_v1_defaults,
    get_sop_v1_batches_payload,
    get_sop_v1_config_payload,
    get_sop_v1_management_payload,
    get_sop_v1_templates_payload,
    record_sop_pool_entry,
    run_due_sop,
    save_sop_v1_pool_config,
    save_sop_v1_template,
)
from .reply_monitor_service import (  # noqa: E402,F401
    _dispatch_reply_monitor_queue_item,
    _reply_monitor_status_payload,
    _serialize_reply_monitor_queue_item,
    run_due_reply_monitor,
    run_reply_monitor_capture,
    run_router_test_dispatch,
    save_reply_monitor_enabled,
)
from .focus_send_service import (  # noqa: E402,F401
    _focus_batch_detail_payload,
    _focus_batch_item_status_label,
    _focus_batch_status_label,
    _serialize_focus_send_batch,
    _serialize_focus_send_batch_item,
    _update_focus_batch_counters,
    create_focus_send_batch,
    get_focus_send_batch_detail,
    get_focus_send_batches_payload,
    run_due_focus_send_batches,
)
from .channel_service import (  # noqa: E402,F401
    _channel_status_is_generated,
    _default_channel_field_statuses,
    _effective_channel_entry_tag_payload,
    _resolve_channel_entry_tag_payload,
    generate_default_channel_qr,
    get_default_channel_settings_payload,
    save_default_channel_settings,
)
from .model_infra_service import (  # noqa: E402,F401
    _deepseek_settings_payload,
    _serialize_agent_llm_call_log,
    _serialize_agent_prompt_row,
    ensure_agent_prompt_defaults,
    get_model_infra_payload,
    save_model_infra_prompt,
    save_model_infra_settings,
    test_model_infra_connection,
)
from .message_activity_service import (  # noqa: E402,F401
    _message_activity_item_status_label,
    _message_activity_pool,
    _message_activity_sync_run_status_label,
    _message_activity_sync_status_payload,
    _serialize_message_activity_sync_item,
    _serialize_message_activity_sync_run,
    run_message_activity_sync,
)
from .due_jobs_service import (  # noqa: E402,F401
    list_registered_due_jobs,
    run_registered_due_jobs,
)
from .manual_send_service import (  # noqa: E402,F401
    _finalize_stage_manual_touch_deliveries,
    _manual_send_allowed_route_keys,
    _manual_send_stage_definition,
    _normalize_manual_send_image_media_ids,
    _stage_manual_send_targets,
    preview_stage_manual_send,
    send_stage_manual_message,
)
