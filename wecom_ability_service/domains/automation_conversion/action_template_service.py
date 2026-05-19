from __future__ import annotations

import json
import time
from typing import Any

from ...db import get_db
from . import workflow_repo
from .agents.llm_client import DeepSeekClientError, call_deepseek_agent
from .workflow_definitions import (
    AGENT_BINDING_SCOPE_BEHAVIOR_TIER,
    AGENT_BINDING_SCOPE_DEFAULT,
    AGENT_BINDING_SCOPE_PERSONALIZED,
    AGENT_BINDING_SCOPE_PROFILE_CATEGORY,
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
    GENERATION_MODE_AUTO_LAYERED_REWRITE,
    GENERATION_MODE_MANUAL_LAYERED,
    GENERATION_MODE_PERSONALIZED_SINGLE,
    NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
    NODE_TRIGGER_MODE_DAILY_RECURRING,
    NODE_TRIGGER_MODE_SCHEDULED,
    RECIPIENT_FILTER_BASIS_BEHAVIOR,
    RECIPIENT_FILTER_BASIS_NONE,
    SEGMENTATION_BASIS_BEHAVIOR,
    SEGMENTATION_BASIS_NONE,
    SEGMENTATION_BASIS_PROFILE,
    WORKFLOW_STATUS_ACTIVE,
    WORKFLOW_STATUS_DRAFT,
    WORKFLOW_STATUS_PAUSED,
    list_supported_behavior_tiers,
)
from .workflow_service import (
    NODE_CONTENT_MODE_MANUAL_LAYERED,
    NODE_CONTENT_MODE_PERSONALIZED_SINGLE,
    NODE_CONTENT_MODE_STANDARD_DIRECT,
    NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE,
    create_conversion_workflow,
    create_conversion_workflow_node,
    get_conversion_workflow_model_bundle,
)

TEMPLATE_SOURCE_BUILTIN = "builtin"
TEMPLATE_SOURCE_CRM_LOCAL = "crm_local"
TEMPLATE_SOURCE_AI_GENERATED = "ai_generated"

CONTENT_STRATEGY_PERSONALIZED_AGENT = "personalized_agent"
CONTENT_STRATEGY_STANDARD_CONTENT = "standard_content"
CONTENT_STRATEGY_LAYERED_CONTENT = "layered_content"
CONTENT_STRATEGY_LAYERED_AGENT_REWRITE = "layered_agent_rewrite"

