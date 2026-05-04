from __future__ import annotations

import hashlib
from importlib import import_module
import json
from datetime import datetime
from typing import Any, Mapping

from flask import current_app, has_app_context, has_request_context

from ...infra.settings import get_setting
from ..customer_pulse import (
    build_customer_pulse_inbox_payload,
    customer_pulse_feature_gate_summary,
    execute_customer_pulse_card_action,
    get_customer_pulse_card_payload,
    preview_customer_pulse_card_action,
    undo_customer_pulse_card_action_execution,
)
from ..customer_pulse import repo as customer_pulse_repo
from ..customer_pulse.access import (
    CustomerPulseAccessDenied,
    current_customer_pulse_request_access_context,
    customer_pulse_template_access_payload,
    customer_pulse_tenant_context_summary,
    resolve_customer_pulse_read_scope,
)
from . import repo

__all__ = [
    "build_customer_pulse_inbox_payload",
    "customer_pulse_repo",
    "customer_pulse_template_access_payload",
    "customer_pulse_tenant_context_summary",
    "execute_customer_pulse_card_action",
    "get_customer_pulse_card_payload",
    "preview_customer_pulse_card_action",
    "repo",
    "undo_customer_pulse_card_action_execution",
]

FOLLOWUP_ORCHESTRATOR_FLAG_KEY = "ai_followup_orchestrator"
FOLLOWUP_ORCHESTRATOR_FLAG_POLICY_KEY = "FOLLOWUP_ORCHESTRATOR_FLAG_POLICY_JSON"
FOLLOWUP_ORCHESTRATOR_POLICY_KEY = "FOLLOWUP_ORCHESTRATOR_POLICY_JSON"
FOLLOWUP_ORCHESTRATOR_SOURCE_TYPE = "customer_pulse_rule_engine"
FOLLOWUP_ORCHESTRATOR_MISSION_STATES = (
    "unassigned",
    "suggested",
    "accepted",
    "approved",
    "executing",
    "completed",
    "skipped",
    "escalated",
)
FOLLOWUP_ORCHESTRATOR_MISSION_ACTIONS = (
    "accept",
    "claim",
    "complete",
    "reject",
    "suggest_assignment",
    "request_manager_approval",
    "prebuild_batch_draft",
    "escalate",
    "mark_blocked",
    "skip",
)
FOLLOWUP_ORCHESTRATOR_DECISION_TYPES = (
    "claim",
    "reassign",
    "escalate",
    "batch",
)
FOLLOWUP_ORCHESTRATOR_DECISION_STATUSES = (
    "suggested",
    "accepted",
    "rejected",
    "approved",
    "executing",
    "completed",
)
FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD = 5
FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD = 3
FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS = 24
FOLLOWUP_ORCHESTRATOR_BATCH_MIN_SIZE = 2
FOLLOWUP_ORCHESTRATOR_REPEAT_UNTREATED_THRESHOLD = 2
FOLLOWUP_ORCHESTRATOR_MAX_MISSION_ITEMS = 200
FOLLOWUP_ORCHESTRATOR_RULES_VERSION = "followup_orchestrator_rules_v1"
FOLLOWUP_ORCHESTRATOR_RULE_WEIGHTS = {
    "base_priority_multiplier": 1.0,
    "overdue_bonus": 22,
    "due_soon_bonus": 8,
    "missing_owner_bonus": 18,
    "owner_overload_bonus": 14,
    "high_risk_bonus": 20,
    "repeat_unhandled_bonus": 10,
    "batchable_bonus": 6,
}
FOLLOWUP_ORCHESTRATOR_REJECTABLE_ACTIONS = {"reject", "skip", "mark_blocked"}
FOLLOWUP_ORCHESTRATOR_ACTIVE_ITEM_STATES = {"unassigned", "suggested", "accepted", "approved", "executing"}
FOLLOWUP_ORCHESTRATOR_STABLE_ITEM_STATES = {"accepted", "approved", "executing", "completed", "skipped", "escalated"}
FOLLOWUP_ORCHESTRATOR_STABLE_MISSION_STATES = {"accepted", "approved", "executing", "completed", "skipped", "escalated"}
FOLLOWUP_ORCHESTRATOR_HIGH_RISK_KEYS = {"unanswered_question", "negative_sentiment", "service_exception"}
FOLLOWUP_ORCHESTRATOR_EXECUTOR_ACTION_TYPES = {
    "generate_reply_draft",
    "create_followup_task",
    "update_followup_segment",
    "update_tags",
    "set_followup_reminder",
}
FOLLOWUP_ORCHESTRATOR_EXECUTION_STATES = (
    "not_started",
    "draft_ready",
    "pending_approval",
    "executed",
    "completed",
    "skipped",
    "escalated",
)
FOLLOWUP_ORCHESTRATOR_DEFAULT_POLICY = {
    "mission_enabled": True,
    "batch_draft_enabled": True,
    "reassign_enabled": True,
    "allow_cross_team_reassign": False,
    "manager_approval_actions": ["reassign", "cross_team_reassign", "batch_draft"],
    "owner_overload_threshold": FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD,
    "owner_high_priority_threshold": FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD,
    "sla_due_soon_hours": FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS,
    "team_map": {},
}
FOLLOWUP_ORCHESTRATOR_DEFAULT_STATS_WINDOW_DAYS = 14
FOLLOWUP_ORCHESTRATOR_SECURITY_UNAUTHORIZED_CODES = {
    "owner_scope_forbidden",
    "operator_role_forbidden",
    "approval_required",
    "feature_disabled",
}
FOLLOWUP_ORCHESTRATOR_SECURITY_CROSS_TENANT_CODES = {"cross_tenant_owner_scope"}
_FOLLOWUP_ORCHESTRATOR_FEATURE_POLICY_RESERVED_KEYS = {"default_enabled", "roles", "userids", "legacy_internal", "tenants"}


