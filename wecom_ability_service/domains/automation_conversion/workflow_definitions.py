from __future__ import annotations

from typing import Any


AUDIENCE_PENDING_QUESTIONNAIRE = "pending_questionnaire"
AUDIENCE_OPERATING = "operating"
AUDIENCE_CONVERTED = "converted"

STAGE_SCAN_ENTER = "scan_enter"
STAGE_ORDER_REVIEW = "order_review"
STAGE_QUESTIONNAIRE_REVIEW = "questionnaire_review"
STAGE_OPERATING = "operating"
STAGE_CONVERSION_REVIEW = "conversion_review"
STAGE_CONVERTED = "converted"
STAGE_FINISHED = "finished"

ENTRY_REASON_ORDER_REVIEW_PENDING = "order_review_pending"
ENTRY_REASON_QUESTIONNAIRE_REVIEW_PENDING = "questionnaire_review_pending"
ENTRY_REASON_AUDIENCE_RULE_PASSED = "audience_entry_rule_passed"
ENTRY_REASON_CONVERSION_PRODUCT_PAID = "conversion_product_paid"

STAGE_LABELS = {
    STAGE_SCAN_ENTER: "扫码进入",
    STAGE_ORDER_REVIEW: "订单审核",
    STAGE_QUESTIONNAIRE_REVIEW: "问卷审核",
    STAGE_OPERATING: "运营中",
    STAGE_CONVERSION_REVIEW: "成交判定",
    STAGE_CONVERTED: "已转化",
    STAGE_FINISHED: "结束",
}

STAGE_DESCRIPTIONS = {
    STAGE_SCAN_ENTER: "当前方案入口",
    STAGE_ORDER_REVIEW: "待支付 / 待确认订单",
    STAGE_QUESTIONNAIRE_REVIEW: "待填写问卷",
    STAGE_OPERATING: "已通过前置条件，进入正式运营",
    STAGE_CONVERSION_REVIEW: "运营后的成交判断动作",
    STAGE_CONVERTED: "已确认成交，可做转化后触达",
    STAGE_FINISHED: "流程结束",
}

STAGE_COMPAT_AUDIENCE = {
    STAGE_ORDER_REVIEW: AUDIENCE_PENDING_QUESTIONNAIRE,
    STAGE_QUESTIONNAIRE_REVIEW: AUDIENCE_PENDING_QUESTIONNAIRE,
    STAGE_OPERATING: AUDIENCE_OPERATING,
    STAGE_CONVERTED: AUDIENCE_CONVERTED,
}

STAGE_COMPAT_ENTRY_REASON = {
    STAGE_ORDER_REVIEW: ENTRY_REASON_ORDER_REVIEW_PENDING,
    STAGE_QUESTIONNAIRE_REVIEW: ENTRY_REASON_QUESTIONNAIRE_REVIEW_PENDING,
}

RECIPIENT_FILTER_BASIS_NONE = "none"
RECIPIENT_FILTER_BASIS_BEHAVIOR = "behavior"

SEGMENTATION_BASIS_NONE = "none"
SEGMENTATION_BASIS_PROFILE = "profile"
SEGMENTATION_BASIS_BEHAVIOR = "behavior"

GENERATION_MODE_MANUAL_LAYERED = "manual_layered"
GENERATION_MODE_AUTO_LAYERED_REWRITE = "auto_layered_rewrite"
GENERATION_MODE_PERSONALIZED_SINGLE = "personalized_single"

NODE_TRIGGER_MODE_SCHEDULED = "scheduled"
NODE_TRIGGER_MODE_DAILY_RECURRING = "daily_recurring"
NODE_TRIGGER_MODE_AUDIENCE_ENTERED = "audience_entered"

AGENT_BINDING_SCOPE_DEFAULT = "default"
AGENT_BINDING_SCOPE_PROFILE_CATEGORY = "profile_category"
AGENT_BINDING_SCOPE_BEHAVIOR_TIER = "behavior_tier"
AGENT_BINDING_SCOPE_PERSONALIZED = "personalized"

NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY = "profile_category"
NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER = "behavior_tier"
NODE_CONTENT_VARIANT_SCOPE_PERSONALIZED = "personalized"

WORKFLOW_STATUS_DRAFT = "draft"
WORKFLOW_STATUS_ACTIVE = "active"
WORKFLOW_STATUS_PAUSED = "paused"
WORKFLOW_STATUS_ARCHIVED = "archived"

BEHAVIOR_TIER_DEFINITIONS = (
    {
        "tier_code": "lt_2",
        "label": "消息少于 2",
        "description": "按消息数据源统计的用户消息条数小于 2。",
        "min_value": None,
        "max_value": 1,
    },
    {
        "tier_code": "between_2_9",
        "label": "消息 2 ~ 9",
        "description": "按消息数据源统计的用户消息条数在 2 到 9 之间。",
        "min_value": 2,
        "max_value": 9,
    },
    {
        "tier_code": "gte_10",
        "label": "消息大于等于 10",
        "description": "按消息数据源统计的用户消息条数大于等于 10。",
        "min_value": 10,
        "max_value": None,
    },
)


