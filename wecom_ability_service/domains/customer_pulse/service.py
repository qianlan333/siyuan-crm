from __future__ import annotations

import hashlib
from importlib import import_module
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from flask import current_app, g, has_app_context, has_request_context

from ...infra.settings import get_setting
from ..marketing_automation import set_manual_followup_segment
from ..tags.service import mark_customer_tags, unmark_customer_tags
from ..tasks.service import get_outbound_task, save_local_private_message_draft, update_outbound_task_status
from .access import (
    CUSTOMER_PULSE_LEGACY_INTERNAL_MODE,
    CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
    CustomerPulseTenantContext,
    CustomerPulseAccessDenied,
    assert_customer_pulse_action_permission,
    assert_customer_pulse_evidence_view,
    assert_customer_pulse_feedback_permission,
    customer_pulse_action_permission,
    customer_pulse_context_tenant_key,
    customer_pulse_external_request_scoped_enforced,
    current_customer_pulse_request_access_context,
    customer_pulse_permission_summary,
    customer_pulse_tenant_context_summary,
    customer_pulse_default_tenant_key,
    customer_pulse_scoped_key,
    customer_pulse_tenant_mode,
)
from .ai_recommendation import (
    customer_pulse_mask_pii,
    customer_pulse_text_guardrail_hits,
    generate_customer_pulse_ai_recommendation,
)
from . import repo

__all__ = [
    "assert_customer_pulse_action_permission",
    "assert_customer_pulse_evidence_view",
    "assert_customer_pulse_feedback_permission",
    "customer_pulse_action_permission",
    "generate_customer_pulse_ai_recommendation",
    "get_outbound_task",
    "mark_customer_tags",
    "save_local_private_message_draft",
    "set_manual_followup_segment",
    "unmark_customer_tags",
    "update_outbound_task_status",
]

CUSTOMER_PULSE_FLAG_KEY = "ai_customer_pulse"
CUSTOMER_PULSE_RULES_VERSION = "customer_pulse_rules_v1"
CUSTOMER_PULSE_RECOMPUTE_JOB_TYPE = "customer_pulse_recompute"
CUSTOMER_PULSE_TENANT_KEY = customer_pulse_default_tenant_key()
CUSTOMER_PULSE_UNDO_WINDOW_MINUTES = 10
CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD_KEY = "CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD"
CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_KEY = "CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS"
CUSTOMER_PULSE_ALLOWED_ACTION_TYPES_KEY = "CUSTOMER_PULSE_ALLOWED_ACTION_TYPES"
CUSTOMER_PULSE_FLAG_POLICY_KEY = "CUSTOMER_PULSE_FLAG_POLICY_JSON"
CUSTOMER_PULSE_DEFAULT_HIGH_PRIORITY_THRESHOLD = 70
CUSTOMER_PULSE_DEFAULT_SHOW_LOW_CONFIDENCE = False
CUSTOMER_PULSE_RESOURCE_CARD = "customer_pulse_card"
CUSTOMER_PULSE_RESOURCE_EVIDENCE = "customer_pulse_evidence"
CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS = 7
_FEATURE_POLICY_RESERVED_KEYS = {"default_enabled", "roles", "userids", "legacy_internal", "tenants"}
_CROSS_TENANT_ERROR_CODES = {"cross_tenant_owner_scope"}
_UNAUTHORIZED_ERROR_CODES = {
    "action_permission_denied",
    "action_permission_unmapped",
    "actor_owner_scope_forbidden",
    "card_view_forbidden",
    "customer_pulse_detail_forbidden",
    "evidence_view_forbidden",
    "feedback_permission_forbidden",
    "inbox_view_forbidden",
    "internal_role_forbidden",
    "operator_role_forbidden",
    "owner_scope_forbidden",
    "page_permission_forbidden",
    "viewer_role_forbidden",
    "widget_view_forbidden",
}
_EXECUTION_AUDIT_AI_SUGGESTED = "ai_suggested"
_EXECUTION_AUDIT_HUMAN_CONFIRMED = "human_confirmed"
_EXECUTION_AUDIT_HUMAN_EDITED = "human_edited"
_EXECUTION_META_FIELDS = {
    "admin_action_token",
    "action_type",
    "operator",
    "metric_source",
    "track_click",
    "feedback_source",
    "note",
}
_EXECUTION_ALLOWED_FIELDS = {
    "generate_reply_draft": {"draft_message"},
    "create_followup_task": {"task_title", "due_at"},
    "update_followup_segment": {"followup_segment"},
    "update_tags": {"add_tag_ids", "remove_tag_ids", "add_tag", "remove_tag"},
    "set_followup_reminder": {"due_at"},
}
_EXECUTION_FORBIDDEN_FIELDS = {
    "tenant_key",
    "tenant_id",
    "card_id",
    "execution_id",
    "price",
    "discount",
    "refund",
    "refund_policy",
    "promise",
    "system_prompt",
    "prompt",
}
_HIGH_INTENT_SEGMENTS = {"core", "top", "focus"}
_HIGH_INTENT_STAGE_KEYS = {
    "pool/active_focus",
    "pool/inactive_focus",
}
_HIGH_INTENT_TAG_KEYWORDS = ("高意向", "待跟进", "已报价", "课程安排", "想报名")
_HIGH_INTENT_MESSAGE_KEYWORDS = (
    "报价",
    "价格",
    "费用",
    "方案",
    "试听",
    "试课",
    "课程",
    "开课",
    "安排",
    "名额",
    "报名",
    "合同",
    "付款",
    "预约",
    "体验",
)
_QUESTION_HINT_KEYWORDS = (
    "?",
    "？",
    "吗",
    "呢",
    "么",
    "什么时候",
    "多久",
    "怎么",
    "如何",
    "可以",
    "报价",
    "价格",
    "费用",
    "安排",
    "链接",
)
_NEGATIVE_MESSAGE_KEYWORDS = (
    "投诉",
    "不满意",
    "退款",
    "退费",
    "退课",
    "太贵",
    "贵了",
    "没人回复",
    "没人联系",
    "生气",
    "失望",
    "问题",
    "故障",
    "异常",
    "取消",
    "算了",
    "不考虑",
    "差评",
    "不好用",
    "被打扰",
)
_FOLLOWUP_DUE_FIELDS = (
    "next_followup_at",
    "next_followup_time",
    "next_touch_at",
    "followup_due_at",
    "remind_at",
)
_SAFE_DISPATCH_STATUSES = {"", "pending", "blocked_quiet_hours", "dispatched", "acked", "cancelled", "converted_before_dispatch"}
_TERMINAL_CARD_STATUSES = {"completed", "dismissed"}
_ACTIVE_CARD_STATUSES = {"open", "draft_ready", "snoozed"}
_CRITICAL_RISK_FLAGS = {"unanswered_question", "negative_sentiment", "service_exception"}
_SUPPORTED_ACTION_TYPES = {
    "generate_reply_draft",
    "create_followup_task",
    "update_followup_segment",
    "update_tags",
    "set_followup_reminder",
}
_ACTION_FEEDBACK_TYPES = {"adopted", "edited_then_sent", "ignored", "misjudged", "unhelpful"}


def _load_customer_pulse_internal_delegate(module_name: str, attr_name: str) -> Any:
    module = import_module(f".{module_name}", __package__)
    return getattr(module, attr_name)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any) -> bool:
    return _normalized_text(value).lower() in {"1", "true", "yes", "on"}


def _config_value(key: str, default: Any = "") -> Any:
    cache: dict[str, Any] | None = None
    if has_app_context():
        existing_cache = g.get("customer_pulse_config_cache")
        if isinstance(existing_cache, dict):
            cache = existing_cache
        else:
            cache = {}
            g.customer_pulse_config_cache = cache
        if key in cache:
            return cache[key]
    stored = get_setting(key)
    if stored not in (None, ""):
        resolved = stored
    else:
        resolved = current_app.config.get(key, default)
    if cache is not None:
        cache[key] = resolved
    return resolved