def _load_followup_internal_delegate(module_name: str, attr_name: str) -> Any:
    module = import_module(f".{module_name}", __package__)
    return getattr(module, attr_name)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_bool(value: Any) -> bool:
    return _normalized_text(value).lower() in {"1", "true", "yes", "on"}


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


def _config_value(key: str, default: Any = "") -> Any:
    stored = get_setting(key)
    if stored not in (None, ""):
        return stored
    if has_app_context():
        return current_app.config.get(key, default)
    return default


def _config_bool(key: str, *, default: bool) -> bool:
    raw_value = _config_value(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value in (None, ""):
        return default
    return _normalized_bool(raw_value)


def _feature_gate_context(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if access_context is not None:
        return dict(access_context)
    if has_request_context():
        return dict(current_customer_pulse_request_access_context())
    return {}


def _feature_policy_map() -> dict[str, Any]:
    payload = _json_loads(_config_value(FOLLOWUP_ORCHESTRATOR_FLAG_POLICY_KEY, "{}"), default={})
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
            if _normalized_text(key) and key not in _FOLLOWUP_ORCHESTRATOR_FEATURE_POLICY_RESERVED_KEYS and isinstance(value, dict)
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


def _normalized_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(minimum, min(parsed, maximum))


def _normalized_string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted({_normalized_text(item) for item in value if _normalized_text(item)})
    return sorted({_normalized_text(item) for item in _normalized_text(value).replace("|", ",").split(",") if _normalized_text(item)})


def _normalized_team_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        _normalized_text(owner_userid): _normalized_text(team_key)
        for owner_userid, team_key in value.items()
        if _normalized_text(owner_userid) and _normalized_text(team_key)
    }


def _normalized_policy_payload(raw: Any, *, base: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = dict(base or FOLLOWUP_ORCHESTRATOR_DEFAULT_POLICY)
    if not isinstance(raw, dict):
        return source
    source["mission_enabled"] = _normalized_bool(raw.get("mission_enabled", source.get("mission_enabled", True)))
    source["batch_draft_enabled"] = _normalized_bool(raw.get("batch_draft_enabled", source.get("batch_draft_enabled", True)))
    source["reassign_enabled"] = _normalized_bool(raw.get("reassign_enabled", source.get("reassign_enabled", True)))
    source["allow_cross_team_reassign"] = _normalized_bool(
        raw.get("allow_cross_team_reassign", source.get("allow_cross_team_reassign", False))
    )
    source["manager_approval_actions"] = _normalized_string_list(
        raw.get("manager_approval_actions", source.get("manager_approval_actions", []))
    )
    source["owner_overload_threshold"] = _normalized_int(
        raw.get("owner_overload_threshold", source.get("owner_overload_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD)),
        default=int(source.get("owner_overload_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_CARD_THRESHOLD)),
        minimum=1,
        maximum=500,
    )
    source["owner_high_priority_threshold"] = _normalized_int(
        raw.get(
            "owner_high_priority_threshold",
            source.get("owner_high_priority_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD),
        ),
        default=int(source.get("owner_high_priority_threshold", FOLLOWUP_ORCHESTRATOR_OWNER_OVERLOAD_HIGH_PRIORITY_THRESHOLD)),
        minimum=1,
        maximum=200,
    )
    source["sla_due_soon_hours"] = _normalized_int(
        raw.get("sla_due_soon_hours", source.get("sla_due_soon_hours", FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS)),
        default=int(source.get("sla_due_soon_hours", FOLLOWUP_ORCHESTRATOR_DUE_SOON_HOURS)),
        minimum=1,
        maximum=24 * 30,
    )
    source["team_map"] = _normalized_team_map(raw.get("team_map", source.get("team_map", {})))
    return source


def _policy_map() -> dict[str, Any]:
    payload = _json_loads(_config_value(FOLLOWUP_ORCHESTRATOR_POLICY_KEY, "{}"), default={})
    if not isinstance(payload, dict):
        return {"default": dict(FOLLOWUP_ORCHESTRATOR_DEFAULT_POLICY), "legacy_internal": {}, "tenants": {}}
    return {
        "default": _normalized_policy_payload(payload.get("default", payload)),
        "legacy_internal": payload.get("legacy_internal") if isinstance(payload.get("legacy_internal"), dict) else {},
        "tenants": payload.get("tenants") if isinstance(payload.get("tenants"), dict) else {},
    }


def resolve_followup_orchestrator_policy(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    tenant_key = _normalized_text(context.get("tenant_key")) or "aicrm"
    actor_role = _normalized_text(context.get("actor_role") or context.get("role")).lower()
    policy_map = _policy_map()
    default_policy = _normalized_policy_payload(policy_map.get("default"))
    legacy_mode = bool(context.get("legacy_mode"))
    tenant_section = policy_map.get("legacy_internal") if legacy_mode else (policy_map.get("tenants") or {}).get(tenant_key)
    resolved = _normalized_policy_payload(tenant_section, base=default_policy)
    source = "default"
    if isinstance(tenant_section, dict):
        source = "legacy_internal" if legacy_mode else f"tenant:{tenant_key}"
        role_overrides: dict[str, Any] = {}
        roles_value = tenant_section.get("roles")
        if isinstance(roles_value, dict):
            role_overrides = roles_value
        role_override = role_overrides.get(actor_role)
        if isinstance(role_override, dict):
            resolved = _normalized_policy_payload(role_override, base=resolved)
            source = f"{source}:role:{actor_role}"
    return {
        **resolved,
        "tenant_key": tenant_key,
        "actor_role": actor_role,
        "legacy_mode": legacy_mode,
        "policy_key": FOLLOWUP_ORCHESTRATOR_POLICY_KEY,
        "source": source,
    }


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _mission_status_label(status: Any) -> str:
    mapping = {
        "unassigned": "待分配",
        "suggested": "待接受",
        "accepted": "已接受",
        "approved": "已批准",
        "executing": "执行中",
        "completed": "已完成",
        "skipped": "已跳过",
        "escalated": "已升级",
    }
    normalized = _normalized_text(status)
    return mapping.get(normalized, normalized or "待处理")


def _decision_status_label(status: Any) -> str:
    mapping = {
        "suggested": "待确认",
        "accepted": "已接受",
        "rejected": "已拒绝",
        "approved": "已批准",
        "executing": "执行中",
        "completed": "已完成",
    }
    normalized = _normalized_text(status)
    return mapping.get(normalized, normalized or "待确认")


def _execution_state_label(state: Any) -> str:
    mapping = {
        "not_started": "未开始",
        "draft_ready": "已生成草稿",
        "pending_approval": "待审批",
        "executed": "已执行",
        "completed": "已完成",
        "skipped": "已跳过",
        "escalated": "已升级",
    }
    normalized = _normalized_text(state)
    return mapping.get(normalized, normalized or "未开始")


def _sha_token(*parts: str, length: int = 12) -> str:
    payload = "|".join(_normalized_text(part) for part in parts if _normalized_text(part))
    if not payload:
        return ""
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:length]


def _feature_gate_reason(global_enabled: bool, pulse_enabled: bool) -> str:
    if not global_enabled:
        return "global_disabled"
    if not pulse_enabled:
        return "customer_pulse_disabled"
    return "enabled"


def followup_orchestrator_feature_gate_summary(access_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _feature_gate_context(access_context)
    pulse_gate = customer_pulse_feature_gate_summary(context)
    global_enabled = _config_bool(FOLLOWUP_ORCHESTRATOR_FLAG_KEY, default=False)
    enabled = bool(global_enabled and pulse_gate.get("enabled"))
    return {
        "enabled": enabled,
        "reason": _feature_gate_reason(global_enabled, bool(pulse_gate.get("enabled"))),
        "feature_flag": FOLLOWUP_ORCHESTRATOR_FLAG_KEY,
        "tenant_key": _normalized_text(context.get("tenant_key")) or _normalized_text(pulse_gate.get("tenant_key")) or "aicrm",
        "actor_userid": _normalized_text(context.get("actor_userid") or context.get("user_id")),
        "actor_role": _normalized_text(context.get("actor_role") or context.get("role")),
        "mode": _normalized_text(context.get("mode") or pulse_gate.get("mode")),
        "auth_mode": _normalized_text(context.get("auth_mode") or pulse_gate.get("auth_mode")),
        "global_enabled": bool(global_enabled),
        "pulse_feature_gate": pulse_gate,
    }


def is_followup_orchestrator_enabled(*, access_context: Mapping[str, Any] | None = None) -> bool:
    return bool(followup_orchestrator_feature_gate_summary(access_context).get("enabled"))


def _collect_evidence_refs(cards: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_collect_evidence_refs",
    )(cards, limit=limit)


def _build_owner_workload(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_build_owner_workload",
    )(cards)


def _team_candidate_owners(read_scope: Mapping[str, Any], owner_workload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_team_candidate_owners",
    )(read_scope, owner_workload)


def _first_signal_key(items: list[dict[str, Any]], *, field: str) -> str:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_first_signal_key",
    )(items, field=field)


def _card_intent_key(card: Mapping[str, Any]) -> str:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_card_intent_key",
    )(card)


def _batch_template_key(card: Mapping[str, Any]) -> str:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_batch_template_key",
    )(card)


def _is_high_risk_card(card: Mapping[str, Any]) -> bool:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_is_high_risk_card",
    )(card)


def _is_batchable_card(card: Mapping[str, Any]) -> bool:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_is_batchable_card",
    )(card)


def _due_urgency(card: Mapping[str, Any]) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_due_urgency",
    )(card)


def _stable_item_status(existing_item: Mapping[str, Any] | None) -> str:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_stable_item_status",
    )(existing_item)


def _stable_mission_status(existing_mission: Mapping[str, Any] | None) -> str:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_stable_mission_status",
    )(existing_mission)