def _copy_items(items: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [dict(item) for item in items]


def list_supported_conversion_audiences() -> list[dict[str, str]]:
    return [
        {
            "audience_code": AUDIENCE_PENDING_QUESTIONNAIRE,
            "label": "未填问卷人群",
            "description": "尚未完成问卷采集，所有第 N 天都按进入该人群时间计算。",
        },
        {
            "audience_code": AUDIENCE_OPERATING,
            "label": "运营中人群",
            "description": "已进入自动化运营的主执行人群。",
        },
        {
            "audience_code": AUDIENCE_CONVERTED,
            "label": "已转化人群",
            "description": "已确认转化，用于转化后触达或留痕。",
        },
    ]


def list_supported_segmentation_bases() -> list[dict[str, str]]:
    return [
        {
            "basis_code": SEGMENTATION_BASIS_NONE,
            "label": "不分层",
            "description": "节点只使用标准版原文。",
        },
        {
            "basis_code": SEGMENTATION_BASIS_PROFILE,
            "label": "按基础画像分层",
            "description": "基于问卷选项映射模板命中画像类别。",
        },
        {
            "basis_code": SEGMENTATION_BASIS_BEHAVIOR,
            "label": "按消息条数分层",
            "description": "使用系统固定消息条数层级：消息少于 2、消息 2 ~ 9、消息大于等于 10。",
        },
    ]


def list_supported_recipient_filter_bases() -> list[dict[str, str]]:
    return [
        {
            "basis_code": RECIPIENT_FILTER_BASIS_NONE,
            "label": "不分层",
            "description": "不额外筛选收件人，命中目标人群即可发送。",
        },
        {
            "basis_code": RECIPIENT_FILTER_BASIS_BEHAVIOR,
            "label": "按行为层级发",
            "description": "仅给命中所选行为层级的成员发送。",
        },
    ]


def list_supported_generation_modes() -> list[dict[str, str]]:
    return [
        {
            "mode_code": GENERATION_MODE_MANUAL_LAYERED,
            "label": "手动分层录入",
            "description": "不同分层直接录入不同内容，不依赖 Agent。",
        },
        {
            "mode_code": GENERATION_MODE_AUTO_LAYERED_REWRITE,
            "label": "标准版自动分层改写",
            "description": "以标准版内容为底稿，按分层类别直接绑定对应 Agent 改写。",
        },
        {
            "mode_code": GENERATION_MODE_PERSONALIZED_SINGLE,
            "label": "单人定制化生成",
            "description": "每个任务流只绑定 1 个 Agent 进行单人定制生成。",
        },
    ]


def list_supported_node_trigger_modes() -> list[dict[str, str]]:
    return [
        {
            "trigger_mode": NODE_TRIGGER_MODE_SCHEDULED,
            "label": "按时间点运行",
            "description": "按第 N 天和具体时间执行。",
        },
        {
            "trigger_mode": NODE_TRIGGER_MODE_DAILY_RECURRING,
            "label": "每日轮巡运行",
            "description": "仅在进入目标人群后的第 N 天指定时间，对当前仍在目标人群内的成员执行。",
        },
        {
            "trigger_mode": NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
            "label": "进入人群后立即运行",
            "description": "成员进入目标人群后，runner 下一轮立即执行一次。",
        },
    ]


def list_supported_agent_binding_scopes() -> list[dict[str, str]]:
    return [
        {"binding_scope": AGENT_BINDING_SCOPE_DEFAULT, "label": "默认绑定", "description": "标准内容或默认兜底使用。"},
        {
            "binding_scope": AGENT_BINDING_SCOPE_PROFILE_CATEGORY,
            "label": "画像分类绑定",
            "description": "按基础画像分类命中到对应 Agent。",
        },
        {
            "binding_scope": AGENT_BINDING_SCOPE_BEHAVIOR_TIER,
            "label": "行为层级绑定",
            "description": "按固定行为层级命中到对应 Agent。",
        },
        {
            "binding_scope": AGENT_BINDING_SCOPE_PERSONALIZED,
            "label": "单人定制绑定",
            "description": "任务流只绑定 1 个用于单人生成的 Agent。",
        },
    ]


def list_supported_node_content_variant_scopes() -> list[dict[str, str]]:
    return [
        {
            "variant_scope": NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY,
            "label": "画像分类内容",
            "description": "手动分层录入时，针对画像分类保存的变体内容。",
        },
        {
            "variant_scope": NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER,
            "label": "行为层级内容",
            "description": "手动分层录入时，针对行为层级保存的变体内容。",
        },
        {
            "variant_scope": NODE_CONTENT_VARIANT_SCOPE_PERSONALIZED,
            "label": "个性化内容",
            "description": "预留给单人定制化内容快照。",
        },
    ]


def list_supported_workflow_statuses() -> list[dict[str, str]]:
    return [
        {"status_code": WORKFLOW_STATUS_DRAFT, "label": "草稿", "description": "已保存但未启用。"},
        {"status_code": WORKFLOW_STATUS_ACTIVE, "label": "启用", "description": "后续可参与调度执行。"},
        {"status_code": WORKFLOW_STATUS_PAUSED, "label": "停用", "description": "保留配置但暂停执行。"},
    ]


def list_supported_behavior_tiers() -> list[dict[str, Any]]:
    return _copy_items(BEHAVIOR_TIER_DEFINITIONS)