_ALLOWED_TEMPLATE_SOURCES = {
    TEMPLATE_SOURCE_BUILTIN,
    TEMPLATE_SOURCE_CRM_LOCAL,
    TEMPLATE_SOURCE_AI_GENERATED,
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _normalized_text(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def _normalize_int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    if minimum is not None:
        result = max(int(minimum), result)
    return result


def _slugify_code(value: Any, *, prefix: str) -> str:
    raw = _normalized_text(value).lower().replace(" ", "_").replace("-", "_")
    safe = "".join(char if (char.isalnum() or char == "_") else "_" for char in raw)
    compact = "_".join(part for part in safe.split("_") if part)
    return compact or prefix


def _unique_template_code(raw_value: Any, *, exclude_id: int | None = None) -> str:
    base = _slugify_code(raw_value, prefix="action_template")
    candidate = base
    index = 2
    while True:
        existing = workflow_repo.get_operation_template_row_by_code(candidate)
        if not existing or (exclude_id and int(existing.get("id") or 0) == int(exclude_id)):
            return candidate
        candidate = f"{base}_{index}"
        index += 1


def _unique_workflow_code(raw_value: Any) -> str:
    base = _slugify_code(raw_value, prefix="operation_action")
    candidate = base
    index = 2
    while workflow_repo.get_workflow_row_by_code(candidate):
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def _source_label(source: str) -> str:
    return {
        TEMPLATE_SOURCE_BUILTIN: "系统内置",
        TEMPLATE_SOURCE_CRM_LOCAL: "CRM 本地",
        TEMPLATE_SOURCE_AI_GENERATED: "AI 生成",
    }.get(_normalized_text(source), "CRM 本地")


def _default_ui_schema(*, allow_multi_nodes: bool = True) -> dict[str, Any]:
    return {
        "show_questionnaire_selector": True,
        "show_agent_selector": True,
        "show_layer_basis": True,
        "show_standard_content": True,
        "show_miniprogram_card": True,
        "allow_multi_nodes": bool(allow_multi_nodes),
        "allow_save_as_template": True,
    }


def _builtin_template(
    *,
    code: str,
    name: str,
    category: str,
    description: str,
    default_config: dict[str, Any],
    workflow_blueprint: dict[str, Any],
    node_blueprints: list[dict[str, Any]],
    allow_multi_nodes: bool = True,
) -> dict[str, Any]:
    return {
        "id": 0,
        "template_code": code,
        "template_name": name,
        "template_source": TEMPLATE_SOURCE_BUILTIN,
        "template_source_label": _source_label(TEMPLATE_SOURCE_BUILTIN),
        "category": category,
        "description": description,
        "status": "active",
        "default_config": default_config,
        "ui_schema": _default_ui_schema(allow_multi_nodes=allow_multi_nodes),
        "workflow_blueprint": workflow_blueprint,
        "node_blueprints": node_blueprints,
        "created_by": "system",
        "updated_by": "system",
        "created_at": "",
        "updated_at": "",
        "archived_at": "",
        "is_builtin": True,
    }


def _behavior_variants() -> list[dict[str, Any]]:
    return [
        {
            "segment_key": _normalized_text(item.get("tier_code")),
            "content_text": "",
        }
        for item in list_supported_behavior_tiers()
    ]


BUILTIN_OPERATION_TEMPLATES: tuple[dict[str, Any], ...] = (
    _builtin_template(
        code="questionnaire_submit_followup",
        name="问卷提交后跟进",
        category="questionnaire",
        description="用户完成问卷后，用 Agent 生成一条定制化跟进内容。",
        default_config={
            "action_name": "问卷提交后跟进",
            "status": WORKFLOW_STATUS_DRAFT,
            "trigger_type": "questionnaire_submitted",
            "trigger_label": "用户提交问卷后",
            "audience_type": "questionnaire_submitter",
            "audience_label": "本次提交问卷的人",
            "send_timing": "immediate",
            "send_timing_label": "立即发送",
            "content_strategy": CONTENT_STRATEGY_PERSONALIZED_AGENT,
            "generation_requirement": "基于用户问卷结果、标签和推荐课程，生成一条自然、具体、可直接发送的跟进内容。",
            "layer_basis": "none",
        },
        workflow_blueprint={
            "audiences": [AUDIENCE_OPERATING],
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_NONE,
            "content_segmentation_basis": SEGMENTATION_BASIS_NONE,
            "generation_mode": GENERATION_MODE_PERSONALIZED_SINGLE,
            "status": WORKFLOW_STATUS_DRAFT,
        },
        node_blueprints=[
            {
                "node_name": "问卷提交后立即跟进",
                "target_audience_code": AUDIENCE_OPERATING,
                "trigger_mode": NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
                "content_mode": NODE_CONTENT_MODE_PERSONALIZED_SINGLE,
                "enabled": True,
            }
        ],
        allow_multi_nodes=False,
    ),
    _builtin_template(
        code="questionnaire_pending_reminder",
        name="未填问卷提醒",
        category="questionnaire",
        description="用户尚未提交问卷时，自动推送问卷入口提醒填写。",
        default_config={
            "action_name": "未填问卷提醒",
            "status": WORKFLOW_STATUS_DRAFT,
            "trigger_type": "check_pending_questionnaire",
            "trigger_label": "检查未填问卷",
            "audience_type": "pending_questionnaire",
            "audience_label": "未填问卷人群",
            "send_timing": "daily_10",
            "send_timing_label": "定时发送",
            "content_strategy": CONTENT_STRATEGY_STANDARD_CONTENT,
            "standard_content_text": "你还没有完成这次测评。点开下面的小程序卡片，花 1 分钟完成问卷，我会根据结果给你发一份适合你的行动建议。",
            "layer_basis": "none",
        },
        workflow_blueprint={
            "audiences": [AUDIENCE_PENDING_QUESTIONNAIRE],
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_NONE,
            "content_segmentation_basis": SEGMENTATION_BASIS_NONE,
            "generation_mode": GENERATION_MODE_MANUAL_LAYERED,
            "status": WORKFLOW_STATUS_DRAFT,
        },
        node_blueprints=[
            {
                "node_name": "提醒用户填写问卷",
                "target_audience_code": AUDIENCE_PENDING_QUESTIONNAIRE,
                "trigger_mode": NODE_TRIGGER_MODE_DAILY_RECURRING,
                "day_offset": 1,
                "send_time": "10:00",
                "content_mode": NODE_CONTENT_MODE_STANDARD_DIRECT,
                "standard_content_text": "你还没有完成这次测评。点开下面的小程序卡片，花 1 分钟完成问卷，我会根据结果给你发一份适合你的行动建议。",
                "enabled": True,
            }
        ],
    ),
    _builtin_template(
        code="low_interaction_wakeup",
        name="低互动用户唤醒",
        category="wakeup",
        description="按消息数或标签筛选低互动用户，发送不同唤醒话术。",
        default_config={
            "action_name": "低互动用户唤醒",
            "status": WORKFLOW_STATUS_DRAFT,
            "trigger_type": "check_low_interaction",
            "trigger_label": "检查低互动用户",
            "audience_type": "low_interaction",
            "audience_label": "低互动用户",
            "send_timing": "daily_14",
            "send_timing_label": "定时发送",
            "content_strategy": CONTENT_STRATEGY_LAYERED_CONTENT,
            "layer_basis": "behavior",
        },
        workflow_blueprint={
            "audiences": [AUDIENCE_OPERATING],
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_BEHAVIOR,
            "recipient_behavior_tier_keys": ["lt_2", "between_2_9"],
            "content_segmentation_basis": SEGMENTATION_BASIS_BEHAVIOR,
            "generation_mode": GENERATION_MODE_MANUAL_LAYERED,
            "status": WORKFLOW_STATUS_DRAFT,
        },
        node_blueprints=[
            {
                "node_name": "低互动用户唤醒",
                "target_audience_code": AUDIENCE_OPERATING,
                "trigger_mode": NODE_TRIGGER_MODE_DAILY_RECURRING,
                "day_offset": 3,
                "send_time": "14:00",
                "content_mode": NODE_CONTENT_MODE_MANUAL_LAYERED,
                "segmentation_basis": SEGMENTATION_BASIS_BEHAVIOR,
                "content_variants": _behavior_variants(),
                "enabled": True,
            }
        ],
    ),
    _builtin_template(
        code="group_entry_reminder",
        name="入群后提醒",
        category="community",
        description="用户进入社群或运营人群后，按指定天数发送提醒。",
        default_config={
            "action_name": "入群后提醒",
            "status": WORKFLOW_STATUS_DRAFT,
            "trigger_type": "audience_entered",
            "trigger_label": "进入社群 / 进入人群",
            "audience_type": "entered_group",
            "audience_label": "入群用户",
            "send_timing": "day_3_10",
            "send_timing_label": "第 3 天 10:00",
            "content_strategy": CONTENT_STRATEGY_STANDARD_CONTENT,
            "standard_content_text": "欢迎加入社群。你可以先完成这份小测评，我会根据你的情况给你发下一步建议。",
            "layer_basis": "none",
        },
        workflow_blueprint={
            "audiences": [AUDIENCE_OPERATING],
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_NONE,
            "content_segmentation_basis": SEGMENTATION_BASIS_NONE,
            "generation_mode": GENERATION_MODE_MANUAL_LAYERED,
            "status": WORKFLOW_STATUS_DRAFT,
        },
        node_blueprints=[
            {
                "node_name": "入群第 3 天提醒",
                "target_audience_code": AUDIENCE_OPERATING,
                "trigger_mode": NODE_TRIGGER_MODE_SCHEDULED,
                "day_offset": 3,
                "send_time": "10:00",
                "content_mode": NODE_CONTENT_MODE_STANDARD_DIRECT,
                "standard_content_text": "欢迎加入社群。你可以先完成这份小测评，我会根据你的情况给你发下一步建议。",
                "enabled": True,
            }
        ],
    ),
    _builtin_template(
        code="high_intent_closing_followup",
        name="高意向客户成交跟进",
        category="closing",
        description="命中高意向标签或问卷高分后，发送成交跟进内容。",
        default_config={
            "action_name": "高意向客户成交跟进",
            "status": WORKFLOW_STATUS_DRAFT,
            "trigger_type": "high_intent_matched",
            "trigger_label": "命中高意向标签或问卷高分",
            "audience_type": "high_intent",
            "audience_label": "高意向人群",
            "send_timing": "immediate",
            "send_timing_label": "立即发送",
            "content_strategy": CONTENT_STRATEGY_PERSONALIZED_AGENT,
            "generation_requirement": "基于用户意向、问卷结果和推荐方案，生成一条适合成交推进的私聊内容。",
            "layer_basis": "none",
        },
        workflow_blueprint={
            "audiences": [AUDIENCE_OPERATING, AUDIENCE_CONVERTED],
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_NONE,
            "content_segmentation_basis": SEGMENTATION_BASIS_NONE,
            "generation_mode": GENERATION_MODE_PERSONALIZED_SINGLE,
            "status": WORKFLOW_STATUS_DRAFT,
        },
        node_blueprints=[
            {
                "node_name": "高意向客户立即跟进",
                "target_audience_code": AUDIENCE_OPERATING,
                "trigger_mode": NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
                "content_mode": NODE_CONTENT_MODE_PERSONALIZED_SINGLE,
                "enabled": True,
            }
        ],
    ),
    _builtin_template(
        code="custom_operation_action",
        name="自定义运营动作",
        category="custom",
        description="自行组合触发、人群、内容和节点。",
        default_config={
            "action_name": "自定义运营动作",
            "status": WORKFLOW_STATUS_DRAFT,
            "trigger_type": "manual",
            "trigger_label": "手动触发",
            "audience_type": "custom",
            "audience_label": "指定人群",
            "send_timing": "immediate",
            "send_timing_label": "立即发送",
            "content_strategy": CONTENT_STRATEGY_STANDARD_CONTENT,
            "standard_content_text": "",
            "layer_basis": "none",
        },
        workflow_blueprint={
            "audiences": [AUDIENCE_OPERATING],
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_NONE,
            "content_segmentation_basis": SEGMENTATION_BASIS_NONE,
            "generation_mode": GENERATION_MODE_MANUAL_LAYERED,
            "status": WORKFLOW_STATUS_DRAFT,
        },
        node_blueprints=[
            {
                "node_name": "自定义执行节点",
                "target_audience_code": AUDIENCE_OPERATING,
                "trigger_mode": NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
                "content_mode": NODE_CONTENT_MODE_STANDARD_DIRECT,
                "standard_content_text": "",
                "enabled": True,
            }
        ],
    ),
)


def _serialize_template(row: dict[str, Any]) -> dict[str, Any]:
    template = dict(row or {})
    source = _normalized_text(template.get("template_source")) or TEMPLATE_SOURCE_CRM_LOCAL
    template["template_source"] = source
    template["template_source_label"] = _source_label(source)
    template["is_builtin"] = source == TEMPLATE_SOURCE_BUILTIN
    template.setdefault("default_config", {})
    template.setdefault("ui_schema", _default_ui_schema())
    template.setdefault("workflow_blueprint", {})
    template.setdefault("node_blueprints", [])
    return template


def list_action_templates(
    *,
    template_source: str = "",
    category: str = "",
    keyword: str = "",
    include_archived: bool = False,
) -> dict[str, Any]:
    source = _normalized_text(template_source)
    if source and source not in _ALLOWED_TEMPLATE_SOURCES:
        raise ValueError("invalid template_source")
    normalized_keyword = _normalized_text(keyword).lower()
    builtin_items = []
    if source in {"", TEMPLATE_SOURCE_BUILTIN}:
        for item in BUILTIN_OPERATION_TEMPLATES:
            if _normalized_text(category) and _normalized_text(item.get("category")) != _normalized_text(category):
                continue
            if normalized_keyword and normalized_keyword not in (
                f"{item.get('template_name', '')} {item.get('description', '')} {item.get('category', '')}".lower()
            ):
                continue
            builtin_items.append(_serialize_template(item))
    db_items = [
        _serialize_template(item)
        for item in workflow_repo.list_operation_template_rows(
            template_source="" if source == TEMPLATE_SOURCE_BUILTIN else source,
            category=category,
            keyword=keyword,
            include_archived=include_archived,
        )
    ]
    if source == TEMPLATE_SOURCE_BUILTIN:
        db_items = []
    items = builtin_items + db_items
    return {"items": items, "total": len(items)}


def get_action_template(template_ref: str | int) -> dict[str, Any]:
    ref_text = _normalized_text(template_ref)
    for item in BUILTIN_OPERATION_TEMPLATES:
        if ref_text in {_normalized_text(item.get("template_code")), str(int(item.get("id") or 0))}:
            return _serialize_template(item)
    row = None
    if ref_text.isdigit():
        row = workflow_repo.get_operation_template_row(int(ref_text))
    if not row:
        row = workflow_repo.get_operation_template_row_by_code(ref_text)
    if not row:
        raise LookupError("action template not found")
    return _serialize_template(row)


def _normalize_template_payload(
    payload: dict[str, Any],
    *,
    template_source: str = TEMPLATE_SOURCE_CRM_LOCAL,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = dict(payload or {})
    current = dict(existing or {})
    source_value = _normalized_text(source.get("template_source") or current.get("template_source") or template_source)
    if source_value not in {TEMPLATE_SOURCE_CRM_LOCAL, TEMPLATE_SOURCE_AI_GENERATED}:
        raise ValueError("template_source must be crm_local or ai_generated")
    template_name = _normalized_text(source.get("template_name") or current.get("template_name"))
    if not template_name:
        raise ValueError("template_name is required")
    template_code = _unique_template_code(source.get("template_code") or current.get("template_code") or template_name, exclude_id=int(current.get("id") or 0) or None)
    status = _normalized_text(source.get("status") or current.get("status")) or "active"
    if status not in {"active", "archived"}:
        raise ValueError("invalid template status")
    return {
        "template_code": template_code,
        "template_name": template_name,
        "template_source": source_value,
        "category": _normalized_text(source.get("category") if "category" in source else current.get("category")),
        "description": _normalized_text(source.get("description") if "description" in source else current.get("description")),
        "status": status,
        "default_config": dict(source.get("default_config") or current.get("default_config") or {}),
        "ui_schema": dict(source.get("ui_schema") or current.get("ui_schema") or _default_ui_schema()),
        "workflow_blueprint": dict(source.get("workflow_blueprint") or current.get("workflow_blueprint") or {}),
        "node_blueprints": list(source.get("node_blueprints") or current.get("node_blueprints") or []),
    }


def create_action_template(payload: dict[str, Any], *, operator_id: str, template_source: str = TEMPLATE_SOURCE_CRM_LOCAL) -> dict[str, Any]:
    normalized = _normalize_template_payload(payload, template_source=template_source)
    row = workflow_repo.insert_operation_template_row(
        {
            **normalized,
            "created_by": operator_id,
            "updated_by": operator_id,
        }
    )
    get_db().commit()
    return {"template": _serialize_template(row)}


def _first_agent_code() -> str:
    rows = workflow_repo.list_agent_config_summary_rows(enabled_only=True)
    if not rows:
        rows = workflow_repo.list_agent_config_summary_rows(enabled_only=False)
    return _normalized_text((rows[0] if rows else {}).get("agent_code"))


def _agent_binding_for_strategy(config: dict[str, Any], strategy: str, layer_basis: str) -> list[dict[str, Any]]:
    agent_code = _normalized_text(config.get("agent_code") or config.get("default_agent_code") or _first_agent_code())
    if strategy in {CONTENT_STRATEGY_PERSONALIZED_AGENT, CONTENT_STRATEGY_LAYERED_AGENT_REWRITE} and not agent_code:
        raise ValueError("请先选择智能体")
    if strategy == CONTENT_STRATEGY_PERSONALIZED_AGENT:
        return [
            {
                "binding_scope": AGENT_BINDING_SCOPE_PERSONALIZED,
                "segment_key": "personalized",
                "agent_code": agent_code,
            }
        ]
    if strategy != CONTENT_STRATEGY_LAYERED_AGENT_REWRITE:
        return []
    if layer_basis == "behavior":
        return [
            {
                "binding_scope": AGENT_BINDING_SCOPE_BEHAVIOR_TIER,
                "segment_key": _normalized_text(item.get("tier_code")),
                "agent_code": agent_code,
            }
            for item in list_supported_behavior_tiers()
        ]
    return [
        {
            "binding_scope": AGENT_BINDING_SCOPE_DEFAULT if not _normalized_text(config.get("profile_segment_template_id")) else AGENT_BINDING_SCOPE_PROFILE_CATEGORY,
            "segment_key": "",
            "agent_code": agent_code,
        }
    ]


def _workflow_payload_from_config(
    template: dict[str, Any],
    config: dict[str, Any],
    *,
    program_id: int,
) -> dict[str, Any]:
    blueprint = dict(template.get("workflow_blueprint") or {})
    strategy = _normalized_text(config.get("content_strategy")) or _normalized_text((template.get("default_config") or {}).get("content_strategy"))
    layer_basis = _normalized_text(config.get("layer_basis")) or "none"
    if strategy == CONTENT_STRATEGY_PERSONALIZED_AGENT:
        generation_mode = GENERATION_MODE_PERSONALIZED_SINGLE
        segmentation_basis = SEGMENTATION_BASIS_NONE
        recipient_filter_basis = RECIPIENT_FILTER_BASIS_NONE
    elif strategy == CONTENT_STRATEGY_LAYERED_CONTENT:
        generation_mode = GENERATION_MODE_MANUAL_LAYERED
        segmentation_basis = SEGMENTATION_BASIS_PROFILE if layer_basis == "profile" else SEGMENTATION_BASIS_BEHAVIOR
        recipient_filter_basis = RECIPIENT_FILTER_BASIS_BEHAVIOR if layer_basis == "behavior" else RECIPIENT_FILTER_BASIS_NONE
    elif strategy == CONTENT_STRATEGY_LAYERED_AGENT_REWRITE:
        generation_mode = GENERATION_MODE_AUTO_LAYERED_REWRITE
        segmentation_basis = SEGMENTATION_BASIS_BEHAVIOR if layer_basis == "behavior" else SEGMENTATION_BASIS_PROFILE
        recipient_filter_basis = RECIPIENT_FILTER_BASIS_BEHAVIOR if layer_basis == "behavior" else RECIPIENT_FILTER_BASIS_NONE
    else:
        generation_mode = GENERATION_MODE_MANUAL_LAYERED
        segmentation_basis = SEGMENTATION_BASIS_NONE
        recipient_filter_basis = RECIPIENT_FILTER_BASIS_NONE

    audiences = list(config.get("audiences") or blueprint.get("audiences") or [AUDIENCE_OPERATING])
    tier_keys = list(config.get("recipient_behavior_tier_keys") or blueprint.get("recipient_behavior_tier_keys") or [])
    if recipient_filter_basis == RECIPIENT_FILTER_BASIS_BEHAVIOR and not tier_keys:
        tier_keys = ["lt_2", "between_2_9"] if strategy == CONTENT_STRATEGY_LAYERED_CONTENT else [item["tier_code"] for item in list_supported_behavior_tiers()]
    profile_template_id = _normalize_int(
        config.get("content_profile_segment_template_id") or config.get("profile_segment_template_id") or blueprint.get("content_profile_segment_template_id") or blueprint.get("profile_segment_template_id"),
        default=0,
        minimum=0,
    ) or None
    return {
        "program_id": int(program_id),
        "workflow_code": _unique_workflow_code(config.get("action_code") or config.get("action_name") or template.get("template_code")),
        "workflow_name": _normalized_text(config.get("action_name") or template.get("template_name")),
        "description": _normalized_text(config.get("description") or template.get("description")),
        "status": _normalized_text(config.get("status")) if _normalized_text(config.get("status")) in {WORKFLOW_STATUS_DRAFT, WORKFLOW_STATUS_ACTIVE, WORKFLOW_STATUS_PAUSED} else WORKFLOW_STATUS_DRAFT,
        "audiences": audiences,
        "recipient_filter_basis": recipient_filter_basis,
        "recipient_behavior_tier_keys": tier_keys,
        "content_segmentation_basis": segmentation_basis,
        "content_profile_segment_template_id": profile_template_id,
        "generation_mode": generation_mode,
        "agent_bindings": _agent_binding_for_strategy(config, strategy, layer_basis),
        "fallback_to_standard_content": True,
    }


def _node_payload_from_blueprint(
    blueprint: dict[str, Any],
    config: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    node = dict(blueprint or {})
    strategy = _normalized_text(node.get("content_strategy") or config.get("content_strategy"))
    layer_basis = _normalized_text(config.get("layer_basis")) or "none"
    content_mode = _normalized_text(node.get("content_mode"))
    if not content_mode:
        if strategy == CONTENT_STRATEGY_PERSONALIZED_AGENT:
            content_mode = NODE_CONTENT_MODE_PERSONALIZED_SINGLE
        elif strategy == CONTENT_STRATEGY_LAYERED_CONTENT:
            content_mode = NODE_CONTENT_MODE_MANUAL_LAYERED
        elif strategy == CONTENT_STRATEGY_LAYERED_AGENT_REWRITE:
            content_mode = NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE
        else:
            content_mode = NODE_CONTENT_MODE_STANDARD_DIRECT
    trigger_mode = _normalized_text(node.get("trigger_mode")) or NODE_TRIGGER_MODE_AUDIENCE_ENTERED
    payload: dict[str, Any] = {
        "node_code": node.get("node_code") or f"action_node_{index}",
        "node_name": _normalized_text(node.get("node_name")) or f"执行节点 {index}",
        "target_audience_code": _normalized_text(node.get("target_audience_code")) or AUDIENCE_OPERATING,
        "trigger_mode": trigger_mode,
        "position_index": _normalize_int(node.get("position_index"), default=index - 1, minimum=0),
        "enabled": _normalize_bool(node.get("enabled"), default=True),
        "content_mode": content_mode,
    }
    if trigger_mode != NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
        payload["day_offset"] = _normalize_int(node.get("day_offset") or config.get("day_offset"), default=1, minimum=1)
        payload["send_time"] = _normalized_text(node.get("send_time") or config.get("send_time")) or "09:00"
    if content_mode == NODE_CONTENT_MODE_STANDARD_DIRECT:
        payload["standard_content_text"] = _normalized_text(config.get("standard_content_text") or node.get("standard_content_text"))
    elif content_mode == NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE:
        payload["standard_content_text"] = _normalized_text(config.get("standard_content_text") or node.get("standard_content_text"))
        payload["segmentation_basis"] = SEGMENTATION_BASIS_BEHAVIOR if layer_basis == "behavior" else SEGMENTATION_BASIS_PROFILE
    elif content_mode == NODE_CONTENT_MODE_MANUAL_LAYERED:
        payload["segmentation_basis"] = SEGMENTATION_BASIS_BEHAVIOR if layer_basis == "behavior" else SEGMENTATION_BASIS_PROFILE if layer_basis == "profile" else SEGMENTATION_BASIS_BEHAVIOR
        payload["content_variants"] = list(node.get("content_variants") or config.get("content_variants") or _behavior_variants())
    elif content_mode == NODE_CONTENT_MODE_PERSONALIZED_SINGLE:
        node_agent_code = _normalized_text(node.get("agent_code"))
        payload["agent_bindings"] = [
            {
                **binding,
                "agent_code": node_agent_code or binding.get("agent_code"),
            }
            for binding in _agent_binding_for_strategy(config, CONTENT_STRATEGY_PERSONALIZED_AGENT, layer_basis)
        ]
    material_payload = dict(node.get("standard_content_payload") or {})
    miniprogram_ids = node.get("miniprogram_library_ids") or material_payload.get("miniprogram_library_ids") or config.get("miniprogram_library_ids") or []
    image_ids = node.get("image_library_ids") or material_payload.get("image_library_ids") or config.get("image_library_ids") or []
    attachment_ids = node.get("attachment_library_ids") or material_payload.get("attachment_library_ids") or config.get("attachment_library_ids") or []
    normalized_material_payload: dict[str, Any] = {}
    operation_config = material_payload.get("operation_config")
    if isinstance(operation_config, dict):
        normalized_material_payload["operation_config"] = dict(operation_config)
    if miniprogram_ids:
        normalized_material_payload["miniprogram_library_ids"] = [
            _normalize_int(item, default=0, minimum=0)
            for item in miniprogram_ids
            if _normalize_int(item, default=0, minimum=0) > 0
        ]
    if image_ids:
        normalized_material_payload["image_library_ids"] = [
            _normalize_int(item, default=0, minimum=0)
            for item in image_ids
            if _normalize_int(item, default=0, minimum=0) > 0
        ]
    if attachment_ids:
        normalized_material_payload["attachment_library_ids"] = [
            _normalize_int(item, default=0, minimum=0)
            for item in attachment_ids
            if _normalize_int(item, default=0, minimum=0) > 0
        ][:9]
    if normalized_material_payload:
        payload["standard_content_payload"] = normalized_material_payload
    return payload


def create_action_from_template(
    program_id: int,
    payload: dict[str, Any],
    *,
    operator_id: str,
) -> dict[str, Any]:
    template_ref = payload.get("template_id") or payload.get("template_code")
    if not _normalized_text(template_ref):
        raise ValueError("template_id or template_code is required")
    template = get_action_template(template_ref)
    config = {
        **dict(template.get("default_config") or {}),
        **dict(payload.get("config") or {}),
    }
    workflow_payload = _workflow_payload_from_config(template, config, program_id=int(program_id))
    workflow_result = create_conversion_workflow(workflow_payload, operator_id=operator_id, program_id=int(program_id))
    workflow_bundle = workflow_result["workflow_bundle"]
    workflow_id = int((workflow_bundle.get("workflow") or {}).get("id") or 0)
    node_blueprints = list((payload.get("nodes") if isinstance(payload.get("nodes"), list) else None) or template.get("node_blueprints") or [])
    if not node_blueprints:
        node_blueprints = [{"node_name": "执行节点", "target_audience_code": (workflow_payload["audiences"] or [AUDIENCE_OPERATING])[0]}]
    created_nodes = []
    for index, node_blueprint in enumerate(node_blueprints, start=1):
        created = create_conversion_workflow_node(
            workflow_id,
            _node_payload_from_blueprint(dict(node_blueprint or {}), config, index=index),
            operator_id=operator_id,
        )
        created_nodes.append(created.get("node"))
    return {
        "workflow_id": workflow_id,
        "workflow_bundle": get_conversion_workflow_model_bundle(workflow_id),
        "template": template,
        "created_nodes": created_nodes,
    }


def infer_action_template_code_from_workflow(workflow_bundle: dict[str, Any]) -> str:
    workflow = dict((workflow_bundle or {}).get("workflow") or {})
    generation_mode = _normalized_text(workflow.get("generation_mode"))
    segmentation_basis = _normalized_text(workflow.get("content_segmentation_basis") or workflow.get("segmentation_basis"))
    nodes = list((workflow_bundle or {}).get("nodes") or [])
    has_variants = any(list(node.get("content_variants") or []) for node in nodes)
    name = _normalized_text(workflow.get("workflow_name"))
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        return "questionnaire_submit_followup" if "问卷" in name else "high_intent_closing_followup"
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED and has_variants:
        return "low_interaction_wakeup" if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR else "custom_operation_action"
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        return "questionnaire_pending_reminder" if "问卷" in name or "提醒" in name else "custom_operation_action"
    if generation_mode == GENERATION_MODE_AUTO_LAYERED_REWRITE:
        return "low_interaction_wakeup" if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR else "custom_operation_action"
    return "custom_operation_action"


def workflow_to_template_payload(
    workflow_id: int,
    *,
    template_name: str,
    description: str = "",
    template_source: str = TEMPLATE_SOURCE_CRM_LOCAL,
) -> dict[str, Any]:
    bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    workflow = dict(bundle.get("workflow") or {})
    nodes = list(bundle.get("nodes") or [])
    inferred_template = get_action_template(infer_action_template_code_from_workflow(bundle))
    default_config = {
        **dict(inferred_template.get("default_config") or {}),
        "action_name": _normalized_text(workflow.get("workflow_name")),
        "description": _normalized_text(workflow.get("description")),
        "status": _normalized_text(workflow.get("status")) or WORKFLOW_STATUS_DRAFT,
    }
    if _normalized_text(workflow.get("generation_mode")) == GENERATION_MODE_PERSONALIZED_SINGLE:
        default_config["content_strategy"] = CONTENT_STRATEGY_PERSONALIZED_AGENT
        default_config["agent_code"] = _normalized_text(((bundle.get("agent_bindings") or [{}])[0]).get("agent_code"))
    elif any(list(node.get("content_variants") or []) for node in nodes):
        default_config["content_strategy"] = CONTENT_STRATEGY_LAYERED_CONTENT
        default_config["layer_basis"] = "behavior" if _normalized_text(workflow.get("content_segmentation_basis")) == SEGMENTATION_BASIS_BEHAVIOR else "profile"
    else:
        default_config["content_strategy"] = CONTENT_STRATEGY_STANDARD_CONTENT
    workflow_blueprint = {
        "audiences": [item.get("audience_code") for item in bundle.get("audiences") or [] if item.get("audience_code")],
        "recipient_filter_basis": _normalized_text(workflow.get("recipient_filter_basis")) or RECIPIENT_FILTER_BASIS_NONE,
        "recipient_behavior_tier_keys": list(workflow.get("recipient_behavior_tier_keys") or []),
        "content_segmentation_basis": _normalized_text(workflow.get("content_segmentation_basis")) or SEGMENTATION_BASIS_NONE,
        "content_profile_segment_template_id": workflow.get("content_profile_segment_template_id"),
        "generation_mode": _normalized_text(workflow.get("generation_mode")) or GENERATION_MODE_MANUAL_LAYERED,
        "status": WORKFLOW_STATUS_DRAFT,
    }
    node_blueprints = [
        {
            "node_name": _normalized_text(node.get("node_name")),
            "target_audience_code": _normalized_text(node.get("target_audience_code")),
            "trigger_mode": _normalized_text(node.get("trigger_mode")),
            "day_offset": int(node.get("day_offset") or 1),
            "send_time": _normalized_text(node.get("send_time")) or "09:00",
            "content_mode": _normalized_text(node.get("content_mode")),
            "segmentation_basis": _normalized_text(node.get("segmentation_basis")),
            "standard_content_text": _normalized_text(node.get("standard_content_text")),
            "standard_content_payload": dict(node.get("standard_content_payload") or {}),
            "content_variants": list(node.get("content_variants") or []),
            "enabled": bool(node.get("enabled")),
        }
        for node in nodes
    ]
    return _normalize_template_payload(
        {
            "template_name": template_name,
            "template_source": template_source,
            "category": _normalized_text(inferred_template.get("category")) or "custom",
            "description": description or _normalized_text(workflow.get("description")),
            "default_config": default_config,
            "ui_schema": _default_ui_schema(),
            "workflow_blueprint": workflow_blueprint,
            "node_blueprints": node_blueprints,
        },
        template_source=template_source,
    )


def create_action_template_from_workflow(payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    workflow_id = _normalize_int(payload.get("workflow_id"), default=0, minimum=1)
    if workflow_id <= 0:
        raise ValueError("workflow_id is required")
    normalized = workflow_to_template_payload(
        workflow_id,
        template_name=_normalized_text(payload.get("template_name")),
        description=_normalized_text(payload.get("description")),
        template_source=TEMPLATE_SOURCE_CRM_LOCAL,
    )
    if not normalized["template_name"]:
        raise ValueError("template_name is required")
    row = workflow_repo.insert_operation_template_row({**normalized, "created_by": operator_id, "updated_by": operator_id})
    get_db().commit()
    return {"template": _serialize_template(row)}


def _template_payload_from_ai_response(payload: dict[str, Any], *, business_goal: str) -> dict[str, Any]:
    template_name = _normalized_text(payload.get("template_name") or payload.get("name")) or "AI 生成运营动作模板"
    default_config = dict(payload.get("default_config") or {})
    workflow_blueprint = dict(payload.get("workflow_blueprint") or {})
    node_blueprints = list(payload.get("node_blueprints") or [])
    if not default_config:
        raise ValueError("AI template missing default_config")
    if not workflow_blueprint:
        raise ValueError("AI template missing workflow_blueprint")
    if not node_blueprints:
        raise ValueError("AI template missing node_blueprints")
    return {
        "template_name": template_name,
        "template_source": TEMPLATE_SOURCE_AI_GENERATED,
        "category": _normalized_text(payload.get("category")) or "ai_generated",
        "description": _normalized_text(payload.get("description")) or business_goal,
        "default_config": default_config,
        "ui_schema": dict(payload.get("ui_schema") or _default_ui_schema()),
        "workflow_blueprint": workflow_blueprint,
        "node_blueprints": node_blueprints,
    }


def generate_action_template(payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    business_goal = _normalized_text(payload.get("business_goal"))
    if not business_goal:
        raise ValueError("business_goal is required")
    preference = _normalized_text(payload.get("preference"))
    system_prompt = (
        "你是 CRM 自动化运营动作模板设计助手。只返回 JSON 对象，不要输出解释。"
        "字段必须包含 template_name, category, description, default_config, ui_schema, "
        "workflow_blueprint, node_blueprints。"
        "content_strategy 只能是 personalized_agent、standard_content、layered_content、layered_agent_rewrite。"
        "audiences 只能使用 pending_questionnaire、operating、converted。"
        "trigger_mode 只能使用 scheduled、daily_recurring、audience_entered。"
    )
    user_input = json.dumps(
        {
            "business_goal": business_goal,
            "preference": preference,
            "program_id": payload.get("program_id"),
            "required_sources": [TEMPLATE_SOURCE_CRM_LOCAL, TEMPLATE_SOURCE_AI_GENERATED],
            "example_business_fields": {
                "trigger_label": "用户提交问卷后",
                "audience_label": "本次提交问卷的人",
                "send_timing_label": "立即发送",
            },
        },
        ensure_ascii=False,
    )
    try:
        result = call_deepseek_agent(
            agent_code="central_router_agent",
            system_prompt=system_prompt,
            user_input=user_input,
            json_output=True,
            request_id=f"action-template-{int(time.time())}",
            source="automation_action_template_generate",
        )
        generated_payload = result.get("parsed_output") if isinstance(result.get("parsed_output"), dict) else {}
        normalized = _normalize_template_payload(
            _template_payload_from_ai_response(generated_payload, business_goal=business_goal),
            template_source=TEMPLATE_SOURCE_AI_GENERATED,
        )
        row = workflow_repo.insert_operation_template_row(
            {
                **normalized,
                "created_by": operator_id,
                "updated_by": operator_id,
            }
        )
        get_db().commit()
        return {"template": _serialize_template(row), "ai_run": {"run_id": result.get("run_id"), "request_id": result.get("request_id")}}
    except (DeepSeekClientError, LookupError, ValueError, TypeError, json.JSONDecodeError) as exc:
        get_db().rollback()
        raise ValueError("AI 模板生成失败，请稍后重试或改用 CRM 本地创建") from exc