def _card_signals(
    card: Mapping[str, Any],
    *,
    owner_workload_map: Mapping[str, Mapping[str, Any]],
    team_candidates: list[dict[str, Any]],
    untreated_counts: Mapping[str, int],
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_card_signals",
    )(
        card,
        owner_workload_map=owner_workload_map,
        team_candidates=team_candidates,
        untreated_counts=untreated_counts,
    )


def _batch_group_key(card: Mapping[str, Any], signals: Mapping[str, Any]) -> str:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_batch_group_key",
    )(card, signals)


def _determine_assignment(card: Mapping[str, Any], signals: Mapping[str, Any], *, can_view_all: bool) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_determine_assignment",
    )(card, signals, can_view_all=can_view_all)


def _escalation_reason(card: Mapping[str, Any], signals: Mapping[str, Any]) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_escalation_reason",
    )(card, signals)


def _mission_type_for_card(
    card: Mapping[str, Any],
    signals: Mapping[str, Any],
    *,
    batch_group_sizes: Mapping[str, int],
    can_view_all: bool,
) -> str:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_mission_type_for_card",
    )(
        card,
        signals,
        batch_group_sizes=batch_group_sizes,
        can_view_all=can_view_all,
    )


def _mission_key_for_card(
    card: Mapping[str, Any],
    signals: Mapping[str, Any],
    *,
    mission_type: str,
    scope_key: str,
    assignment: Mapping[str, Any],
) -> str:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_mission_key_for_card",
    )(
        card,
        signals,
        mission_type=mission_type,
        scope_key=scope_key,
        assignment=assignment,
    )


def _mission_title(mission_type: str) -> str:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_mission_title",
    )(mission_type)


def _mission_summary(mission_type: str, *, item_count: int, scope_label: str) -> str:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_mission_summary",
    )(mission_type, item_count=item_count, scope_label=scope_label)


def _mission_payload(
    mission_type: str,
    *,
    cards: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    assignment_suggestions: list[dict[str, Any]],
    escalation_suggestions: list[dict[str, Any]],
    batch_group_key: str = "",
    scope_key: str,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_mission_payload",
    )(
        mission_type,
        cards=cards,
        signals=signals,
        assignment_suggestions=assignment_suggestions,
        escalation_suggestions=escalation_suggestions,
        batch_group_key=batch_group_key,
        scope_key=scope_key,
    )


def _summarize_mission_items(items: list[dict[str, Any]]) -> tuple[str, int]:
    return _load_followup_internal_delegate(
        "mission_assignment_service",
        "_summarize_mission_items",
    )(items)


def _resolved_followup_read_scope(
    *,
    access_context: Mapping[str, Any] | None,
    requested_owner_userid: str = "",
) -> dict[str, Any]:
    return resolve_customer_pulse_read_scope(
        requested_owner_userid=_normalized_text(requested_owner_userid),
        access_context=_feature_gate_context(access_context),
    )