def _config_bool(key: str, *, default: bool) -> bool:
    raw_value = _config_value(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_bool(raw_value) if raw_value not in (None, "") else default


def _config_int(key: str, *, default: int, minimum: int, maximum: int) -> int:
    raw_value = _config_value(key, default)
    try:
        resolved = int(raw_value)
    except (TypeError, ValueError):
        resolved = default
    return max(minimum, min(resolved, maximum))


def _high_priority_threshold() -> int:
    return _config_int(
        CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD_KEY,
        default=CUSTOMER_PULSE_DEFAULT_HIGH_PRIORITY_THRESHOLD,
        minimum=1,
        maximum=100,
    )


def _show_low_confidence_suggestions() -> bool:
    return _config_bool(
        CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_KEY,
        default=CUSTOMER_PULSE_DEFAULT_SHOW_LOW_CONFIDENCE,
    )


def _allowed_action_types() -> set[str]:
    raw_value = _config_value(CUSTOMER_PULSE_ALLOWED_ACTION_TYPES_KEY, "")
    if isinstance(raw_value, (list, tuple, set)):
        normalized = {_normalized_text(item) for item in raw_value if _normalized_text(item)}
    else:
        normalized = {
            _normalized_text(item)
            for item in str(raw_value or "").replace("|", ",").split(",")
            if _normalized_text(item)
        }
    filtered = {item for item in normalized if item in _SUPPORTED_ACTION_TYPES}
    return filtered or set(_SUPPORTED_ACTION_TYPES)


def _action_allowed(action_type: str) -> bool:
    return _normalized_text(action_type) in _allowed_action_types()


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


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for pattern in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_followup_time() -> str:
    return (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _soon_followup_time(*, hours: int = 2) -> str:
    return (datetime.now() + timedelta(hours=max(1, int(hours or 0)))).strftime("%Y-%m-%d %H:%M:%S")


def _setting_enabled() -> bool:
    raw_value = _config_value(
        CUSTOMER_PULSE_FLAG_KEY,
        current_app.config.get(CUSTOMER_PULSE_FLAG_KEY, False) if has_app_context() else False,
    )
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value in (None, ""):
        return False
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _feature_policy_map() -> dict[str, Any]:
    payload = _json_loads(_config_value(CUSTOMER_PULSE_FLAG_POLICY_KEY, "{}"), default={})
    if not isinstance(payload, dict):
        return {
            "default_enabled": True,
            "roles": {},
            "userids": {},
            "legacy_internal": {},
            "tenants": {},
        }
    tenants = payload.get("tenants") if isinstance(payload.get("tenants"), dict) else {}
    if not tenants:
        tenants = {
            _normalized_text(key): value
            for key, value in payload.items()
            if _normalized_text(key) and key not in _FEATURE_POLICY_RESERVED_KEYS and isinstance(value, dict)
        }
    return {
        "default_enabled": _normalized_bool(payload.get("default_enabled", True)),
        "roles": payload.get("roles") if isinstance(payload.get("roles"), dict) else {},
        "userids": payload.get("userids") if isinstance(payload.get("userids"), dict) else {},
        "legacy_internal": payload.get("legacy_internal") if isinstance(payload.get("legacy_internal"), dict) else {},
        "tenants": tenants,
    }


def _feature_override_map(section: Any, *keys: str) -> dict[str, bool]:
    if not isinstance(section, dict):
        return {}
    for key in keys:
        value = section.get(key)
        if not isinstance(value, dict):
            continue
        return {
            _normalized_text(actor_key).lower(): _normalized_bool(actor_enabled)
            for actor_key, actor_enabled in value.items()
            if _normalized_text(actor_key)
        }
    return {}


def _feature_gate_context(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if access_context is not None:
        return dict(access_context)
    if has_request_context():
        return dict(current_customer_pulse_request_access_context())
    return {}


def customer_pulse_feature_gate(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    global_enabled = _setting_enabled()
    tenant_key = _normalized_text(context.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY
    actor_role = _normalized_text(context.get("actor_role") or context.get("role")).lower()
    actor_userid = _normalized_text(context.get("actor_userid") or context.get("user_id")).lower()
    feature_policy = _feature_policy_map()
    tenant_map = feature_policy.get("tenants") if isinstance(feature_policy.get("tenants"), dict) else {}
    global_role_overrides = _feature_override_map(feature_policy, "roles")
    global_user_overrides = _feature_override_map(feature_policy, "userids")
    legacy_mode = bool(context.get("legacy_mode"))
    section_key = CUSTOMER_PULSE_LEGACY_INTERNAL_MODE if legacy_mode else tenant_key
    section = (
        feature_policy.get("legacy_internal")
        if legacy_mode
        else (tenant_map.get(section_key) if isinstance(tenant_map, dict) else {})
    )
    if not isinstance(section, dict):
        section = {}
    section_enabled = (
        _normalized_bool(section.get("enabled"))
        if "enabled" in section
        else _normalized_bool(feature_policy.get("default_enabled", True))
    )
    tenant_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:{section_key}" if "enabled" in section else "global_default"
    actor_enabled = True
    actor_override_source = ""
    section_user_overrides = _feature_override_map(section, "userids", "users")
    section_role_overrides = _feature_override_map(section, "roles")
    if actor_userid and actor_userid in section_user_overrides:
        actor_enabled = bool(section_user_overrides[actor_userid])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:{section_key}:userids"
    elif actor_role and actor_role in section_role_overrides:
        actor_enabled = bool(section_role_overrides[actor_role])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:{section_key}:roles"
    elif actor_userid and actor_userid in global_user_overrides:
        actor_enabled = bool(global_user_overrides[actor_userid])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:userids"
    elif actor_role and actor_role in global_role_overrides:
        actor_enabled = bool(global_role_overrides[actor_role])
        actor_override_source = f"{CUSTOMER_PULSE_FLAG_POLICY_KEY}:roles"
    enabled = bool(global_enabled and section_enabled and actor_enabled)
    reason = "enabled"
    if not global_enabled:
        reason = "global_disabled"
    elif not section_enabled:
        reason = "tenant_disabled" if not legacy_mode else "legacy_internal_disabled"
    elif not actor_enabled:
        reason = "actor_disabled"
    return {
        "enabled": enabled,
        "reason": reason,
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "policy_key": CUSTOMER_PULSE_FLAG_POLICY_KEY,
        "global_enabled": bool(global_enabled),
        "tenant_enabled": bool(section_enabled),
        "actor_enabled": bool(actor_enabled),
        "tenant_key": tenant_key,
        "actor_userid": actor_userid,
        "actor_role": actor_role,
        "mode": _normalized_text(context.get("mode")) or customer_pulse_tenant_mode(),
        "auth_mode": _normalized_text(context.get("auth_mode")) or customer_pulse_tenant_mode(),
        "legacy_mode": legacy_mode,
        "tenant_scope": section_key,
        "tenant_override_source": tenant_override_source,
        "actor_override_source": actor_override_source,
    }


def is_customer_pulse_inbox_enabled(*, access_context: Mapping[str, Any] | None = None) -> bool:
    return bool(customer_pulse_feature_gate(access_context).get("enabled"))


def customer_pulse_feature_gate_summary(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    gate = customer_pulse_feature_gate(access_context)
    return {
        "enabled": bool(gate.get("enabled")),
        "reason": _normalized_text(gate.get("reason")) or "enabled",
        "feature_flag": CUSTOMER_PULSE_FLAG_KEY,
        "policy_key": CUSTOMER_PULSE_FLAG_POLICY_KEY,
        "global_enabled": bool(gate.get("global_enabled")),
        "tenant_enabled": bool(gate.get("tenant_enabled")),
        "actor_enabled": bool(gate.get("actor_enabled")),
        "tenant_key": _normalized_text(gate.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "actor_userid": _normalized_text(gate.get("actor_userid")),
        "actor_role": _normalized_text(gate.get("actor_role")),
        "mode": _normalized_text(gate.get("mode")),
        "auth_mode": _normalized_text(gate.get("auth_mode")),
        "legacy_mode": bool(gate.get("legacy_mode")),
        "tenant_scope": _normalized_text(gate.get("tenant_scope")),
        "tenant_override_source": _normalized_text(gate.get("tenant_override_source")),
        "actor_override_source": _normalized_text(gate.get("actor_override_source")),
    }


def customer_pulse_rollout_whitelist_summary() -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_feedback_metrics_service",
        "customer_pulse_rollout_whitelist_summary",
    )
    return delegate()


def build_customer_pulse_tenant_rollout_report(
    *,
    days: int = CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS,
    tenant_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_feedback_metrics_service",
        "build_customer_pulse_tenant_rollout_report",
    )
    return delegate(days=days, tenant_keys=tenant_keys)


def _customer_pulse_review_data_source_summary() -> dict[str, Any]:
    database_url = _normalized_text(current_app.config.get("DATABASE_URL"))
    database_path = _normalized_text(current_app.config.get("DATABASE_PATH"))
    project_root = Path(current_app.root_path).parent.resolve()
    if database_url:
        return {
            "backend": "postgres",
            "source_type": "configured_database_url",
            "production_evidence_verified": True,
            "summary": "当前通过 DATABASE_URL 连接数据库，默认视为外部部署数据库来源。",
        }
    resolved_path = Path(database_path).expanduser().resolve() if database_path else Path("")
    source_type = "workspace_local_sqlite"
    production_evidence_verified = False
    if database_path and not str(resolved_path).startswith(str(project_root)):
        source_type = "external_sqlite"
    return {
        "backend": "sqlite",
        "source_type": source_type,
        "database_path": str(resolved_path) if database_path else "",
        "production_evidence_verified": production_evidence_verified,
        "summary": "当前使用本地 SQLite 数据源，不能自动视为已验证的 7 天真实生产数据。",
    }


def _trend_direction(series: list[int]) -> str:
    if len(series) < 2:
        return "flat"
    first = float(series[0] or 0)
    last = float(series[-1] or 0)
    if last - first >= 1:
        return "up"
    if first - last >= 1:
        return "down"
    return "flat"


def _tenant_review_status(
    *,
    ai_error_rate: float,
    fallback_rate: float,
    draft_confirm_rate: float,
    writeback_success_rate: float,
    unauthorized_denied: int,
    cross_tenant_denied: int,
    production_evidence_verified: bool,
    observed_days: int,
) -> dict[str, Any]:
    meets_expansion = (
        production_evidence_verified
        and observed_days >= 7
        and ai_error_rate <= 0.10
        and fallback_rate <= 0.20
        and draft_confirm_rate >= 0.20
        and writeback_success_rate >= 0.95
        and unauthorized_denied <= 0
        and cross_tenant_denied <= 0
    )
    rollback_risk = cross_tenant_denied > 0 and production_evidence_verified
    if rollback_risk:
        return {"label": "风险，建议暂停或回滚", "decision": "rollback"}
    if meets_expansion:
        return {"label": "健康，可扩容参考", "decision": "expand"}
    return {"label": "观察中，继续当前灰度", "decision": "hold"}


def build_customer_pulse_first_wave_review_report(
    *,
    days: int = 7,
    tenant_keys: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_feedback_metrics_service",
        "build_customer_pulse_first_wave_review_report",
    )
    return delegate(days=days, tenant_keys=tenant_keys)


def _priority_label(priority: str) -> str:
    return {
        "high": "高优先级",
        "normal": "常规",
        "low": "低优先级",
    }.get(_normalized_text(priority), "常规")


def _card_status_label(status: str) -> str:
    return {
        "open": "待处理",
        "draft_ready": "草稿已生成",
        "snoozed": "已设置提醒",
        "completed": "已完成",
        "dismissed": "已忽略",
    }.get(_normalized_text(status), "待处理")


def _action_label(action_type: str) -> str:
    return {
        "generate_reply_draft": "生成回复草稿",
        "create_followup_task": "创建跟进任务",
        "update_followup_segment": "更新跟进阶段",
        "update_tags": "更新客户标签",
        "set_followup_reminder": "设置下次提醒",
    }.get(_normalized_text(action_type), "人工确认")


def _stage_label(main_stage: str, sub_stage: str) -> str:
    key = "/".join(part for part in [_normalized_text(main_stage), _normalized_text(sub_stage)] if part)
    mapping = {
        "pool/new_user": "新用户池",
        "pool/inactive_normal": "未激活普通池",
        "pool/inactive_focus": "未激活重点跟进池",
        "pool/active_normal": "激活普通池",
        "pool/active_focus": "激活重点跟进池",
        "pool/silent": "沉默池",
        "converted/enrolled": "已确认成交",
    }
    return mapping.get(key, key or "未分类")


def _segment_label(segment: str) -> str:
    return {
        "unknown": "未知",
        "normal": "普通",
        "core": "Core",
        "top": "Top",
        "focus": "重点跟进",
    }.get(_normalized_text(segment).lower(), _normalized_text(segment) or "未知")


def _safe_preview(value: Any, *, max_length: int = 80) -> str:
    text = _normalized_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _dedupe_evidence(items: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            _normalized_text(item.get("title")),
            _normalized_text(item.get("detail")),
            _normalized_text(item.get("event_time")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "title": _normalized_text(item.get("title")) or "证据",
                "detail": _normalized_text(item.get("detail")) or "暂无详情",
                "event_time": _normalized_text(item.get("event_time")),
                "source": _normalized_text(item.get("source")),
            }
        )
        if len(result) >= limit:
            break
    return result


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _explicit_tenant_context_from_key(tenant_key: str) -> CustomerPulseTenantContext:
    normalized_tenant_key = _normalized_text(tenant_key)
    return {
        "mode": CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
        "auth_mode": CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
        "valid": True,
        "legacy_mode": False,
        "tenant_key": normalized_tenant_key,
        "user_id": "",
        "role": "",
        "source": "explicit_tenant_key",
        "tenant_source": "explicit_tenant_key",
        "user_source": "",
        "role_source": "",
        "actor_userid": "",
        "actor_role": "",
        "operator": "crm_console",
        "policy": {},
        "allowed_owner_userids": [],
        "member_userids": [],
        "viewer_roles": [],
        "operator_roles": [],
        "internal_roles": [],
        "can_view_all": True,
        "error_code": "",
        "error_message": "",
        "http_status": 200,
    }


def _resolved_tenant_context(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> CustomerPulseTenantContext:
    context = dict(tenant_context or {})
    normalized_tenant_key = _normalized_text(tenant_key)
    if not context:
        if normalized_tenant_key:
            context = _explicit_tenant_context_from_key(normalized_tenant_key)
    elif normalized_tenant_key:
        context_tenant_key = customer_pulse_context_tenant_key(context, require_valid=not bool(context.get("legacy_mode")))
        if context_tenant_key and normalized_tenant_key != context_tenant_key:
            raise CustomerPulseAccessDenied(
                "显式 tenant_key 与 tenant_context 中的 tenant_key 不一致，拒绝继续访问 Customer Pulse。",
                code="tenant_context_conflict",
                http_status=400,
            )
    if not context:
        raise CustomerPulseAccessDenied(
            "当前调用必须显式传入 tenant_context 或 tenant_key，拒绝继续访问 Customer Pulse。",
            code="tenant_context_required",
            http_status=403,
        )
    context_tenant_key = customer_pulse_context_tenant_key(context, require_valid=not bool(context.get("legacy_mode")))
    return CustomerPulseTenantContext(context)


def _resolved_tenant_key(*, tenant_context: dict[str, Any] | None = None, tenant_key: str = "") -> str:
    context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    if bool(context.get("legacy_mode")) and customer_pulse_tenant_mode() == CUSTOMER_PULSE_LEGACY_INTERNAL_MODE:
        return CUSTOMER_PULSE_TENANT_KEY
    resolved_tenant_key = customer_pulse_context_tenant_key(context, require_valid=not bool(context.get("legacy_mode")))
    if resolved_tenant_key:
        return resolved_tenant_key
    raise CustomerPulseAccessDenied(
        "当前环境要求显式 tenant_key，拒绝继续访问 Customer Pulse。",
        code=_normalized_text(context.get("error_code")) or "tenant_context_required",
        http_status=403,
    )


def _resolved_tenant_context_summary(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    return customer_pulse_tenant_context_summary(
        _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    )


def _execution_key() -> str:
    return f"pulse-exec-{uuid.uuid4().hex}"


def _undo_until() -> str:
    return (datetime.now() + timedelta(minutes=CUSTOMER_PULSE_UNDO_WINDOW_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")


def _card_state_snapshot(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_status": _normalized_text(card.get("card_status")),
        "draft_message": _normalized_text(card.get("draft_message")),
        "need_human_confirmation": bool(card.get("need_human_confirmation")),
        "due_at": _normalized_text(card.get("due_at")),
        "snooze_until": _normalized_text(card.get("snooze_until")),
        "resolved_at": _normalized_text(card.get("resolved_at")),
        "resolution_note": _normalized_text(card.get("resolution_note")),
    }


def _card_state_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_status": _normalized_text(snapshot.get("card_status")),
        "need_human_confirmation": bool(snapshot.get("need_human_confirmation")),
        "due_at": _normalized_text(snapshot.get("due_at")),
        "snooze_until": _normalized_text(snapshot.get("snooze_until")),
        "resolved_at": _normalized_text(snapshot.get("resolved_at")),
        "resolution_note": _normalized_text(snapshot.get("resolution_note")),
        "draft_message_preview": customer_pulse_mask_pii(snapshot.get("draft_message"), max_length=60),
    }


def _resource_summary(*, resource_type: str, resource_id: Any) -> dict[str, Any]:
    return {
        "resource_type": _normalized_text(resource_type) or CUSTOMER_PULSE_RESOURCE_CARD,
        "resource_id": _normalized_text(resource_id),
    }


def _actor_summary(
    *,
    tenant_context: dict[str, Any] | None = None,
    operator: str = "",
) -> dict[str, Any]:
    resolved_context = dict(tenant_context or {})
    return {
        "actor_userid": _normalized_text(resolved_context.get("actor_userid") or resolved_context.get("user_id")),
        "actor_role": _normalized_text(resolved_context.get("actor_role") or resolved_context.get("role")),
        "operator": _normalized_text(operator) or _normalized_text(resolved_context.get("operator")),
        "auth_mode": _normalized_text(resolved_context.get("auth_mode") or resolved_context.get("mode")),
        "source": _normalized_text(resolved_context.get("source")),
    }


def _ai_audit_labels_from_candidate(candidate: dict[str, Any], action_payload: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    payload = dict(action_payload or {})
    if isinstance(payload.get("ai_recommendation"), dict) or _normalized_text(candidate.get("source")) == "ai":
        labels.append(_EXECUTION_AUDIT_AI_SUGGESTED)
    return labels


def _execution_audit_labels(
    *,
    base_labels: list[str],
    edited_fields: list[str],
) -> list[str]:
    labels = [item for item in base_labels if _normalized_text(item)]
    labels.append(_EXECUTION_AUDIT_HUMAN_EDITED if edited_fields else _EXECUTION_AUDIT_HUMAN_CONFIRMED)
    return list(dict.fromkeys(labels))


def _guardrail_summary(
    *,
    execution_labels: list[str],
    unsafe_input_fields: list[str],
    text_guardrail_hits: list[str],
    ai_guardrails: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ai_payload = dict(ai_guardrails or {})
    return {
        "audit_labels": list(dict.fromkeys([_normalized_text(item) for item in execution_labels if _normalized_text(item)])),
        "unsafe_input_fields": [_normalized_text(item) for item in unsafe_input_fields if _normalized_text(item)],
        "text_guardrail_hits": [_normalized_text(item) for item in text_guardrail_hits if _normalized_text(item)],
        "ai_guardrails": {
            "blocked": bool(ai_payload.get("blocked")),
            "input_violations": list(ai_payload.get("input_violations") or []),
            "output_violations": list(ai_payload.get("output_violations") or []),
        },
    }


def _request_payload_audit_summary(
    *,
    action_type: str,
    request_payload: dict[str, Any],
    tenant_context: dict[str, Any],
    operator: str,
    card: dict[str, Any],
    execution_labels: list[str],
    unsafe_input_fields: list[str],
    text_guardrail_hits: list[str],
) -> dict[str, Any]:
    ai_payload = dict(((card.get("snapshot") or {}).get("ai_payload") or {})) if isinstance((card.get("snapshot") or {}).get("ai_payload"), dict) else {}
    ai_recommendation_payload = dict((card.get("suggested_action_payload") or {}).get("ai_recommendation") or {})
    safe_field_updates = dict(ai_recommendation_payload.get("safe_field_updates") or {})
    return {
        "actor": _actor_summary(tenant_context=tenant_context, operator=operator),
        "resource": _resource_summary(resource_type=CUSTOMER_PULSE_RESOURCE_CARD, resource_id=card.get("id")),
        "tenant_context": customer_pulse_tenant_context_summary(tenant_context),
        "action_type": _normalized_text(action_type),
        "request_fields": sorted(request_payload.keys()),
        "safe_field_update_keys": sorted(
            key
            for key, value in safe_field_updates.items()
            if value not in (None, "", [], {})
        ),
        "guardrails": _guardrail_summary(
            execution_labels=execution_labels,
            unsafe_input_fields=unsafe_input_fields,
            text_guardrail_hits=text_guardrail_hits,
            ai_guardrails=ai_payload.get("guardrails") if isinstance(ai_payload.get("guardrails"), dict) else {},
        ),
    }


def _result_payload_audit_summary(
    *,
    action_type: str,
    card_before: dict[str, Any],
    card_after: dict[str, Any] | None,
    execution_labels: list[str],
    edited_fields: list[str],
    status: str,
    error_message: str = "",
    rollback_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "action_type": _normalized_text(action_type),
        "status": _normalized_text(status),
        "edited_fields": [_normalized_text(item) for item in edited_fields if _normalized_text(item)],
        "labels": list(dict.fromkeys([_normalized_text(item) for item in execution_labels if _normalized_text(item)])),
        "before": _card_state_summary(card_before),
        "after": _card_state_summary(card_after or {}),
        "error_message": _normalized_text(error_message),
        "rollback": dict(rollback_payload or {}),
    }


def _execution_rollback_payload(
    *,
    action_type: str,
    pre_card_snapshot: dict[str, Any],
    undo_until: str = "",
    status: str = "pending",
    activity_log_id: int = 0,
) -> dict[str, Any]:
    return {
        "resource_type": CUSTOMER_PULSE_RESOURCE_CARD,
        "resource_id": "",
        "action_type": _normalized_text(action_type),
        "undo_supported": _action_requires_undo_window(action_type),
        "undo_until": _normalized_text(undo_until),
        "status": _normalized_text(status),
        "activity_log_id": int(activity_log_id or 0),
        "card_before": _card_state_summary(pre_card_snapshot),
    }


def _unsafe_execution_input_fields(action_type: str, action_payload: dict[str, Any]) -> list[str]:
    normalized_action_type = _normalized_text(action_type)
    allowed_fields = set(_EXECUTION_ALLOWED_FIELDS.get(normalized_action_type, set()))
    unexpected_fields = {
        _normalized_text(key)
        for key in dict(action_payload or {}).keys()
        if _normalized_text(key) and _normalized_text(key) not in allowed_fields and _normalized_text(key) not in _EXECUTION_META_FIELDS
    }
    forbidden = sorted(
        key
        for key in unexpected_fields
        if key in _EXECUTION_FORBIDDEN_FIELDS or key.endswith("_json") or key.endswith("_payload")
    )
    return forbidden


def _draft_execution_guardrail_hits(action_type: str, action_payload: dict[str, Any]) -> list[str]:
    if _normalized_text(action_type) != "generate_reply_draft":
        return []
    return customer_pulse_text_guardrail_hits(action_payload.get("draft_message"))


def _restore_card_state(
    card_id: int,
    snapshot: dict[str, Any],
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    return repo.update_customer_pulse_card(
        int(card_id),
        tenant_key=_resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key),
        card_status=_normalized_text(snapshot.get("card_status")) or "open",
        draft_message=_normalized_text(snapshot.get("draft_message")),
        need_human_confirmation=bool(snapshot.get("need_human_confirmation")),
        due_at=_normalized_text(snapshot.get("due_at")),
        snooze_until=_normalized_text(snapshot.get("snooze_until")),
        resolved_at=_normalized_text(snapshot.get("resolved_at")),
        resolution_note=_normalized_text(snapshot.get("resolution_note")),
    )


def _action_requires_undo_window(action_type: str) -> bool:
    return _normalized_text(action_type) in {
        "generate_reply_draft",
        "create_followup_task",
        "update_followup_segment",
        "update_tags",
        "set_followup_reminder",
    }


def _present_execution_log(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    request_payload = _json_loads(row.get("request_payload_json"), default={})
    if not isinstance(request_payload, dict):
        request_payload = {}
    result_payload = _json_loads(row.get("result_payload_json"), default={})
    if not isinstance(result_payload, dict):
        result_payload = {}
    tenant_context = _json_loads(row.get("tenant_context_json"), default={})
    if not isinstance(tenant_context, dict):
        tenant_context = {}
    audit_labels = _json_loads(row.get("audit_labels_json"), default=[])
    if not isinstance(audit_labels, list):
        audit_labels = []
    rollback_payload = _json_loads(row.get("rollback_payload_json"), default={})
    if not isinstance(rollback_payload, dict):
        rollback_payload = {}
    request_summary = dict(request_payload.get("audit") or {}) if isinstance(request_payload.get("audit"), dict) else {}
    result_summary = dict(result_payload.get("audit") or {}) if isinstance(result_payload.get("audit"), dict) else {}
    undo_until = _normalized_text(row.get("undo_until"))
    undo_supported = _action_requires_undo_window(row.get("action_type"))
    undo_available = False
    if undo_supported and _normalized_text(row.get("execution_status")) == "confirmed" and not _normalized_text(row.get("undone_at")):
        undo_deadline = _parse_datetime(undo_until)
        undo_available = bool(undo_deadline and undo_deadline >= datetime.now())
    return {
        "id": int(row.get("id") or 0),
        "card_id": int(row.get("card_id") or 0),
        "external_userid": _normalized_text(row.get("external_userid")),
        "action_type": _normalized_text(row.get("action_type")),
        "action_label": _action_label(row.get("action_type")),
        "execution_status": _normalized_text(row.get("execution_status")),
        "channel_type": _normalized_text(row.get("channel_type")),
        "operator": _normalized_text(row.get("operator")),
        "actor_userid": _normalized_text(row.get("actor_userid")),
        "actor_role": _normalized_text(row.get("actor_role")),
        "tenant_key": _normalized_text(row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "tenant_context": tenant_context,
        "resource_type": _normalized_text(row.get("resource_type")) or CUSTOMER_PULSE_RESOURCE_CARD,
        "resource_id": _normalized_text(row.get("resource_id")),
        "execution_key": _normalized_text(row.get("execution_key")),
        "idempotency_key": _normalized_text(row.get("idempotency_key")),
        "activity_log_id": int(row.get("activity_log_id") or 0) if row.get("activity_log_id") not in (None, "") else 0,
        "outbound_task_id": int(row.get("outbound_task_id") or 0) if row.get("outbound_task_id") not in (None, "") else 0,
        "audit_labels": [_normalized_text(item) for item in audit_labels if _normalized_text(item)],
        "undo_status": _normalized_text(row.get("undo_status")),
        "undo_until": undo_until,
        "undone_at": _normalized_text(row.get("undone_at")),
        "undo_supported": undo_supported,
        "undo_available": undo_available,
        "request_payload": request_payload,
        "request_summary": request_summary,
        "result_payload": result_payload,
        "result_summary": result_summary,
        "rollback_payload": rollback_payload,
        "error_message": _normalized_text(row.get("error_message")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _build_action_idempotency_key(card_id: int, action_type: str, payload: dict[str, Any]) -> str:
    normalized_payload = _json_dump(payload)
    digest = hashlib.sha256(f"{int(card_id)}:{_normalized_text(action_type)}:{normalized_payload}".encode("utf-8")).hexdigest()
    return f"pulse-card-{int(card_id)}-{_normalized_text(action_type)}-{digest[:24]}"


def _edited_fields(reference_payload: dict[str, Any], actual_payload: dict[str, Any]) -> list[str]:
    keys = sorted(set(reference_payload.keys()) | set(actual_payload.keys()))
    changed: list[str] = []
    for key in keys:
        if _json_dump(reference_payload.get(key)) != _json_dump(actual_payload.get(key)):
            changed.append(key)
    return changed


def _record_metric_event(
    *,
    event_type: str,
    event_source: str,
    card: dict[str, Any] | None = None,
    execution_log_id: int | None = None,
    action_type: str = "",
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _normalized_text(event_type):
        return {}
    card = dict(card or {})
    resolved_tenant_key = (
        _resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key)
        or _normalized_text(card.get("tenant_key"))
        or CUSTOMER_PULSE_TENANT_KEY
    )
    return repo.insert_customer_pulse_metric_event(
        card_id=int(card.get("id") or 0) or None,
        execution_log_id=execution_log_id,
        external_userid=_normalized_text(card.get("external_userid")),
        owner_userid=_normalized_text(card.get("owner_userid")),
        action_type=_normalized_text(action_type) or _normalized_text(card.get("suggested_action_type")),
        event_type=event_type,
        event_source=event_source,
        tenant_key=resolved_tenant_key,
        operator=_normalized_text(operator),
        payload=payload or {},
    )


def _record_action_feedback(
    *,
    card: dict[str, Any],
    feedback_type: str,
    feedback_source: str,
    operator: str,
    action_type: str = "",
    execution_log_id: int | None = None,
    note: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_feedback_type = _normalized_text(feedback_type)
    if normalized_feedback_type not in _ACTION_FEEDBACK_TYPES:
        return {}
    resolved_tenant_key = (
        _resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key)
        or _normalized_text(card.get("tenant_key"))
        or CUSTOMER_PULSE_TENANT_KEY
    )
    return repo.insert_customer_pulse_action_feedback(
        card_id=int(card.get("id") or 0),
        execution_log_id=execution_log_id,
        external_userid=_normalized_text(card.get("external_userid")),
        owner_userid=_normalized_text(card.get("owner_userid")),
        action_type=_normalized_text(action_type) or _normalized_text(card.get("suggested_action_type")),
        feedback_type=normalized_feedback_type,
        feedback_source=_normalized_text(feedback_source),
        tenant_key=resolved_tenant_key,
        operator=_normalized_text(operator),
        note=_normalized_text(note),
        payload=payload or {},
    )


def _card_hidden_by_low_confidence(card: dict[str, Any]) -> bool:
    if _show_low_confidence_suggestions():
        return False
    snapshot = dict(card.get("snapshot") or {})
    ai_payload = dict(snapshot.get("ai_payload") or {}) if isinstance(snapshot.get("ai_payload"), dict) else {}
    return _normalized_text(ai_payload.get("fallback_reason")) == "low_confidence"


def _apply_action_allowlist(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_types = _allowed_action_types()
    return [
        dict(item)
        for item in candidates
        if isinstance(item, dict) and _normalized_text(item.get("action_type")) in allowed_types
    ]


def _customer_pulse_metrics_summary(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, int]:
    counts = repo.count_customer_pulse_metric_events(
        tenant_key=_resolved_tenant_key(tenant_context=tenant_context, tenant_key=tenant_key),
        owner_userids=owner_userids,
        event_types=(
            "ai_success",
            "fallback_count",
            "card_exposed",
            "card_clicked",
            "draft_preview_started",
            "draft_confirmed",
            "followup_task_created",
            "followup_segment_updated",
            "card_ignored",
            "ai_error",
            "writeback_success",
            "writeback_failed",
        )
    )
    return {
        "ai_success": int(counts.get("ai_success", 0) or 0),
        "fallback_count": int(counts.get("fallback_count", 0) or 0),
        "card_exposed": int(counts.get("card_exposed", 0) or 0),
        "card_clicked": int(counts.get("card_clicked", 0) or 0),
        "draft_preview_started": int(counts.get("draft_preview_started", 0) or 0),
        "draft_confirmed": int(counts.get("draft_confirmed", 0) or 0),
        "followup_task_created": int(counts.get("followup_task_created", 0) or 0),
        "followup_segment_updated": int(counts.get("followup_segment_updated", 0) or 0),
        "card_ignored": int(counts.get("card_ignored", 0) or 0),
        "ai_error": int(counts.get("ai_error", 0) or 0),
        "writeback_success": int(counts.get("writeback_success", 0) or 0),
        "writeback_failed": int(counts.get("writeback_failed", 0) or 0),
    }


def _stats_since(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days or 0)))).strftime("%Y-%m-%d %H:%M:%S")


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _customer_pulse_dependency_status(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = dict(access_context or {})
    tenant_mode = customer_pulse_tenant_mode()
    external_request_scoped_enforced = customer_pulse_external_request_scoped_enforced()
    tenant_policy_text = _normalized_text(_config_value("CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON", ""))
    feature_policy_text = _normalized_text(_config_value(CUSTOMER_PULSE_FLAG_POLICY_KEY, ""))
    permissions = customer_pulse_permission_summary(context)
    return {
        "tenant_mode": {
            "ready": tenant_mode in {CUSTOMER_PULSE_LEGACY_INTERNAL_MODE, CUSTOMER_PULSE_REQUEST_SCOPED_MODE}
            and (not external_request_scoped_enforced or tenant_mode == CUSTOMER_PULSE_REQUEST_SCOPED_MODE),
            "value": tenant_mode,
            "label": "租户模式",
        },
        "external_guard": {
            "ready": not external_request_scoped_enforced or tenant_mode == CUSTOMER_PULSE_REQUEST_SCOPED_MODE,
            "value": (
                "request_scoped_enforced"
                if external_request_scoped_enforced and tenant_mode == CUSTOMER_PULSE_REQUEST_SCOPED_MODE
                else ("legacy_internal_blocked" if external_request_scoped_enforced else "not_enforced")
            ),
            "label": "外部环境 request-scoped 保护",
        },
        "rbac": {
            "ready": bool(context.get("legacy_mode")) or bool(tenant_policy_text),
            "value": "legacy_full_access" if bool(context.get("legacy_mode")) else ("policy_loaded" if tenant_policy_text else "missing_policy"),
            "label": "RBAC / owner scope",
        },
        "audit": {
            "ready": True,
            "value": "admin_operation_logs + customer_pulse_execution_logs",
            "label": "审计",
        },
        "metrics": {
            "ready": True,
            "value": "customer_pulse_metric_events",
            "label": "埋点 / 统计",
        },
        "seed_demo": {
            "ready": True,
            "value": "scripts/seed_customer_pulse_demo.py",
            "label": "Demo / Fixture",
        },
        "alerts": {
            "ready": True,
            "value": "stats_api_available" if permissions.get("inbox_view") else "stats_api_requires_inbox_view",
            "label": "告警入口",
        },
        "flag_policy": {
            "ready": True,
            "value": "configured" if feature_policy_text else "global_only",
            "label": "灰度策略",
        },
    }


def build_customer_pulse_ops_dashboard_payload(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    owner_userids: list[str] | tuple[str, ...] | None = None,
    days: int = CUSTOMER_PULSE_DEFAULT_STATS_WINDOW_DAYS,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_feedback_metrics_service",
        "build_customer_pulse_ops_dashboard_payload",
    )
    return delegate(
        tenant_context=tenant_context,
        tenant_key=tenant_key,
        owner_userids=owner_userids,
        days=days,
    )


def _normalize_action_execution_payload(
    *,
    card: dict[str, Any],
    action_type: str,
    candidate: dict[str, Any],
    action_payload: dict[str, Any],
) -> dict[str, Any]:
    normalized_action_type = _normalized_text(action_type)
    if normalized_action_type == "generate_reply_draft":
        return {
            "draft_message": _normalized_text(action_payload.get("draft_message")) or _normalized_text(card.get("draft_message")),
        }
    if normalized_action_type == "create_followup_task":
        return {
            "task_title": _normalized_text(action_payload.get("task_title")) or _normalized_text(candidate.get("title")) or _normalized_text(card.get("title")),
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    if normalized_action_type == "update_followup_segment":
        return {
            "followup_segment": _normalized_text(action_payload.get("followup_segment")) or "focus",
        }
    if normalized_action_type == "update_tags":
        add_tag_ids = sorted(
            {
                _normalized_text(item)
                for item in (action_payload.get("add_tag_ids") or action_payload.get("add_tag") or [])
                if _normalized_text(item)
            }
        )
        remove_tag_ids = sorted(
            {
                _normalized_text(item)
                for item in (action_payload.get("remove_tag_ids") or action_payload.get("remove_tag") or [])
                if _normalized_text(item)
            }
        )
        return {
            "add_tag_ids": add_tag_ids,
            "remove_tag_ids": remove_tag_ids,
        }
    if normalized_action_type == "set_followup_reminder":
        return {
            "due_at": _normalized_text(action_payload.get("due_at")) or _next_followup_time(),
        }
    raise ValueError("unsupported action_type")


def _assert_action_scope(card: dict[str, Any], action_payload: dict[str, Any]) -> None:
    requested_external_userid = _normalized_text(action_payload.get("external_userid"))
    if requested_external_userid and requested_external_userid != _normalized_text(card.get("external_userid")):
        raise ValueError("外部客户标识与当前行动卡不一致")
    raw_external_userids = action_payload.get("external_userids") or []
    if isinstance(raw_external_userids, list):
        normalized_external_userids = [_normalized_text(item) for item in raw_external_userids if _normalized_text(item)]
        if normalized_external_userids and normalized_external_userids != [_normalized_text(card.get("external_userid"))]:
            raise ValueError("不允许跨客户执行 AI 推进行动")
    requested_owner_userid = _normalized_text(action_payload.get("owner_userid"))
    if requested_owner_userid and requested_owner_userid != _normalized_text(card.get("owner_userid")):
        raise ValueError("owner_userid 与当前客户负责人不一致")


def _signal_priority(points: float) -> str:
    numeric = float(points or 0)
    if numeric >= 24:
        return "high"
    if numeric >= 10:
        return "normal"
    return "low"


def _priority_from_score(priority_score: float, *, risk_keys: set[str]) -> str:
    score = float(priority_score or 0)
    high_priority_threshold = float(_high_priority_threshold())
    if score >= high_priority_threshold:
        return "high"
    if score >= max(high_priority_threshold - 25, 35) and risk_keys.intersection(_CRITICAL_RISK_FLAGS):
        return "high"
    if score >= 35:
        return "normal"
    return "low"


def _message_direction(message_row: dict[str, Any], *, external_userid: str) -> str:
    sender = _normalized_text(message_row.get("sender"))
    return "inbound" if sender == _normalized_text(external_userid) else "outbound"


def _contains_any_keyword(content: str, keywords: tuple[str, ...]) -> bool:
    normalized = _normalized_text(content)
    return bool(normalized) and any(keyword in normalized for keyword in keywords)


def _hours_since(moment_text: str) -> float | None:
    moment = _parse_datetime(moment_text)
    if not moment:
        return None
    return max((datetime.now() - moment).total_seconds() / 3600, 0.0)


def _days_since(moment_text: str) -> int | None:
    moment = _parse_datetime(moment_text)
    if not moment:
        return None
    return max((datetime.now() - moment).days, 0)


def _followup_segment_from_marketing_state(marketing_state: dict[str, Any]) -> str:
    payload = _json_loads(marketing_state.get("state_payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    return _normalized_text(
        payload.get("manual_followup_segment")
        or payload.get("followup_segment")
        or payload.get("current_segment")
    ).lower()


def _known_followup_due_at(marketing_state: dict[str, Any], existing_card: dict[str, Any]) -> str:
    existing_status = _normalized_text(existing_card.get("card_status"))
    existing_resolution_note = _normalized_text(existing_card.get("resolution_note"))
    if existing_status == "snoozed" or existing_resolution_note in {
        "next_followup_reminder_set",
        "local_followup_task_created",
    }:
        due_at = _normalized_text(existing_card.get("snooze_until")) or _normalized_text(existing_card.get("due_at"))
        if due_at:
            return due_at
    payload = _json_loads(marketing_state.get("state_payload_json"), default={})
    if not isinstance(payload, dict):
        return ""
    for field_name in _FOLLOWUP_DUE_FIELDS:
        value = _normalized_text(payload.get(field_name))
        if value:
            return value
    return ""


def _ai_assist_payload(ai_row: dict[str, Any]) -> dict[str, Any]:
    if not ai_row:
        return {
            "available": False,
            "confidence": 0.0,
            "draft_message": "",
            "reason": "",
            "output_type": "",
            "output_id": "",
        }
    confidence = float(ai_row.get("confidence") or 0)
    normalized_output = _json_loads(ai_row.get("normalized_output_json"), default={})
    if not isinstance(normalized_output, dict):
        normalized_output = {}
    return {
        "available": confidence >= 0.75,
        "confidence": confidence,
        "draft_message": _normalized_text(
            normalized_output.get("draft_reply")
            or normalized_output.get("draftText")
            or ai_row.get("rendered_output_text")
            or normalized_output.get("reply")
        ),
        "reason": _normalized_text(
            ai_row.get("reason") or normalized_output.get("summary") or normalized_output.get("whyNow")
        ),
        "output_type": _normalized_text(ai_row.get("output_type")),
        "output_id": _normalized_text(ai_row.get("output_id") or ai_row.get("id")),
        "created_at": _normalized_text(ai_row.get("created_at")),
    }


def _make_signal(
    *,
    tenant_key: str,
    external_userid: str,
    owner_userid: str,
    signal_type: str,
    signal_source: str,
    score: float,
    summary: str,
    source_ref_type: str,
    source_ref_id: str,
    source_updated_at: str,
    payload: dict[str, Any],
    evidence: list[dict[str, Any]],
    flag_bucket: str,
    flag_key: str,
    flag_label: str,
) -> dict[str, Any]:
    return {
        "signal_key": customer_pulse_scoped_key(tenant_key=tenant_key, base_key=f"{external_userid}:{signal_type}"),
        "tenant_key": _resolved_tenant_key(tenant_key=tenant_key),
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "signal_type": signal_type,
        "signal_source": signal_source,
        "priority": _signal_priority(score),
        "score": float(score or 0),
        "summary": _normalized_text(summary),
        "source_ref_type": _normalized_text(source_ref_type),
        "source_ref_id": _normalized_text(source_ref_id),
        "source_updated_at": _normalized_text(source_updated_at),
        "payload": {
            **dict(payload or {}),
            "flag_bucket": _normalized_text(flag_bucket),
            "flag_key": _normalized_text(flag_key),
            "flag_label": _normalized_text(flag_label),
        },
        "evidence": _dedupe_evidence(list(evidence or []), limit=3),
    }


def _build_rule_based_draft_message(*, customer_name: str, summary: str, evidence: list[dict[str, Any]]) -> str:
    evidence_detail = next((_normalized_text(item.get("detail")) for item in evidence if _normalized_text(item.get("detail"))), "")
    greeting_name = _normalized_text(customer_name) or "你"
    lines = [f"{greeting_name}，你好。"]
    if evidence_detail:
        lines.append(f"我先根据你刚才提到的情况整理了一版草稿：{evidence_detail}")
    elif _normalized_text(summary):
        lines.append(f"我先根据你目前的进展整理了一版草稿：{_normalized_text(summary)}")
    else:
        lines.append("我先根据你最近的情况整理了一版草稿，供人工确认后再发送。")
    lines.append("如果你方便，我可以继续按你当前最关心的问题帮你梳理下一步。")
    return "\n".join(lines)


def _load_context(
    external_userid: str,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_signal_service",
        "_load_context",
    )
    return delegate(
        external_userid,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def _build_rule_signals(context: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_signal_service",
        "_build_rule_signals",
    )
    return delegate(context)


def _persist_signals(
    external_userid: str,
    *,
    signals: list[dict[str, Any]],
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> list[dict[str, Any]]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_persist_signals",
    )
    return delegate(
        external_userid,
        signals=signals,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def _build_scoring(signals: list[dict[str, Any]], *, metrics: dict[str, Any]) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_build_scoring",
    )
    return delegate(signals, metrics=metrics)


def _build_action_candidates(context: dict[str, Any], *, scoring: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_build_action_candidates",
    )
    return delegate(context, scoring=scoring, metrics=metrics)


def _merge_ai_recommendation_into_candidates(
    *,
    candidates: list[dict[str, Any]],
    recommendation_result: dict[str, Any],
    default_evidence: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_merge_ai_recommendation_into_candidates",
    )
    return delegate(
        candidates=candidates,
        recommendation_result=recommendation_result,
        default_evidence=default_evidence,
    )


def _suppress_reply_draft_when_ai_is_untrusted(
    *,
    candidates: list[dict[str, Any]],
    recommendation_result: dict[str, Any],
) -> list[dict[str, Any]]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_suppress_reply_draft_when_ai_is_untrusted",
    )
    return delegate(
        candidates=candidates,
        recommendation_result=recommendation_result,
    )


def _card_title(primary_candidate: dict[str, Any]) -> str:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_card_title",
    )
    return delegate(primary_candidate)


def _card_summary(scoring: dict[str, Any], *, primary_candidate: dict[str, Any]) -> str:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_card_summary",
    )
    return delegate(scoring, primary_candidate=primary_candidate)


def _stable_ai_payload(value: Any) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_stable_ai_payload",
    )
    return delegate(value)


def _snapshot_matches(latest_snapshot: dict[str, Any], *, incoming: dict[str, Any]) -> bool:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_snapshot_matches",
    )
    return delegate(latest_snapshot, incoming=incoming)


def _upsert_primary_card(
    *,
    context: dict[str, Any],
    scoring: dict[str, Any],
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_upsert_primary_card",
    )
    return delegate(
        context=context,
        scoring=scoring,
        evidence=evidence,
        candidates=candidates,
        snapshot=snapshot,
    )


def _materialize_customer_pulse(
    external_userid: str,
    *,
    operator: str,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_snapshot_service",
        "_materialize_customer_pulse",
    )
    return delegate(
        external_userid,
        operator=operator,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def refresh_customer_pulse_cards(
    *,
    limit: int = 50,
    operator: str = "system",
    external_userids: list[str] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_action_service",
        "refresh_customer_pulse_cards",
    )
    return delegate(
        limit=limit,
        operator=operator,
        external_userids=external_userids,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
        allowed_owner_userids=allowed_owner_userids,
    )


def enqueue_customer_pulse_recompute(
    *,
    external_userid: str,
    owner_userid: str = "",
    delay_seconds: int = 0,
    operator: str = "",
    trigger_source: str = "",
    trigger_ref_type: str = "",
    trigger_ref_id: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_action_service",
        "enqueue_customer_pulse_recompute",
    )
    return delegate(
        external_userid=external_userid,
        owner_userid=owner_userid,
        delay_seconds=delay_seconds,
        operator=operator,
        trigger_source=trigger_source,
        trigger_ref_type=trigger_ref_type,
        trigger_ref_id=trigger_ref_id,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def run_due_customer_pulse_recompute_jobs(
    *,
    limit: int = 20,
    operator: str = "system",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_action_service",
        "run_due_customer_pulse_recompute_jobs",
    )
    return delegate(
        limit=limit,
        operator=operator,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
        allowed_owner_userids=allowed_owner_userids,
    )


def run_due_customer_pulse_snapshot_job(
    *,
    limit: int = 20,
    rescan_limit: int = 20,
    operator: str = "system",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_action_service",
        "run_due_customer_pulse_snapshot_job",
    )
    return delegate(
        limit=limit,
        rescan_limit=rescan_limit,
        operator=operator,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
        allowed_owner_userids=allowed_owner_userids,
    )


def _customer_pulse_access_permissions(access_context: Mapping[str, Any] | None) -> dict[str, Any]:
    return customer_pulse_permission_summary(access_context)


def _can_view_evidence(access_context: Mapping[str, Any] | None) -> bool:
    return bool(_customer_pulse_access_permissions(access_context).get("evidence_view"))


def _allowed_action_map(access_context: Mapping[str, Any] | None) -> dict[str, bool]:
    action_permissions = _customer_pulse_access_permissions(access_context).get("action_permissions")
    return dict(action_permissions or {}) if isinstance(action_permissions, dict) else {}


def _sanitize_evidence_ref_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceType": _normalized_text(item.get("sourceType")),
        "sourceId": _normalized_text(item.get("sourceId")),
        "title": customer_pulse_mask_pii(item.get("title"), max_length=48),
        "eventTime": _normalized_text(item.get("eventTime")),
    }


def _sanitize_evidence_text(value: Any, *, max_length: int = 120) -> str:
    return customer_pulse_mask_pii(value, max_length=max_length)


def _sanitize_evidence_refs(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = _sanitize_evidence_ref_item(item)
        if not sanitized["sourceType"] or not sanitized["sourceId"]:
            continue
        refs.append(sanitized)
    return refs


def _sanitize_ai_payload(ai_payload: Any, *, access_context: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _json_loads(ai_payload, default={})
    if not isinstance(payload, dict):
        return {}
    recommendation = dict(payload.get("recommendation") or {}) if isinstance(payload.get("recommendation"), dict) else {}
    if recommendation:
        recommendation["evidenceRefs"] = _sanitize_evidence_refs(recommendation.get("evidenceRefs") or [])
        payload["recommendation"] = recommendation
    if not _can_view_evidence(access_context):
        payload["evidence"] = []
    return payload


def _present_snapshot(snapshot_row: dict[str, Any], *, access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    can_view_evidence = _can_view_evidence(access_context)
    signals = _json_loads(snapshot_row.get("signals_json"), default=[])
    if not isinstance(signals, list):
        signals = []
    presented_signals = []
    for item in signals:
        if not isinstance(item, dict):
            continue
        signal_evidence = item.get("evidence") if can_view_evidence else []
        presented_signals.append(
            {
                **dict(item),
                "evidence": signal_evidence if isinstance(signal_evidence, list) else [],
            }
        )
    return {
        "id": int(snapshot_row.get("id") or 0),
        "tenant_key": _normalized_text(snapshot_row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "external_userid": _normalized_text(snapshot_row.get("external_userid")),
        "owner_userid": _normalized_text(snapshot_row.get("owner_userid")),
        "snapshot_status": _normalized_text(snapshot_row.get("snapshot_status")) or "ready",
        "confidence": float(snapshot_row.get("confidence") or 0) if snapshot_row.get("confidence") not in (None, "") else None,
        "priority_score": round(float(snapshot_row.get("priority_score") or 0), 2),
        "summary": _normalized_text(snapshot_row.get("summary")),
        "recommended_action_type": _normalized_text(snapshot_row.get("recommended_action_type")),
        "recommended_action_label": _normalized_text(snapshot_row.get("recommended_action_label"))
        or _action_label(snapshot_row.get("recommended_action_type")),
        "evidence": _json_loads(snapshot_row.get("evidence_json"), default=[]) if can_view_evidence else [],
        "ai_payload": _sanitize_ai_payload(snapshot_row.get("ai_payload_json"), access_context=access_context),
        "signals": presented_signals,
        "risk_flags": _json_loads(snapshot_row.get("risk_flags_json"), default=[]),
        "opportunity_flags": _json_loads(snapshot_row.get("opportunity_flags_json"), default=[]),
        "suggested_action_candidates": _json_loads(snapshot_row.get("suggested_action_candidates_json"), default=[]),
        "score_breakdown": _json_loads(snapshot_row.get("score_breakdown_json"), default=[]),
        "source_updated_at": _normalized_text(snapshot_row.get("source_updated_at")),
        "created_by": _normalized_text(snapshot_row.get("created_by")),
        "created_at": _normalized_text(snapshot_row.get("created_at")),
        "updated_at": _normalized_text(snapshot_row.get("updated_at")),
    }


def _present_signal(row: dict[str, Any], *, access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = _json_loads(row.get("payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "signal_key": _normalized_text(row.get("signal_key")),
        "tenant_key": _normalized_text(row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "signal_type": _normalized_text(row.get("signal_type")),
        "signal_source": _normalized_text(row.get("signal_source")),
        "signal_status": _normalized_text(row.get("signal_status")) or "open",
        "priority": _normalized_text(row.get("priority")) or "normal",
        "score": round(float(row.get("score") or 0), 2),
        "summary": _normalized_text(row.get("summary")),
        "payload": payload,
        "evidence": _json_loads(row.get("evidence_json"), default=[]) if _can_view_evidence(access_context) else [],
        "source_ref_type": _normalized_text(row.get("source_ref_type")),
        "source_ref_id": _normalized_text(row.get("source_ref_id")),
        "source_updated_at": _normalized_text(row.get("source_updated_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _card_evidence_refs(
    *,
    snapshot_payload: dict[str, Any] | None,
    ai_recommendation: dict[str, Any],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    raw_ai_refs = ai_recommendation.get("evidenceRefs") or []
    if isinstance(raw_ai_refs, list):
        for item in raw_ai_refs:
            if not isinstance(item, dict):
                continue
            source_type = _normalized_text(item.get("sourceType"))
            source_id = _normalized_text(item.get("sourceId"))
            if not source_type or not source_id:
                continue
            dedupe_key = (source_type, source_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            refs.append(
                {
                    "sourceType": source_type,
                    "sourceId": source_id,
                    "title": _normalized_text(item.get("title")),
                    "eventTime": _normalized_text(item.get("eventTime")),
                }
            )
    if refs:
        return _sanitize_evidence_refs(refs)

    for signal in (snapshot_payload or {}).get("signals") or []:
        if not isinstance(signal, dict):
            continue
        source_type = _normalized_text(signal.get("source_ref_type") or signal.get("signal_source"))
        source_id = _normalized_text(signal.get("source_ref_id"))
        if not source_type or not source_id:
            continue
        dedupe_key = (source_type, source_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        evidence = signal.get("evidence") or []
        first_evidence = evidence[0] if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict) else {}
        refs.append(
            {
                "sourceType": source_type,
                "sourceId": source_id,
                "title": _normalized_text(first_evidence.get("title")) or _normalized_text(signal.get("summary")),
                "eventTime": _normalized_text(first_evidence.get("event_time")) or _normalized_text(signal.get("source_updated_at")),
            }
        )
    return _sanitize_evidence_refs(refs)


def _present_card(
    row: dict[str, Any],
    *,
    snapshot_row: dict[str, Any] | None = None,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    suggested_action_payload = _json_loads(row.get("suggested_action_payload_json"), default={})
    if not isinstance(suggested_action_payload, dict):
        suggested_action_payload = {}
    snapshot = dict(snapshot_row or {})
    if not snapshot and row.get("snapshot_id"):
        snapshot = repo.get_customer_pulse_snapshot(
            int(row.get("snapshot_id") or 0),
            tenant_key=_normalized_text(row.get("tenant_key")),
        ) or {}
    snapshot_payload = _present_snapshot(snapshot, access_context=access_context) if snapshot else None
    permissions = _customer_pulse_access_permissions(access_context)
    action_permissions = _allowed_action_map(access_context)
    can_view_evidence = bool(permissions.get("evidence_view"))
    stage_label = _stage_label(row.get("marketing_main_stage"), row.get("marketing_sub_stage"))
    stage_key = "/".join(
        part
        for part in [_normalized_text(row.get("marketing_main_stage")), _normalized_text(row.get("marketing_sub_stage"))]
        if part
    )
    segment_label = _segment_label(row.get("value_segment"))
    status = _normalized_text(row.get("card_status")) or "open"
    evidence = _json_loads(row.get("evidence_json"), default=[]) if can_view_evidence else []
    if not isinstance(evidence, list):
        evidence = []
    suggested_action_candidates = _json_loads(row.get("suggested_action_candidates_json"), default=[])
    if not isinstance(suggested_action_candidates, list):
        suggested_action_candidates = []
    suggested_action_candidates = _apply_action_allowlist(suggested_action_candidates)
    permitted_candidates = [
        item
        for item in suggested_action_candidates
        if isinstance(item, dict) and action_permissions.get(_normalized_text(item.get("action_type")), False)
    ]
    suggested_action_type = _normalized_text(row.get("suggested_action_type"))
    if suggested_action_type and (
        not _action_allowed(suggested_action_type) or not action_permissions.get(suggested_action_type, False)
    ):
        suggested_action_type = _normalized_text((permitted_candidates[0] if permitted_candidates else {}).get("action_type"))
        replacement_payload = dict((permitted_candidates[0] if permitted_candidates else {}).get("payload") or {})
        if replacement_payload:
            suggested_action_payload = replacement_payload
    elif suggested_action_type and not permitted_candidates and not action_permissions.get(suggested_action_type, False):
        suggested_action_type = ""
    ai_recommendation = (
        dict(((snapshot_payload or {}).get("ai_payload") or {}).get("recommendation") or {})
        if isinstance((snapshot_payload or {}).get("ai_payload"), dict)
        else {}
    )
    evidence_refs = _card_evidence_refs(snapshot_payload=snapshot_payload, ai_recommendation=ai_recommendation)
    why_now = _normalized_text(ai_recommendation.get("whyNow"))
    if not why_now and permitted_candidates:
        primary_candidate = permitted_candidates[0] if isinstance(permitted_candidates[0], dict) else {}
        why_now = _normalized_text(primary_candidate.get("why_now") or primary_candidate.get("reason"))
    latest_event = next((item for item in evidence if isinstance(item, dict)), {})
    fallback_ref = evidence_refs[0] if evidence_refs else {}
    due_anchor = _normalized_text(row.get("snooze_until")) or _normalized_text(row.get("due_at"))
    due_moment = _parse_datetime(due_anchor)
    is_overdue = bool(due_moment and due_moment <= datetime.now() and status in _ACTIVE_CARD_STATUSES)
    current_judgement = _normalized_text(ai_recommendation.get("summary")) or _normalized_text(row.get("summary"))
    draft_blocked_by_ai = bool(suggested_action_payload.get("draft_blocked_by_ai"))
    supported_action_buttons = [
        {
            "action_type": _normalized_text(item.get("action_type")),
            "action_label": _normalized_text(item.get("action_label")) or _action_label(item.get("action_type")),
            "title": _normalized_text(item.get("title")),
            "candidate_score": round(float(item.get("candidate_score") or 0), 2),
        }
        for item in permitted_candidates
        if isinstance(item, dict) and _normalized_text(item.get("action_type"))
    ]
    feedback_actions = []
    if bool(permissions.get("submit_feedback")) and status == "snoozed":
        feedback_actions.append({"type": "reopen", "label": "重新打开"})
    elif bool(permissions.get("submit_feedback")) and status in _ACTIVE_CARD_STATUSES:
        feedback_actions.extend(
            [
                {"type": "complete", "label": "标记完成"},
                {"type": "snooze", "label": "明天提醒我"},
                {"type": "dismiss", "label": "暂不处理"},
            ]
        )
    if bool(permissions.get("submit_feedback")):
        feedback_actions.extend(
            [
                {"type": "misjudged", "label": "误判"},
                {"type": "unhelpful", "label": "无帮助"},
            ]
        )
    return {
        "id": int(row.get("id") or 0),
        "card_key": _normalized_text(row.get("card_key")),
        "tenant_key": _normalized_text(row.get("tenant_key")) or CUSTOMER_PULSE_TENANT_KEY,
        "external_userid": _normalized_text(row.get("external_userid")),
        "customer_name": _normalized_text(row.get("customer_name")) or _normalized_text(row.get("external_userid")),
        "owner_userid": _normalized_text(row.get("owner_userid")),
        "owner_display_name": _normalized_text(row.get("owner_display_name")) or _normalized_text(row.get("owner_userid")),
        "mobile": _normalized_text(row.get("mobile")),
        "card_status": status,
        "card_status_label": _card_status_label(status),
        "priority": _normalized_text(row.get("priority")) or "normal",
        "priority_label": _priority_label(row.get("priority")),
        "priority_score": round(float(row.get("priority_score") or 0), 2),
        "card_type": _normalized_text(row.get("card_type")) or "followup",
        "title": _normalized_text(row.get("title")) or "客户推进行动卡",
        "summary": _normalized_text(row.get("summary")),
        "current_judgement": current_judgement,
        "why_now": why_now,
        "suggested_action_type": suggested_action_type,
        "suggested_action_label": _action_label(suggested_action_type) if suggested_action_type else "当前无可执行动作",
        "suggested_action_payload": suggested_action_payload if suggested_action_type else {},
        "suggested_action_candidates": permitted_candidates,
        "supported_action_buttons": supported_action_buttons,
        "score_breakdown": _json_loads(row.get("score_breakdown_json"), default=[]),
        "risk_flags": _json_loads(row.get("risk_flags_json"), default=[]),
        "opportunity_flags": _json_loads(row.get("opportunity_flags_json"), default=[]),
        "evidence": evidence,
        "evidence_refs": evidence_refs,
        "evidenceRefs": evidence_refs,
        "latest_event": {
            "title": _normalized_text(latest_event.get("title")) or _normalized_text(fallback_ref.get("title")) or "最近事件",
            "detail": _normalized_text(latest_event.get("detail"))
            or (_normalized_text(fallback_ref.get("title")) if _normalized_text(fallback_ref.get("title")) else "暂无详情"),
            "event_time": _normalized_text(latest_event.get("event_time")) or _normalized_text(fallback_ref.get("eventTime")),
            "source": _normalized_text(latest_event.get("source")) or _normalized_text(fallback_ref.get("sourceType")),
        },
        "draft_message": _normalized_text(row.get("draft_message")),
        "draft_blocked_by_ai": draft_blocked_by_ai,
        "draft_notice": _normalized_text(suggested_action_payload.get("draft_notice")) or "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "draft_editor_available": bool(action_permissions.get("generate_reply_draft"))
        and (
            suggested_action_type == "generate_reply_draft"
            or any(item.get("action_type") == "generate_reply_draft" for item in supported_action_buttons)
        ),
        "need_human_confirmation": bool(row.get("need_human_confirmation")),
        "confidence": float(snapshot.get("confidence") or 0) if snapshot and snapshot.get("confidence") not in (None, "") else None,
        "stage_label": stage_label,
        "stage_key": stage_key,
        "segment_label": segment_label,
        "due_at": _normalized_text(row.get("due_at")),
        "snooze_until": _normalized_text(row.get("snooze_until")),
        "is_overdue": is_overdue,
        "resolved_at": _normalized_text(row.get("resolved_at")),
        "resolution_note": _normalized_text(row.get("resolution_note")),
        "source_updated_at": _normalized_text(row.get("source_updated_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
        "feedback_actions": feedback_actions,
        "review_notice": "所有外发消息默认只生成草稿，需人工确认后再发送。",
        "permissions": permissions,
        "action_disabled_by_config": not bool(suggested_action_type),
        "action_disabled_by_permission": not bool(permissions.get("can_execute_any")),
        "evidence_expand_available": bool(can_view_evidence and evidence_refs),
        "snapshot": snapshot_payload,
    }


def _resolve_card_action_candidate(
    card: dict[str, Any],
    *,
    action_type: str = "",
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    resolved_action_type = _normalized_text(action_type) or _normalized_text(card.get("suggested_action_type"))
    if not resolved_action_type:
        raise ValueError("unsupported action_type")
    primary_candidate = {
        "action_type": _normalized_text(card.get("suggested_action_type")),
        "payload": dict(card.get("suggested_action_payload") or {}),
        "title": _normalized_text(card.get("title")),
        "why_now": _normalized_text(card.get("why_now")),
    }
    if resolved_action_type == primary_candidate["action_type"]:
        return resolved_action_type, dict(primary_candidate.get("payload") or {}), primary_candidate
    for item in card.get("suggested_action_candidates") or []:
        if not isinstance(item, dict):
            continue
        if _normalized_text(item.get("action_type")) != resolved_action_type:
            continue
        return resolved_action_type, dict(item.get("payload") or {}), item
    raise ValueError("unsupported action_type")


def _searchable_card_text(card: dict[str, Any]) -> str:
    parts = [
        card.get("customer_name"),
        card.get("external_userid"),
        card.get("owner_display_name"),
        card.get("owner_userid"),
        card.get("mobile"),
        card.get("title"),
        card.get("summary"),
        card.get("current_judgement"),
        card.get("why_now"),
        card.get("stage_label"),
        card.get("segment_label"),
        (card.get("latest_event") or {}).get("detail"),
        (card.get("latest_event") or {}).get("title"),
    ]
    for item in card.get("risk_flags") or []:
        if isinstance(item, dict):
            parts.extend([item.get("key"), item.get("label")])
    for item in card.get("opportunity_flags") or []:
        if isinstance(item, dict):
            parts.extend([item.get("key"), item.get("label")])
    return " ".join(_normalized_text(part).lower() for part in parts if _normalized_text(part))


def _filter_match(card: dict[str, Any], *, filters: dict[str, Any]) -> bool:
    scope = _normalized_text(filters.get("scope")) or "all"
    stage = _normalized_text(filters.get("stage"))
    risk = _normalized_text(filters.get("risk"))
    search = _normalized_text(filters.get("search")).lower()
    resolved_owner_userid = _normalized_text(filters.get("resolved_owner_userid"))
    if scope == "mine" and resolved_owner_userid and _normalized_text(card.get("owner_userid")) != resolved_owner_userid:
        return False
    if stage and _normalized_text(card.get("stage_key")) != stage:
        return False
    if risk and not any(_normalized_text(item.get("key")) == risk for item in (card.get("risk_flags") or []) if isinstance(item, dict)):
        return False
    if filters.get("overdue_only") and not bool(card.get("is_overdue")):
        return False
    if filters.get("draft_only") and not (bool(_normalized_text(card.get("draft_message"))) or _normalized_text(card.get("card_status")) == "draft_ready"):
        return False
    if filters.get("high_priority_only") and _normalized_text(card.get("priority")) != "high":
        return False
    if search and search not in _searchable_card_text(card):
        return False
    return True


def _build_inbox_filter_options(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    stage_options: list[dict[str, str]] = []
    seen_stage_keys: set[str] = set()
    risk_options: list[dict[str, str]] = []
    seen_risk_keys: set[str] = set()
    for card in cards:
        stage_key = _normalized_text(card.get("stage_key"))
        if stage_key and stage_key not in seen_stage_keys:
            seen_stage_keys.add(stage_key)
            stage_options.append({"value": stage_key, "label": _normalized_text(card.get("stage_label")) or stage_key})
        for item in card.get("risk_flags") or []:
            if not isinstance(item, dict):
                continue
            risk_key = _normalized_text(item.get("key"))
            if not risk_key or risk_key in seen_risk_keys:
                continue
            seen_risk_keys.add(risk_key)
            risk_options.append({"value": risk_key, "label": _normalized_text(item.get("label")) or risk_key})
    return {
        "stages": sorted(stage_options, key=lambda item: item["label"]),
        "risks": sorted(risk_options, key=lambda item: item["label"]),
    }


def build_customer_pulse_inbox_payload(
    *,
    limit: int = 50,
    owner_userid: str = "",
    external_userid: str = "",
    operator: str = "",
    scope: str = "all",
    stage: str = "",
    risk: str = "",
    overdue_only: bool = False,
    draft_only: bool = False,
    high_priority_only: bool = False,
    search: str = "",
    track_metrics: bool = False,
    metric_source: str = "",
    include_ops_dashboard: bool = False,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_read_service",
        "build_customer_pulse_inbox_payload",
    )
    return delegate(
        limit=limit,
        owner_userid=owner_userid,
        external_userid=external_userid,
        operator=operator,
        scope=scope,
        stage=stage,
        risk=risk,
        overdue_only=overdue_only,
        draft_only=draft_only,
        high_priority_only=high_priority_only,
        search=search,
        track_metrics=track_metrics,
        metric_source=metric_source,
        include_ops_dashboard=include_ops_dashboard,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
        allowed_owner_userids=allowed_owner_userids,
    )


def get_customer_pulse_card_payload(
    card_id: int,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_read_service",
        "get_customer_pulse_card_payload",
    )
    return delegate(
        card_id,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def _customer_pulse_evidence_source_allowed(
    *,
    source_type: str,
    source_id: str,
    external_userid: str,
    owner_userid: str,
) -> bool:
    normalized_source_type = _normalized_text(source_type)
    normalized_source_id = _normalized_text(source_id)
    normalized_external_userid = _normalized_text(external_userid)
    normalized_owner_userid = _normalized_text(owner_userid)
    if not normalized_source_type or not normalized_source_id or not normalized_external_userid:
        return False
    if normalized_source_type == "archived_messages":
        row = repo.get_archived_message_ref_row(normalized_source_id, external_userid=normalized_external_userid) or {}
        return bool(row) and (
            not _normalized_text(row.get("owner_userid")) or _normalized_text(row.get("owner_userid")) == normalized_owner_userid
        )
    if normalized_source_type == "automation_reply_monitor_queue":
        row = repo.get_reply_monitor_row_by_id(normalized_source_id, external_userid=normalized_external_userid) or {}
        return bool(row) and (
            not _normalized_text(row.get("owner_userid")) or _normalized_text(row.get("owner_userid")) == normalized_owner_userid
        )
    if normalized_source_type in {"questionnaire_submissions", "questionnaire_scrm_apply_logs"}:
        return bool(repo.get_questionnaire_submission_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    if normalized_source_type == "conversion_dispatch_log":
        return bool(repo.get_conversion_dispatch_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    if normalized_source_type == "customer_marketing_state_current":
        return bool(repo.get_customer_marketing_state_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    if normalized_source_type == "external_contact_bindings":
        return bool(repo.get_external_contact_binding_ref_row(normalized_source_id, external_userid=normalized_external_userid))
    return False


def get_customer_pulse_card_evidence_payload(
    card_id: int,
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_read_service",
        "get_customer_pulse_card_evidence_payload",
    )
    return delegate(
        card_id,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
        limit=limit,
    )


def build_customer_pulse_customer_detail_payload(
    external_userid: str,
    *,
    track_metrics: bool = False,
    metric_source: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_read_service",
        "build_customer_pulse_customer_detail_payload",
    )
    return delegate(
        external_userid,
        track_metrics=track_metrics,
        metric_source=metric_source,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
        allowed_owner_userids=allowed_owner_userids,
    )


def _reply_draft_task_payload(card: dict[str, Any], draft_message: str, execution_key: str) -> dict[str, Any]:
    return {
        "chat_type": "single",
        "external_userid": [_normalized_text(card.get("external_userid"))],
        "sender": [_normalized_text(card.get("owner_userid"))],
        "text": {"content": draft_message},
        "draft_only": True,
        "need_human_confirmation": True,
        "source": CUSTOMER_PULSE_FLAG_KEY,
        "source_card_id": int(card.get("id") or 0),
        "source_execution_key": execution_key,
    }


def _build_execution_response(
    *,
    card_id: int,
    action_type: str,
    result_payload: dict[str, Any],
    execution_log: dict[str, Any] | None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    resolved_context = _resolved_tenant_context(tenant_context=tenant_context, tenant_key=tenant_key)
    resolved_tenant_key = _resolved_tenant_key(tenant_context=resolved_context)
    latest_card = repo.get_customer_pulse_card(int(card_id), tenant_key=resolved_tenant_key)
    return {
        "ok": True,
        "action_type": _normalized_text(action_type),
        "action_label": _action_label(action_type),
        "tenant_context": customer_pulse_tenant_context_summary(resolved_context),
        "card": _present_card(latest_card or {}, access_context=resolved_context),
        "result": result_payload,
        "execution": _present_execution_log(execution_log),
    }


def _existing_execution_response(
    existing_log: dict[str, Any],
    *,
    card_id: int,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    result_payload = _json_loads(existing_log.get("result_payload_json"), default={})
    if not isinstance(result_payload, dict):
        result_payload = {}
    result_payload["deduplicated"] = True
    return _build_execution_response(
        card_id=card_id,
        action_type=_normalized_text(existing_log.get("action_type")),
        result_payload=result_payload,
        execution_log=existing_log,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def preview_customer_pulse_card_action(
    card_id: int,
    *,
    action_type: str = "",
    track_click: bool = False,
    metric_source: str = "",
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_action_service",
        "preview_customer_pulse_card_action",
    )
    return delegate(
        card_id,
        action_type=action_type,
        track_click=track_click,
        metric_source=metric_source,
        operator=operator,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def execute_customer_pulse_card_action(
    card_id: int,
    *,
    action_type: str = "",
    operator: str = "",
    extra_payload: dict[str, Any] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_action_service",
        "execute_customer_pulse_card_action",
    )
    return delegate(
        card_id,
        action_type=action_type,
        operator=operator,
        extra_payload=extra_payload,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def undo_customer_pulse_card_action_execution(
    execution_id: int,
    *,
    operator: str = "",
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_action_service",
        "undo_customer_pulse_card_action_execution",
    )
    return delegate(
        execution_id,
        operator=operator,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def submit_customer_pulse_feedback(
    card_id: int,
    *,
    feedback_type: str,
    note: str = "",
    operator: str = "",
    payload: dict[str, Any] | None = None,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_feedback_metrics_service",
        "submit_customer_pulse_feedback",
    )
    return delegate(
        card_id,
        feedback_type=feedback_type,
        note=note,
        operator=operator,
        payload=payload,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def build_customer_pulse_dashboard_group(
    *,
    tenant_context: dict[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    delegate = _load_customer_pulse_internal_delegate(
        "customer_pulse_read_service",
        "build_customer_pulse_dashboard_group",
    )
    return delegate(
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )
