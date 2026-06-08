from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, text

from aicrm_next.automation_engine.operation_task_contract import (
    BEHAVIOR_FILTERS,
    CONTENT_MODES,
    TASK_STATUSES,
    TRIGGER_TYPES,
    agent_runtime_diagnostics,
    has_send_body,
    publishable_diagnostics,
    validate_publishable_task,
)
from aicrm_next.shared.db_session import get_engine
from aicrm_next.shared.runtime import production_data_ready, raw_database_url


class AutomationProgramDataUnavailable(RuntimeError):
    pass


SETUP_STEPS: tuple[dict[str, str], ...] = (
    {"key": "basic", "label": "基础信息"},
    {"key": "entry", "label": "入口渠道"},
    {"key": "segmentation", "label": "分层规则"},
    {"key": "entry-rule", "label": "入池规则"},
    {"key": "operations", "label": "运营编排"},
    {"key": "publish", "label": "检查并发布"},
)

SETUP_STEP_KEYS = {item["key"] for item in SETUP_STEPS}
BLOCK_BASIC = "basic"
BLOCK_ENTRY_CHANNEL = "entry_channel"
BLOCK_SEGMENTATION = "questionnaire_segmentation"
BLOCK_AUDIENCE_ENTRY_RULE = "audience_entry_rule"
BLOCK_PUBLISH_STATE = "publish_state"
AUDIENCE_LABELS = {
    "pending_questionnaire": "待填问卷",
    "operating": "运营中",
    "converted": "已转化",
}
ENTRY_CONDITION_LABELS = {
    "any_entry_channel": "任一当前方案入口",
    "specific_entry_channel": "指定入口渠道",
}
QUESTIONNAIRE_CONDITION_LABELS = {
    "questionnaire_id_matched": "当前方案问卷提交",
    "any_questionnaire_submitted": "任一问卷提交",
}
DEFAULT_AUDIENCE_ENTRY_RULES = (
    {
        "event": "channel_enter",
        "condition_type": "any_entry_channel",
        "target_audience_code": "pending_questionnaire",
        "enabled": True,
    },
    {
        "event": "questionnaire_submitted",
        "condition_type": "questionnaire_id_matched",
        "target_audience_code": "operating",
        "enabled": True,
    },
)
AUDIENCE_REVIEW_STEP_KEYS = {"order_product", "questionnaire", "conversion_product"}
AUDIENCE_STAGE_LABELS = {
    "pending_questionnaire": "待填问卷",
    "questionnaire_review": "问卷审核",
    "order_review": "订单审核",
    "operating": "运营中",
    "conversion_review": "成交审核",
    "converted": "已转化",
    "exited": "已退出",
    "finished": "已结束",
    "unknown": "未识别阶段",
}
BEHAVIOR_TIER_LABELS = {
    "lt_2": "少于 2 次互动",
    "between_2_9": "2-9 次互动",
    "gte_10": "10 次及以上互动",
    "unknown": "未识别行为分层",
}


_FIXTURE_PROGRAM = {
    "id": 1,
    "program_name": "自动化运营方案",
    "program_code": "next_local_preview",
    "description": "本地结构校验方案；生产环境读取 PostgreSQL。",
    "status": "active",
    "updated_at": "2026-05-20T12:00:00Z",
    "config_json": {},
}
_FIXTURE_OPERATION_GROUPS: list[dict[str, Any]] = []
_FIXTURE_OPERATION_TASKS: list[dict[str, Any]] = []
_FIXTURE_SEGMENTATION_BY_PROGRAM: dict[int, dict[str, Any]] = {}
_FIXTURE_OPERATION_GROUP_ID = 1000
_FIXTURE_OPERATION_TASK_ID = 5000


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    if value is None:
        return deepcopy(default)
    text_value = str(value or "").strip()
    if not text_value:
        return deepcopy(default)
    try:
        return json.loads(text_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return deepcopy(default)


def _json_text(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _stringify_datetime(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _sqlalchemy_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _program_summary(program: dict[str, Any], summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = dict(summary or {})
    publish_state = _effective_publish_state(program, summary)
    full_published = bool(publish_state.get("full_published"))
    entry_published = bool(publish_state.get("entry_published"))
    publish_status = "full" if full_published else "entry" if entry_published else "unpublished"
    publish_label = "完整自动化已发布" if full_published else "入口已发布" if entry_published else "未发布"
    return {
        "member_count": int(summary.get("member_count") or 0),
        "channel_count": int(summary.get("channel_count") or 0),
        "workflow_count": int(summary.get("workflow_count") or 0),
        "latest_execution_at": _clean_text(summary.get("latest_execution_at")),
        "publish_state": publish_state,
        "publish_status": publish_status,
        "publish_status_label": publish_label,
    }


def _effective_publish_state(program: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    publish_state = dict(summary.get("publish_state") or {})
    if "entry_published" in publish_state or "full_published" in publish_state:
        return publish_state
    if _clean_text(program.get("status")) != "active":
        return publish_state
    entry_ready = bool(summary.get("entry_publish_ready"))
    full_ready = bool(summary.get("full_publish_ready"))
    if not entry_ready and int(summary.get("channel_count") or 0) > 0:
        entry_ready = True
    if full_ready:
        return {"entry_published": True, "full_published": True, "source": "derived_from_next_read_model"}
    if entry_ready:
        return {"entry_published": True, "full_published": False, "source": "derived_from_next_read_model"}
    return publish_state


def _fixture_summary() -> dict[str, Any]:
    return _program_summary(
        _FIXTURE_PROGRAM,
        {
            "channel_count": 1,
            "workflow_count": 0,
            "latest_execution_at": "",
            "publish_state": {},
        },
    )


def _fixture_setup_payload(program_id: int, *, step: str = "basic") -> dict[str, Any]:
    normalized_step = step if step in SETUP_STEP_KEYS else "basic"
    program = deepcopy(_FIXTURE_PROGRAM)
    program["id"] = int(program_id)
    return {
        "program": program,
        "summary": _fixture_summary(),
        "step": normalized_step,
        "steps": list(SETUP_STEPS),
        "is_default_program": True,
        "legacy_fallback_used": False,
        "blocks": {},
        "basic": dict(program.get("config_json") or {}),
        "entry_channel": {},
        "entry": {
            "channels": [
                {
                    "id": 1,
                    "binding_id": 101,
                    "channel_name": "默认渠道二维码",
                    "channel_code": "next_local_qrcode",
                    "channel_type": "qrcode",
                    "carrier_type": "qrcode",
                    "status": "active",
                    "qr_url": "",
                    "scene_value": "next_local_preview",
                    "auto_accept_friend": False,
                    "welcome_message": "",
                    "initial_audience_code": "pending_questionnaire",
                    "binding_status": "active",
                }
            ],
            "candidate_channels": [],
            "api_urls": _entry_channel_api_urls(int(program_id)),
            "qrcode_channel": {
                "id": 1,
                "binding_id": 101,
                "channel_name": "默认渠道二维码",
                "channel_code": "next_local_qrcode",
                "channel_type": "qrcode",
                "carrier_type": "qrcode",
                "status": "active",
                "qr_url": "",
                "scene_value": "next_local_preview",
                "auto_accept_friend": False,
                "welcome_message": "",
                "initial_audience_code": "pending_questionnaire",
                "binding_status": "active",
            },
            "customer_acquisition_links": [],
        },
        "segmentation": _segmentation_view_model(
            _FIXTURE_SEGMENTATION_BY_PROGRAM.get(
                int(program_id),
                {
                    "questionnaire_id": None,
                    "default_strategy": "normal_question_rules",
                    "strategies": {},
                },
            ),
            program_id=int(program_id),
        ),
        "audience_entry_rule": _audience_rule_view_model({}, program_id=int(program_id)),
        "operations": {"tasks": [], **_operation_profile_context_from_segmentation(_FIXTURE_SEGMENTATION_BY_PROGRAM.get(int(program_id), {}))},
        "publish_state": {},
        "publish_check": _publish_check_from_parts(
            program,
            has_config=True,
            has_entry=True,
            segmentation={},
            audience_rules=list(DEFAULT_AUDIENCE_ENTRY_RULES),
            active_task_count=0,
            operation_task_contract=_operation_task_runtime_contract([]),
        ),
    }


def _fixture_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "route_owner": "ai_crm_next",
        "items": [{"program": deepcopy(_FIXTURE_PROGRAM), "summary": _fixture_summary()}],
        "default_program": {"id": _FIXTURE_PROGRAM["id"], "program_name": _FIXTURE_PROGRAM["program_name"]},
        "total": 1,
        "source_status": "next_local_preview",
    }


def _payload_from_block(blocks: dict[str, dict[str, Any]], block_key: str) -> dict[str, Any]:
    payload = dict((blocks.get(block_key) or {}).get("payload") or {})
    return deepcopy(payload)


def _normalize_option_category_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    raw_option_ids = item.get("option_ids") or []
    if isinstance(raw_option_ids, str):
        raw_option_ids = [value.strip() for value in raw_option_ids.split(",")]
    option_ids: list[int] = []
    for value in list(raw_option_ids or []):
        try:
            option_id = int(value)
        except (TypeError, ValueError):
            continue
        if option_id:
            option_ids.append(option_id)
    snapshots_by_id = {
        int(snapshot.get("id") or 0): dict(snapshot)
        for snapshot in list(item.get("option_snapshots") or [])
        if int(snapshot.get("id") or 0)
    }
    option_snapshots = []
    for option_id in option_ids:
        option = snapshots_by_id.get(option_id) or {}
        option_snapshots.append(
            {
                "id": option_id,
                "option_text": _clean_text(option.get("option_text")) or f"选项 {option_id}",
            }
        )
    return {
        "category_key": _clean_text(item.get("category_key")) or f"category_{index + 1}",
        "category_name": _clean_text(item.get("category_name")) or f"分类 {index + 1}",
        "description": _clean_text(item.get("description")),
        "option_ids": option_ids,
        "option_snapshots": option_snapshots,
    }


def _normalize_normal_rule_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    hit_option_ids = item.get("hit_option_ids_json")
    if hit_option_ids is None:
        hit_option_ids = item.get("hit_option_ids") or []
    return {
        "questionnaire_id": int(item.get("questionnaire_id") or 0) or None,
        "questionnaire_question_id": int(item.get("questionnaire_question_id") or item.get("question_id") or 0) or None,
        "question_title": _clean_text(item.get("question_title")),
        "question_type": _clean_text(item.get("question_type")) or "single_choice",
        "hit_option_ids_json": [int(value) for value in list(hit_option_ids or []) if str(value).strip().isdigit()],
        "hit_options": list(item.get("hit_options") or []),
        "segment_key": _clean_text(item.get("segment_key")) or _clean_text(item.get("hit_segment_key")) or "core",
        "segment_name": _clean_text(item.get("segment_name")) or _clean_text(item.get("hit_segment_name")) or "重点",
        "rule_note": _clean_text(item.get("rule_note") or item.get("description")),
        "sort_order": int(item.get("sort_order") or index + 1),
    }


def _normalize_score_range_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    return {
        "min_score": item.get("min_score"),
        "max_score": item.get("max_score"),
        "segment_key": _clean_text(item.get("segment_key")) or f"score_segment_{index + 1}",
        "segment_name": _clean_text(item.get("segment_name")) or f"分层 {index + 1}",
        "diagnosis_text": _clean_text(item.get("diagnosis_text")),
        "recommended_action": _clean_text(item.get("recommended_action")),
    }


def _normalize_segmentation_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    profile = dict(strategies.get("profile_dimension") or {})
    questionnaire_id = int(payload.get("questionnaire_id") or 0) or None
    category_rows = payload.get("normal_question_categories")
    if category_rows is None:
        category_rows = normal.get("categories") or []
    normal_rows = payload.get("normal_question_rules_rows")
    if normal_rows is None:
        normal_rows = normal.get("rules") or []
    score_rows = payload.get("score_segment_rows")
    if score_rows is None:
        score_rows = score.get("ranges") or []
    segmentation_question_id = int(payload.get("segmentation_question_id") or normal.get("segmentation_question_id") or 0) or None
    return {
        "questionnaire_id": questionnaire_id,
        "default_strategy": _clean_text(payload.get("default_strategy")) or "normal_question_rules",
        "strategies": {
            "normal_question_rules": {
                "enabled": bool(normal.get("enabled", payload.get("default_strategy") != "manual")),
                "mode": _clean_text(payload.get("normal_question_mode") or normal.get("mode")) or "single_question_option_category",
                "segmentation_question_id": segmentation_question_id,
                "segmentation_question_title": _clean_text(normal.get("segmentation_question_title")),
                "categories": [
                    _normalize_option_category_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(category_rows or []))
                ],
                "core_threshold": int(normal.get("core_threshold") or payload.get("core_threshold") or 2),
                "rules": [
                    _normalize_normal_rule_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(normal_rows or []))
                ],
            },
            "score_segments": {
                "enabled": bool(score.get("enabled", False)),
                "ranges": [
                    _normalize_score_range_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(score_rows or []))
                ],
            },
            "profile_dimension": {
                "enabled": bool(profile.get("enabled", False)),
                "template_id": int(profile.get("template_id") or payload.get("profile_template_id") or 0) or None,
                "usage": _clean_text(profile.get("usage")) or "content_variable_only",
            },
        },
        "priority": list(payload.get("priority") or ["normal_question_rules", "score_segments"]),
    }


def _segmentation_view_model(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    del program_id
    normalized = _normalize_segmentation_payload(payload)
    normal = dict((normalized.get("strategies") or {}).get("normal_question_rules") or {})
    return {
        **normalized,
        "available_questionnaires": [],
        "selected_questionnaire": {},
        "question_rows": [],
        "selected_segmentation_question": {},
        "normal_question_rules": {
            "mode": _clean_text(normal.get("mode")) or "single_question_option_category",
            "core_threshold": int(normal.get("core_threshold") or 2),
            "segmentation_question_id": normal.get("segmentation_question_id"),
            "segmentation_question_title": _clean_text(normal.get("segmentation_question_title")),
            "selected_question": {},
            "category_rows": list(normal.get("categories") or []),
            "unassigned_options": [],
            "legacy_rows": list(normal.get("rules") or []),
            "rows": list(normal.get("rules") or []),
        },
        "score_segments": {
            "enabled": bool(((normalized.get("strategies") or {}).get("score_segments") or {}).get("enabled")),
            "rows": list(((normalized.get("strategies") or {}).get("score_segments") or {}).get("ranges") or []),
        },
        "profile_dimension": {
            **dict(((normalized.get("strategies") or {}).get("profile_dimension") or {})),
            "available_templates": [],
        },
    }


def _operation_profile_context_from_segmentation(payload: dict[str, Any] | None, *, template_id: int | None = None) -> dict[str, Any]:
    normalized = _normalize_segmentation_payload(payload or {})
    normal = dict((normalized.get("strategies") or {}).get("normal_question_rules") or {})
    categories = list(normal.get("categories") or [])
    segments = [
        {
            "segment_key": _clean_text(category.get("category_key")) or f"category_{index}",
            "segment_name": _clean_text(category.get("category_name")) or f"分类 {index}",
            "category_key": _clean_text(category.get("category_key")) or f"category_{index}",
            "category_name": _clean_text(category.get("category_name")) or f"分类 {index}",
            "description": _clean_text(category.get("description")),
            "option_ids": list(category.get("option_ids") or []),
            "option_snapshots": list(category.get("option_snapshots") or []),
            "source": "setup_segmentation",
        }
        for index, category in enumerate(categories, start=1)
    ]
    template_name = _clean_text(normal.get("segmentation_question_title")) or "当前方案分层规则"
    templates = []
    if segments:
        templates.append(
            {
                "id": int(template_id or 0),
                "template_id": int(template_id or 0),
                "template_code": "setup_segmentation",
                "template_name": f"{template_name} · 当前方案分层",
                "label": f"{template_name} · 当前方案分层",
                "source": "setup_segmentation",
                "enabled": True,
            }
        )
    return {"profile_templates": templates, "profile_segments": segments}


def _selected_product_snapshot(selected_product_id: Any, provided: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = dict(provided or {})
    product_id = _clean_text(selected_product_id)
    return {
        "id": product_id,
        "name": _clean_text(snapshot.get("name")) or _clean_text(snapshot.get("product_name")) or product_id,
        "price_text": _clean_text(snapshot.get("price_text")) or _clean_text(snapshot.get("amount_text")),
    }


def _selected_questionnaire_snapshot(
    selected_questionnaire_id: Any,
    *,
    available: list[dict[str, Any]] | None = None,
    provided: dict[str, Any] | None = None,
) -> dict[str, Any]:
    questionnaire_id = int(selected_questionnaire_id or 0)
    snapshot = dict(provided or {})
    matched = next((dict(item) for item in list(available or []) if int(item.get("id") or 0) == questionnaire_id), {})
    return {
        "id": questionnaire_id,
        "title": _clean_text(matched.get("title")) or _clean_text(snapshot.get("title")) or (f"问卷 {questionnaire_id}" if questionnaire_id else ""),
        "status": _clean_text(matched.get("status")) or _clean_text(snapshot.get("status")),
        "question_count": int(matched.get("question_count") or snapshot.get("question_count") or 0),
    }


def _normalize_audience_review_item(
    item: dict[str, Any],
    *,
    enabled_default: bool,
    product: bool = False,
    questionnaire: bool = False,
    available_questionnaires: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    enabled = bool(item.get("enabled", enabled_default))
    result: dict[str, Any] = {"enabled": enabled}
    if product:
        selected_product_id = _clean_text(item.get("selected_product_id") or item.get("product_id"))
        result["selected_product_id"] = selected_product_id or None
        result["selected_product_snapshot"] = _selected_product_snapshot(
            selected_product_id,
            item.get("selected_product_snapshot") if isinstance(item.get("selected_product_snapshot"), dict) else {},
        )
    if questionnaire:
        selected_questionnaire_id = int(item.get("selected_questionnaire_id") or item.get("questionnaire_id") or 0) or None
        result["selected_questionnaire_id"] = selected_questionnaire_id
        result["selected_questionnaire_snapshot"] = _selected_questionnaire_snapshot(
            selected_questionnaire_id,
            available=available_questionnaires,
            provided=item.get("selected_questionnaire_snapshot") if isinstance(item.get("selected_questionnaire_snapshot"), dict) else {},
        )
    return result


def _normalize_audience_entry_rule_payload(
    payload: dict[str, Any] | None,
    *,
    validate: bool = True,
    available_questionnaires: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(payload or {})
    has_review_config = any(
        key in payload
        for key in ("entry_source", "order_review", "questionnaire_review", "operating", "conversion_review")
    )
    if not has_review_config and (payload.get("cards") or payload.get("rules")):
        rules = list(payload.get("rules") or [])
        cards = dict(payload.get("cards") or {})
        if cards:
            submit_card = dict(cards.get("questionnaire_submitted") or {})
            questionnaire_enabled = bool(submit_card.get("enabled", True))
        else:
            by_event = {str(item.get("event") or ""): dict(item or {}) for item in rules}
            submit_rule = by_event.get("questionnaire_submitted") or dict(DEFAULT_AUDIENCE_ENTRY_RULES[1])
            questionnaire_enabled = bool(submit_rule.get("enabled", True))
        normalized = {
            "entry_source": "both",
            "order_review": _normalize_audience_review_item({}, enabled_default=False, product=True),
            "questionnaire_review": _normalize_audience_review_item(
                {
                    "enabled": questionnaire_enabled,
                    "selected_questionnaire_id": payload.get("selected_questionnaire_id"),
                    "selected_questionnaire_snapshot": payload.get("selected_questionnaire_snapshot"),
                },
                enabled_default=questionnaire_enabled,
                questionnaire=True,
                available_questionnaires=available_questionnaires,
            ),
            "operating": {"enabled": True, "fixed": True},
            "conversion_review": _normalize_audience_review_item({}, enabled_default=False, product=True),
        }
    else:
        normalized = {
            "entry_source": _clean_text(payload.get("entry_source")) or "both",
            "order_review": _normalize_audience_review_item(dict(payload.get("order_review") or {}), enabled_default=False, product=True),
            "questionnaire_review": _normalize_audience_review_item(
                dict(payload.get("questionnaire_review") or {}),
                enabled_default=False,
                questionnaire=True,
                available_questionnaires=available_questionnaires,
            ),
            "operating": {"enabled": True, "fixed": True},
            "conversion_review": _normalize_audience_review_item(
                dict(payload.get("conversion_review") or {}),
                enabled_default=False,
                product=True,
            ),
        }
    normalized["rules"] = _legacy_rules_from_entry_rule(normalized)
    if validate:
        order_review = dict(normalized.get("order_review") or {})
        questionnaire_review = dict(normalized.get("questionnaire_review") or {})
        conversion_review = dict(normalized.get("conversion_review") or {})
        if order_review.get("enabled") and not _clean_text(order_review.get("selected_product_id")):
            raise ValueError("订单审核已启用，请先选择商品")
        if questionnaire_review.get("enabled") and not int(questionnaire_review.get("selected_questionnaire_id") or 0):
            raise ValueError("问卷审核已启用，请先选择问卷")
        if conversion_review.get("enabled") and not _clean_text(conversion_review.get("selected_product_id")):
            raise ValueError("已转化判定已启用，请先选择成交商品")
    return normalized


def _legacy_rules_from_entry_rule(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    rules = list((payload or {}).get("rules") or [])
    if rules:
        return rules
    payload = dict(payload or {})
    order_enabled = bool((payload.get("order_review") or {}).get("enabled"))
    questionnaire_enabled = bool((payload.get("questionnaire_review") or {}).get("enabled"))
    return [
        {
            "event": "channel_enter",
            "condition_type": "any_entry_channel",
            "target_audience_code": "pending_questionnaire" if order_enabled or questionnaire_enabled else "operating",
            "enabled": True,
        },
        {
            "event": "questionnaire_submitted",
            "condition_type": "questionnaire_id_matched",
            "target_audience_code": "operating",
            "enabled": questionnaire_enabled,
        },
    ]


def _audience_next_steps(payload: dict[str, Any]) -> dict[str, str]:
    order_enabled = bool((payload.get("order_review") or {}).get("enabled"))
    questionnaire_enabled = bool((payload.get("questionnaire_review") or {}).get("enabled"))
    conversion_enabled = bool((payload.get("conversion_review") or {}).get("enabled"))
    return {
        "scan_enter": "订单审核" if order_enabled else ("问卷审核" if questionnaire_enabled else "运营中"),
        "order_review": ("问卷审核" if questionnaire_enabled else "运营中") if order_enabled else "本项已跳过",
        "questionnaire_review": "运营中" if questionnaire_enabled else "本项已跳过",
        "operating": "已转化" if conversion_enabled else "结束",
        "conversion_review": "结束" if conversion_enabled else "本项已关闭",
    }


def _audience_rule_view_model(
    payload: dict[str, Any] | None,
    *,
    program_id: int,
    available_questionnaires: list[dict[str, Any]] | None = None,
    available_products: list[dict[str, Any]] | None = None,
    picker: str = "",
) -> dict[str, Any]:
    del program_id
    normalized = _normalize_audience_entry_rule_payload(
        payload,
        validate=False,
        available_questionnaires=available_questionnaires,
    )
    picker_key = _clean_text(picker)
    if picker_key not in AUDIENCE_REVIEW_STEP_KEYS:
        picker_key = ""
    return {
        **normalized,
        "rules": _legacy_rules_from_entry_rule(normalized),
        "next_steps": _audience_next_steps(normalized),
        "available_products": list(available_products or []),
        "available_questionnaires": list(available_questionnaires or []),
        "picker": picker_key,
        "picker_title": {
            "order_product": "选择订单审核商品",
            "questionnaire": "选择问卷审核问卷",
            "conversion_product": "选择成交判定商品",
        }.get(picker_key, ""),
        "manual_cards": [
            {"event_label": "人工移除", "target_label": "退出当前方案"},
            {"event_label": "成交标记", "target_label": "已转化"},
            {"event_label": "取消成交", "target_label": "运营中"},
        ],
    }


def _has_segmentation(segmentation: dict[str, Any]) -> bool:
    normalized = _normalize_segmentation_payload(segmentation)
    strategies = dict(normalized.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    return bool(normal.get("categories") or normal.get("rules") or score.get("ranges"))


def _validate_option_categories(payload: dict[str, Any]) -> None:
    normal = dict((payload.get("strategies") or {}).get("normal_question_rules") or {})
    seen: set[int] = set()
    for category in list(normal.get("categories") or []):
        for option_id in list((category or {}).get("option_ids") or []):
            normalized_id = int(option_id or 0)
            if not normalized_id:
                continue
            if normalized_id in seen:
                raise ValueError("同一个选项不能同时属于多个分类")
            seen.add(normalized_id)


def _validate_score_ranges(payload: dict[str, Any]) -> None:
    score = dict((payload.get("strategies") or {}).get("score_segments") or {})
    ranges = []
    for row in list(score.get("ranges") or []):
        if row.get("min_score") in (None, "") and row.get("max_score") in (None, ""):
            continue
        try:
            min_score = float(row.get("min_score"))
            max_score = float(row.get("max_score"))
        except (TypeError, ValueError) as exc:
            raise ValueError("总分分层的最低分和最高分必须填写数字") from exc
        if max_score < min_score:
            raise ValueError("总分分层的最高分必须大于等于最低分")
        ranges.append((min_score, max_score))
    ranges.sort(key=lambda item: (item[0], item[1]))
    for previous, current in zip(ranges, ranges[1:], strict=False):
        if current[0] <= previous[1]:
            raise ValueError("总分分层区间不能重叠")


def _publish_item(label: str, passed: bool, message: str, fix_step: str) -> dict[str, Any]:
    return {
        "label": label,
        "passed": bool(passed),
        "severity": "pass" if passed else "fail",
        "message": "已完成" if passed else message,
        "fix_step": fix_step,
        "fix_url": f"?step={fix_step}",
    }


def _agent_code_from_task(task: dict[str, Any]) -> str:
    return _clean_text((dict(task.get("agent_config_json") or {})).get("agent_code"))


def _agent_context_sources_from_published(row: dict[str, Any]) -> list[str]:
    prompt_text = "\n".join(
        item
        for item in [
            _clean_text(row.get("published_role_prompt")),
            _clean_text(row.get("published_task_prompt")),
        ]
        if item
    )
    sources: list[str] = []
    if "questionnaire" in prompt_text.lower() or "问卷" in prompt_text:
        sources.append("questionnaire")
    variables = row.get("published_variables_json")
    if isinstance(variables, str):
        try:
            variables = json.loads(variables)
        except json.JSONDecodeError:
            variables = []
    for item in list(variables or []):
        if not isinstance(item, dict):
            continue
        candidates = [
            _clean_text(item.get("source")).lower(),
            _clean_text(item.get("variable_key")).lower(),
            _clean_text(item.get("field_key")).lower(),
            _clean_text(item.get("display_name")).lower(),
            _clean_text(item.get("description")).lower(),
        ]
        if any("questionnaire" in candidate or "问卷" in candidate for candidate in candidates):
            if "questionnaire" not in sources:
                sources.append("questionnaire")
    return sources


def _agent_task_runtime_context(task: dict[str, Any], *, require_questionnaire_context: bool | None = None) -> dict[str, Any] | None:
    if _clean_text(task.get("content_mode")) != "agent":
        return None
    context: dict[str, Any] = {
        "agent_published_prompt_present": False,
        "agent_published_role_prompt_present": False,
        "agent_published_task_prompt_present": False,
        "enabled_context_sources": [],
        "questionnaire_context_available": False,
        "questionnaire_submission_id": 0,
        "questionnaire_answer_count": 0,
    }
    agent_code = _agent_code_from_task(task)
    if production_data_ready() and raw_database_url() and agent_code:
        engine = get_engine(raw_database_url())
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT published_role_prompt, published_task_prompt, published_variables_json
                    FROM automation_agent_config
                    WHERE agent_code = :agent_code
                    LIMIT 1
                    """
                ),
                {"agent_code": agent_code},
            ).mappings().first()
        if row:
            row_dict = dict(row)
            role_prompt = _clean_text(row_dict.get("published_role_prompt"))
            task_prompt = _clean_text(row_dict.get("published_task_prompt"))
            context.update(
                {
                    "agent_published_prompt_present": bool(role_prompt or task_prompt),
                    "agent_published_role_prompt_present": bool(role_prompt),
                    "agent_published_task_prompt_present": bool(task_prompt),
                    "enabled_context_sources": _agent_context_sources_from_published(row_dict),
                }
            )
    if require_questionnaire_context is None:
        require_questionnaire_context = bool((dict(task.get("agent_config_json") or {})).get("questionnaire_context_required")) or (
            "questionnaire" in list(context.get("enabled_context_sources") or [])
        )
    context["questionnaire_context_required"] = bool(require_questionnaire_context)
    return context


def _operation_task_runtime_contract(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    active_tasks = [dict(item or {}) for item in list(tasks or []) if _clean_text(item.get("status")) == "active"]
    diagnostics: list[dict[str, Any]] = []
    executable_ok = True
    trigger_ok = True
    target_ok = True
    schedule_ok = True
    previewable_ok = True

    for task in active_tasks:
        task_id = int(task.get("id") or 0)
        trigger_type = _clean_text(task.get("trigger_type"))
        target_stage_code = _clean_text(task.get("target_stage_code") or task.get("target_audience_code"))
        target_audience_code = _clean_text(task.get("target_audience_code"))
        send_time = _clean_text(task.get("send_time"))
        agent_context = _agent_task_runtime_context(task, require_questionnaire_context=False)
        content = publishable_diagnostics(task, agent_runtime_context=agent_context)
        task_trigger_ok = trigger_type in TRIGGER_TYPES
        task_target_ok = bool(target_stage_code or target_audience_code)
        task_schedule_ok = trigger_type != "scheduled_daily" or bool(send_time)
        task_previewable_ok = task_target_ok and bool(target_audience_code or target_stage_code)
        executable_ok = executable_ok and bool(content.get("ok"))
        trigger_ok = trigger_ok and task_trigger_ok
        target_ok = target_ok and task_target_ok
        schedule_ok = schedule_ok and task_schedule_ok
        previewable_ok = previewable_ok and task_previewable_ok
        diagnostics.append(
            {
                "task_id": task_id,
                "task_name": _clean_text(task.get("task_name")) or f"任务 {task_id}",
                "trigger_type": trigger_type,
                "target_stage_code": target_stage_code,
                "target_audience_code": target_audience_code,
                "send_time": send_time,
                "executable_content": content,
                "trigger_configured": task_trigger_ok,
                "target_configured": task_target_ok,
                "schedule_covered": task_schedule_ok,
                "previewable": task_previewable_ok,
            }
        )

    return {
        "active_count": len(active_tasks),
        "executable_ok": bool(active_tasks) and executable_ok,
        "trigger_ok": bool(active_tasks) and trigger_ok,
        "target_ok": bool(active_tasks) and target_ok,
        "schedule_ok": bool(active_tasks) and schedule_ok,
        "previewable_ok": bool(active_tasks) and previewable_ok,
        "diagnostics": diagnostics,
        "runtime_requirements": {
            "audience_transition_hook_required": any(
                item.get("trigger_type") == "audience_entered" for item in diagnostics
            ),
            "operation_task_due_runner_required": any(
                item.get("trigger_type") == "scheduled_daily" for item in diagnostics
            ),
            "broadcast_queue_worker_required": bool(active_tasks),
        },
    }


def _publish_check_from_parts(
    program: dict[str, Any],
    *,
    has_config: bool,
    has_entry: bool,
    segmentation: dict[str, Any],
    audience_rules: list[dict[str, Any]],
    active_task_count: int,
    operation_task_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    archived = _clean_text(program.get("status")) == "archived"
    is_default = _clean_text(program.get("program_code")) == "signup_conversion_v1"
    contract = dict(operation_task_contract or {})
    has_active_task = int(contract.get("active_count") if contract else active_task_count or 0) > 0
    executable_ok = bool(contract.get("executable_ok")) if contract else has_active_task
    trigger_ok = bool(contract.get("trigger_ok")) if contract else has_active_task
    target_ok = bool(contract.get("target_ok")) if contract else has_active_task
    schedule_ok = bool(contract.get("schedule_ok")) if contract else has_active_task
    previewable_ok = bool(contract.get("previewable_ok")) if contract else has_active_task
    entry_ok = bool(program) and not archived and (is_default or has_config) and has_entry
    full_ok = (
        entry_ok
        and bool(segmentation.get("questionnaire_id"))
        and _has_segmentation(segmentation)
        and bool(audience_rules)
        and has_active_task
        and executable_ok
        and trigger_ok
        and target_ok
        and schedule_ok
        and previewable_ok
    )
    return {
        "entry": {
            "passed": entry_ok,
            "severity": "pass" if entry_ok else "fail",
            "items": [
                _publish_item("方案可用", bool(program), "方案不存在或已被删除", "basic"),
                _publish_item("方案未归档", not archived, "归档方案不能发布入口", "basic"),
                _publish_item("当前方案未读取默认方案配置", is_default or has_config, "请先保存当前方案配置", "basic"),
                _publish_item("至少有一个当前方案入口", has_entry, "请先配置渠道二维码或获客助手入口", "entry"),
            ],
        },
        "full": {
            "passed": full_ok,
            "severity": "pass" if full_ok else ("warning" if entry_ok else "fail"),
            "items": [
                _publish_item("入口发布检查通过", entry_ok, "请先完成入口发布检查", "entry"),
                _publish_item("已绑定问卷", bool(segmentation.get("questionnaire_id")), "请选择当前方案使用的问卷", "segmentation"),
                _publish_item("已配置分层策略", _has_segmentation(segmentation), "请配置普通问卷规则或总分分层", "segmentation"),
                _publish_item("入池规则完整", bool(audience_rules), "请保存入池规则", "entry-rule"),
                _publish_item("存在启用中的运营任务", has_active_task, "请至少启用一个运营任务", "operations"),
                _publish_item("启用任务具备可执行内容", executable_ok, "请补齐启用任务的统一内容、分层内容或 Agent fallback/素材", "operations"),
                _publish_item("启用任务具备触发方式和目标阶段", trigger_ok and target_ok, "请补齐任务触发方式和目标阶段", "operations"),
                _publish_item("定时任务具备调度覆盖", schedule_ok, "请为定时任务配置发送时间，并确认 due runner 覆盖 operation_task", "operations"),
                _publish_item("任务人群预览可诊断", previewable_ok, "请配置目标阶段/人群后刷新命中人数", "operations"),
            ],
            "operation_task_contract": contract,
        },
    }


def _segment_row(key: str, label: str, count: int, *, kind: str) -> dict[str, Any]:
    normalized_key = _clean_text(key) or "unknown"
    return {
        "key": normalized_key,
        "label": _clean_text(label) or normalized_key,
        "count": int(count or 0),
        "kind": kind,
    }


def _program_member_stage_label(stage_key: str) -> str:
    normalized = _clean_text(stage_key) or "unknown"
    return AUDIENCE_STAGE_LABELS.get(normalized, normalized)


def _configured_profile_segment_labels(segmentation: dict[str, Any], profile_categories: list[dict[str, Any]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    strategies = dict(segmentation.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    for index, row in enumerate(list(normal.get("categories") or segmentation.get("normal_question_categories") or [])):
        item = dict(row or {})
        key = _clean_text(item.get("category_key")) or f"category_{index + 1}"
        labels[key] = _clean_text(item.get("category_name")) or key
    for row in list(segmentation.get("score_segment_rows") or []):
        item = dict(row or {})
        key = _clean_text(item.get("segment_key"))
        if key:
            labels[key] = _clean_text(item.get("segment_name")) or key
    for row in profile_categories:
        item = dict(row or {})
        key = _clean_text(item.get("category_key"))
        if key:
            labels[key] = _clean_text(item.get("category_name")) or key
    return labels


def _entry_channel_api_urls(program_id: int) -> dict[str, str]:
    return {
        "bindings": f"/api/admin/automation-conversion/programs/{int(program_id)}/channel-bindings",
        "binding_base": f"/api/admin/automation-conversion/programs/{int(program_id)}/channel-bindings/0",
    }


def _overview_payload_from_parts(
    *,
    program: dict[str, Any],
    summary: dict[str, Any],
    audience_counts: list[dict[str, Any]],
    stage_counts: list[dict[str, Any]],
    profile_counts: list[dict[str, Any]],
    behavior_counts: list[dict[str, Any]],
    segmentation: dict[str, Any],
    profile_categories: list[dict[str, Any]],
) -> dict[str, Any]:
    profile_labels = _configured_profile_segment_labels(segmentation, profile_categories)
    audience_rows = [
        _segment_row(
            _clean_text(item.get("key")),
            AUDIENCE_STAGE_LABELS.get(_clean_text(item.get("key")), _clean_text(item.get("key"))),
            int(item.get("total") or 0),
            kind="audience",
        )
        for item in audience_counts
    ]
    stage_rows = [
        _segment_row(
            _clean_text(item.get("key")),
            AUDIENCE_STAGE_LABELS.get(_clean_text(item.get("key")), _clean_text(item.get("key"))),
            int(item.get("total") or 0),
            kind="stage",
        )
        for item in stage_counts
    ]
    profile_rows = [
        _segment_row(
            _clean_text(item.get("key")) or "unknown",
            profile_labels.get(_clean_text(item.get("key")), "未识别画像分层" if not _clean_text(item.get("key")) else _clean_text(item.get("key"))),
            int(item.get("total") or 0),
            kind="profile",
        )
        for item in profile_counts
    ]
    behavior_rows = [
        _segment_row(
            _clean_text(item.get("key")) or "unknown",
            BEHAVIOR_TIER_LABELS.get(_clean_text(item.get("key")) or "unknown", _clean_text(item.get("key"))),
            int(item.get("total") or 0),
            kind="behavior",
        )
        for item in behavior_counts
    ]
    return {
        "program": program,
        "summary": summary,
        "audience_segments": audience_rows,
        "stage_segments": stage_rows,
        "profile_segments": profile_rows,
        "behavior_segments": behavior_rows,
        "profile_segment_template": {
            "enabled": bool(profile_categories),
            "categories": [
                _segment_row(
                    _clean_text(item.get("category_key")),
                    _clean_text(item.get("category_name")),
                    next((row["count"] for row in profile_rows if row["key"] == _clean_text(item.get("category_key"))), 0),
                    kind="profile",
                )
                for item in profile_categories
            ],
        },
    }


def _program_members_url(program_id: int, stage_key: str, *, page: int = 1, page_size: int | None = None) -> str:
    url = f"/admin/automation-conversion/programs/{int(program_id)}/members?stage={_clean_text(stage_key) or 'all'}"
    if int(page or 1) != 1:
        url = f"{url}&page={int(page)}"
    if page_size is not None and int(page_size or 50) != 50:
        url = f"{url}&page_size={int(page_size)}"
    return url


def _program_data_overview_payload(
    *,
    program: dict[str, Any],
    member_count: int,
    stage_counts: list[dict[str, Any]],
    source_status: str = "next_postgres",
) -> dict[str, Any]:
    program_id = int(program.get("id") or 0)
    stage_segments = [
        {
            "key": _clean_text(item.get("key")) or "unknown",
            "label": _program_member_stage_label(_clean_text(item.get("key")) or "unknown"),
            "count": int(item.get("total") or item.get("count") or 0),
            "list_url": _program_members_url(program_id, _clean_text(item.get("key")) or "unknown"),
        }
        for item in list(stage_counts or [])
    ]
    return {
        "ok": True,
        "route_owner": "ai_crm_next",
        "source_status": source_status,
        "program": program,
        "summary": {"member_count": int(member_count or 0)},
        "stage_segments": stage_segments,
        "all_members_url": _program_members_url(program_id, "all"),
    }


def _project_entry_channel(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "binding_id": int(row.get("binding_id") or 0),
        "channel_code": _clean_text(row.get("channel_code")),
        "channel_name": _clean_text(row.get("channel_name")),
        "channel_type": _clean_text(row.get("channel_type")) or "qrcode",
        "carrier_type": _clean_text(row.get("carrier_type")) or "qrcode",
        "status": _clean_text(row.get("status")) or "inactive",
        "binding_status": _clean_text(row.get("binding_status")) or "active",
        "auto_enter_pool": bool(row.get("auto_enter_pool", True)),
        "initial_audience_code": _clean_text(row.get("initial_audience_code")) or "pending_questionnaire",
        "initial_audience_label": AUDIENCE_LABELS.get(_clean_text(row.get("initial_audience_code")), "待填问卷"),
        "priority": int(row.get("priority") or 0),
        "qr_url": _clean_text(row.get("qr_url")),
        "qr_ticket": _clean_text(row.get("qr_ticket")),
        "scene_value": _clean_text(row.get("scene_value")),
        "customer_channel": _clean_text(row.get("customer_channel")),
        "link_url": _clean_text(row.get("link_url")),
        "final_url": _clean_text(row.get("final_url")),
        "welcome_message": _clean_text(row.get("welcome_message")),
        "auto_accept_friend": bool(row.get("auto_accept_friend", False)),
        "entry_tag_id": _clean_text(row.get("entry_tag_id")),
        "entry_tag_name": _clean_text(row.get("entry_tag_name")),
        "entry_tag_group_name": _clean_text(row.get("entry_tag_group_name")),
        "owner_staff_id": _clean_text(row.get("owner_staff_id")),
        "updated_at": _stringify_datetime(row.get("updated_at")),
        "bound_at": _stringify_datetime(row.get("bound_at")),
    }


def _project_customer_acquisition_link(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "link_id": _clean_text(row.get("link_id")),
        "link_name": _clean_text(row.get("link_name")),
        "link_url": _clean_text(row.get("link_url")),
        "customer_channel": _clean_text(row.get("customer_channel")),
        "final_url": _clean_text(row.get("final_url")),
        "initial_audience_code": _clean_text(row.get("initial_audience_code")) or "pending_questionnaire",
        "workflow_id": int(row.get("workflow_id") or 0) or None,
        "skip_verify": bool(row.get("skip_verify", False)),
        "status": _clean_text(row.get("status")) or "active",
        "last_event_at": _stringify_datetime(row.get("last_event_at")),
        "updated_at": _stringify_datetime(row.get("updated_at")),
    }


def _project_operation_task(row: dict[str, Any]) -> dict[str, Any]:
    content_mode = _clean_text(row.get("content_mode")) or "unified"
    unified = _json_loads(row.get("unified_content_json"), default={})
    segments = _json_loads(row.get("segment_contents_json"), default=[])
    agent = _json_loads(row.get("agent_config_json"), default={})
    projected = {
        "id": int(row.get("id") or 0),
        "program_id": int(row.get("program_id") or 0),
        "task_name": _clean_text(row.get("task_name")),
        "description": _clean_text(row.get("description")),
        "group_id": int(row.get("group_id") or 0) or None,
        "group_name": _clean_text(row.get("group_name")) or "未分组",
        "status": _clean_text(row.get("status")) or "draft",
        "trigger_type": _clean_text(row.get("trigger_type")) or "scheduled_daily",
        "send_time": _clean_text(row.get("send_time")),
        "timezone": _clean_text(row.get("timezone")) or "Asia/Shanghai",
        "target_audience_code": _clean_text(row.get("target_audience_code")) or "operating",
        "target_audience_label": AUDIENCE_LABELS.get(_clean_text(row.get("target_audience_code")), "运营中"),
        "target_stage_code": _clean_text(row.get("target_stage_code")),
        "audience_day_offset": int(row.get("audience_day_offset") or 0),
        "behavior_filter": _clean_text(row.get("behavior_filter")) or "none",
        "content_mode": content_mode,
        "profile_segment_template_id": int(row.get("profile_segment_template_id") or 0) or None,
        "unified_content_json": unified if isinstance(unified, dict) else {},
        "segment_contents_json": segments if isinstance(segments, list) else [],
        "agent_config_json": agent if isinstance(agent, dict) else {},
        "operation_content": {
            "content_mode": content_mode,
            "profile_segment_template_id": int(row.get("profile_segment_template_id") or 0) or None,
            "unified_content_json": unified if isinstance(unified, dict) else {},
            "segment_contents_json": segments if isinstance(segments, list) else [],
            "agent_config_json": agent if isinstance(agent, dict) else {},
        },
        "updated_at": _stringify_datetime(row.get("updated_at")),
        "published_at": _stringify_datetime(row.get("published_at")),
    }
    agent_context = _agent_task_runtime_context(projected, require_questionnaire_context=False)
    diagnostics = publishable_diagnostics(projected, agent_runtime_context=agent_context)
    projected["runtime_contract"] = {
        "status": "executable" if diagnostics.get("ok") else "unexecutable",
        "diagnostics": diagnostics,
        "agent_runtime_diagnostics": agent_runtime_diagnostics(projected, agent_runtime_context=agent_context)
        if content_mode == "agent"
        else {},
    }
    return projected


def _project_operation_task_group(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "program_id": int(row.get("program_id") or 0),
        "group_name": _clean_text(row.get("group_name")),
        "sort_order": int(row.get("sort_order") or 0),
        "created_at": _stringify_datetime(row.get("created_at")),
        "updated_at": _stringify_datetime(row.get("updated_at")),
        "archived_at": _clean_text(row.get("archived_at")),
    }


def _normalize_operation_task_payload(
    payload: dict[str, Any] | None,
    *,
    program_id: int,
    existing: dict[str, Any] | None = None,
    validate_active: bool = True,
) -> dict[str, Any]:
    payload = dict(payload or {})
    existing = dict(existing or {})
    content = dict(existing.get("operation_content") or {})
    content.update(payload.get("operation_content") if isinstance(payload.get("operation_content"), dict) else {})
    content_mode = _clean_text(payload.get("content_mode") or content.get("content_mode") or existing.get("content_mode")) or "unified"
    if content_mode not in CONTENT_MODES:
        raise ValueError("发送策略不正确")
    status = _clean_text(payload.get("status") or existing.get("status")) or "draft"
    if status not in TASK_STATUSES:
        raise ValueError("运营任务状态不正确")
    trigger_type = _clean_text(payload.get("trigger_type") or existing.get("trigger_type")) or "scheduled_daily"
    if trigger_type not in TRIGGER_TYPES:
        raise ValueError("触发方式不正确")
    behavior_filter = _clean_text(payload.get("behavior_filter") or existing.get("behavior_filter")) or "none"
    if behavior_filter not in BEHAVIOR_FILTERS:
        raise ValueError("行为过滤不正确")
    target_stage_code = _clean_text(payload.get("target_stage_code") or existing.get("target_stage_code"))
    target_audience_code = _clean_text(payload.get("target_audience_code") or existing.get("target_audience_code")) or "operating"
    if target_stage_code in {"operating", "converted", "pending_questionnaire"}:
        target_audience_code = "converted" if target_stage_code == "converted" else "pending_questionnaire" if target_stage_code == "pending_questionnaire" else "operating"
    if target_audience_code not in AUDIENCE_LABELS:
        target_audience_code = "operating"
    group_value = payload.get("group_id")
    if group_value is None and existing:
        group_value = existing.get("group_id")
    normalized = {
        "program_id": int(program_id),
        "group_id": int(group_value or 0) or None,
        "task_name": _clean_text(payload.get("task_name") or existing.get("task_name")) or "新运营任务",
        "description": _clean_text(payload.get("description") or existing.get("description")),
        "status": status,
        "trigger_type": trigger_type,
        "send_time": _clean_text(payload.get("send_time") or existing.get("send_time")) or "10:00",
        "timezone": _clean_text(payload.get("timezone") or existing.get("timezone")) or "Asia/Shanghai",
        "target_audience_code": target_audience_code,
        "target_stage_code": target_stage_code or target_audience_code,
        "audience_day_offset": max(int(payload.get("audience_day_offset") or existing.get("audience_day_offset") or 1), 1),
        "behavior_filter": behavior_filter,
        "content_mode": content_mode,
        "profile_segment_template_id": int(payload.get("profile_segment_template_id") or content.get("profile_segment_template_id") or existing.get("profile_segment_template_id") or 0) or None,
        "unified_content_json": dict(payload.get("unified_content_json") or content.get("unified_content_json") or existing.get("unified_content_json") or {}),
        "segment_contents_json": list(payload.get("segment_contents_json") or content.get("segment_contents_json") or existing.get("segment_contents_json") or []),
        "agent_config_json": dict(payload.get("agent_config_json") or content.get("agent_config_json") or existing.get("agent_config_json") or {}),
    }
    if validate_active:
        _validate_operation_task_payload(normalized)
    return normalized


def _validate_operation_task_payload(task: dict[str, Any]) -> None:
    if _clean_text(task.get("status")) != "active":
        return
    validate_publishable_task(task, agent_runtime_context=_agent_task_runtime_context(task, require_questionnaire_context=False))


def _fixture_operation_payload(program_id: int) -> dict[str, Any]:
    profile_context = _operation_profile_context_from_segmentation(_FIXTURE_SEGMENTATION_BY_PROGRAM.get(int(program_id), {}))
    groups = [
        _project_operation_task_group(item)
        for item in _FIXTURE_OPERATION_GROUPS
        if int(item.get("program_id") or 0) == int(program_id) and not _clean_text(item.get("archived_at"))
    ]
    group_names = {int(item["id"]): item["group_name"] for item in groups}
    tasks = [
        _project_operation_task({**item, "group_name": group_names.get(int(item.get("group_id") or 0), "未分组")})
        for item in _FIXTURE_OPERATION_TASKS
        if int(item.get("program_id") or 0) == int(program_id) and _clean_text(item.get("status")) != "archived"
    ]
    return {
        "ok": True,
        "route_owner": "ai_crm_next",
        "source_status": "next_fixture",
        "groups": groups,
        "tasks": tasks,
        "items": tasks,
        "total": len(tasks),
        "active_count": sum(1 for item in tasks if item.get("status") == "active"),
        **profile_context,
    }


class PostgresAutomationProgramRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_payload(self) -> dict[str, Any]:
        rows = self._fetch_program_rows()
        items = [{"program": row["program"], "summary": row["summary"]} for row in rows]
        default = next((item["program"] for item in items if item["program"].get("program_code") == "signup_conversion_v1"), None)
        if default is None and items:
            default = items[0]["program"]
        return {
            "ok": True,
            "route_owner": "ai_crm_next",
            "items": items,
            "default_program": {"id": default.get("id"), "program_name": default.get("program_name")} if default else {},
            "total": len(items),
            "source_status": "next_postgres",
        }

    def get_program_with_summary(self, program_id: int) -> dict[str, Any] | None:
        rows = self._fetch_program_rows(program_id=int(program_id))
        return rows[0] if rows else None

    def get_setup_payload(self, program_id: int, *, step: str = "basic") -> dict[str, Any]:
        current = self.get_program_with_summary(int(program_id))
        if not current:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        program = dict(current["program"])
        summary = dict(current["summary"])
        normalized_step = step if step in SETUP_STEP_KEYS else "basic"
        with self._engine.connect() as conn:
            blocks = self._fetch_config_blocks(conn, int(program_id))
            entry = self._fetch_entry_payload(conn, int(program_id))
            segmentation_payload = _payload_from_block(blocks, BLOCK_SEGMENTATION)
            segmentation = self._segmentation_view_model(conn, segmentation_payload, program_id=int(program_id))
            audience_payload = _payload_from_block(blocks, BLOCK_AUDIENCE_ENTRY_RULE)
            audience = self._audience_rule_view_model(conn, audience_payload, program_id=int(program_id))
            operations = self._fetch_operations_payload(conn, int(program_id))
        publish_check = _publish_check_from_parts(
            program,
            has_config=bool(blocks),
            has_entry=bool(entry.get("channels")),
            segmentation=segmentation_payload,
            audience_rules=list(audience.get("rules") or []),
            active_task_count=int(operations.get("active_count") or 0),
            operation_task_contract=_operation_task_runtime_contract(list(operations.get("tasks") or [])),
        )
        return {
            "program": program,
            "summary": summary,
            "step": normalized_step,
            "steps": list(SETUP_STEPS),
            "is_default_program": str(program.get("program_code") or "") == "signup_conversion_v1",
            "legacy_fallback_used": False,
            "blocks": blocks,
            "basic": _payload_from_block(blocks, BLOCK_BASIC) or dict(program.get("config_json") or {}),
            "entry_channel": _payload_from_block(blocks, BLOCK_ENTRY_CHANNEL),
            "entry": entry,
            "segmentation": segmentation,
            "audience_entry_rule": audience,
            "operations": operations,
            "publish_state": _payload_from_block(blocks, BLOCK_PUBLISH_STATE),
            "publish_check": publish_check,
        }

    def get_overview_payload(self, program_id: int) -> dict[str, Any]:
        current = self.get_program_with_summary(int(program_id))
        if not current:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        with self._engine.connect() as conn:
            stage_counts = self._fetch_program_stage_counts(conn, int(program_id))
        program = dict(current.get("program") or {})
        member_count = sum(int(item.get("total") or 0) for item in stage_counts)
        return _program_data_overview_payload(
            program=program,
            member_count=member_count,
            stage_counts=stage_counts,
        )

    def get_members_payload(
        self,
        program_id: int,
        *,
        stage_key: str = "all",
        page: int = 1,
        page_size: int = 50,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_program_with_summary(int(program_id))
        if not current:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        normalized_stage = _clean_text(stage_key) or "all"
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 50), 1), 200)
        offset = (normalized_page - 1) * normalized_page_size
        with self._engine.connect() as conn:
            total = self._count_program_members(
                conn,
                int(program_id),
                stage_key=normalized_stage,
                keyword=keyword,
            )
            rows = self._fetch_program_members(
                conn,
                int(program_id),
                stage_key=normalized_stage,
                limit=normalized_page_size,
                offset=offset,
                keyword=keyword,
            )
        stage_label = "全部成员" if normalized_stage == "all" else _program_member_stage_label(normalized_stage)
        return {
            "ok": True,
            "route_owner": "ai_crm_next",
            "source_status": "next_postgres",
            "program_id": int(program_id),
            "program": dict(current.get("program") or {}),
            "stage_key": normalized_stage,
            "stage_label": stage_label,
            "total": total,
            "page": normalized_page,
            "page_size": normalized_page_size,
            "items": rows,
            "pagination": {
                "total": total,
                "page": normalized_page,
                "page_size": normalized_page_size,
                "has_prev": normalized_page > 1,
                "has_next": offset + normalized_page_size < total,
                "prev_url": _program_members_url(int(program_id), normalized_stage, page=max(normalized_page - 1, 1), page_size=normalized_page_size)
                if normalized_page > 1
                else "",
                "next_url": _program_members_url(int(program_id), normalized_stage, page=normalized_page + 1, page_size=normalized_page_size)
                if offset + normalized_page_size < total
                else "",
            },
        }

    def publish_program(self, program_id: int, *, operator_id: str, scope: str) -> dict[str, Any]:
        payload = self.get_setup_payload(int(program_id), step="publish")
        check = dict(payload.get("publish_check") or {})
        group_key = "full" if scope == "full" else "entry"
        group = dict(check.get(group_key) or {})
        if not bool(group.get("passed")):
            raise ValueError("完整自动化发布检查未通过" if group_key == "full" else "入口发布检查未通过")
        with self._engine.begin() as conn:
            state = {"entry_published": True, "full_published": group_key == "full", "published_by": _clean_text(operator_id), "published_at": datetime.now(timezone.utc).isoformat()}
            block = self._upsert_config_block(conn, int(program_id), BLOCK_PUBLISH_STATE, state, status="published")
            conn.execute(
                text(
                    """
                    UPDATE automation_program
                    SET status = 'active',
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :program_id
                    """
                ),
                {"program_id": int(program_id), "operator_id": _clean_text(operator_id)},
            )
        refreshed = self.get_program_with_summary(int(program_id))
        if not refreshed:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        return {
            "program": refreshed["program"],
            "summary": refreshed["summary"],
            "publish_state": block,
            "publish_check": self.get_setup_payload(int(program_id), step="publish").get("publish_check") or {},
        }

    def copy_program(self, program_id: int, *, operator_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        with self._engine.begin() as conn:
            source = conn.execute(
                text("SELECT * FROM automation_program WHERE id = :program_id LIMIT 1"),
                {"program_id": int(program_id)},
            ).mappings().first()
            if not source:
                raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
            source_dict = dict(source)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            program_name = _clean_text(payload.get("program_name")) or f"{source_dict.get('program_name') or '自动化运营方案'} 副本"
            program_code = _clean_text(payload.get("program_code")) or f"{source_dict.get('program_code') or 'program'}_copy_{timestamp}"
            inserted = conn.execute(
                text(
                    """
                    INSERT INTO automation_program (
                        program_code,
                        program_name,
                        description,
                        status,
                        config_json,
                        created_by,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :program_code,
                        :program_name,
                        :description,
                        'draft',
                        CAST(:config_json AS jsonb),
                        :operator_id,
                        :operator_id,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING *
                    """
                ),
                {
                    "program_code": program_code,
                    "program_name": program_name,
                    "description": _clean_text(source_dict.get("description")),
                    "config_json": _json_text(_json_loads(source_dict.get("config_json"), default={})),
                    "operator_id": _clean_text(operator_id),
                },
            ).mappings().first()
            if not inserted:
                raise AutomationProgramDataUnavailable("automation program copy insert failed")
            target_id = int(inserted["id"])
            blocks = conn.execute(
                text(
                    """
                    SELECT *
                    FROM automation_program_config_block
                    WHERE program_id = :program_id
                    ORDER BY block_key ASC
                    """
                ),
                {"program_id": int(program_id)},
            ).mappings().all()
            for block in blocks:
                block_dict = dict(block)
                block_payload = _json_loads(block_dict.get("payload_json"), default={})
                if _clean_text(block_dict.get("block_key")) == "entry_channel":
                    qrcode = dict(block_payload.get("qrcode") or {})
                    for key in ("qr_ticket", "qr_url", "scene_value", "config_id", "wecom_response"):
                        qrcode.pop(key, None)
                    block_payload["qrcode"] = qrcode
                    block_payload.pop("customer_acquisition_link_ids", None)
                conn.execute(
                    text(
                        """
                        INSERT INTO automation_program_config_block (
                            program_id,
                            block_key,
                            payload_json,
                            status,
                            version,
                            copied_from_program_id,
                            copied_from_block_id,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            :target_id,
                            :block_key,
                            CAST(:payload_json AS jsonb),
                            :status,
                            1,
                            :source_program_id,
                            :source_block_id,
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "target_id": target_id,
                        "block_key": _clean_text(block_dict.get("block_key")),
                        "payload_json": _json_text(block_payload),
                        "status": _clean_text(block_dict.get("status")) or "draft",
                        "source_program_id": int(program_id),
                        "source_block_id": int(block_dict.get("id") or 0),
                    },
                )
        copied = self.get_program_with_summary(target_id)
        if not copied:
            raise AutomationProgramDataUnavailable(f"copied automation program {target_id} not found")
        return copied

    def update_basic_info(self, program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        status = _clean_text(payload.get("status")) or "draft"
        if status not in {"draft", "active", "paused", "archived"}:
            status = "draft"
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_program
                    SET program_name = :program_name,
                        program_code = :program_code,
                        description = :description,
                        status = :status,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :program_id
                    RETURNING *
                    """
                ),
                {
                    "program_id": int(program_id),
                    "program_name": _clean_text(payload.get("program_name")),
                    "program_code": _clean_text(payload.get("program_code")),
                    "description": _clean_text(payload.get("description")),
                    "status": status,
                    "operator_id": _clean_text(operator_id),
                },
            ).mappings().first()
        if not row:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        updated = self.get_program_with_summary(int(program_id))
        if not updated:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        return updated

    def update_status(self, program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
        if status not in {"draft", "active", "paused", "archived"}:
            raise AutomationProgramDataUnavailable(f"unsupported automation program status: {status}")
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_program
                    SET status = :status,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :program_id
                    RETURNING id
                    """
                ),
                {"program_id": int(program_id), "status": status, "operator_id": _clean_text(operator_id)},
            ).mappings().first()
        if not row:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        updated = self.get_program_with_summary(int(program_id))
        if not updated:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        return updated

    def save_segmentation(self, program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        normalized = _normalize_segmentation_payload(payload)
        _validate_option_categories(normalized)
        _validate_score_ranges(normalized)
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM automation_program WHERE id = :program_id LIMIT 1"),
                {"program_id": int(program_id)},
            ).mappings().first()
            if not row:
                raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
            block = self._upsert_config_block(conn, int(program_id), BLOCK_SEGMENTATION, normalized, status="saved")
            profile_template = self._sync_profile_segment_template(conn, int(program_id), normalized, operator_id=operator_id)
        return {"segmentation": block, "profile_segment_template": profile_template}

    def save_audience_entry_rule(self, program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        del operator_id
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM automation_program WHERE id = :program_id LIMIT 1"),
                {"program_id": int(program_id)},
            ).mappings().first()
            if not row:
                raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
            available_questionnaires = self._list_available_questionnaires(conn)
            normalized = _normalize_audience_entry_rule_payload(
                payload,
                validate=not bool(payload.get("_allow_incomplete")),
                available_questionnaires=available_questionnaires,
            )
            block = self._upsert_config_block(conn, int(program_id), BLOCK_AUDIENCE_ENTRY_RULE, normalized, status="saved")
        return {"audience_entry_rule": block, "next_steps": _audience_next_steps(normalized)}

    def _upsert_config_block(
        self,
        conn: Any,
        program_id: int,
        block_key: str,
        payload: dict[str, Any],
        *,
        status: str = "saved",
    ) -> dict[str, Any]:
        row = conn.execute(
            text(
                """
                INSERT INTO automation_program_config_block (
                    program_id,
                    block_key,
                    payload_json,
                    status,
                    version,
                    created_at,
                    updated_at
                )
                VALUES (
                    :program_id,
                    :block_key,
                    CAST(:payload_json AS jsonb),
                    :status,
                    1,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (program_id, block_key)
                DO UPDATE SET
                    payload_json = EXCLUDED.payload_json,
                    status = EXCLUDED.status,
                    version = automation_program_config_block.version + 1,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, block_key, payload_json, status, version, updated_at
                """
            ),
            {
                "program_id": int(program_id),
                "block_key": block_key,
                "payload_json": _json_text(payload),
                "status": status,
            },
        ).mappings().first()
        item = dict(row or {})
        return {
            "id": int(item.get("id") or 0),
            "block_key": _clean_text(item.get("block_key")),
            "payload": _json_loads(item.get("payload_json"), default={}),
            "status": _clean_text(item.get("status")) or status,
            "version": int(item.get("version") or 1),
            "updated_at": _stringify_datetime(item.get("updated_at")),
        }

    def _sync_profile_segment_template(
        self,
        conn: Any,
        program_id: int,
        payload: dict[str, Any],
        *,
        operator_id: str,
    ) -> dict[str, Any] | None:
        normal = dict((payload.get("strategies") or {}).get("normal_question_rules") or {})
        categories = list(normal.get("categories") or [])
        questionnaire_id = int(payload.get("questionnaire_id") or 0)
        question_id = int(normal.get("segmentation_question_id") or 0)
        template_code = f"setup_normal_option_category_{int(program_id)}"
        existing = conn.execute(
            text(
                """
                SELECT *
                FROM automation_profile_segment_template
                WHERE template_code = :template_code
                LIMIT 1
                """
            ),
            {"template_code": template_code},
        ).mappings().first()
        if not questionnaire_id or not question_id or not categories:
            if existing:
                disabled = conn.execute(
                    text(
                        """
                        UPDATE automation_profile_segment_template
                        SET enabled = false,
                            version = COALESCE(version, 1) + 1,
                            updated_by = :updated_by,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :template_id
                        RETURNING *
                        """
                    ),
                    {"template_id": int(existing["id"]), "updated_by": _clean_text(operator_id) or "setup_wizard"},
                ).mappings().first()
                return dict(disabled or existing)
            return None

        template_name = _clean_text(normal.get("segmentation_question_title")) or "普通问卷选项分类"
        common = {
            "program_id": int(program_id),
            "template_code": template_code,
            "template_name": f"{template_name} · 自然画像",
            "questionnaire_id": questionnaire_id,
            "segmentation_question_id": question_id,
            "description": "由 Next 配置向导的普通问卷选项分类自动同步。",
            "enabled": True,
            "operator_id": _clean_text(operator_id) or "setup_wizard",
        }
        if existing:
            saved = conn.execute(
                text(
                    """
                    UPDATE automation_profile_segment_template
                    SET program_id = :program_id,
                        template_name = :template_name,
                        questionnaire_id = :questionnaire_id,
                        segmentation_question_id = :segmentation_question_id,
                        description = :description,
                        enabled = :enabled,
                        version = COALESCE(version, 1) + 1,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :template_id
                    RETURNING *
                    """
                ),
                {**common, "template_id": int(existing["id"])},
            ).mappings().first()
        else:
            saved = conn.execute(
                text(
                    """
                    INSERT INTO automation_profile_segment_template (
                        program_id,
                        template_code,
                        template_name,
                        questionnaire_id,
                        segmentation_question_id,
                        description,
                        enabled,
                        version,
                        created_by,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :program_id,
                        :template_code,
                        :template_name,
                        :questionnaire_id,
                        :segmentation_question_id,
                        :description,
                        :enabled,
                        1,
                        :operator_id,
                        :operator_id,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING *
                    """
                ),
                common,
            ).mappings().first()
        template = dict(saved or {})
        template_id = int(template.get("id") or 0)
        conn.execute(
            text("DELETE FROM automation_profile_segment_option_mapping WHERE template_id = :template_id"),
            {"template_id": template_id},
        )
        conn.execute(
            text("DELETE FROM automation_profile_segment_category WHERE template_id = :template_id"),
            {"template_id": template_id},
        )
        for index, category in enumerate(categories, start=1):
            category_row = conn.execute(
                text(
                    """
                    INSERT INTO automation_profile_segment_category (
                        template_id,
                        category_key,
                        category_name,
                        description,
                        sort_order,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :template_id,
                        :category_key,
                        :category_name,
                        :description,
                        :sort_order,
                        true,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING id
                    """
                ),
                {
                    "template_id": template_id,
                    "category_key": _clean_text(category.get("category_key")) or f"category_{index}",
                    "category_name": _clean_text(category.get("category_name")) or f"分类 {index}",
                    "description": _clean_text(category.get("description")),
                    "sort_order": index,
                },
            ).mappings().first()
            category_id = int((category_row or {}).get("id") or 0)
            for option_id in list(category.get("option_ids") or []):
                normalized_option_id = int(option_id or 0)
                if not normalized_option_id:
                    continue
                conn.execute(
                    text(
                        """
                        INSERT INTO automation_profile_segment_option_mapping (
                            template_id,
                            category_id,
                            question_id,
                            option_id,
                            created_at
                        )
                        VALUES (
                            :template_id,
                            :category_id,
                            :question_id,
                            :option_id,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "template_id": template_id,
                        "category_id": category_id,
                        "question_id": question_id,
                        "option_id": normalized_option_id,
                    },
                )
        return template

    def _fetch_program_rows(self, *, program_id: int | None = None) -> list[dict[str, Any]]:
        where_sql = "WHERE p.id = :program_id" if program_id is not None else "WHERE 1 = 1"
        params = {"program_id": int(program_id)} if program_id is not None else {}
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        p.*,
                        COALESCE(members.member_count, 0) AS member_count,
                        COALESCE(bindings.channel_count, 0) AS channel_count,
                        COALESCE(workflows.workflow_count, 0) AS workflow_count,
                        COALESCE(operation_tasks.operation_task_count, 0) AS operation_task_count,
                        COALESCE(operation_tasks.active_operation_task_count, 0) AS active_operation_task_count,
                        executions.latest_execution_at AS latest_execution_at,
                        publish_state.payload_json AS publish_state,
                        basic_block.payload_json AS basic_payload,
                        segmentation_block.payload_json AS segmentation_payload,
                        audience_block.payload_json AS audience_payload
                    FROM automation_program p
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS member_count
                        FROM automation_program_member pm
                        WHERE pm.program_id = p.id
                          AND pm.in_program = true
                    ) members ON true
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS channel_count
                        FROM automation_program_channel_binding b
                        WHERE b.program_id = p.id
                          AND b.binding_status <> 'archived'
                    ) bindings ON true
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS workflow_count
                        FROM automation_workflow w
                        WHERE w.program_id = p.id
                          AND w.status <> 'archived'
                    ) workflows ON true
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(*) AS operation_task_count,
                            COUNT(*) FILTER (WHERE t.status = 'active') AS active_operation_task_count
                        FROM automation_operation_task t
                        WHERE t.program_id = p.id
                          AND t.status <> 'archived'
                    ) operation_tasks ON true
                    LEFT JOIN LATERAL (
                        SELECT MAX(COALESCE(CAST(e.scheduled_for AS TEXT), CAST(e.updated_at AS TEXT), CAST(e.created_at AS TEXT), '')) AS latest_execution_at
                        FROM automation_workflow_execution e
                        WHERE e.program_id = p.id
                    ) executions ON true
                    LEFT JOIN automation_program_config_block publish_state
                      ON publish_state.program_id = p.id
                     AND publish_state.block_key = 'publish_state'
                    LEFT JOIN automation_program_config_block basic_block
                      ON basic_block.program_id = p.id
                     AND basic_block.block_key = 'basic'
                    LEFT JOIN automation_program_config_block segmentation_block
                      ON segmentation_block.program_id = p.id
                     AND segmentation_block.block_key = 'questionnaire_segmentation'
                    LEFT JOIN automation_program_config_block audience_block
                      ON audience_block.program_id = p.id
                     AND audience_block.block_key = 'audience_entry_rule'
                    {where_sql}
                    ORDER BY
                        CASE p.status
                            WHEN 'active' THEN 0
                            WHEN 'draft' THEN 1
                            WHEN 'paused' THEN 2
                            ELSE 3
                        END,
                        p.updated_at DESC,
                        p.id DESC
                    """
                ),
                params,
            ).mappings().all()
        return [self._project_row(dict(row)) for row in rows]

    def _fetch_config_blocks(self, conn: Any, program_id: int) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT id, block_key, payload_json, status, version, updated_at
                FROM automation_program_config_block
                WHERE program_id = :program_id
                ORDER BY block_key ASC
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        blocks: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            block_key = _clean_text(item.get("block_key"))
            if not block_key:
                continue
            blocks[block_key] = {
                "id": int(item.get("id") or 0),
                "block_key": block_key,
                "payload": _json_loads(item.get("payload_json"), default={}),
                "status": _clean_text(item.get("status")) or "draft",
                "version": int(item.get("version") or 1),
                "updated_at": _stringify_datetime(item.get("updated_at")),
            }
        return blocks

    def _fetch_member_group_counts(self, conn: Any, program_id: int, column: str) -> list[dict[str, Any]]:
        if column not in {"current_audience_code", "current_stage_code"}:
            raise ValueError("unsupported automation member group column")
        rows = conn.execute(
            text(
                f"""
                SELECT COALESCE(NULLIF({column}, ''), 'unknown') AS key, COUNT(*) AS total
                FROM automation_program_member
                WHERE program_id = :program_id
                  AND in_program = true
                GROUP BY COALESCE(NULLIF({column}, ''), 'unknown')
                ORDER BY total DESC, key ASC
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        return [{"key": _clean_text(row.get("key")), "total": int(row.get("total") or 0)} for row in rows]

    def _fetch_program_stage_counts(self, conn: Any, program_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT
                    COALESCE(NULLIF(current_stage_code, ''), current_audience_code, 'unknown') AS key,
                    COUNT(*) AS total
                FROM automation_program_member
                WHERE program_id = :program_id
                  AND in_program = true
                GROUP BY COALESCE(NULLIF(current_stage_code, ''), current_audience_code, 'unknown')
                ORDER BY total DESC, key ASC
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        return [{"key": _clean_text(row.get("key")) or "unknown", "total": int(row.get("total") or 0)} for row in rows]

    def _program_members_keyword_sql(self, keyword: str | None) -> tuple[str, dict[str, Any]]:
        normalized = _clean_text(keyword)
        if not normalized:
            return "", {}
        return (
            """
              AND (
                pm.external_contact_id ILIKE :keyword
                OR COALESCE(ct.customer_name, '') ILIKE :keyword
                OR COALESCE(ct.remark, '') ILIKE :keyword
                OR COALESCE(p.mobile, '') ILIKE :keyword
                OR COALESCE(am.phone, '') ILIKE :keyword
              )
            """,
            {"keyword": f"%{normalized}%"},
        )

    def _program_members_join_sql(self) -> str:
        return """
            LEFT JOIN contacts ct
              ON ct.external_userid = pm.external_contact_id
            LEFT JOIN LATERAL (
                SELECT id, phone, master_customer_id
                FROM automation_member am
                WHERE am.external_contact_id = pm.external_contact_id
                ORDER BY am.updated_at DESC, am.id DESC
                LIMIT 1
            ) am ON true
            LEFT JOIN people p
              ON p.id = COALESCE(pm.master_customer_id, am.master_customer_id)
            LEFT JOIN automation_channel ch
              ON ch.id = pm.latest_source_channel_id
        """

    def _count_program_members(self, conn: Any, program_id: int, *, stage_key: str, keyword: str | None = None) -> int:
        keyword_sql, keyword_params = self._program_members_keyword_sql(keyword)
        row = conn.execute(
            text(
                f"""
                SELECT COUNT(*) AS total
                FROM automation_program_member pm
                {self._program_members_join_sql()}
                WHERE pm.program_id = :program_id
                  AND pm.in_program = true
                  AND (
                    :stage_key = 'all'
                    OR COALESCE(NULLIF(pm.current_stage_code, ''), pm.current_audience_code, 'unknown') = :stage_key
                  )
                {keyword_sql}
                """
            ),
            {"program_id": int(program_id), "stage_key": _clean_text(stage_key) or "all", **keyword_params},
        ).mappings().first()
        return int((row or {}).get("total") or 0)

    def _fetch_program_members(
        self,
        conn: Any,
        program_id: int,
        *,
        stage_key: str,
        limit: int,
        offset: int,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        keyword_sql, keyword_params = self._program_members_keyword_sql(keyword)
        rows = conn.execute(
            text(
                f"""
                SELECT
                    pm.id AS program_member_id,
                    pm.program_id,
                    pm.external_contact_id,
                    COALESCE(NULLIF(pm.current_stage_code, ''), pm.current_audience_code, 'unknown') AS stage_key,
                    pm.current_audience_code,
                    pm.pool_entered_at,
                    pm.current_stage_entered_at,
                    pm.latest_source_channel_id,
                    ch.channel_name AS latest_source_channel_name,
                    pm.updated_at,
                    COALESCE(NULLIF(ct.customer_name, ''), NULLIF(ct.remark, ''), pm.external_contact_id) AS customer_name,
                    COALESCE(NULLIF(p.mobile, ''), NULLIF(am.phone, '')) AS phone
                FROM automation_program_member pm
                {self._program_members_join_sql()}
                WHERE pm.program_id = :program_id
                  AND pm.in_program = true
                  AND (
                    :stage_key = 'all'
                    OR COALESCE(NULLIF(pm.current_stage_code, ''), pm.current_audience_code, 'unknown') = :stage_key
                  )
                {keyword_sql}
                ORDER BY pm.updated_at DESC, pm.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "program_id": int(program_id),
                "stage_key": _clean_text(stage_key) or "all",
                "limit": int(limit),
                "offset": int(offset),
                **keyword_params,
            },
        ).mappings().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            stage = _clean_text(item.get("stage_key")) or "unknown"
            items.append(
                {
                    "program_member_id": int(item.get("program_member_id") or 0),
                    "program_id": int(item.get("program_id") or 0),
                    "external_contact_id": _clean_text(item.get("external_contact_id")),
                    "customer_name": _clean_text(item.get("customer_name")),
                    "phone": _clean_text(item.get("phone")),
                    "stage_key": stage,
                    "stage_label": _program_member_stage_label(stage),
                    "current_audience_code": _clean_text(item.get("current_audience_code")),
                    "pool_entered_at": _stringify_datetime(item.get("pool_entered_at")),
                    "current_stage_entered_at": _stringify_datetime(item.get("current_stage_entered_at")),
                    "latest_source_channel_id": int(item.get("latest_source_channel_id") or 0) or None,
                    "latest_source_channel_name": _clean_text(item.get("latest_source_channel_name")),
                    "updated_at": _stringify_datetime(item.get("updated_at")),
                }
            )
        return items

    def _fetch_segment_key_counts(self, conn: Any, program_id: int, key: str) -> list[dict[str, Any]]:
        if key not in {"profile_segment_key", "behavior_tier_key"}:
            raise ValueError("unsupported automation segment key")
        rows = conn.execute(
            text(
                f"""
                SELECT COALESCE(NULLIF(COALESCE(pm.state_payload_json ->> :key, am.{key}, ''), ''), 'unknown') AS key, COUNT(*) AS total
                FROM automation_program_member pm
                LEFT JOIN LATERAL (
                    SELECT {key}
                    FROM automation_member am
                    WHERE am.external_contact_id = pm.external_contact_id
                    ORDER BY am.updated_at DESC, am.id DESC
                    LIMIT 1
                ) am ON true
                WHERE pm.program_id = :program_id
                  AND pm.in_program = true
                GROUP BY COALESCE(NULLIF(COALESCE(pm.state_payload_json ->> :key, am.{key}, ''), ''), 'unknown')
                ORDER BY total DESC, key ASC
                """
            ),
            {"program_id": int(program_id), "key": key},
        ).mappings().all()
        return [{"key": _clean_text(row.get("key")), "total": int(row.get("total") or 0)} for row in rows]

    def _fetch_profile_categories(self, conn: Any, program_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT c.category_key, c.category_name, c.sort_order
                FROM automation_profile_segment_template t
                JOIN automation_profile_segment_category c ON c.template_id = t.id
                WHERE t.enabled = true
                  AND c.enabled = true
                  AND (t.program_id = :program_id OR t.program_id IS NULL)
                ORDER BY
                  CASE WHEN t.program_id = :program_id THEN 0 ELSE 1 END,
                  t.updated_at DESC,
                  c.sort_order ASC,
                  c.id ASC
                LIMIT 50
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        seen: set[str] = set()
        categories: list[dict[str, Any]] = []
        for row in rows:
            key = _clean_text(row.get("category_key"))
            if not key or key in seen:
                continue
            seen.add(key)
            categories.append({"category_key": key, "category_name": _clean_text(row.get("category_name")) or key})
        return categories

    def _fetch_entry_payload(self, conn: Any, program_id: int) -> dict[str, Any]:
        rows = conn.execute(
            text(
                """
                SELECT
                    c.*,
                    b.id AS binding_id,
                    b.binding_status,
                    b.auto_enter_pool,
                    b.initial_audience_code,
                    b.priority,
                    b.entry_rule_json,
                    b.bound_at,
                    b.updated_at AS binding_updated_at
                FROM automation_program_channel_binding b
                JOIN automation_channel c ON c.id = b.channel_id
                WHERE b.program_id = :program_id
                  AND b.binding_status <> 'archived'
                ORDER BY b.priority DESC, b.id DESC
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        channels = [_project_entry_channel(dict(row)) for row in rows]
        qrcode = next((item for item in channels if item.get("carrier_type") != "link" and item.get("channel_type") != "wecom_customer_acquisition"), {})
        from aicrm_next.automation_engine.channels_api import list_program_entry_candidate_channels

        link_rows = conn.execute(
            text(
                """
                SELECT *
                FROM wecom_customer_acquisition_links
                WHERE program_id = :program_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 100
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        return {
            "channels": channels,
            "candidate_channels": list_program_entry_candidate_channels(int(program_id)),
            "api_urls": _entry_channel_api_urls(int(program_id)),
            "qrcode_channel": dict(qrcode or {}),
            "customer_acquisition_links": [_project_customer_acquisition_link(dict(row)) for row in link_rows],
        }

    def _segmentation_view_model(self, conn: Any, payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
        normalized = _normalize_segmentation_payload(payload)
        questionnaire_id = int(normalized.get("questionnaire_id") or 0) or None
        available = self._list_available_questionnaires(conn)
        for item in available:
            item["questions"] = self._questionnaire_questions(conn, int(item.get("id") or 0))
        question_rows = next(
            (list(item.get("questions") or []) for item in available if int(item.get("id") or 0) == int(questionnaire_id or 0)),
            self._questionnaire_questions(conn, questionnaire_id),
        )
        selected = next((dict(item) for item in available if int(item.get("id") or 0) == int(questionnaire_id or 0)), {})
        if questionnaire_id and not selected:
            selected = {"id": questionnaire_id, "title": f"问卷 {questionnaire_id}", "status": "未找到", "question_count": 0}
        if selected:
            selected["questions"] = list(question_rows)
        normal_strategy = dict((normalized.get("strategies") or {}).get("normal_question_rules") or {})
        selected_question_id = int(normal_strategy.get("segmentation_question_id") or 0) or (int(question_rows[0]["id"]) if question_rows else None)
        selected_question = next((dict(item) for item in question_rows if int(item.get("id") or 0) == int(selected_question_id or 0)), {})
        option_lookup = {
            int(option.get("id") or 0): dict(option)
            for option in list(selected_question.get("options") or [])
            if int(option.get("id") or 0)
        }
        category_rows = []
        for category in list(normal_strategy.get("categories") or []):
            row = dict(category or {})
            snapshots_by_id = {
                int(item.get("id") or 0): dict(item)
                for item in list(row.get("option_snapshots") or [])
                if int(item.get("id") or 0)
            }
            row["option_snapshots"] = [
                {
                    "id": int(option_id),
                    "option_text": _clean_text((option_lookup.get(int(option_id)) or snapshots_by_id.get(int(option_id)) or {}).get("option_text"))
                    or f"选项 {int(option_id)}",
                }
                for option_id in list(row.get("option_ids") or [])
                if int(option_id or 0)
            ]
            category_rows.append(row)
        assigned_option_ids = {
            int(option_id)
            for category in category_rows
            for option_id in list((category or {}).get("option_ids") or [])
            if int(option_id or 0)
        }
        unassigned_options = [
            dict(option)
            for option in list(selected_question.get("options") or [])
            if int(option.get("id") or 0) not in assigned_option_ids
        ]
        return {
            **normalized,
            "available_questionnaires": available,
            "selected_questionnaire": selected,
            "question_rows": question_rows,
            "selected_segmentation_question": selected_question,
            "normal_question_rules": {
                "mode": _clean_text(normal_strategy.get("mode")) or "single_question_option_category",
                "core_threshold": int(normal_strategy.get("core_threshold") or 2),
                "segmentation_question_id": selected_question_id,
                "segmentation_question_title": _clean_text(selected_question.get("title")),
                "selected_question": selected_question,
                "category_rows": category_rows,
                "unassigned_options": unassigned_options,
                "legacy_rows": list(normal_strategy.get("rules") or []),
                "rows": list(normal_strategy.get("rules") or []),
            },
            "score_segments": {
                "enabled": bool(((normalized.get("strategies") or {}).get("score_segments") or {}).get("enabled")),
                "rows": list(((normalized.get("strategies") or {}).get("score_segments") or {}).get("ranges") or []),
            },
            "profile_dimension": {
                **dict(((normalized.get("strategies") or {}).get("profile_dimension") or {})),
                "available_templates": self._profile_templates(conn, int(program_id)),
            },
        }

    def _audience_rule_view_model(self, conn: Any, payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
        return _audience_rule_view_model(
            payload,
            program_id=int(program_id),
            available_questionnaires=self._list_available_questionnaires(conn),
            available_products=self._available_products(conn),
        )

    def _list_available_questionnaires(self, conn: Any) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT q.id, q.title, q.name, q.slug, q.is_disabled, COUNT(qq.id) AS question_count
                FROM questionnaires q
                LEFT JOIN questionnaire_questions qq ON qq.questionnaire_id = q.id
                GROUP BY q.id, q.title, q.name, q.slug, q.is_disabled
                ORDER BY q.is_disabled ASC, q.updated_at DESC, q.id DESC
                LIMIT 100
                """
            )
        ).mappings().all()
        return [
            {
                "id": int(row.get("id") or 0),
                "title": _clean_text(row.get("title")) or _clean_text(row.get("name")) or _clean_text(row.get("slug")),
                "status": "停用" if row.get("is_disabled") else "启用",
                "question_count": int(row.get("question_count") or 0),
            }
            for row in rows
        ]

    def _available_products(self, conn: Any) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT id, product_code, name, amount_total, currency, status, enabled
                FROM wechat_pay_products
                ORDER BY enabled DESC, status ASC, updated_at DESC, id DESC
                LIMIT 100
                """
            )
        ).mappings().all()
        products = []
        for row in rows:
            amount_total = int(row.get("amount_total") or 0)
            currency = _clean_text(row.get("currency")) or "CNY"
            price_text = "免费" if amount_total <= 0 else f"¥{amount_total / 100:.2f}" if currency == "CNY" else f"{amount_total / 100:.2f} {currency}"
            product_id = _clean_text(row.get("product_code")) or str(int(row.get("id") or 0))
            products.append(
                {
                    "id": product_id,
                    "product_code": _clean_text(row.get("product_code")),
                    "name": _clean_text(row.get("name")) or product_id,
                    "price_text": price_text,
                    "status": _clean_text(row.get("status")) or ("active" if row.get("enabled") else "draft"),
                    "enabled": bool(row.get("enabled")),
                }
            )
        return products

    def _questionnaire_questions(self, conn: Any, questionnaire_id: int | None) -> list[dict[str, Any]]:
        normalized_id = int(questionnaire_id or 0)
        if not normalized_id:
            return []
        question_rows = conn.execute(
            text(
                """
                SELECT id, title, type, sort_order
                FROM questionnaire_questions
                WHERE questionnaire_id = :questionnaire_id
                ORDER BY sort_order ASC, id ASC
                """
            ),
            {"questionnaire_id": normalized_id},
        ).mappings().all()
        option_rows = conn.execute(
            text(
                """
                SELECT o.id, o.question_id, o.option_text, o.sort_order
                FROM questionnaire_options o
                JOIN questionnaire_questions q ON q.id = o.question_id
                WHERE q.questionnaire_id = :questionnaire_id
                ORDER BY q.sort_order ASC, o.sort_order ASC, o.id ASC
                """
            ),
            {"questionnaire_id": normalized_id},
        ).mappings().all()
        options_by_question: dict[int, list[dict[str, Any]]] = {}
        for row in option_rows:
            question_id = int(row.get("question_id") or 0)
            options_by_question.setdefault(question_id, []).append(
                {"id": int(row.get("id") or 0), "option_text": _clean_text(row.get("option_text"))}
            )
        questions: list[dict[str, Any]] = []
        for row in question_rows:
            question_type = _clean_text(row.get("type"))
            if question_type not in {"single_choice", "multi_choice"}:
                continue
            question_id = int(row.get("id") or 0)
            options = options_by_question.get(question_id, [])
            if not options:
                continue
            questions.append(
                {
                    "id": question_id,
                    "title": _clean_text(row.get("title")),
                    "question_type": question_type,
                    "sort_order": int(row.get("sort_order") or 0),
                    "options": options,
                }
            )
        return questions

    def _profile_templates(self, conn: Any, program_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT id, template_name, template_code, enabled
                FROM automation_profile_segment_template
                WHERE program_id = :program_id OR program_id IS NULL
                ORDER BY enabled DESC, updated_at DESC, id DESC
                LIMIT 100
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        return [
            {
                "id": int(row.get("id") or 0),
                "template_name": _clean_text(row.get("template_name")),
                "template_code": _clean_text(row.get("template_code")),
                "enabled": bool(row.get("enabled", True)),
            }
            for row in rows
        ]

    def _fetch_operations_payload(self, conn: Any, program_id: int) -> dict[str, Any]:
        segmentation_row = conn.execute(
            text(
                """
                SELECT payload_json
                FROM automation_program_config_block
                WHERE program_id = :program_id
                  AND block_key = :block_key
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"program_id": int(program_id), "block_key": BLOCK_SEGMENTATION},
        ).mappings().first()
        template_row = conn.execute(
            text(
                """
                SELECT id
                FROM automation_profile_segment_template
                WHERE template_code = :template_code
                  AND enabled = true
                LIMIT 1
                """
            ),
            {"template_code": f"setup_normal_option_category_{int(program_id)}"},
        ).mappings().first()
        profile_context = _operation_profile_context_from_segmentation(
            _json_loads((segmentation_row or {}).get("payload_json"), default={}),
            template_id=int((template_row or {}).get("id") or 0) or None,
        )
        group_rows = conn.execute(
            text(
                """
                SELECT *
                FROM automation_operation_task_group
                WHERE program_id = :program_id
                  AND COALESCE(archived_at, '') = ''
                ORDER BY sort_order ASC, id ASC
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        task_rows = conn.execute(
            text(
                """
                SELECT t.*, g.group_name
                FROM automation_operation_task t
                LEFT JOIN automation_operation_task_group g ON g.id = t.group_id
                WHERE t.program_id = :program_id
                  AND t.status <> 'archived'
                ORDER BY
                    CASE t.status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 WHEN 'paused' THEN 2 ELSE 3 END,
                    t.updated_at DESC,
                    t.id DESC
                LIMIT 200
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        tasks = [_project_operation_task(dict(row)) for row in task_rows]
        return {
            "groups": [_project_operation_task_group(dict(row)) for row in group_rows],
            "tasks": tasks,
            "items": tasks,
            "total": len(tasks),
            "active_count": sum(1 for item in tasks if item.get("status") == "active"),
            **profile_context,
        }

    def list_operation_tasks(self, program_id: int) -> dict[str, Any]:
        with self._engine.connect() as conn:
            payload = self._fetch_operations_payload(conn, int(program_id))
        return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_postgres", **payload}

    def create_operation_task_group(self, program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        group_name = _clean_text(payload.get("group_name") or payload.get("name"))
        if not group_name:
            raise ValueError("分组名称不能为空")
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO automation_operation_task_group (
                        program_id, group_name, sort_order, created_by, updated_by, created_at, updated_at, archived_at
                    )
                    VALUES (
                        :program_id, :group_name, :sort_order, :operator_id, :operator_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ''
                    )
                    RETURNING *
                    """
                ),
                {
                    "program_id": int(program_id),
                    "group_name": group_name,
                    "sort_order": int(payload.get("sort_order") or 0),
                    "operator_id": _clean_text(operator_id) or "setup_wizard",
                },
            ).mappings().first()
        group = _project_operation_task_group(dict(row or {}))
        return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_postgres", "group": group, "groups": [group]}

    def archive_operation_task_group(self, program_id: int, group_id: int, *, operator_id: str) -> dict[str, Any]:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_operation_task_group
                    SET archived_at = CAST(CURRENT_TIMESTAMP AS TEXT),
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :group_id
                      AND program_id = :program_id
                      AND COALESCE(archived_at, '') = ''
                    RETURNING *
                    """
                ),
                {"program_id": int(program_id), "group_id": int(group_id), "operator_id": _clean_text(operator_id) or "setup_wizard"},
            ).mappings().first()
            if not row:
                raise AutomationProgramDataUnavailable(f"operation task group {group_id} not found")
            conn.execute(
                text(
                    """
                    UPDATE automation_operation_task
                    SET group_id = NULL,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE program_id = :program_id
                      AND group_id = :group_id
                    """
                ),
                {"program_id": int(program_id), "group_id": int(group_id), "operator_id": _clean_text(operator_id) or "setup_wizard"},
            )
        return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_postgres", "group": _project_operation_task_group(dict(row))}

    def create_operation_task(self, program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        normalized = _normalize_operation_task_payload(payload, program_id=int(program_id))
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO automation_operation_task (
                        program_id, group_id, task_name, description, status, trigger_type, send_time, timezone,
                        target_audience_code, target_stage_code, audience_day_offset, behavior_filter,
                        content_mode, profile_segment_template_id, unified_content_json, segment_contents_json,
                        agent_config_json, created_by, updated_by, created_at, updated_at, published_at
                    )
                    VALUES (
                        :program_id, :group_id, :task_name, :description, :status, :trigger_type, :send_time, :timezone,
                        :target_audience_code, :target_stage_code, :audience_day_offset, :behavior_filter,
                        :content_mode, :profile_segment_template_id, CAST(:unified_content_json AS jsonb), CAST(:segment_contents_json AS jsonb),
                        CAST(:agent_config_json AS jsonb), :operator_id, :operator_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                        CASE WHEN :status = 'active' THEN CURRENT_TIMESTAMP ELSE NULL END
                    )
                    RETURNING *
                    """
                ),
                {**normalized, "operator_id": _clean_text(operator_id) or "setup_wizard", "unified_content_json": _json_text(normalized["unified_content_json"]), "segment_contents_json": json.dumps(normalized["segment_contents_json"], ensure_ascii=False), "agent_config_json": _json_text(normalized["agent_config_json"])},
            ).mappings().first()
        task = _project_operation_task(dict(row or {}))
        return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_postgres", "task": task, "tasks": [task]}

    def get_operation_task(self, program_id: int, task_id: int) -> dict[str, Any]:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT t.*, g.group_name
                    FROM automation_operation_task t
                    LEFT JOIN automation_operation_task_group g ON g.id = t.group_id
                    WHERE t.program_id = :program_id
                      AND t.id = :task_id
                    LIMIT 1
                    """
                ),
                {"program_id": int(program_id), "task_id": int(task_id)},
            ).mappings().first()
        if not row:
            raise AutomationProgramDataUnavailable(f"operation task {task_id} not found")
        return _project_operation_task(dict(row))

    def update_operation_task(self, program_id: int, task_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        existing = self.get_operation_task(int(program_id), int(task_id))
        normalized = _normalize_operation_task_payload(payload, program_id=int(program_id), existing=existing)
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_operation_task
                    SET group_id = :group_id,
                        task_name = :task_name,
                        description = :description,
                        status = :status,
                        trigger_type = :trigger_type,
                        send_time = :send_time,
                        timezone = :timezone,
                        target_audience_code = :target_audience_code,
                        target_stage_code = :target_stage_code,
                        audience_day_offset = :audience_day_offset,
                        behavior_filter = :behavior_filter,
                        content_mode = :content_mode,
                        profile_segment_template_id = :profile_segment_template_id,
                        unified_content_json = CAST(:unified_content_json AS jsonb),
                        segment_contents_json = CAST(:segment_contents_json AS jsonb),
                        agent_config_json = CAST(:agent_config_json AS jsonb),
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP,
                        published_at = CASE WHEN :status = 'active' THEN COALESCE(published_at, CURRENT_TIMESTAMP) ELSE published_at END
                    WHERE program_id = :program_id
                      AND id = :task_id
                    RETURNING *
                    """
                ),
                {**normalized, "task_id": int(task_id), "operator_id": _clean_text(operator_id) or "setup_wizard", "unified_content_json": _json_text(normalized["unified_content_json"]), "segment_contents_json": json.dumps(normalized["segment_contents_json"], ensure_ascii=False), "agent_config_json": _json_text(normalized["agent_config_json"])},
            ).mappings().first()
        task = _project_operation_task(dict(row or {}))
        return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_postgres", "task": task}

    def copy_operation_task(self, program_id: int, task_id: int, *, operator_id: str) -> dict[str, Any]:
        existing = self.get_operation_task(int(program_id), int(task_id))
        payload = {**existing, "task_name": f"{existing.get('task_name') or '运营任务'} / 复制", "status": "draft"}
        return self.create_operation_task(int(program_id), payload, operator_id=operator_id)

    def archive_operation_task(self, program_id: int, task_id: int, *, operator_id: str) -> dict[str, Any]:
        return self.update_operation_task(int(program_id), int(task_id), {"status": "archived"}, operator_id=operator_id)

    def _project_row(self, row: dict[str, Any]) -> dict[str, Any]:
        program = {
            "id": int(row.get("id") or 0),
            "program_code": _clean_text(row.get("program_code")),
            "program_name": _clean_text(row.get("program_name")),
            "description": _clean_text(row.get("description")),
            "status": _clean_text(row.get("status")) or "draft",
            "config_json": _json_loads(row.get("config_json"), default={}),
            "created_by": _clean_text(row.get("created_by")),
            "updated_by": _clean_text(row.get("updated_by")),
            "created_at": _stringify_datetime(row.get("created_at")),
            "updated_at": _stringify_datetime(row.get("updated_at")),
        }
        summary = _program_summary(
            program,
            {
                "member_count": row.get("member_count"),
                "channel_count": row.get("channel_count"),
                "workflow_count": row.get("operation_task_count") or row.get("workflow_count"),
                "latest_execution_at": row.get("latest_execution_at"),
                "publish_state": _json_loads(row.get("publish_state"), default={}),
                "entry_publish_ready": self._entry_publish_ready(program, row),
                "full_publish_ready": self._full_publish_ready(program, row),
            },
        )
        return {"program": program, "summary": summary}

    def _entry_publish_ready(self, program: dict[str, Any], row: dict[str, Any]) -> bool:
        if _clean_text(program.get("status")) == "archived":
            return False
        has_config = bool(_json_loads(row.get("basic_payload"), default={}))
        is_default = _clean_text(program.get("program_code")) == "signup_conversion_v1"
        return (is_default or has_config) and int(row.get("channel_count") or 0) > 0

    def _full_publish_ready(self, program: dict[str, Any], row: dict[str, Any]) -> bool:
        segmentation = _json_loads(row.get("segmentation_payload"), default={})
        audience = _json_loads(row.get("audience_payload"), default={})
        rules = list(audience.get("rules") or []) or list(
            _audience_rule_view_model(audience, program_id=int(program.get("id") or 0)).get("rules") or []
        )
        return (
            self._entry_publish_ready(program, row)
            and bool(segmentation.get("questionnaire_id"))
            and _has_segmentation(segmentation)
            and bool(rules)
            and int(row.get("active_operation_task_count") or 0) > 0
        )


def _build_postgres_repository() -> PostgresAutomationProgramRepository:
    database_url = raw_database_url()
    if not database_url:
        raise AutomationProgramDataUnavailable("DATABASE_URL is required for automation program repository")
    return PostgresAutomationProgramRepository(get_engine(database_url))


def list_automation_programs_payload() -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().list_payload()
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    return _fixture_payload()


def get_automation_program_with_summary(program_id: int) -> dict[str, Any] | None:
    if production_data_ready():
        try:
            return _build_postgres_repository().get_program_with_summary(int(program_id))
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    if int(program_id) == int(_FIXTURE_PROGRAM["id"]):
        return {"program": deepcopy(_FIXTURE_PROGRAM), "summary": _fixture_summary()}
    return None


def get_automation_program_setup_payload(program_id: int, *, step: str = "basic") -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().get_setup_payload(int(program_id), step=step)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    if int(program_id) == int(_FIXTURE_PROGRAM["id"]):
        return _fixture_setup_payload(int(program_id), step=step)
    raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")


def get_automation_program_overview_payload(program_id: int) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().get_overview_payload(int(program_id))
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    if int(program_id) != int(_FIXTURE_PROGRAM["id"]):
        raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
    program = deepcopy(_FIXTURE_PROGRAM)
    program["id"] = int(program_id)
    return _program_data_overview_payload(
        program=program,
        member_count=0,
        stage_counts=[],
        source_status="next_local_preview",
    )


def get_automation_program_members_payload(
    program_id: int,
    *,
    stage_key: str = "all",
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().get_members_payload(
                int(program_id),
                stage_key=stage_key,
                page=page,
                page_size=page_size,
                keyword=keyword,
            )
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    if int(program_id) != int(_FIXTURE_PROGRAM["id"]):
        raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
    normalized_stage = _clean_text(stage_key) or "all"
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = min(max(int(page_size or 50), 1), 200)
    program = deepcopy(_FIXTURE_PROGRAM)
    program["id"] = int(program_id)
    return {
        "ok": True,
        "route_owner": "ai_crm_next",
        "source_status": "next_local_preview",
        "program_id": int(program_id),
        "program": program,
        "stage_key": normalized_stage,
        "stage_label": "全部成员" if normalized_stage == "all" else _program_member_stage_label(normalized_stage),
        "total": 0,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "items": [],
        "pagination": {
            "total": 0,
            "page": normalized_page,
            "page_size": normalized_page_size,
            "has_prev": False,
            "has_next": False,
            "prev_url": "",
            "next_url": "",
        },
    }


def copy_automation_program(program_id: int, *, operator_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().copy_program(int(program_id), operator_id=operator_id, payload=payload)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    copied_program = deepcopy(_FIXTURE_PROGRAM)
    copied_program["id"] = int(program_id) + 1000
    copied_program["program_name"] = _clean_text((payload or {}).get("program_name")) or f"{copied_program['program_name']} 副本"
    copied_program["program_code"] = _clean_text((payload or {}).get("program_code")) or f"{copied_program['program_code']}_copy"
    copied_program["status"] = "draft"
    copied_program["updated_at"] = datetime.now(timezone.utc).isoformat()
    return {"program": copied_program, "summary": _fixture_summary()}


def update_automation_program_basic_info(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().update_basic_info(int(program_id), payload, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    updated = deepcopy(_FIXTURE_PROGRAM)
    updated["id"] = int(program_id)
    updated["program_name"] = _clean_text(payload.get("program_name")) or updated["program_name"]
    updated["program_code"] = _clean_text(payload.get("program_code")) or updated["program_code"]
    updated["description"] = _clean_text(payload.get("description"))
    updated["status"] = _clean_text(payload.get("status")) or updated["status"]
    return {"program": updated, "summary": _fixture_summary()}


def save_automation_program_segmentation(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    normalized = _normalize_segmentation_payload(payload)
    _validate_option_categories(normalized)
    _validate_score_ranges(normalized)
    if production_data_ready():
        try:
            return _build_postgres_repository().save_segmentation(int(program_id), normalized, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    _FIXTURE_SEGMENTATION_BY_PROGRAM[int(program_id)] = deepcopy(normalized)
    return {
        "segmentation": {
            "id": 0,
            "block_key": BLOCK_SEGMENTATION,
            "payload": normalized,
            "status": "saved",
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "profile_segment_template": None,
    }


def save_automation_program_audience_entry_rule(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    normalized = _normalize_audience_entry_rule_payload(
        payload,
        validate=not bool((payload or {}).get("_allow_incomplete")),
    )
    if production_data_ready():
        try:
            return _build_postgres_repository().save_audience_entry_rule(int(program_id), payload, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    return {
        "audience_entry_rule": {
            "id": 0,
            "block_key": BLOCK_AUDIENCE_ENTRY_RULE,
            "payload": normalized,
            "status": "saved",
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "next_steps": _audience_next_steps(normalized),
    }


def list_automation_program_operation_tasks(program_id: int) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().list_operation_tasks(int(program_id))
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    return _fixture_operation_payload(int(program_id))


def create_automation_program_operation_task_group(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().create_operation_task_group(int(program_id), payload, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    global _FIXTURE_OPERATION_GROUP_ID
    group_name = _clean_text(payload.get("group_name") or payload.get("name"))
    if not group_name:
        raise ValueError("分组名称不能为空")
    _FIXTURE_OPERATION_GROUP_ID += 1
    group = {
        "id": _FIXTURE_OPERATION_GROUP_ID,
        "program_id": int(program_id),
        "group_name": group_name,
        "sort_order": int(payload.get("sort_order") or len(_FIXTURE_OPERATION_GROUPS) + 1),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "archived_at": "",
    }
    _FIXTURE_OPERATION_GROUPS.append(group)
    return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_fixture", "group": _project_operation_task_group(group), "groups": [_project_operation_task_group(group)]}


def delete_automation_program_operation_task_group(program_id: int, group_id: int, *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().archive_operation_task_group(int(program_id), int(group_id), operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    for group in _FIXTURE_OPERATION_GROUPS:
        if int(group.get("program_id") or 0) == int(program_id) and int(group.get("id") or 0) == int(group_id):
            group["archived_at"] = datetime.now(timezone.utc).isoformat()
            group["updated_at"] = datetime.now(timezone.utc).isoformat()
            for task in _FIXTURE_OPERATION_TASKS:
                if int(task.get("program_id") or 0) == int(program_id) and int(task.get("group_id") or 0) == int(group_id):
                    task["group_id"] = None
            return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_fixture", "group": _project_operation_task_group(group)}
    raise AutomationProgramDataUnavailable(f"operation task group {group_id} not found")


def create_automation_program_operation_task(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().create_operation_task(int(program_id), payload, operator_id=operator_id)
        except ValueError:
            raise
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    global _FIXTURE_OPERATION_TASK_ID
    _FIXTURE_OPERATION_TASK_ID += 1
    normalized = _normalize_operation_task_payload(payload, program_id=int(program_id))
    now = datetime.now(timezone.utc).isoformat()
    task = {**normalized, "id": _FIXTURE_OPERATION_TASK_ID, "created_at": now, "updated_at": now, "published_at": now if normalized["status"] == "active" else ""}
    _FIXTURE_OPERATION_TASKS.append(task)
    projected = _project_operation_task(task)
    return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_fixture", "task": projected, "tasks": [projected]}


def _fixture_get_operation_task(program_id: int, task_id: int) -> dict[str, Any]:
    for task in _FIXTURE_OPERATION_TASKS:
        if int(task.get("program_id") or 0) == int(program_id) and int(task.get("id") or 0) == int(task_id):
            return _project_operation_task(task)
    raise AutomationProgramDataUnavailable(f"operation task {task_id} not found")


def update_automation_program_operation_task(program_id: int, task_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().update_operation_task(int(program_id), int(task_id), payload, operator_id=operator_id)
        except ValueError:
            raise
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    for index, task in enumerate(_FIXTURE_OPERATION_TASKS):
        if int(task.get("program_id") or 0) == int(program_id) and int(task.get("id") or 0) == int(task_id):
            normalized = _normalize_operation_task_payload(payload, program_id=int(program_id), existing=_project_operation_task(task))
            now = datetime.now(timezone.utc).isoformat()
            _FIXTURE_OPERATION_TASKS[index] = {**task, **normalized, "updated_at": now, "published_at": task.get("published_at") or (now if normalized["status"] == "active" else "")}
            return {"ok": True, "route_owner": "ai_crm_next", "source_status": "next_fixture", "task": _project_operation_task(_FIXTURE_OPERATION_TASKS[index])}
    raise AutomationProgramDataUnavailable(f"operation task {task_id} not found")


def copy_automation_program_operation_task(program_id: int, task_id: int, *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().copy_operation_task(int(program_id), int(task_id), operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    existing = _fixture_get_operation_task(int(program_id), int(task_id))
    return create_automation_program_operation_task(int(program_id), {**existing, "task_name": f"{existing.get('task_name') or '运营任务'} / 复制", "status": "draft"}, operator_id=operator_id)


def set_automation_program_operation_task_status(program_id: int, task_id: int, status: str, *, operator_id: str) -> dict[str, Any]:
    if _clean_text(status) not in {"draft", "active", "paused", "archived"}:
        raise ValueError("运营任务状态不正确")
    return update_automation_program_operation_task(int(program_id), int(task_id), {"status": _clean_text(status)}, operator_id=operator_id)


PREVIEW_REASON_KEYS = (
    "source_channel_missing",
    "program_channel_not_matched",
    "audience_code_not_matched",
    "entry_reason_not_matched",
    "day_offset_not_due",
    "behavior_filter_not_matched",
    "profile_segment_not_matched",
    "content_missing",
    "external_contact_id_missing",
)


STAGE_PREVIEW_ENTRY_REASON = {
    "order_review": "order_review_pending",
    "questionnaire_review": "questionnaire_review_pending",
    "operating": "audience_entry_rule_passed",
    "converted": "conversion_product_paid",
}


def _preview_required_entry_reason(task: dict[str, Any]) -> str:
    return STAGE_PREVIEW_ENTRY_REASON.get(_clean_text(task.get("target_stage_code")), "")


def _agent_preview_runtime_context(
    task: dict[str, Any],
    row: dict[str, Any],
    *,
    base_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if _clean_text(task.get("content_mode")) != "agent":
        return None
    context = dict(base_context or _agent_task_runtime_context(task) or {})
    answer_count = int(row.get("questionnaire_answer_count") or 0)
    context["questionnaire_context_available"] = answer_count > 0
    context["questionnaire_submission_id"] = int(row.get("questionnaire_submission_id") or 0)
    context["questionnaire_answer_count"] = answer_count
    if "questionnaire_context_required" not in context:
        context["questionnaire_context_required"] = bool((dict(task.get("agent_config_json") or {})).get("questionnaire_context_required")) or (
            "questionnaire" in list(context.get("enabled_context_sources") or [])
        )
    return context


def _preview_content_ready(
    task: dict[str, Any],
    member: dict[str, Any],
    *,
    agent_runtime_context: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    mode = _clean_text(task.get("content_mode")) or "unified"
    if mode == "agent":
        return bool(agent_runtime_diagnostics(task, agent_runtime_context=agent_runtime_context).get("expected_send_body_present")), "agent"
    if mode == "behavior_layered":
        key = _clean_text(member.get("behavior_tier_key"))
        for item in list(task.get("segment_contents_json") or []):
            if _clean_text((item or {}).get("segment_key")) == key:
                return has_send_body(dict(item or {})), key
        return False, key
    if mode == "profile_layered":
        key = _clean_text(member.get("profile_segment_key"))
        for item in list(task.get("segment_contents_json") or []):
            if _clean_text((item or {}).get("segment_key")) == key:
                return has_send_body(dict(item or {})), key
        return False, key
    return has_send_body(dict(task.get("unified_content_json") or {})), "unified"


def _preview_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = _clean_text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _preview_day_offset_due(task: dict[str, Any], row: dict[str, Any]) -> bool:
    if _clean_text(task.get("trigger_type")) == "audience_entered":
        return True
    entered_at = _preview_datetime(row.get("entered_at"))
    if entered_at is None:
        return False
    local_tz = timezone(timedelta(hours=8))
    entered_date = entered_at.astimezone(local_tz).date() if entered_at.tzinfo else entered_at.date()
    current_date = datetime.now(local_tz).date()
    offset = max(int(task.get("audience_day_offset") or 1), 1)
    return current_date >= entered_date + timedelta(days=offset - 1)


def _preview_candidates_next(program_id: int, task: dict[str, Any]) -> dict[str, Any]:
    if not production_data_ready():
        agent_context = _agent_task_runtime_context(task, require_questionnaire_context=False)
        diagnostics = publishable_diagnostics(task, agent_runtime_context=agent_context)
        return {
            "target_count": 0,
            "segment_counts": {},
            "filtered_out_counts": {},
            "reasons": [],
            "content_diagnostics": diagnostics,
            "agent_runtime_diagnostics": agent_runtime_diagnostics(task, agent_runtime_context=agent_context) if task["content_mode"] == "agent" else {},
            "blocked_reason": "production_data_not_ready",
        }
    database_url = raw_database_url()
    if not database_url:
        raise AutomationProgramDataUnavailable("DATABASE_URL is required for operation task audience preview")
    engine = get_engine(database_url)
    with engine.connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT
                        e.id AS audience_entry_id,
                        e.audience_code,
                        e.entry_reason,
                        e.entered_at,
                        m.id AS member_id,
                        m.external_contact_id,
                        qs.questionnaire_submission_id,
                        COALESCE(qs.questionnaire_answer_count, 0) AS questionnaire_answer_count,
                        COALESCE(pm.latest_source_channel_id, pm.source_channel_id, m.source_channel_id) AS source_channel_id,
                        COALESCE(NULLIF(pm.state_payload_json ->> 'behavior_tier_key', ''), m.behavior_tier_key) AS behavior_tier_key,
                        COALESCE(NULLIF(pm.state_payload_json ->> 'profile_segment_key', ''), m.profile_segment_key) AS profile_segment_key,
                        c.program_id AS channel_program_id,
                        b.program_id AS binding_program_id
                    FROM automation_member_audience_entry e
                    JOIN automation_member m ON m.id = e.member_id
                    LEFT JOIN automation_program_member pm
                      ON pm.program_id = :program_id
                     AND pm.external_contact_id = m.external_contact_id
                     AND pm.in_program = TRUE
                    LEFT JOIN automation_channel c
                      ON c.id = COALESCE(pm.latest_source_channel_id, pm.source_channel_id, m.source_channel_id)
                    LEFT JOIN automation_program_channel_binding b
                      ON b.channel_id = COALESCE(pm.latest_source_channel_id, pm.source_channel_id, m.source_channel_id)
                     AND b.program_id = :program_id
                    LEFT JOIN LATERAL (
                        SELECT
                            latest_qs.id AS questionnaire_submission_id,
                            (
                                SELECT COUNT(*)
                                FROM questionnaire_submission_answers qsa
                                WHERE qsa.submission_id = latest_qs.id
                            ) AS questionnaire_answer_count
                        FROM questionnaire_submissions latest_qs
                        WHERE latest_qs.external_userid = m.external_contact_id
                        ORDER BY latest_qs.submitted_at DESC, latest_qs.id DESC
                        LIMIT 1
                    ) qs ON TRUE
                    WHERE e.is_current = TRUE
                    """
                ),
                {"program_id": int(program_id)},
            ).mappings()
        ]
    filtered_out_counts = {key: 0 for key in PREVIEW_REASON_KEYS}
    segment_counts: dict[str, int] = {}
    target_count = 0
    required_reason = _preview_required_entry_reason(task)
    behavior_filter = _clean_text(task.get("behavior_filter")) or "none"
    task_agent_context = _agent_task_runtime_context(task)
    aggregate_agent_context = dict(task_agent_context or {})
    for row in rows:
        reasons: list[str] = []
        if not int(row.get("source_channel_id") or 0):
            reasons.append("source_channel_missing")
        elif int(row.get("channel_program_id") or 0) != int(program_id) and int(row.get("binding_program_id") or 0) != int(program_id):
            reasons.append("program_channel_not_matched")
        if _clean_text(row.get("audience_code")) != _clean_text(task.get("target_audience_code")):
            reasons.append("audience_code_not_matched")
        if required_reason and _clean_text(row.get("entry_reason")) != required_reason:
            reasons.append("entry_reason_not_matched")
        if not _preview_day_offset_due(task, row):
            reasons.append("day_offset_not_due")
        if behavior_filter != "none" and _clean_text(row.get("behavior_tier_key")) != behavior_filter:
            reasons.append("behavior_filter_not_matched")
        if _clean_text(task.get("content_mode")) == "profile_layered" and not _clean_text(row.get("profile_segment_key")):
            reasons.append("profile_segment_not_matched")
        row_agent_context = _agent_preview_runtime_context(task, row, base_context=task_agent_context)
        if row_agent_context and bool(row_agent_context.get("questionnaire_context_available")):
            aggregate_agent_context.update(
                {
                    "questionnaire_context_available": True,
                    "questionnaire_submission_id": int(row_agent_context.get("questionnaire_submission_id") or 0),
                    "questionnaire_answer_count": int(aggregate_agent_context.get("questionnaire_answer_count") or 0)
                    + int(row_agent_context.get("questionnaire_answer_count") or 0),
                }
            )
        content_ready, segment_key = _preview_content_ready(task, row, agent_runtime_context=row_agent_context)
        if not content_ready:
            reasons.append("content_missing")
        if not _clean_text(row.get("external_contact_id")):
            reasons.append("external_contact_id_missing")
        if reasons:
            for reason in dict.fromkeys(reasons):
                filtered_out_counts[reason] += 1
            continue
        target_count += 1
        if segment_key:
            segment_counts[segment_key] = segment_counts.get(segment_key, 0) + 1
    diagnostics = publishable_diagnostics(task, agent_runtime_context=aggregate_agent_context or task_agent_context)
    return {
        "target_count": target_count,
        "segment_counts": segment_counts,
        "filtered_out_counts": {key: value for key, value in filtered_out_counts.items() if value},
        "reasons": [key for key, value in filtered_out_counts.items() if value],
        "content_diagnostics": diagnostics,
        "agent_runtime_diagnostics": agent_runtime_diagnostics(task, agent_runtime_context=aggregate_agent_context or task_agent_context)
        if task["content_mode"] == "agent"
        else {},
    }


def preview_automation_program_operation_task_audience(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_operation_task_payload(
        {"task_name": dict(payload or {}).get("task_name") or "预览任务", **dict(payload or {})},
        program_id=int(program_id),
        validate_active=False,
    )
    try:
        preview = _preview_candidates_next(int(program_id), normalized)
    except Exception as exc:
        if production_data_ready():
            raise AutomationProgramDataUnavailable(str(exc)) from exc
        agent_context = _agent_task_runtime_context(normalized, require_questionnaire_context=False)
        diagnostics = publishable_diagnostics(normalized, agent_runtime_context=agent_context)
        preview = {
            "target_count": 0,
            "segment_counts": {},
            "filtered_out_counts": {},
            "reasons": [],
            "content_diagnostics": diagnostics,
            "blocked_reason": str(exc),
        }
    return {
        "ok": True,
        "route_owner": "ai_crm_next",
        "source_status": "next_postgres" if production_data_ready() else "next_fixture",
        "preview": preview,
    }


def update_automation_program_operation_task_send_strategy(program_id: int, task_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    patch: dict[str, Any] = {"content_mode": _clean_text(payload.get("content_mode")) or "unified"}
    if patch["content_mode"] == "profile_layered":
        patch["profile_segment_template_id"] = int(payload.get("profile_segment_template_id") or 0) or None
    if patch["content_mode"] == "agent":
        agent_code = _clean_text(payload.get("agent_code"))
        if agent_code:
            current = _fixture_get_operation_task(program_id, task_id) if not production_data_ready() else _build_postgres_repository().get_operation_task(program_id, task_id)
            agent_config = dict(current.get("agent_config_json") or {})
            agent_config["agent_code"] = agent_code
            patch["agent_config_json"] = agent_config
    return update_automation_program_operation_task(int(program_id), int(task_id), patch, operator_id=operator_id)


def save_automation_program_operation_task_content(
    program_id: int,
    task_id: int,
    payload: dict[str, Any],
    *,
    content_kind: str,
    segment_key: str = "",
    operator_id: str,
) -> dict[str, Any]:
    current = _fixture_get_operation_task(program_id, task_id) if not production_data_ready() else _build_postgres_repository().get_operation_task(program_id, task_id)
    content_package = dict(payload.get("content_package") or {})
    patch: dict[str, Any] = {}
    if content_kind == "unified":
        patch = {"content_mode": "unified", "unified_content_json": content_package}
    elif content_kind in {"profile", "behavior"}:
        rows = [dict(item) for item in list(current.get("segment_contents_json") or []) if isinstance(item, dict)]
        next_rows = [item for item in rows if _clean_text(item.get("segment_key")) != _clean_text(segment_key)]
        next_rows.append({"segment_key": _clean_text(segment_key), "segment_name": _clean_text(payload.get("segment_name")), "content_package": content_package, **content_package})
        patch = {"content_mode": "profile_layered" if content_kind == "profile" else "behavior_layered", "segment_contents_json": next_rows}
        if content_kind == "profile":
            patch["profile_segment_template_id"] = int(payload.get("profile_segment_template_id") or current.get("profile_segment_template_id") or 0) or None
    elif content_kind == "agent":
        agent_config = dict(current.get("agent_config_json") or {})
        agent_config.update(content_package)
        agent_config["agent_code"] = _clean_text(payload.get("agent_code")) or _clean_text(agent_config.get("agent_code"))
        for key in ("requirement", "fallback_content", "prompt", "material_prompt"):
            if key in payload:
                agent_config[key] = _clean_text(payload.get(key))
        content_text = _clean_text(content_package.get("content_text"))
        if content_text and not _clean_text(agent_config.get("requirement")):
            agent_config["requirement"] = content_text
        patch = {"content_mode": "agent", "agent_config_json": agent_config}
    else:
        raise ValueError("发送内容类型不正确")
    return update_automation_program_operation_task(int(program_id), int(task_id), patch, operator_id=operator_id)


def update_automation_program_status(program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().update_status(int(program_id), status=status, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    updated = deepcopy(_FIXTURE_PROGRAM)
    updated["id"] = int(program_id)
    updated["status"] = status
    return {"program": updated, "summary": _fixture_summary()}


def publish_automation_program_entry(program_id: int, *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().publish_program(int(program_id), operator_id=operator_id, scope="entry")
        except ValueError:
            raise
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    payload = _fixture_setup_payload(int(program_id), step="publish")
    if not bool(((payload.get("publish_check") or {}).get("entry") or {}).get("passed")):
        raise ValueError("入口发布检查未通过")
    program = deepcopy(_FIXTURE_PROGRAM)
    program["id"] = int(program_id)
    program["status"] = "active"
    return {
        "program": program,
        "summary": _program_summary(program, {"channel_count": 1, "publish_state": {"entry_published": True, "full_published": False}}),
        "publish_state": {"entry_published": True, "full_published": False},
        "publish_check": payload.get("publish_check") or {},
    }


def publish_automation_program_full(program_id: int, *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().publish_program(int(program_id), operator_id=operator_id, scope="full")
        except ValueError:
            raise
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    payload = _fixture_setup_payload(int(program_id), step="publish")
    if not bool(((payload.get("publish_check") or {}).get("full") or {}).get("passed")):
        raise ValueError("完整自动化发布检查未通过")
    program = deepcopy(_FIXTURE_PROGRAM)
    program["id"] = int(program_id)
    program["status"] = "active"
    return {
        "program": program,
        "summary": _program_summary(program, {"channel_count": 1, "publish_state": {"entry_published": True, "full_published": True}}),
        "publish_state": {"entry_published": True, "full_published": True},
        "publish_check": payload.get("publish_check") or {},
    }