def _assert_mission_items_accessible(
    items: list[dict[str, Any]],
    *,
    read_scope: Mapping[str, Any],
    action_type: str = "",
) -> None:
    if not items:
        return
    if bool(read_scope.get("can_view_all")):
        allowed_owner_userids = {
            _normalized_text(item)
            for item in (read_scope.get("allowed_owner_userids") or [])
            if _normalized_text(item)
        }
        if not allowed_owner_userids:
            return
        for item in items:
            owner_userid = _normalized_text(item.get("owner_userid"))
            suggested_assignee_userid = _normalized_text(item.get("suggested_assignee_userid"))
            if owner_userid and owner_userid not in allowed_owner_userids:
                raise CustomerPulseAccessDenied(
                    "当前任务包包含超出 owner scope 的客户。",
                    code="owner_scope_forbidden",
                    http_status=403,
                )
            if suggested_assignee_userid and suggested_assignee_userid not in allowed_owner_userids:
                raise CustomerPulseAccessDenied(
                    "当前任务包包含超出 owner scope 的转派建议。",
                    code="owner_scope_forbidden",
                    http_status=403,
                )
        return

    actor_userid = _normalized_text(read_scope.get("actor_userid"))
    normalized_action_type = _normalized_text(action_type)
    for item in items:
        owner_userid = _normalized_text(item.get("owner_userid"))
        suggested_assignee_userid = _normalized_text(item.get("suggested_assignee_userid"))
        accessible = actor_userid and actor_userid in {owner_userid, suggested_assignee_userid}
        if not accessible and not owner_userid and normalized_action_type in {"claim", "accept"}:
            accessible = True
        if not accessible:
            raise CustomerPulseAccessDenied(
                "当前角色不能访问或操作该任务包。",
                code="owner_scope_forbidden",
                http_status=403,
            )
    if normalized_action_type in {"suggest_assignment", "request_manager_approval"} and not bool(read_scope.get("can_view_all")):
        raise CustomerPulseAccessDenied(
            "当前角色没有调整团队分配的权限。",
            code="operator_role_forbidden",
            http_status=403,
        )


def _current_item_execution_state(
    item: Mapping[str, Any],
    *,
    decision: Mapping[str, Any] | None,
) -> str:
    return _load_followup_internal_delegate(
        "mission_board_service",
        "_current_item_execution_state",
    )(item, decision=decision)


def _artifact_status_from_card_payload(card_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_artifact_status_from_card_payload",
    )(card_payload)


def _build_handoff_packet(
    *,
    mission: Mapping[str, Any],
    item: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    tenant_context: Mapping[str, Any],
    tenant_key: str,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_build_handoff_packet",
    )(
        mission=mission,
        item=item,
        decision=decision,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def _record_orchestrator_activity(
    *,
    item: Mapping[str, Any],
    tenant_key: str,
    operator: str,
    activity_type: str,
    activity_status: str,
    title: str,
    summary: str,
    payload: Mapping[str, Any] | None = None,
    due_at: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_record_orchestrator_activity",
    )(
        item=item,
        tenant_key=tenant_key,
        operator=operator,
        activity_type=activity_type,
        activity_status=activity_status,
        title=title,
        summary=summary,
        payload=payload,
        due_at=due_at,
        idempotency_key=idempotency_key,
    )


def _with_item_runtime_payload(
    item_payload: Mapping[str, Any],
    *,
    execution_state: str | None = None,
    latest_pulse_execution: Mapping[str, Any] | None = None,
    latest_pulse_result: Mapping[str, Any] | None = None,
    latest_pulse_action_type: str = "",
    latest_pulse_execution_id: int = 0,
    latest_pulse_activity_log_id: int = 0,
    handoff_packet: Mapping[str, Any] | None = None,
    active_assignee_userid: str = "",
    latest_orchestrator_activity_id: int = 0,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_with_item_runtime_payload",
    )(
        item_payload,
        execution_state=execution_state,
        latest_pulse_execution=latest_pulse_execution,
        latest_pulse_result=latest_pulse_result,
        latest_pulse_action_type=latest_pulse_action_type,
        latest_pulse_execution_id=latest_pulse_execution_id,
        latest_pulse_activity_log_id=latest_pulse_activity_log_id,
        handoff_packet=handoff_packet,
        active_assignee_userid=active_assignee_userid,
        latest_orchestrator_activity_id=latest_orchestrator_activity_id,
    )


def _apply_mission_ai_if_enabled(
    mission: dict[str, Any],
    *,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(mission, dict):
        return {}
    return _load_followup_internal_delegate(
        "followup_ai_enhancement_service",
        "apply_mission_ai_if_enabled",
    )(dict(mission))


def _decorate_mission(mission: Mapping[str, Any], *, items: list[dict[str, Any]], decisions: list[dict[str, Any]], logs: list[dict[str, Any]]) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_board_service",
        "_decorate_mission",
    )(mission, items=items, decisions=decisions, logs=logs)


def _decorate_item(item: Mapping[str, Any], *, decision: Mapping[str, Any] | None) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_board_service",
        "_decorate_item",
    )(item, decision=decision)


def _sync_scope_label(read_scope: Mapping[str, Any], requested_scope: str) -> str:
    return _load_followup_internal_delegate(
        "mission_sync_service",
        "_sync_scope_label",
    )(read_scope, requested_scope)


def sync_followup_orchestrator_missions(
    *,
    scope: str = "team",
    owner_userid: str = "",
    external_userid: str = "",
    limit: int = 50,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_read_service",
        "sync_followup_orchestrator_missions",
    )(
        scope=scope,
        owner_userid=owner_userid,
        external_userid=external_userid,
        limit=limit,
        access_context=access_context,
    )


def build_followup_orchestrator_overview_payload(
    *,
    scope: str = "team",
    owner_userid: str = "",
    external_userid: str = "",
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_read_service",
        "build_followup_orchestrator_overview_payload",
    )(
        scope=scope,
        owner_userid=owner_userid,
        external_userid=external_userid,
        limit=limit,
        auto_sync=auto_sync,
        access_context=access_context,
    )


def build_followup_orchestrator_customer_payload(
    *,
    external_userid: str,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_read_service",
        "build_followup_orchestrator_customer_payload",
    )(
        external_userid=external_userid,
        access_context=access_context,
    )


def build_followup_orchestrator_my_missions_payload(
    *,
    actor_userid: str,
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_read_service",
        "build_followup_orchestrator_my_missions_payload",
    )(
        actor_userid=actor_userid,
        limit=limit,
        auto_sync=auto_sync,
        access_context=access_context,
    )


def build_followup_orchestrator_team_board_payload(
    *,
    limit: int = 50,
    auto_sync: bool = True,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_read_service",
        "build_followup_orchestrator_team_board_payload",
    )(
        limit=limit,
        auto_sync=auto_sync,
        access_context=access_context,
    )


def get_followup_orchestrator_mission_detail_payload(
    *,
    mission_key: str,
    access_context: Mapping[str, Any] | None = None,
    tenant_key: str = "",
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_read_service",
        "get_followup_orchestrator_mission_detail_payload",
    )(
        mission_key=mission_key,
        access_context=access_context,
        tenant_key=tenant_key,
    )


def _resolved_mission_item_context(
    *,
    mission_key: str,
    mission_item_key: str,
    access_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_resolved_mission_item_context",
    )(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        access_context=access_context,
    )


def _executor_execution_state(action_type: str) -> str:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_executor_execution_state",
    )(action_type)


def _undo_restored_item_status(item: Mapping[str, Any], decision: Mapping[str, Any] | None) -> str:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_undo_restored_item_status",
    )(item, decision)


def preview_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    action_type: str = "",
    actor_userid: str = "",
    operator: str = "",
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_action_service",
        "preview_followup_orchestrator_mission_item_action",
    )(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        action_type=action_type,
        actor_userid=actor_userid,
        operator=operator,
        access_context=access_context,
    )


def _execute_followup_orchestrator_item_action(
    *,
    mission: Mapping[str, Any],
    item: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    action_type: str,
    actor_userid: str,
    actor_role: str,
    operator: str,
    note: str,
    extra_payload: Mapping[str, Any] | None,
    tenant_context: Mapping[str, Any] | None,
    tenant_key: str,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "mission_action_service",
        "_execute_followup_orchestrator_item_action",
    )(
        mission=mission,
        item=item,
        decision=decision,
        action_type=action_type,
        actor_userid=actor_userid,
        actor_role=actor_role,
        operator=operator,
        note=note,
        extra_payload=extra_payload,
        tenant_context=tenant_context,
        tenant_key=tenant_key,
    )


def execute_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    action_type: str = "",
    actor_userid: str,
    actor_role: str,
    operator: str,
    note: str = "",
    extra_payload: Mapping[str, Any] | None = None,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_action_service",
        "execute_followup_orchestrator_mission_item_action",
    )(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        action_type=action_type,
        actor_userid=actor_userid,
        actor_role=actor_role,
        operator=operator,
        note=note,
        extra_payload=extra_payload,
        access_context=access_context,
    )


def undo_followup_orchestrator_mission_item_action(
    *,
    mission_key: str,
    mission_item_key: str,
    execution_id: int = 0,
    actor_userid: str,
    actor_role: str,
    operator: str,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_action_service",
        "undo_followup_orchestrator_mission_item_action",
    )(
        mission_key=mission_key,
        mission_item_key=mission_item_key,
        execution_id=execution_id,
        actor_userid=actor_userid,
        actor_role=actor_role,
        operator=operator,
        access_context=access_context,
    )


def apply_followup_orchestrator_mission_action(
    *,
    mission_key: str,
    action_type: str,
    actor_userid: str,
    actor_role: str,
    operator: str,
    tenant_context: Mapping[str, Any] | None = None,
    mission_item_key: str = "",
    note: str = "",
) -> dict[str, Any]:
    return _load_followup_internal_delegate(
        "followup_mission_action_service",
        "apply_followup_orchestrator_mission_action",
    )(
        mission_key=mission_key,
        action_type=action_type,
        actor_userid=actor_userid,
        actor_role=actor_role,
        operator=operator,
        tenant_context=tenant_context,
        mission_item_key=mission_item_key,
        note=note,
    )
