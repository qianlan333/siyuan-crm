from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any

import requests
from flask import current_app

from ...db import get_db
from ...infra.wecom_runtime import get_app_runtime_client
from ...infra.settings import get_setting
from ...wecom_client import WeComClientError
from ..tags import repo as tags_repo
from ..tags import service as tags_service
from ..user_ops import page_service as user_ops_page_service
from . import program_repo, program_service, repo as orchestration_repo, workflow_repo
from .message_activity_client import get_message_activity_db_status, query_message_activity_counts
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
    NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER,
    NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY,
    NODE_TRIGGER_MODE_SCHEDULED,
    RECIPIENT_FILTER_BASIS_BEHAVIOR,
    RECIPIENT_FILTER_BASIS_NONE,
    SEGMENTATION_BASIS_BEHAVIOR,
    SEGMENTATION_BASIS_NONE,
    SEGMENTATION_BASIS_PROFILE,
    WORKFLOW_STATUS_ACTIVE,
    WORKFLOW_STATUS_DRAFT,
    WORKFLOW_STATUS_PAUSED,
    list_supported_agent_binding_scopes,
    list_supported_behavior_tiers,
    list_supported_conversion_audiences,
    list_supported_generation_modes,
    list_supported_node_content_variant_scopes,
    list_supported_node_trigger_modes,
    list_supported_recipient_filter_bases,
    list_supported_segmentation_bases,
    list_supported_workflow_statuses,
)

_ALLOWED_AUDIENCES = {
    AUDIENCE_PENDING_QUESTIONNAIRE,
    AUDIENCE_OPERATING,
    AUDIENCE_CONVERTED,
}
_ALLOWED_SEGMENTATION_BASES = {
    SEGMENTATION_BASIS_NONE,
    SEGMENTATION_BASIS_PROFILE,
    SEGMENTATION_BASIS_BEHAVIOR,
}
_ALLOWED_RECIPIENT_FILTER_BASES = {
    RECIPIENT_FILTER_BASIS_NONE,
    RECIPIENT_FILTER_BASIS_BEHAVIOR,
}
_ALLOWED_GENERATION_MODES = {
    GENERATION_MODE_MANUAL_LAYERED,
    GENERATION_MODE_AUTO_LAYERED_REWRITE,
    GENERATION_MODE_PERSONALIZED_SINGLE,
}
_ALLOWED_WORKFLOW_STATUSES = {
    WORKFLOW_STATUS_DRAFT,
    WORKFLOW_STATUS_ACTIVE,
    WORKFLOW_STATUS_PAUSED,
}
_ALLOWED_NODE_TRIGGER_MODES = {
    NODE_TRIGGER_MODE_SCHEDULED,
    NODE_TRIGGER_MODE_DAILY_RECURRING,
    NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
}

NODE_CONTENT_MODE_STANDARD_DIRECT = "standard_direct"
NODE_CONTENT_MODE_MANUAL_LAYERED = "manual_layered"
NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE = "standard_layered_rewrite"
NODE_CONTENT_MODE_PERSONALIZED_SINGLE = "personalized_single"

_ALLOWED_NODE_CONTENT_MODES = {
    NODE_CONTENT_MODE_STANDARD_DIRECT,
    NODE_CONTENT_MODE_MANUAL_LAYERED,
    NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE,
    NODE_CONTENT_MODE_PERSONALIZED_SINGLE,
}

_NODE_CONTENT_META_KEY = "_automation_conversion_node_meta"
_BAZHUAYU_DEFAULT_WEBHOOK_URL = "https://api-rpa.bazhuayu.com/api/v1/bots/webhooks/69cc9c20612e78c4472b2f4d/invoke"
_BAZHUAYU_DEFAULT_SIGNING_SECRET = "mPwS+MOxF0O9dyED6z5LlA=="
_BAZHUAYU_DEFAULT_TIMEOUT_SECONDS = 15
_OVERVIEW_SIGNUP_TAG_NAME = "报名引流品"
_SETUP_SEGMENTATION_BLOCK_KEY = "questionnaire_segmentation"
_SETUP_OPTION_CATEGORY_MODE = "single_question_option_category"


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
        result = default
    if minimum is not None:
        result = max(result, minimum)
    return result


def _truncate_text(value: Any, *, limit: int = 120) -> str:
    text = _normalized_text(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _setting_text(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _setting_int(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def _slugify_code(value: Any, *, prefix: str) -> str:
    raw = _normalized_text(value).lower().replace(" ", "_").replace("-", "_")
    safe = "".join(char if (char.isalnum() or char == "_") else "_" for char in raw)
    compact = "_".join(part for part in safe.split("_") if part)
    return compact or prefix


def _json_fingerprint(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _behavior_tier_codes() -> list[str]:
    return [str(item["tier_code"]) for item in list_supported_behavior_tiers()]


def _behavior_tier_map() -> dict[str, dict[str, Any]]:
    return {str(item["tier_code"]): dict(item) for item in list_supported_behavior_tiers()}


def _normalize_behavior_tier_key_list(payload: Any) -> list[str]:
    items = payload if isinstance(payload, list) else []
    normalized: list[str] = []
    seen: set[str] = set()
    allowed = set(_behavior_tier_codes())
    for item in items:
        tier_key = _normalized_text(item)
        if not tier_key or tier_key in seen:
            continue
        if tier_key not in allowed:
            raise ValueError(f"invalid recipient_behavior_tier_key: {tier_key}")
        seen.add(tier_key)
        normalized.append(tier_key)
    return normalized


def _decode_recipient_filter_config(behavior_tier_scheme: str) -> dict[str, Any]:
    raw_text = _normalized_text(behavior_tier_scheme)
    if raw_text in {"", "fixed_v1"}:
        return {
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_NONE,
            "recipient_behavior_tier_keys": [],
        }
    try:
        payload = json.loads(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {
            "recipient_filter_basis": RECIPIENT_FILTER_BASIS_NONE,
            "recipient_behavior_tier_keys": [],
        }
    basis = _normalized_text((payload or {}).get("recipient_filter_basis")) or RECIPIENT_FILTER_BASIS_NONE
    if basis not in _ALLOWED_RECIPIENT_FILTER_BASES:
        basis = RECIPIENT_FILTER_BASIS_NONE
    try:
        tier_keys = _normalize_behavior_tier_key_list((payload or {}).get("recipient_behavior_tier_keys") or [])
    except ValueError:
        tier_keys = []
    if basis != RECIPIENT_FILTER_BASIS_BEHAVIOR:
        tier_keys = []
    return {
        "recipient_filter_basis": basis,
        "recipient_behavior_tier_keys": tier_keys,
    }


def _encode_recipient_filter_config(recipient_filter_basis: str, recipient_behavior_tier_keys: list[str]) -> str:
    basis = _normalized_text(recipient_filter_basis) or RECIPIENT_FILTER_BASIS_NONE
    tier_keys = [str(item) for item in recipient_behavior_tier_keys or []]
    if basis == RECIPIENT_FILTER_BASIS_NONE and not tier_keys:
        return "fixed_v1"
    return json.dumps(
        {
            "recipient_filter_basis": basis,
            "recipient_behavior_tier_keys": tier_keys,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _workflow_status_to_enabled(status: str) -> bool:
    return _normalized_text(status) == WORKFLOW_STATUS_ACTIVE


def _validate_send_time(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) != 5 or text[2] != ":":
        raise ValueError("send_time must be HH:MM")
    hour_text, minute_text = text.split(":", 1)
    if not hour_text.isdigit() or not minute_text.isdigit():
        raise ValueError("send_time must be HH:MM")
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("send_time must be HH:MM")
    return f"{hour:02d}:{minute:02d}"


def _validate_node_trigger_mode(value: Any) -> str:
    normalized = _normalized_text(value) or NODE_TRIGGER_MODE_SCHEDULED
    if normalized not in _ALLOWED_NODE_TRIGGER_MODES:
        raise ValueError("trigger_mode must be one of scheduled, daily_recurring, audience_entered")
    return normalized


def _workflow_generation_mode_to_node_content_mode(value: Any) -> str:
    generation_mode = _normalized_text(value)
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        return NODE_CONTENT_MODE_MANUAL_LAYERED
    if generation_mode == GENERATION_MODE_AUTO_LAYERED_REWRITE:
        return NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        return NODE_CONTENT_MODE_PERSONALIZED_SINGLE
    return NODE_CONTENT_MODE_STANDARD_DIRECT


def _node_content_mode_to_generation_mode(value: Any) -> str:
    content_mode = _normalized_text(value)
    if content_mode == NODE_CONTENT_MODE_MANUAL_LAYERED:
        return GENERATION_MODE_MANUAL_LAYERED
    if content_mode == NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE:
        return GENERATION_MODE_AUTO_LAYERED_REWRITE
    if content_mode == NODE_CONTENT_MODE_PERSONALIZED_SINGLE:
        return GENERATION_MODE_PERSONALIZED_SINGLE
    return ""


def _normalize_node_content_mode(value: Any, *, default: str) -> str:
    normalized = _normalized_text(value) or _normalized_text(default) or NODE_CONTENT_MODE_STANDARD_DIRECT
    if normalized not in _ALLOWED_NODE_CONTENT_MODES:
        raise ValueError("content_mode must be one of standard_direct, manual_layered, standard_layered_rewrite, personalized_single")
    return normalized


def _strip_node_content_meta(payload: Any) -> dict[str, Any]:
    cleaned = dict(payload or {})
    cleaned.pop(_NODE_CONTENT_META_KEY, None)
    return cleaned


def _build_node_content_payload_json(
    payload: Any,
    *,
    content_mode: str,
    segmentation_basis: str,
) -> dict[str, Any]:
    base_payload = _strip_node_content_meta(payload)
    base_payload[_NODE_CONTENT_META_KEY] = {
        "content_mode": _normalized_text(content_mode) or NODE_CONTENT_MODE_STANDARD_DIRECT,
        "segmentation_basis": _normalized_text(segmentation_basis) or SEGMENTATION_BASIS_NONE,
    }
    return base_payload


def _extract_node_content_meta(content_payload: Any) -> dict[str, str]:
    payload = dict(content_payload or {})
    meta = dict(payload.get(_NODE_CONTENT_META_KEY) or {})
    content_mode = _normalized_text(meta.get("content_mode"))
    if content_mode not in _ALLOWED_NODE_CONTENT_MODES:
        content_mode = ""
    segmentation_basis = _normalized_text(meta.get("segmentation_basis"))
    if segmentation_basis not in _ALLOWED_SEGMENTATION_BASES:
        segmentation_basis = ""
    return {
        "content_mode": content_mode,
        "segmentation_basis": segmentation_basis,
    }


def _binding_scope_to_segmentation_basis(binding_scope: str) -> str:
    normalized = _normalized_text(binding_scope)
    if normalized == AGENT_BINDING_SCOPE_PROFILE_CATEGORY:
        return SEGMENTATION_BASIS_PROFILE
    if normalized == AGENT_BINDING_SCOPE_BEHAVIOR_TIER:
        return SEGMENTATION_BASIS_BEHAVIOR
    return SEGMENTATION_BASIS_NONE


def _variant_scope_to_segmentation_basis(variant_scope: str) -> str:
    normalized = _normalized_text(variant_scope)
    if normalized == NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY:
        return SEGMENTATION_BASIS_PROFILE
    if normalized == NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER:
        return SEGMENTATION_BASIS_BEHAVIOR
    return SEGMENTATION_BASIS_NONE


def _allowed_manual_variant_keys_for_basis(workflow_bundle: dict[str, Any], segmentation_basis: str) -> tuple[str, list[str]]:
    normalized_basis = _normalized_text(segmentation_basis)
    if normalized_basis == SEGMENTATION_BASIS_PROFILE:
        keys = [
            _normalized_text(item.get("category_key"))
            for item in (workflow_bundle.get("profile_segment_template") or {}).get("categories") or []
            if bool(item.get("enabled"))
        ]
        return NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY, keys
    if normalized_basis == SEGMENTATION_BASIS_BEHAVIOR:
        return NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER, _behavior_tier_codes()
    return "", []


def _content_mode_uses_standard_content(content_mode: str) -> bool:
    return _normalized_text(content_mode) in {
        NODE_CONTENT_MODE_STANDARD_DIRECT,
        NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE,
    }


def _normalize_template_categories_payload(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    seen_category_keys: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError("category must be an object")
        category_key = _slugify_code(item.get("category_key") or item.get("key") or item.get("category_name"), prefix=f"category_{index}")
        if category_key in seen_category_keys:
            raise ValueError(f"duplicate category_key: {category_key}")
        seen_category_keys.add(category_key)
        category_name = _normalized_text(item.get("category_name") or item.get("name"))
        if not category_name:
            raise ValueError("category_name is required")
        raw_option_ids = item.get("option_ids")
        if raw_option_ids is None:
            raw_option_ids = [mapping.get("option_id") for mapping in item.get("option_mappings") or [] if isinstance(mapping, dict)]
        if not isinstance(raw_option_ids or [], list):
            raise ValueError("option_ids must be an array")
        option_ids: list[int] = []
        seen_option_ids: set[int] = set()
        for option_id in raw_option_ids or []:
            normalized_option_id = _normalize_int(option_id, default=0, minimum=1)
            if normalized_option_id <= 0:
                raise ValueError("option_id must be a positive integer")
            if normalized_option_id in seen_option_ids:
                continue
            seen_option_ids.add(normalized_option_id)
            option_ids.append(normalized_option_id)
        normalized.append(
            {
                "category_key": category_key,
                "category_name": category_name,
                "description": _normalized_text(item.get("description")),
                "sort_order": _normalize_int(item.get("sort_order"), default=index, minimum=0),
                "enabled": _normalize_bool(item.get("enabled"), default=True),
                "option_ids": option_ids,
            }
        )
    return normalized


def _normalize_workflow_audiences(payload: Any) -> list[str]:
    items = payload if isinstance(payload, list) else []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        audience_code = _normalized_text(item.get("audience_code") if isinstance(item, dict) else item)
        if not audience_code:
            continue
        if audience_code not in _ALLOWED_AUDIENCES:
            raise ValueError(f"invalid audience_code: {audience_code}")
        if audience_code in seen:
            continue
        seen.add(audience_code)
        normalized.append(audience_code)
    if not normalized:
        raise ValueError("audiences is required")
    return normalized


def _normalize_workflow_agent_bindings(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    seen_scope_keys: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("agent_bindings item must be an object")
        agent_code = _normalized_text(item.get("agent_code"))
        if not agent_code:
            raise ValueError("agent_code is required")
        binding_scope = _normalized_text(item.get("binding_scope")) or AGENT_BINDING_SCOPE_DEFAULT
        if binding_scope not in {
            AGENT_BINDING_SCOPE_DEFAULT,
            AGENT_BINDING_SCOPE_PROFILE_CATEGORY,
            AGENT_BINDING_SCOPE_BEHAVIOR_TIER,
            AGENT_BINDING_SCOPE_PERSONALIZED,
        }:
            raise ValueError("invalid binding_scope")
        segment_key = _normalized_text(item.get("segment_key"))
        identity = (binding_scope, segment_key)
        if identity in seen_scope_keys:
            raise ValueError(f"duplicate binding for {binding_scope}:{segment_key}")
        seen_scope_keys.add(identity)
        normalized.append(
            {
                "node_id": _normalize_int(item.get("node_id"), default=0, minimum=0) or None,
                "binding_scope": binding_scope,
                "segment_key": segment_key,
                "agent_code": agent_code,
            }
        )
    return normalized


def _normalize_node_variants_payload(payload: Any) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    seen_segment_keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("content_variants item must be an object")
        segment_key = _normalized_text(item.get("segment_key"))
        if not segment_key:
            raise ValueError("content_variants.segment_key is required")
        if segment_key in seen_segment_keys:
            raise ValueError(f"duplicate content_variants.segment_key: {segment_key}")
        seen_segment_keys.add(segment_key)
        normalized.append(
            {
                "segment_key": segment_key,
                "content_text": _normalized_text(item.get("content_text")),
                "content_payload_json": dict(item.get("content_payload_json") or item.get("content_payload") or {}),
            }
        )
    return normalized


def _validate_segmentation_question(questionnaire_id: int, question_id: int, categories: list[dict[str, Any]]) -> dict[str, Any]:
    questionnaire = workflow_repo.get_questionnaire_row(questionnaire_id)
    if not questionnaire:
        raise LookupError("questionnaire not found")
    question = workflow_repo.get_questionnaire_question_row(questionnaire_id, question_id)
    if not question:
        raise LookupError("segmentation question not found")
    question_type = _normalized_text(question.get("type"))
    if question_type not in {"single_choice", "multi_choice"}:
        raise ValueError("segmentation question must be single_choice or multi_choice")
    options = workflow_repo.list_questionnaire_option_rows(question_id)
    option_map = {int(item["id"]): dict(item) for item in options}
    used_option_ids: dict[int, str] = {}
    for category in categories:
        for option_id in category["option_ids"]:
            if option_id not in option_map:
                raise ValueError(f"invalid option_id for selected question: {option_id}")
            if option_id in used_option_ids:
                raise ValueError(f"option_id {option_id} is already mapped to category {used_option_ids[option_id]}")
            used_option_ids[option_id] = category["category_key"]
    return {
        "questionnaire": questionnaire,
        "question": question,
        "options": options,
    }


def _profile_segment_category_label(category: dict[str, Any], *, fallback_index: int = 0) -> str:
    return (
        _normalized_text(category.get("category_name"))
        or _normalized_text(category.get("category_key"))
        or (f"分类{fallback_index}" if fallback_index > 0 else "分类")
    )


def _build_profile_segment_template_validity(
    *,
    template: dict[str, Any],
    questionnaire: dict[str, Any] | None,
    question: dict[str, Any] | None,
    categories: list[dict[str, Any]],
) -> dict[str, Any]:
    reason_codes: list[str] = []
    reason_messages: list[str] = []

    def add_reason(code: str, message: str) -> None:
        normalized_code = _normalized_text(code)
        normalized_message = _normalized_text(message)
        if not normalized_code or normalized_code in reason_codes:
            return
        reason_codes.append(normalized_code)
        reason_messages.append(normalized_message or normalized_code)

    questionnaire_id = int(template.get("questionnaire_id") or 0)
    question_id = int(template.get("segmentation_question_id") or 0)
    enabled_categories = [dict(item) for item in categories if bool(item.get("enabled"))]

    if questionnaire_id <= 0 or not questionnaire:
        add_reason("questionnaire_missing", "绑定问卷不存在，请重新选择问卷。")

    if question_id <= 0 or not question:
        add_reason("segmentation_question_missing", "分层题目不存在，请重新选择分层题目。")
    else:
        question_type = _normalized_text(question.get("type"))
        if question_type not in {"single_choice", "multi_choice"}:
            add_reason("segmentation_question_invalid_type", "分层题目必须是单选题或多选题。")

    if not enabled_categories:
        add_reason("enabled_categories_missing", "至少需要一个启用分类。")

    categories_without_mappings: list[str] = []
    categories_with_mismatched_question: list[str] = []
    categories_with_missing_options: list[str] = []
    mapping_count = 0

    for index, category in enumerate(enabled_categories, start=1):
        mappings = list(category.get("option_mappings") or [])
        option_ids = [int(option_id) for option_id in list(category.get("option_ids") or []) if int(option_id or 0) > 0]
        label = _profile_segment_category_label(category, fallback_index=index)
        if not option_ids or not mappings:
            categories_without_mappings.append(label)
            continue
        has_mismatched_question = False
        has_missing_option = False
        for mapping in mappings:
            mapping_count += 1
            if question_id > 0 and int(mapping.get("question_id") or 0) != question_id:
                has_mismatched_question = True
            option = dict(mapping.get("option") or {})
            if int(option.get("id") or 0) <= 0:
                has_missing_option = True
        if has_mismatched_question:
            categories_with_mismatched_question.append(label)
        if has_missing_option:
            categories_with_missing_options.append(label)

    if categories_without_mappings:
        add_reason(
            "enabled_category_without_mappings",
            f"启用分类未绑定当前分层题目的选项：{'、'.join(categories_without_mappings)}。",
        )
    if categories_with_mismatched_question:
        add_reason(
            "mapping_question_mismatch",
            f"存在分类映射不属于当前分层题目：{'、'.join(categories_with_mismatched_question)}。",
        )
    if categories_with_missing_options:
        add_reason(
            "mapping_option_missing",
            f"存在分类映射引用的问卷选项已失效：{'、'.join(categories_with_missing_options)}。",
        )

    return {
        "is_valid": not reason_codes,
        "status": "valid" if not reason_codes else "invalid",
        "reason_codes": reason_codes,
        "reason_messages": reason_messages,
        "enabled_category_count": len(enabled_categories),
        "mapping_count": mapping_count,
    }


def _profile_segment_template_is_valid(bundle: dict[str, Any]) -> bool:
    return bool((bundle.get("validity") or {}).get("is_valid"))


def _profile_segment_template_primary_reason(bundle: dict[str, Any]) -> str:
    validity = dict(bundle.get("validity") or {})
    reason_messages = [str(item).strip() for item in list(validity.get("reason_messages") or []) if str(item).strip()]
    if reason_messages:
        return reason_messages[0]
    return "画像模板结构无效，请修复后再启用。"


def _ensure_profile_segment_template_bundle_valid(bundle: dict[str, Any]) -> dict[str, Any]:
    if _profile_segment_template_is_valid(bundle):
        return bundle
    raise ValueError(_profile_segment_template_primary_reason(bundle))


def _serialize_agent_reference(agent: dict[str, Any]) -> dict[str, Any]:
    status_code = _normalized_text(agent.get("status_code")) or "draft"
    return {
        "agent_code": _normalized_text(agent.get("agent_code")),
        "agent_name": _normalized_text(agent.get("display_name")) or _normalized_text(agent.get("agent_name")),
        "description": _normalized_text(agent.get("description")),
        "status": status_code,
        "updated_at": _normalized_text(agent.get("updated_at")),
    }


def _serialize_profile_segment_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(template.get("id") or 0),
        "program_id": int(template.get("program_id") or 0) or None,
        "template_code": _normalized_text(template.get("template_code")),
        "template_name": _normalized_text(template.get("template_name")),
        "questionnaire_id": int(template.get("questionnaire_id") or 0) or None,
        "segmentation_question_id": int(template.get("segmentation_question_id") or 0) or None,
        "description": _normalized_text(template.get("description")),
        "enabled": bool(template.get("enabled")),
        "status": "enabled" if bool(template.get("enabled")) else "disabled",
        "version": int(template.get("version") or 1),
        "updated_at": _normalized_text(template.get("updated_at")),
        "created_at": _normalized_text(template.get("created_at")),
    }


def _build_questionnaire_catalog_item(questionnaire: dict[str, Any]) -> dict[str, Any]:
    questionnaire_id = int(questionnaire.get("id") or 0)
    question_items: list[dict[str, Any]] = []
    for question in workflow_repo.list_questionnaire_question_rows(questionnaire_id):
        option_rows = workflow_repo.list_questionnaire_option_rows(int(question["id"]))
        question_items.append(
            {
                "id": int(question["id"]),
                "title": _normalized_text(question.get("title")),
                "type": _normalized_text(question.get("type")),
                "sort_order": int(question.get("sort_order") or 0),
                "options": [
                    {
                        "id": int(option["id"]),
                        "option_text": _normalized_text(option.get("option_text")),
                        "sort_order": int(option.get("sort_order") or 0),
                    }
                    for option in option_rows
                ],
            }
        )
    return {
        "id": questionnaire_id,
        "name": _normalized_text(questionnaire.get("title")) or _normalized_text(questionnaire.get("name")),
        "slug": _normalized_text(questionnaire.get("slug")),
        "questions": question_items,
    }


def list_conversion_profile_segment_catalog() -> dict[str, Any]:
    items = [_build_questionnaire_catalog_item(row) for row in workflow_repo.list_questionnaire_rows()]
    return {"items": items, "total": len(items)}


def _build_profile_segment_template_bundle(template: dict[str, Any]) -> dict[str, Any]:
    template_id = int(template["id"])
    questionnaire_id = int(template.get("questionnaire_id") or 0)
    question_id = int(template.get("segmentation_question_id") or 0)
    questionnaire = workflow_repo.get_questionnaire_row(questionnaire_id) if questionnaire_id else None
    question = workflow_repo.get_questionnaire_question_row(questionnaire_id, question_id) if questionnaire_id and question_id else None
    options = workflow_repo.list_questionnaire_option_rows(question_id) if question_id else []
    option_map = {int(item["id"]): dict(item) for item in options}
    categories = workflow_repo.list_profile_segment_category_rows(template_id)
    mappings = workflow_repo.list_profile_segment_option_mapping_rows(template_id)
    mappings_by_category: dict[int, list[dict[str, Any]]] = {}
    option_ids_by_category: dict[int, list[int]] = {}
    for mapping in mappings:
        category_id = int(mapping["category_id"])
        option_snapshot = option_map.get(int(mapping["option_id"])) or {}
        enriched_mapping = {
            "id": int(mapping["id"]),
            "question_id": int(mapping["question_id"]),
            "option_id": int(mapping["option_id"]),
            "option": {
                "id": int(option_snapshot.get("id") or 0),
                "option_text": _normalized_text(option_snapshot.get("option_text")),
                "sort_order": int(option_snapshot.get("sort_order") or 0),
            },
        }
        mappings_by_category.setdefault(category_id, []).append(enriched_mapping)
        option_ids_by_category.setdefault(category_id, []).append(int(mapping["option_id"]))
    category_items = [
        {
            "id": int(category["id"]),
            "category_key": _normalized_text(category.get("category_key")),
            "category_name": _normalized_text(category.get("category_name")),
            "description": _normalized_text(category.get("description")),
            "sort_order": int(category.get("sort_order") or 0),
            "enabled": bool(category.get("enabled")),
            "option_ids": option_ids_by_category.get(int(category["id"]), []),
            "option_mappings": mappings_by_category.get(int(category["id"]), []),
            "mapping_count": len(mappings_by_category.get(int(category["id"]), [])),
        }
        for category in categories
    ]
    validity = _build_profile_segment_template_validity(
        template=template,
        questionnaire=questionnaire,
        question=question,
        categories=category_items,
    )
    serialized_template = _serialize_profile_segment_template(template)
    serialized_template["valid"] = bool(validity.get("is_valid"))
    serialized_template["validity_status"] = _normalized_text(validity.get("status")) or "invalid"
    return {
        "template": serialized_template,
        "questionnaire": {
            "id": int((questionnaire or {}).get("id") or 0) or None,
            "name": _normalized_text((questionnaire or {}).get("title")) or _normalized_text((questionnaire or {}).get("name")),
            "slug": _normalized_text((questionnaire or {}).get("slug")),
        },
        "segmentation_question": {
            "id": int((question or {}).get("id") or 0) or None,
            "title": _normalized_text((question or {}).get("title")),
            "type": _normalized_text((question or {}).get("type")),
            "sort_order": int((question or {}).get("sort_order") or 0),
        },
        "question_options": [
            {
                "id": int(item["id"]),
                "option_text": _normalized_text(item.get("option_text")),
                "sort_order": int(item.get("sort_order") or 0),
            }
            for item in options
        ],
        "categories": category_items,
        "validity": validity,
        "supports_standard_fallback": True,
    }


def _extract_bundle_categories(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "category_key": _normalized_text(item.get("category_key")),
            "category_name": _normalized_text(item.get("category_name")),
            "description": _normalized_text(item.get("description")),
            "sort_order": _normalize_int(item.get("sort_order"), default=index, minimum=0),
            "enabled": _normalize_bool(item.get("enabled"), default=True),
            "option_ids": [_normalize_int(option_id, default=0, minimum=1) for option_id in item.get("option_ids") or []],
        }
        for index, item in enumerate(bundle.get("categories") or [], start=1)
    ]


def _sync_profile_template_categories(template_id: int, question_id: int, categories: list[dict[str, Any]]) -> None:
    workflow_repo.delete_profile_segment_option_mapping_rows(template_id)
    workflow_repo.delete_profile_segment_category_rows(template_id)
    for category in categories:
        saved_category = workflow_repo.insert_profile_segment_category_row(
            {
                "template_id": int(template_id),
                "category_key": category["category_key"],
                "category_name": category["category_name"],
                "description": category["description"],
                "sort_order": category["sort_order"],
                "enabled": category["enabled"],
            }
        )
        for option_id in category["option_ids"]:
            workflow_repo.insert_profile_segment_option_mapping_row(
                {
                    "template_id": int(template_id),
                    "category_id": int(saved_category["id"]),
                    "question_id": int(question_id),
                    "option_id": int(option_id),
                }
            )


def _workflow_expected_binding_targets(
    *,
    segmentation_basis: str,
    generation_mode: str,
    profile_segment_template_id: int | None,
) -> dict[str, Any]:
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        return {"binding_scope": AGENT_BINDING_SCOPE_DEFAULT, "segment_keys": []}
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        return {"binding_scope": AGENT_BINDING_SCOPE_PERSONALIZED, "segment_keys": ["personalized"]}
    if segmentation_basis == SEGMENTATION_BASIS_PROFILE:
        template = _ensure_profile_segment_template_bundle_valid(
            get_conversion_profile_segment_template_bundle(int(profile_segment_template_id or 0))
        )
        category_keys = [
            _normalized_text(item.get("category_key"))
            for item in template.get("categories") or []
            if bool(item.get("enabled"))
        ]
        return {"binding_scope": AGENT_BINDING_SCOPE_PROFILE_CATEGORY, "segment_keys": category_keys}
    if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR:
        return {"binding_scope": AGENT_BINDING_SCOPE_BEHAVIOR_TIER, "segment_keys": _behavior_tier_codes()}
    raise ValueError("auto_layered_rewrite requires segmentation_basis profile or behavior")


def _validate_workflow_agent_bindings(
    *,
    segmentation_basis: str,
    generation_mode: str,
    profile_segment_template_id: int | None,
    bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        if bindings:
            raise ValueError("manual_layered does not allow agent_bindings")
        return []
    expected = _workflow_expected_binding_targets(
        segmentation_basis=segmentation_basis,
        generation_mode=generation_mode,
        profile_segment_template_id=profile_segment_template_id,
    )
    binding_scope = expected["binding_scope"]
    expected_keys = list(expected["segment_keys"])
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        if len(bindings) != 1:
            raise ValueError("personalized_single requires exactly 1 agent_binding")
    else:
        if len(bindings) != len(expected_keys):
            raise ValueError("agent_bindings does not match expected segmentation targets")
    resolved_by_key: dict[str, dict[str, Any]] = {}
    available_codes = set(workflow_repo.list_agent_config_codes())
    for item in bindings:
        item_scope = _normalized_text(item.get("binding_scope")) or binding_scope
        segment_key = _normalized_text(item.get("segment_key"))
        if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
            segment_key = "personalized"
            item_scope = AGENT_BINDING_SCOPE_PERSONALIZED
        if item_scope != binding_scope:
            raise ValueError("invalid binding_scope for workflow generation_mode")
        if generation_mode != GENERATION_MODE_PERSONALIZED_SINGLE and segment_key not in expected_keys:
            raise ValueError(f"unexpected binding segment_key: {segment_key}")
        agent_code = _normalized_text(item.get("agent_code"))
        if not agent_code:
            raise ValueError("agent_code is required")
        if agent_code not in available_codes:
            raise ValueError(f"invalid agent_code: {agent_code}")
        resolved_by_key[segment_key] = {
            "node_id": int(item.get("node_id") or 0) or None,
            "binding_scope": item_scope,
            "segment_key": segment_key if generation_mode != GENERATION_MODE_PERSONALIZED_SINGLE else "",
            "agent_code": agent_code,
        }
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        only_item = next(iter(resolved_by_key.values()))
        return [only_item]
    if set(resolved_by_key.keys()) != set(expected_keys):
        raise ValueError("agent_bindings must cover every segmentation target")
    return [resolved_by_key[key] for key in expected_keys]


def _normalize_workflow_payload(
    payload: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
    program_id: int | None = None,
) -> dict[str, Any]:
    source = dict(payload or {})
    current = dict(existing or {})
    workflow_name = _normalized_text(source.get("workflow_name") or current.get("workflow_name"))
    if not workflow_name:
        raise ValueError("workflow_name is required")
    workflow_code = _slugify_code(source.get("workflow_code") or current.get("workflow_code") or workflow_name, prefix="workflow")
    audiences = _normalize_workflow_audiences(source.get("audiences") if "audiences" in source else [item.get("audience_code") for item in current.get("audiences") or []])
    current_recipient_config = _decode_recipient_filter_config(_normalized_text(current.get("behavior_tier_scheme")))

    recipient_filter_basis = _normalized_text(
        source.get("recipient_filter_basis") if "recipient_filter_basis" in source else current_recipient_config.get("recipient_filter_basis")
    ) or RECIPIENT_FILTER_BASIS_NONE
    if recipient_filter_basis not in _ALLOWED_RECIPIENT_FILTER_BASES:
        raise ValueError("invalid recipient_filter_basis")
    if "recipient_behavior_tier_keys" in source:
        recipient_behavior_tier_keys = _normalize_behavior_tier_key_list(source.get("recipient_behavior_tier_keys") or [])
    else:
        recipient_behavior_tier_keys = list(current_recipient_config.get("recipient_behavior_tier_keys") or [])
    if recipient_filter_basis == RECIPIENT_FILTER_BASIS_NONE:
        recipient_behavior_tier_keys = []
    elif recipient_filter_basis == RECIPIENT_FILTER_BASIS_BEHAVIOR and not recipient_behavior_tier_keys:
        raise ValueError("recipient_behavior_tier_keys is required when recipient_filter_basis is behavior")

    raw_content_segmentation_basis = source.get("content_segmentation_basis") if "content_segmentation_basis" in source else None
    if raw_content_segmentation_basis in {None, ""}:
        raw_content_segmentation_basis = source.get("segmentation_basis") if "segmentation_basis" in source else current.get("content_segmentation_basis")
    if raw_content_segmentation_basis in {None, ""}:
        raw_content_segmentation_basis = current.get("segmentation_basis")
    segmentation_basis = _normalized_text(raw_content_segmentation_basis) or SEGMENTATION_BASIS_NONE
    if segmentation_basis not in _ALLOWED_SEGMENTATION_BASES:
        raise ValueError("invalid segmentation_basis")

    generation_mode = _normalized_text(source.get("generation_mode") or current.get("generation_mode")) or GENERATION_MODE_MANUAL_LAYERED
    if generation_mode not in _ALLOWED_GENERATION_MODES:
        raise ValueError("invalid generation_mode")

    raw_content_profile_segment_template_id = (
        source.get("content_profile_segment_template_id") if "content_profile_segment_template_id" in source else None
    )
    if raw_content_profile_segment_template_id in {None, ""}:
        raw_content_profile_segment_template_id = (
            source.get("profile_segment_template_id") if "profile_segment_template_id" in source else current.get("content_profile_segment_template_id")
        )
    if raw_content_profile_segment_template_id in {None, ""}:
        raw_content_profile_segment_template_id = current.get("profile_segment_template_id")
    profile_segment_template_id = _normalize_int(
        raw_content_profile_segment_template_id,
        default=0,
        minimum=0,
    ) or None
    if segmentation_basis == SEGMENTATION_BASIS_PROFILE:
        if not profile_segment_template_id:
            raise ValueError("profile_segment_template_id is required for profile segmentation")
        template_bundle = get_conversion_profile_segment_template_bundle(int(profile_segment_template_id))
        template_program_id = int(((template_bundle.get("template") or {}).get("program_id")) or 0) or None
        if program_id and template_program_id and int(template_program_id) != int(program_id):
            raise ValueError("profile_segment_template_id does not belong to current program")
    else:
        profile_segment_template_id = None
    if generation_mode == GENERATION_MODE_AUTO_LAYERED_REWRITE and segmentation_basis == SEGMENTATION_BASIS_NONE:
        raise ValueError("auto_layered_rewrite requires profile or behavior segmentation")
    bindings_input = source.get("agent_bindings") if "agent_bindings" in source else current.get("agent_bindings") or []
    bindings = _normalize_workflow_agent_bindings(bindings_input)
    normalized_bindings = _validate_workflow_agent_bindings(
        segmentation_basis=segmentation_basis,
        generation_mode=generation_mode,
        profile_segment_template_id=profile_segment_template_id,
        bindings=bindings,
    )
    status = _normalized_text(source.get("status") or current.get("status")) or WORKFLOW_STATUS_DRAFT
    if status not in _ALLOWED_WORKFLOW_STATUSES:
        raise ValueError("invalid workflow status")
    fallback_to_standard_content = _normalize_bool(
        source.get("fallback_to_standard_content"),
        default=_normalize_bool(current.get("fallback_to_standard_content"), default=True),
    )
    return {
        "workflow_code": workflow_code,
        "workflow_name": workflow_name,
        "description": _normalized_text(source.get("description") if "description" in source else current.get("description")),
        "status": status,
        "segmentation_basis": segmentation_basis,
        "generation_mode": generation_mode,
        "profile_segment_template_id": profile_segment_template_id,
        "behavior_tier_scheme": _encode_recipient_filter_config(recipient_filter_basis, recipient_behavior_tier_keys),
        "fallback_to_standard_content": fallback_to_standard_content,
        "enabled": _workflow_status_to_enabled(status),
        "audiences": audiences,
        "agent_bindings": normalized_bindings,
        "recipient_filter_basis": recipient_filter_basis,
        "recipient_behavior_tier_keys": recipient_behavior_tier_keys,
        "content_segmentation_basis": segmentation_basis,
        "content_profile_segment_template_id": profile_segment_template_id,
    }


def _allowed_manual_variant_keys(workflow_bundle: dict[str, Any]) -> tuple[str, list[str]]:
    workflow = dict(workflow_bundle.get("workflow") or {})
    return _allowed_manual_variant_keys_for_basis(workflow_bundle, _normalized_text(workflow.get("segmentation_basis")))


def _resolve_node_content_mode_and_basis(
    *,
    workflow: dict[str, Any],
    content_row: dict[str, Any],
    variants: list[dict[str, Any]],
    node_bindings: list[dict[str, Any]],
) -> tuple[str, str]:
    if node_bindings:
        scopes = {_normalized_text(item.get("binding_scope")) for item in node_bindings if _normalized_text(item.get("binding_scope"))}
        if AGENT_BINDING_SCOPE_PERSONALIZED in scopes:
            return NODE_CONTENT_MODE_PERSONALIZED_SINGLE, SEGMENTATION_BASIS_NONE
        if AGENT_BINDING_SCOPE_PROFILE_CATEGORY in scopes:
            return NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE, SEGMENTATION_BASIS_PROFILE
        if AGENT_BINDING_SCOPE_BEHAVIOR_TIER in scopes:
            return NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE, SEGMENTATION_BASIS_BEHAVIOR
    if variants:
        scopes = {_normalized_text(item.get("variant_scope")) for item in variants if _normalized_text(item.get("variant_scope"))}
        if NODE_CONTENT_VARIANT_SCOPE_PROFILE_CATEGORY in scopes:
            return NODE_CONTENT_MODE_MANUAL_LAYERED, SEGMENTATION_BASIS_PROFILE
        if NODE_CONTENT_VARIANT_SCOPE_BEHAVIOR_TIER in scopes:
            return NODE_CONTENT_MODE_MANUAL_LAYERED, SEGMENTATION_BASIS_BEHAVIOR
    fallback_mode = _workflow_generation_mode_to_node_content_mode(workflow.get("generation_mode"))
    fallback_basis = _normalized_text(workflow.get("segmentation_basis")) or SEGMENTATION_BASIS_NONE
    if fallback_mode in {
        NODE_CONTENT_MODE_MANUAL_LAYERED,
        NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE,
    } and fallback_basis in {SEGMENTATION_BASIS_PROFILE, SEGMENTATION_BASIS_BEHAVIOR}:
        return fallback_mode, fallback_basis
    if fallback_mode in {
        NODE_CONTENT_MODE_STANDARD_DIRECT,
        NODE_CONTENT_MODE_PERSONALIZED_SINGLE,
    }:
        return fallback_mode, SEGMENTATION_BASIS_NONE
    return NODE_CONTENT_MODE_STANDARD_DIRECT, SEGMENTATION_BASIS_NONE


def _build_node_bundle(
    node: dict[str, Any],
    workflow_bundle: dict[str, Any],
    *,
    node_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    content = workflow_repo.get_workflow_node_content_row(int(node["id"])) or {}
    variants = workflow_repo.list_workflow_node_content_variant_rows(int(content["id"])) if content else []
    node_binding_items = [dict(item) for item in (node_bindings or [])]
    workflow = dict(workflow_bundle.get("workflow") or {})
    content_mode, segmentation_basis = _resolve_node_content_mode_and_basis(
        workflow=workflow,
        content_row=content,
        variants=variants,
        node_bindings=node_binding_items,
    )
    manual_layered_profile_fallback_enabled = (
        content_mode == NODE_CONTENT_MODE_MANUAL_LAYERED
        and segmentation_basis == SEGMENTATION_BASIS_PROFILE
        and bool(content.get("fallback_to_standard_content"))
        and bool(_normalized_text(content.get("standard_content_text")))
    )
    content_payload = _strip_node_content_meta(content.get("standard_content_payload_json") or {}) if content else {}
    exposes_standard_content = _content_mode_uses_standard_content(content_mode) or manual_layered_profile_fallback_enabled
    exposes_standard_payload = exposes_standard_content or bool(content_payload)
    standard_content_text = _normalized_text(content.get("standard_content_text")) if exposes_standard_content else ""
    return {
        "id": int(node["id"]),
        "node_code": _normalized_text(node.get("node_code")),
        "node_name": _normalized_text(node.get("node_name")),
        "target_audience_code": _normalized_text(node.get("target_audience_code")),
        "trigger_mode": _normalized_text(node.get("trigger_mode")) or NODE_TRIGGER_MODE_SCHEDULED,
        "day_offset": int(node.get("day_offset") or 1),
        "send_time": _normalized_text(node.get("send_time")),
        "timezone": _normalized_text(node.get("timezone")) or "Asia/Shanghai",
        "position_index": int(node.get("position_index") or 0),
        "enabled": bool(node.get("enabled")),
        "status": "enabled" if bool(node.get("enabled")) else "disabled",
        "content_mode": content_mode,
        "segmentation_basis": segmentation_basis,
        "standard_content_text": standard_content_text,
        "standard_content_payload": content_payload if exposes_standard_payload else {},
        "fallback_to_standard_content": bool(content.get("fallback_to_standard_content")) if content and exposes_standard_content else False,
        "agent_bindings": node_binding_items,
        "content_variants": [
            {
                "id": int(item["id"]),
                "variant_scope": _normalized_text(item.get("variant_scope")),
                "segment_key": _normalized_text(item.get("segment_key")),
                "content_text": _normalized_text(item.get("content_text")),
                "content_payload": dict(item.get("content_payload_json") or {}),
            }
            for item in variants
        ],
    }


def _build_workflow_bundle(workflow: dict[str, Any]) -> dict[str, Any]:
    workflow_id = int(workflow["id"])
    audiences = workflow_repo.list_workflow_audience_rows(workflow_id)
    bindings = workflow_repo.list_workflow_agent_binding_rows(workflow_id)
    nodes = workflow_repo.list_workflow_node_rows(workflow_id)
    recipient_filter_config = _decode_recipient_filter_config(_normalized_text(workflow.get("behavior_tier_scheme")))
    profile_segment_template = (
        get_conversion_profile_segment_template_bundle(int(workflow.get("profile_segment_template_id") or 0))
        if int(workflow.get("profile_segment_template_id") or 0) > 0
        else None
    )
    agent_map = {
        _normalized_text(item.get("agent_code")): _serialize_agent_reference(item)
        for item in workflow_repo.list_agent_config_summary_rows()
    }
    binding_items = []
    node_bindings_by_node_id: dict[int, list[dict[str, Any]]] = {}
    for binding in bindings:
        agent_code = _normalized_text(binding.get("agent_code"))
        if not agent_code:
            continue
        binding_item = {
            "id": int(binding["id"]),
            "node_id": int(binding.get("node_id") or 0) or None,
            "binding_scope": _normalized_text(binding.get("binding_scope")),
            "segment_key": _normalized_text(binding.get("segment_key")),
            "agent_code": agent_code,
            "agent": dict(agent_map.get(agent_code) or {"agent_code": agent_code, "agent_name": agent_code, "status": ""}),
        }
        if binding_item["node_id"]:
            node_bindings_by_node_id.setdefault(int(binding_item["node_id"]), []).append(binding_item)
        else:
            binding_items.append(binding_item)
    workflow_payload = {
        "id": workflow_id,
        "workflow_code": _normalized_text(workflow.get("workflow_code")),
        "workflow_name": _normalized_text(workflow.get("workflow_name")),
        "description": _normalized_text(workflow.get("description")),
        "status": _normalized_text(workflow.get("status")) or WORKFLOW_STATUS_DRAFT,
        "enabled": bool(workflow.get("enabled")),
        "segmentation_basis": _normalized_text(workflow.get("segmentation_basis")) or SEGMENTATION_BASIS_NONE,
        "generation_mode": _normalized_text(workflow.get("generation_mode")) or GENERATION_MODE_MANUAL_LAYERED,
        "profile_segment_template_id": int(workflow.get("profile_segment_template_id") or 0) or None,
        "behavior_tier_scheme": _normalized_text(workflow.get("behavior_tier_scheme")) or "fixed_v1",
        "recipient_filter_basis": _normalized_text(recipient_filter_config.get("recipient_filter_basis")) or RECIPIENT_FILTER_BASIS_NONE,
        "recipient_behavior_tier_keys": list(recipient_filter_config.get("recipient_behavior_tier_keys") or []),
        "content_segmentation_basis": _normalized_text(workflow.get("segmentation_basis")) or SEGMENTATION_BASIS_NONE,
        "content_profile_segment_template_id": int(workflow.get("profile_segment_template_id") or 0) or None,
        "fallback_to_standard_content": bool(workflow.get("fallback_to_standard_content")),
        "updated_at": _normalized_text(workflow.get("updated_at")),
        "created_at": _normalized_text(workflow.get("created_at")),
    }
    bundle = {
        "workflow": workflow_payload,
        "audiences": [
            {
                "audience_code": _normalized_text(item.get("audience_code")),
            }
            for item in audiences
        ],
        "profile_segment_template": profile_segment_template,
        "agent_bindings": binding_items,
        "behavior_tiers": list_supported_behavior_tiers()
        if (
            workflow_payload["recipient_filter_basis"] == RECIPIENT_FILTER_BASIS_BEHAVIOR
            or workflow_payload["content_segmentation_basis"] == SEGMENTATION_BASIS_BEHAVIOR
        )
        else [],
    }
    workflow_binding_signature = {
        (
            _normalized_text(item.get("binding_scope")),
            _normalized_text(item.get("segment_key")),
            _normalized_text(item.get("agent_code")),
        )
        for item in binding_items
    }
    bundle["nodes"] = [
        _build_node_bundle(
            node,
            bundle,
            node_bindings=(
                []
                if {
                    (
                        _normalized_text(item.get("binding_scope")),
                        _normalized_text(item.get("segment_key")),
                        _normalized_text(item.get("agent_code")),
                    )
                    for item in node_bindings_by_node_id.get(int(node["id"]), [])
                }
                == workflow_binding_signature
                else node_bindings_by_node_id.get(int(node["id"]), [])
            ),
        )
        for node in nodes
    ]
    return bundle


def _sync_workflow_children(workflow_id: int, payload: dict[str, Any]) -> None:
    workflow_repo.delete_workflow_audience_rows(workflow_id)
    for audience_code in payload["audiences"]:
        workflow_repo.insert_workflow_audience_row({"workflow_id": int(workflow_id), "audience_code": audience_code})
    workflow_repo.delete_workflow_agent_binding_rows(workflow_id)
    for item in payload["agent_bindings"]:
        workflow_repo.insert_workflow_agent_binding_row({"workflow_id": int(workflow_id), **item})


def _workflow_binding_payload_items(workflow_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "node_id": int(item.get("node_id") or 0) or None,
            "binding_scope": _normalized_text(item.get("binding_scope")),
            "segment_key": _normalized_text(item.get("segment_key")),
            "agent_code": _normalized_text(item.get("agent_code") or (item.get("agent") or {}).get("agent_code")),
        }
        for item in workflow_bundle.get("agent_bindings") or []
    ]


def _ensure_node_inherited_workflow_ready(
    workflow_bundle: dict[str, Any],
    *,
    content_mode: str,
    segmentation_basis: str,
) -> None:
    workflow = dict(workflow_bundle.get("workflow") or {})
    generation_mode = _normalized_text(workflow.get("generation_mode"))
    if not generation_mode:
        raise ValueError("workflow generation_mode is required for node inheritance")

    if content_mode == NODE_CONTENT_MODE_MANUAL_LAYERED:
        if segmentation_basis == SEGMENTATION_BASIS_PROFILE and not int(workflow.get("profile_segment_template_id") or 0):
            raise ValueError("workflow profile_segment_template_id is required for inherited profile segmentation")
        _, allowed_keys = _allowed_manual_variant_keys_for_basis(workflow_bundle, segmentation_basis)
        if not allowed_keys:
            raise ValueError("workflow segmentation targets are not configured for inherited content_mode")
        return

    if content_mode == NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE:
        if segmentation_basis not in {SEGMENTATION_BASIS_PROFILE, SEGMENTATION_BASIS_BEHAVIOR}:
            raise ValueError("workflow segmentation_basis is invalid for inherited layered content_mode")
        try:
            _validate_workflow_agent_bindings(
                segmentation_basis=segmentation_basis,
                generation_mode=GENERATION_MODE_AUTO_LAYERED_REWRITE,
                profile_segment_template_id=int(workflow.get("profile_segment_template_id") or 0) or None,
                bindings=_workflow_binding_payload_items(workflow_bundle),
            )
        except ValueError as exc:
            message = str(exc)
            if message in {
                "agent_bindings does not match expected segmentation targets",
                "agent_bindings must cover every segmentation target",
                "agent_code is required",
                "invalid binding_scope for workflow generation_mode",
            } or message.startswith("invalid agent_code:") or message.startswith("unexpected binding segment_key:"):
                raise ValueError("workflow agent_bindings are invalid for inherited layered content_mode") from exc
            raise ValueError("workflow configuration is incomplete for inherited content_mode") from exc
        return

    if content_mode == NODE_CONTENT_MODE_PERSONALIZED_SINGLE:
        try:
            normalized_bindings = _validate_workflow_agent_bindings(
                segmentation_basis=SEGMENTATION_BASIS_NONE,
                generation_mode=GENERATION_MODE_PERSONALIZED_SINGLE,
                profile_segment_template_id=None,
                bindings=_workflow_binding_payload_items(workflow_bundle),
            )
        except ValueError as exc:
            message = str(exc)
            if message == "personalized_single requires exactly 1 agent_binding":
                raise ValueError("workflow personalized_single requires exactly 1 agent_binding") from exc
            if message == "agent_code is required" or message.startswith("invalid agent_code:"):
                raise ValueError("workflow personalized_single agent_binding is invalid") from exc
            raise ValueError("workflow configuration is incomplete for inherited content_mode") from exc
        if len(normalized_bindings) != 1:
            raise ValueError("workflow personalized_single requires exactly 1 agent_binding")


def _normalize_node_payload(payload: dict[str, Any], workflow_bundle: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    source = dict(payload or {})
    current = dict(existing or {})
    workflow = dict(workflow_bundle.get("workflow") or {})
    node_name = _normalized_text(source.get("node_name") or current.get("node_name"))
    if not node_name:
        raise ValueError("node_name is required")
    node_code = _slugify_code(source.get("node_code") or current.get("node_code") or node_name, prefix="node")
    target_audience_code = _normalized_text(source.get("target_audience_code") or current.get("target_audience_code"))
    if not target_audience_code:
        raise ValueError("target_audience_code is required")
    if target_audience_code not in [item["audience_code"] for item in workflow_bundle.get("audiences") or []]:
        raise ValueError("target_audience_code must belong to workflow audiences")
    trigger_mode = _validate_node_trigger_mode(
        source.get("trigger_mode") if "trigger_mode" in source else current.get("trigger_mode") or NODE_TRIGGER_MODE_SCHEDULED
    )

    raw_day_offset = source.get("day_offset") if "day_offset" in source else current.get("day_offset")
    raw_send_time = source.get("send_time") if "send_time" in source else current.get("send_time")
    if trigger_mode in {NODE_TRIGGER_MODE_SCHEDULED, NODE_TRIGGER_MODE_DAILY_RECURRING}:
        if raw_day_offset in {None, ""}:
            raise ValueError("day_offset is required when trigger_mode is scheduled or daily_recurring")
        if _normalized_text(raw_send_time) == "":
            raise ValueError("send_time is required when trigger_mode is scheduled or daily_recurring")
        day_offset = _normalize_int(raw_day_offset, default=0, minimum=1)
        if day_offset <= 0:
            raise ValueError("day_offset is required when trigger_mode is scheduled or daily_recurring")
        send_time = _validate_send_time(raw_send_time)
    else:
        has_day_offset = "day_offset" in source and source.get("day_offset") not in {None, ""}
        has_send_time = "send_time" in source and _normalized_text(source.get("send_time")) != ""
        if has_day_offset and has_send_time:
            raise ValueError("day_offset and send_time are not allowed when trigger_mode is audience_entered")
        if has_day_offset:
            raise ValueError("day_offset is not allowed when trigger_mode is audience_entered")
        if has_send_time:
            raise ValueError("send_time is not allowed when trigger_mode is audience_entered")
        day_offset = 1
        send_time = "00:00"

    raw_content_mode = source.get("content_mode") if "content_mode" in source else current.get("content_mode")
    raw_segmentation_basis = source.get("segmentation_basis") if "segmentation_basis" in source else current.get("segmentation_basis")
    inherited_content_mode = _workflow_generation_mode_to_node_content_mode(workflow.get("generation_mode"))
    content_mode = _normalize_node_content_mode(raw_content_mode, default=inherited_content_mode)
    explicit_content_mode = "content_mode" in source and _normalized_text(source.get("content_mode")) != ""
    explicit_segmentation_basis = "segmentation_basis" in source and _normalized_text(source.get("segmentation_basis")) != ""
    bindings_input = source.get("agent_bindings") if "agent_bindings" in source else current.get("agent_bindings") or []
    normalized_binding_payloads = _normalize_workflow_agent_bindings(bindings_input)
    uses_inherited_workflow_config = not explicit_content_mode and not explicit_segmentation_basis and not normalized_binding_payloads
    if content_mode in {
        NODE_CONTENT_MODE_MANUAL_LAYERED,
        NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE,
    }:
        segmentation_basis = _normalized_text(raw_segmentation_basis if explicit_segmentation_basis else workflow.get("segmentation_basis"))
        if segmentation_basis not in {SEGMENTATION_BASIS_PROFILE, SEGMENTATION_BASIS_BEHAVIOR}:
            if explicit_content_mode or explicit_segmentation_basis:
                raise ValueError("segmentation_basis must be profile or behavior when content_mode requires layered segmentation")
            content_mode = NODE_CONTENT_MODE_STANDARD_DIRECT
            segmentation_basis = SEGMENTATION_BASIS_NONE
    else:
        content_mode = NODE_CONTENT_MODE_PERSONALIZED_SINGLE if content_mode == NODE_CONTENT_MODE_PERSONALIZED_SINGLE else NODE_CONTENT_MODE_STANDARD_DIRECT
        segmentation_basis = SEGMENTATION_BASIS_NONE
    if uses_inherited_workflow_config:
        _ensure_node_inherited_workflow_ready(
            workflow_bundle,
            content_mode=content_mode,
            segmentation_basis=segmentation_basis,
        )

    raw_standard_content_text = (
        source.get("standard_content_text")
        if "standard_content_text" in source
        else current.get("standard_content_text")
    )
    standard_content_text = _normalized_text(raw_standard_content_text)
    if trigger_mode == NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
        day_offset = 1
        send_time = "00:00"
    position_index = _normalize_int(
        source.get("position_index") if "position_index" in source else current.get("position_index"),
        default=len(workflow_bundle.get("nodes") or []),
        minimum=0,
    )
    content_variants_input = source.get("content_variants") if "content_variants" in source else current.get("content_variants") or []
    content_variants = _normalize_node_variants_payload(content_variants_input)
    agent_bindings: list[dict[str, Any]] = []

    if content_mode == NODE_CONTENT_MODE_STANDARD_DIRECT:
        if not standard_content_text:
            raise ValueError("standard_content_text is required")
        content_variants = []
        agent_bindings = []
    elif content_mode == NODE_CONTENT_MODE_MANUAL_LAYERED:
        variant_scope, allowed_keys = _allowed_manual_variant_keys_for_basis(workflow_bundle, segmentation_basis)
        if segmentation_basis == SEGMENTATION_BASIS_PROFILE and not allowed_keys:
            raise ValueError("profile segmentation requires a workflow profile segment template")
        if not content_variants:
            raise ValueError("content_variants is required for manual_layered")
        if not allowed_keys:
            raise ValueError("current node segmentation does not allow content_variants")
        variant_by_key: dict[str, dict[str, Any]] = {}
        for item in content_variants:
            if item["segment_key"] not in allowed_keys:
                raise ValueError(f"invalid content_variants.segment_key: {item['segment_key']}")
            variant_by_key[item["segment_key"]] = item
        missing_keys = [key for key in allowed_keys if key not in variant_by_key or not _normalized_text(variant_by_key[key].get("content_text"))]
        if missing_keys:
            raise ValueError("manual_layered requires content for every active segmentation target")
        standard_content_text = ""
        agent_bindings = []
        content_variants = [
            {
                "variant_scope": variant_scope,
                **variant_by_key[key],
            }
            for key in allowed_keys
        ]
    elif content_mode == NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE:
        if not standard_content_text:
            raise ValueError("standard_content_text is required")
        content_variants = []
        if uses_inherited_workflow_config:
            agent_bindings = _workflow_binding_payload_items(workflow_bundle)
        else:
            agent_bindings = _validate_workflow_agent_bindings(
                segmentation_basis=segmentation_basis,
                generation_mode=GENERATION_MODE_AUTO_LAYERED_REWRITE,
                profile_segment_template_id=int(workflow.get("profile_segment_template_id") or 0) or None,
                bindings=normalized_binding_payloads,
            )
    else:
        standard_content_text = ""
        content_variants = []
        if uses_inherited_workflow_config:
            agent_bindings = _workflow_binding_payload_items(workflow_bundle)
        else:
            agent_bindings = _validate_workflow_agent_bindings(
                segmentation_basis=SEGMENTATION_BASIS_NONE,
                generation_mode=GENERATION_MODE_PERSONALIZED_SINGLE,
                profile_segment_template_id=None,
                bindings=normalized_binding_payloads,
            )

    return {
        "node_code": node_code,
        "node_name": node_name,
        "target_audience_code": target_audience_code,
        "trigger_mode": trigger_mode,
        "day_offset": day_offset,
        "send_time": send_time,
        "timezone": _normalized_text(source.get("timezone") or current.get("timezone") or "Asia/Shanghai"),
        "position_index": position_index,
        "enabled": _normalize_bool(source.get("enabled"), default=_normalize_bool(current.get("enabled"), default=True)),
        "content_mode": content_mode,
        "segmentation_basis": segmentation_basis,
        "standard_content_text": standard_content_text,
        "standard_content_payload_json": _build_node_content_payload_json(
            source.get("standard_content_payload")
            or source.get("standard_content_payload_json")
            or current.get("standard_content_payload")
            or {},
            content_mode=content_mode,
            segmentation_basis=segmentation_basis,
        ),
        "fallback_to_standard_content": _normalize_bool(
            source.get("fallback_to_standard_content"),
            default=_normalize_bool(current.get("fallback_to_standard_content"), default=True),
        ) if content_mode in {NODE_CONTENT_MODE_STANDARD_DIRECT, NODE_CONTENT_MODE_STANDARD_LAYERED_REWRITE} else False,
        "agent_bindings": agent_bindings,
        "content_variants": content_variants,
    }


def _save_node_content(workflow_id: int, node_id: int, normalized_node: dict[str, Any]) -> None:
    content_row = workflow_repo.get_workflow_node_content_row(node_id)
    if content_row:
        saved_content = workflow_repo.update_workflow_node_content_row(
            node_id,
            {
                "standard_content_text": normalized_node["standard_content_text"],
                "standard_content_payload_json": normalized_node["standard_content_payload_json"],
                "fallback_to_standard_content": normalized_node["fallback_to_standard_content"],
            },
        )
    else:
        saved_content = workflow_repo.insert_workflow_node_content_row(
            {
                "node_id": int(node_id),
                "standard_content_text": normalized_node["standard_content_text"],
                "standard_content_payload_json": normalized_node["standard_content_payload_json"],
                "fallback_to_standard_content": normalized_node["fallback_to_standard_content"],
            }
        )
    workflow_repo.delete_workflow_node_content_variant_rows(int(saved_content["id"]))
    for item in normalized_node["content_variants"]:
        workflow_repo.insert_workflow_node_content_variant_row(
            {
                "node_content_id": int(saved_content["id"]),
                "variant_scope": item["variant_scope"],
                "segment_key": item["segment_key"],
                "content_text": item["content_text"],
                "content_payload_json": item["content_payload_json"],
            }
        )

    workflow_repo.delete_workflow_agent_binding_rows_for_node(int(workflow_id), int(node_id))
    for item in normalized_node["agent_bindings"]:
        workflow_repo.insert_workflow_agent_binding_row(
            {
                "workflow_id": int(workflow_id),
                "node_id": int(node_id),
                "binding_scope": item["binding_scope"],
                "segment_key": item["segment_key"],
                "agent_code": item["agent_code"],
            }
        )
def list_conversion_workflow_registry() -> dict[str, Any]:
    return {
        "audiences": list_supported_conversion_audiences(),
        "recipient_filter_bases": list_supported_recipient_filter_bases(),
        "segmentation_bases": list_supported_segmentation_bases(),
        "generation_modes": list_supported_generation_modes(),
        "node_trigger_modes": list_supported_node_trigger_modes(),
        "behavior_tiers": list_supported_behavior_tiers(),
        "agent_binding_scopes": list_supported_agent_binding_scopes(),
        "node_content_variant_scopes": list_supported_node_content_variant_scopes(),
        "workflow_statuses": list_supported_workflow_statuses(),
    }


def list_conversion_agent_options(*, enabled_only: bool = True) -> dict[str, Any]:
    items = [
        _serialize_agent_reference(item)
        for item in workflow_repo.list_agent_config_summary_rows(enabled_only=enabled_only)
    ]
    return {"items": items, "total": len(items)}


def list_conversion_profile_segment_templates(*, enabled_only: bool = False, program_id: int | None = None) -> dict[str, Any]:
    items = [
        _build_profile_segment_template_bundle(item)
        for item in workflow_repo.list_profile_segment_template_rows(
            enabled_only=enabled_only,
            program_id=_effective_program_id(program_id),
        )
    ]
    return {"items": items, "total": len(items)}


def get_conversion_profile_segment_template_bundle(template_id: int) -> dict[str, Any]:
    template = workflow_repo.get_profile_segment_template_row(int(template_id))
    if not template:
        raise LookupError("profile segment template not found")
    return _build_profile_segment_template_bundle(template)


def create_conversion_profile_segment_template(
    payload: dict[str, Any],
    *,
    operator_id: str,
    program_id: int | None = None,
) -> dict[str, Any]:
    effective_program_id = _effective_program_id(program_id or payload.get("program_id"))
    template_name = _normalized_text(payload.get("template_name"))
    if not template_name:
        raise ValueError("template_name is required")
    template_code = _slugify_code(payload.get("template_code") or template_name, prefix="profile_template")
    if workflow_repo.get_profile_segment_template_row_by_code(template_code):
        raise ValueError("template_code already exists")
    questionnaire_id = _normalize_int(payload.get("questionnaire_id"), default=0, minimum=1)
    question_id = _normalize_int(payload.get("segmentation_question_id"), default=0, minimum=1)
    if questionnaire_id <= 0:
        raise ValueError("questionnaire_id is required")
    if question_id <= 0:
        raise ValueError("segmentation_question_id is required")
    categories = _normalize_template_categories_payload(payload.get("categories") or [])
    if not categories:
        raise ValueError("at least one category is required")
    enabled_categories = [item for item in categories if bool(item.get("enabled"))]
    if not enabled_categories:
        raise ValueError("at least one enabled category is required")
    for category in enabled_categories:
        if not list(category.get("option_ids") or []):
            raise ValueError(f"enabled category '{_profile_segment_category_label(category)}' must bind at least one option")
    _validate_segmentation_question(questionnaire_id, question_id, categories)
    saved_template = workflow_repo.insert_profile_segment_template_row(
        {
            "program_id": effective_program_id,
            "template_code": template_code,
            "template_name": template_name,
            "questionnaire_id": questionnaire_id,
            "segmentation_question_id": question_id,
            "description": _normalized_text(payload.get("description")),
            "enabled": _normalize_bool(payload.get("enabled"), default=True),
            "version": 1,
            "created_by": operator_id,
            "updated_by": operator_id,
        }
    )
    _sync_profile_template_categories(int(saved_template["id"]), question_id, categories)
    get_db().commit()
    return {"template_bundle": get_conversion_profile_segment_template_bundle(int(saved_template["id"]))}


def update_conversion_profile_segment_template(
    template_id: int,
    payload: dict[str, Any],
    *,
    operator_id: str,
    program_id: int | None = None,
) -> dict[str, Any]:
    existing = workflow_repo.get_profile_segment_template_row(int(template_id))
    if not existing:
        raise LookupError("profile segment template not found")
    effective_program_id = _effective_program_id(program_id or payload.get("program_id") or existing.get("program_id"))
    if existing.get("program_id") and int(existing.get("program_id") or 0) != int(effective_program_id):
        raise ValueError("profile segment template does not belong to current program")
    existing_bundle = _build_profile_segment_template_bundle(existing)
    next_template_name = _normalized_text(payload.get("template_name") or existing.get("template_name"))
    if not next_template_name:
        raise ValueError("template_name is required")
    next_template_code = _slugify_code(payload.get("template_code") or existing.get("template_code") or next_template_name, prefix="profile_template")
    duplicate = workflow_repo.get_profile_segment_template_row_by_code(next_template_code)
    if duplicate and int(duplicate["id"]) != int(existing["id"]):
        raise ValueError("template_code already exists")
    next_enabled = _normalize_bool(payload.get("enabled"), default=bool(existing.get("enabled")))
    next_questionnaire_id = _normalize_int(
        payload.get("questionnaire_id") if "questionnaire_id" in payload else existing.get("questionnaire_id"),
        default=0,
        minimum=0,
    )
    next_question_id = _normalize_int(
        payload.get("segmentation_question_id") if "segmentation_question_id" in payload else existing.get("segmentation_question_id"),
        default=0,
        minimum=0,
    )
    next_categories = _normalize_template_categories_payload(payload.get("categories")) if "categories" in payload else _extract_bundle_categories(existing_bundle)
    if next_enabled:
        if next_questionnaire_id <= 0:
            raise ValueError("questionnaire_id is required")
        if next_question_id <= 0:
            raise ValueError("segmentation_question_id is required")
        if not next_categories:
            raise ValueError("at least one category is required")
        enabled_categories = [item for item in next_categories if bool(item.get("enabled"))]
        if not enabled_categories:
            raise ValueError("at least one enabled category is required")
        for category in enabled_categories:
            if not list(category.get("option_ids") or []):
                raise ValueError(f"enabled category '{_profile_segment_category_label(category)}' must bind at least one option")
        _validate_segmentation_question(next_questionnaire_id, next_question_id, next_categories)
    next_state = {
        "program_id": effective_program_id,
        "template_code": next_template_code,
        "template_name": next_template_name,
        "questionnaire_id": next_questionnaire_id or None,
        "segmentation_question_id": next_question_id or None,
        "description": _normalized_text(payload.get("description") if "description" in payload else existing.get("description")),
        "enabled": next_enabled,
        "categories": next_categories,
    }
    previous_state = {
        "program_id": int(existing.get("program_id") or 0),
        "template_code": _normalized_text(existing.get("template_code")),
        "template_name": _normalized_text(existing.get("template_name")),
        "questionnaire_id": int(existing.get("questionnaire_id") or 0),
        "segmentation_question_id": int(existing.get("segmentation_question_id") or 0),
        "description": _normalized_text(existing.get("description")),
        "enabled": bool(existing.get("enabled")),
        "categories": _extract_bundle_categories(existing_bundle),
    }
    next_version = int(existing.get("version") or 1) + (1 if _json_fingerprint(next_state) != _json_fingerprint(previous_state) else 0)
    workflow_repo.update_profile_segment_template_row(
        int(existing["id"]),
        {
            "program_id": next_state["program_id"],
            "template_code": next_state["template_code"],
            "template_name": next_state["template_name"],
            "questionnaire_id": next_state["questionnaire_id"],
            "segmentation_question_id": next_state["segmentation_question_id"],
            "description": next_state["description"],
            "enabled": next_state["enabled"],
            "version": next_version,
            "updated_by": operator_id,
        },
    )
    _sync_profile_template_categories(int(existing["id"]), next_question_id, next_categories)
    get_db().commit()
    return {"template_bundle": get_conversion_profile_segment_template_bundle(int(existing["id"]))}


def _effective_program_id(program_id: int | None = None) -> int:
    return int(program_id or 0) or program_service.get_default_automation_program_id()


def list_conversion_workflows(*, include_archived: bool = False, status: str = "", program_id: int | None = None) -> dict[str, Any]:
    effective_program_id = _effective_program_id(program_id)
    items = [
        _build_workflow_bundle(item)
        for item in workflow_repo.list_workflow_rows(
            include_archived=include_archived,
            status=status,
            program_id=effective_program_id,
        )
    ]
    return {"items": items, "total": len(items)}


def get_conversion_workflow_model_bundle(workflow_id: int) -> dict[str, Any]:
    workflow = workflow_repo.get_workflow_row(int(workflow_id))
    if not workflow:
        raise LookupError("workflow not found")
    bundle = _build_workflow_bundle(workflow)
    bundle["registry"] = list_conversion_workflow_registry()
    return bundle


def create_conversion_workflow(payload: dict[str, Any], *, operator_id: str, program_id: int | None = None) -> dict[str, Any]:
    effective_program_id = _effective_program_id(program_id or payload.get("program_id"))
    normalized = _normalize_workflow_payload(payload, program_id=effective_program_id)
    duplicate = workflow_repo.get_workflow_row_by_code(normalized["workflow_code"])
    if duplicate:
        raise ValueError("workflow_code already exists")
    saved_workflow = workflow_repo.insert_workflow_row(
        {**normalized, "program_id": effective_program_id, "created_by": operator_id, "updated_by": operator_id}
    )
    _sync_workflow_children(int(saved_workflow["id"]), normalized)
    get_db().commit()
    return {"workflow_bundle": get_conversion_workflow_model_bundle(int(saved_workflow["id"]))}


def update_conversion_workflow(workflow_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = get_conversion_workflow_model_bundle(int(workflow_id))
    effective_program_id = int((existing.get("workflow") or {}).get("program_id") or 0) or _effective_program_id()
    normalized = _normalize_workflow_payload(payload, existing={**existing["workflow"], "audiences": existing["audiences"], "agent_bindings": [
        {
            "node_id": int(item.get("node_id") or 0) or None,
            "binding_scope": _normalized_text(item.get("binding_scope")),
            "segment_key": _normalized_text(item.get("segment_key")),
            "agent_code": _normalized_text(item.get("agent_code") or (item.get("agent") or {}).get("agent_code")),
        }
        for item in existing.get("agent_bindings") or []
    ]}, program_id=effective_program_id)
    duplicate = workflow_repo.get_workflow_row_by_code(normalized["workflow_code"])
    if duplicate and int(duplicate["id"]) != int(workflow_id):
        raise ValueError("workflow_code already exists")
    workflow_repo.update_workflow_row(
        int(workflow_id),
        {
            **normalized,
            "program_id": effective_program_id,
            "updated_by": operator_id,
        },
    )
    _sync_workflow_children(int(workflow_id), normalized)
    get_db().commit()
    return {"workflow_bundle": get_conversion_workflow_model_bundle(int(workflow_id))}


def activate_conversion_workflow(workflow_id: int, *, operator_id: str) -> dict[str, Any]:
    return update_conversion_workflow(int(workflow_id), {"status": WORKFLOW_STATUS_ACTIVE}, operator_id=operator_id)


def pause_conversion_workflow(workflow_id: int, *, operator_id: str) -> dict[str, Any]:
    return update_conversion_workflow(int(workflow_id), {"status": WORKFLOW_STATUS_PAUSED}, operator_id=operator_id)


def delete_conversion_workflow(workflow_id: int) -> dict[str, Any]:
    existing = workflow_repo.get_workflow_row(int(workflow_id))
    if not existing:
        raise LookupError("workflow not found")
    workflow_repo.delete_workflow_row(int(workflow_id))
    get_db().commit()
    return {
        "deleted_workflow_id": int(workflow_id),
        "workflow_code": _normalized_text(existing.get("workflow_code")),
        "workflow_name": _normalized_text(existing.get("workflow_name")),
    }


def list_conversion_workflow_nodes(workflow_id: int) -> dict[str, Any]:
    bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    return {"items": list(bundle.get("nodes") or []), "total": len(bundle.get("nodes") or [])}


def create_conversion_workflow_node(workflow_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    workflow_bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    normalized = _normalize_node_payload(payload, workflow_bundle)
    node = workflow_repo.insert_workflow_node_row({"workflow_id": int(workflow_id), **normalized})
    _save_node_content(int(workflow_id), int(node["id"]), normalized)
    get_db().commit()
    refreshed_workflow_bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    refreshed_node = next((item for item in refreshed_workflow_bundle.get("nodes") or [] if int(item.get("id") or 0) == int(node["id"])), None)
    return {"node": refreshed_node or _build_node_bundle(workflow_repo.get_workflow_node_row(int(node["id"])) or node, refreshed_workflow_bundle)}


def update_conversion_workflow_node(node_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = workflow_repo.get_workflow_node_row(int(node_id))
    if not existing:
        raise LookupError("workflow node not found")
    workflow_bundle = get_conversion_workflow_model_bundle(int(existing["workflow_id"]))
    existing_node_bundle = next((item for item in workflow_bundle.get("nodes") or [] if int(item.get("id") or 0) == int(node_id)), None) or _build_node_bundle(existing, workflow_bundle)
    normalized = _normalize_node_payload(payload, workflow_bundle, existing=existing_node_bundle)
    workflow_repo.update_workflow_node_row(int(node_id), normalized)
    _save_node_content(int(existing["workflow_id"]), int(node_id), normalized)
    get_db().commit()
    refreshed_workflow_bundle = get_conversion_workflow_model_bundle(int(existing["workflow_id"]))
    refreshed_node = next((item for item in refreshed_workflow_bundle.get("nodes") or [] if int(item.get("id") or 0) == int(node_id)), None)
    return {"node": refreshed_node or _build_node_bundle(workflow_repo.get_workflow_node_row(int(node_id)) or existing, refreshed_workflow_bundle)}


def delete_conversion_workflow_node(node_id: int) -> dict[str, Any]:
    existing = workflow_repo.get_workflow_node_row(int(node_id))
    if not existing:
        raise LookupError("workflow node not found")
    workflow_repo.delete_workflow_node_row(int(node_id))
    get_db().commit()
    return {"deleted_node_id": int(node_id), "workflow_id": int(existing["workflow_id"])}


def list_conversion_workflow_executions(
    *,
    workflow_id: int | None = None,
    node_id: int | None = None,
    program_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    items = workflow_repo.list_workflow_execution_rows(
        workflow_id=workflow_id,
        node_id=node_id,
        program_id=_effective_program_id(program_id),
        limit=limit,
    )
    return {"items": items, "total": len(items)}


def get_conversion_workflow_execution_bundle(execution_row_id: int) -> dict[str, Any]:
    execution = workflow_repo.get_workflow_execution_row(execution_row_id)
    if not execution:
        raise LookupError("workflow execution not found")
    return {
        "execution": execution,
        "items": workflow_repo.list_workflow_execution_item_rows(execution_row_id),
    }


def _send_record_payload(record_id: int | None, *, include_detail: bool = False) -> dict[str, Any]:
    normalized_record_id = int(record_id or 0)
    if normalized_record_id <= 0:
        return {}
    row = user_ops_page_service._load_send_record_row(normalized_record_id)
    if not row:
        return {}
    task_results = user_ops_page_service._hydrate_task_results(row)
    if include_detail:
        return user_ops_page_service._serialize_send_record_detail(row, task_results)
    return user_ops_page_service._serialize_send_record_summary(row, task_results=task_results)


def _build_execution_item_payload(item: dict[str, Any], *, include_send_record_detail: bool = False) -> dict[str, Any]:
    snapshot = dict(item.get("content_snapshot_json") or {})
    member = workflow_repo.get_automation_member_row(int(item.get("member_id") or 0)) or {}
    send_record_id = int(item.get("send_record_id") or 0) or None
    return {
        **item,
        "member": {
            "id": int(member.get("id") or 0) or None,
            "external_contact_id": _normalized_text(member.get("external_contact_id")),
            "phone": _normalized_text(member.get("phone")),
            "owner_staff_id": _normalized_text(member.get("owner_staff_id")),
            "current_audience_code": _normalized_text(member.get("current_audience_code")),
            "current_audience_entered_at": _normalized_text(member.get("current_audience_entered_at")),
        },
        "rendered_content_preview": _truncate_text(item.get("rendered_content_text"), limit=160),
        "generation_summary": {
            "content_source": _normalized_text(snapshot.get("content_source")),
            "fallback_reason": _normalized_text(snapshot.get("fallback_reason")),
            "segment_match": dict(snapshot.get("segment_match") or {}),
            "behavior_match": dict(snapshot.get("behavior_match") or {}),
            "agent_code": _normalized_text(item.get("agent_code")),
            "agent_run_id": _normalized_text(item.get("agent_run_id")),
            "agent_output_id": _normalized_text(item.get("agent_output_id")),
        },
        "send_record_id": send_record_id,
        "send_record": _send_record_payload(send_record_id, include_detail=include_send_record_detail),
    }


def _execution_count_payload(execution: dict[str, Any], count_summary: dict[str, Any] | None = None) -> dict[str, int]:
    summary = dict(count_summary or {})
    total_count = int((summary.get("total_count") if "total_count" in summary else execution.get("total_count")) or 0)
    success_count = int((summary.get("success_count") if "success_count" in summary else execution.get("success_count")) or 0)
    failed_count = int((summary.get("failed_count") if "failed_count" in summary else execution.get("failed_count")) or 0)
    skipped_count = int((summary.get("skipped_count") if "skipped_count" in summary else execution.get("skipped_count")) or 0)
    return {
        "total_count": total_count,
        "hit_count": total_count,
        "success_count": success_count,
        "sent_count": success_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
    }


def _build_execution_payload(execution: dict[str, Any], count_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    workflow = workflow_repo.get_workflow_row(int(execution.get("workflow_id") or 0)) or {}
    node = workflow_repo.get_workflow_node_row(int(execution.get("node_id") or 0)) or {}
    return {
        **execution,
        **_execution_count_payload(execution, count_summary),
        "workflow": {
            "id": int(workflow.get("id") or 0) or None,
            "workflow_code": _normalized_text(workflow.get("workflow_code")),
            "workflow_name": _normalized_text(workflow.get("workflow_name")),
            "status": _normalized_text(workflow.get("status")),
        },
        "node": {
            "id": int(node.get("id") or 0) or None,
            "node_code": _normalized_text(node.get("node_code")),
            "node_name": _normalized_text(node.get("node_name")),
            "target_audience_code": _normalized_text(node.get("target_audience_code")),
            "trigger_mode": _normalized_text(node.get("trigger_mode")) or NODE_TRIGGER_MODE_SCHEDULED,
            "day_offset": int(node.get("day_offset") or 0),
            "send_time": _normalized_text(node.get("send_time")),
        },
    }


def _build_workflow_execution_summary_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_name": _normalized_text(row.get("workflow_name")),
        "execution_count": int(row.get("execution_count") or 0),
        "latest_execution_at": _normalized_text(row.get("latest_execution_at")),
    }


def _conversion_audience_meta_map() -> dict[str, dict[str, str]]:
    return {
        _normalized_text(item.get("audience_code")): {
            "label": _normalized_text(item.get("label")),
            "description": _normalized_text(item.get("description")),
        }
        for item in list_supported_conversion_audiences()
    }


def _questionnaire_status_label(value: Any) -> str:
    normalized = _normalized_text(value)
    return {
        "pending": "待提交",
        "submitted": "已提交",
    }.get(normalized, normalized or "待提交")


def _activation_status_label(value: Any) -> str:
    normalized = _normalized_text(value)
    return {
        "active": "已激活",
        "inactive": "未激活",
        "activated": "已激活",
        "not_activated": "未激活",
        "high_intent": "高意向",
    }.get(normalized, "")


def _behavior_tier_for_count(message_count: int) -> dict[str, Any]:
    normalized_count = max(0, int(message_count or 0))
    for item in list_supported_behavior_tiers():
        min_value = item.get("min_value")
        max_value = item.get("max_value")
        if min_value is not None and normalized_count < int(min_value):
            continue
        if max_value is not None and normalized_count > int(max_value):
            continue
        return dict(item)
    return dict(list_supported_behavior_tiers()[0])


def _message_activity_count_map_by_phone_match_key() -> dict[str, int]:
    status = get_message_activity_db_status()
    if not bool(status.get("configured")):
        return {}
    try:
        rows = query_message_activity_counts()
    except Exception:
        return {}
    return {
        _normalized_text(row.get("phone_match_key")): int(row.get("message_count") or 0)
        for row in rows
        if _normalized_text(row.get("phone_match_key"))
    }


def _message_activity_for_phone(phone: Any, *, counts_by_match_key: dict[str, int], audience_code: str = "") -> dict[str, Any]:
    digits = "".join(char for char in _normalized_text(phone) if char.isdigit())
    if len(digits) < 7:
        return {"available": False, "message_count": 0, "phone_match_key": ""}
    phone_match_key = f"{digits[:3]}_{digits[-4:]}"
    if phone_match_key not in counts_by_match_key:
        if _normalized_text(audience_code) in {AUDIENCE_OPERATING, AUDIENCE_CONVERTED}:
            return {
                "available": True,
                "message_count": 0,
                "phone_match_key": phone_match_key,
                "source": "message_activity_db_missing_as_zero",
            }
        return {"available": False, "message_count": 0, "phone_match_key": phone_match_key}
    return {
        "available": True,
        "message_count": int(counts_by_match_key.get(phone_match_key) or 0),
        "phone_match_key": phone_match_key,
    }


def _latest_enabled_profile_segment_template_bundle(*, program_id: int | None = None) -> dict[str, Any]:
    invalid_enabled_templates: list[dict[str, Any]] = []
    for template in workflow_repo.list_profile_segment_template_rows(
        enabled_only=True,
        program_id=_effective_program_id(program_id),
    ):
        bundle = _build_profile_segment_template_bundle(template)
        if _profile_segment_template_is_valid(bundle):
            bundle["selection"] = {
                "strategy": "latest_valid_enabled",
                "status": "selected",
                "invalid_enabled_templates": invalid_enabled_templates,
            }
            return bundle
        invalid_enabled_templates.append(
            {
                "id": int(((bundle.get("template") or {}).get("id")) or 0) or None,
                "template_name": _normalized_text(((bundle.get("template") or {}).get("template_name"))),
                "reason_messages": list((bundle.get("validity") or {}).get("reason_messages") or []),
            }
        )
    if invalid_enabled_templates:
        return {
            "template": {},
            "questionnaire": {},
            "segmentation_question": {},
            "question_options": [],
            "categories": [],
            "validity": {
                "is_valid": False,
                "status": "invalid",
                "reason_codes": ["no_valid_enabled_template"],
                "reason_messages": ["当前没有有效的启用自然画像模板。"],
                "enabled_category_count": 0,
                "mapping_count": 0,
            },
            "selection": {
                "strategy": "latest_valid_enabled",
                "status": "no_valid_enabled_template",
                "invalid_enabled_templates": invalid_enabled_templates,
            },
            "supports_standard_fallback": True,
        }
    return {
        "template": {},
        "questionnaire": {},
        "segmentation_question": {},
        "question_options": [],
        "categories": [],
        "validity": {
            "is_valid": False,
            "status": "empty",
            "reason_codes": ["no_enabled_template"],
            "reason_messages": ["当前未启用自然画像模板。"],
            "enabled_category_count": 0,
            "mapping_count": 0,
        },
        "selection": {
            "strategy": "latest_valid_enabled",
            "status": "no_enabled_template",
            "invalid_enabled_templates": [],
        },
        "supports_standard_fallback": True,
    }


def _program_setup_segmentation_payload(*, program_id: int | None = None) -> dict[str, Any]:
    effective_program_id = _effective_program_id(program_id)
    block = program_repo.get_config_block_row(effective_program_id, _SETUP_SEGMENTATION_BLOCK_KEY)
    payload = dict((block or {}).get("payload_json") or {})
    return payload


def _setup_normal_question_categories(payload: dict[str, Any]) -> list[dict[str, Any]]:
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    if _normalized_text(payload.get("default_strategy")) != "normal_question_rules":
        return []
    if not bool(normal.get("enabled", True)):
        return []
    if _normalized_text(normal.get("mode")) not in {"", _SETUP_OPTION_CATEGORY_MODE}:
        return []
    categories: list[dict[str, Any]] = []
    for index, category in enumerate(list(normal.get("categories") or []), start=1):
        option_ids: list[int] = []
        for option_id in list(category.get("option_ids") or []):
            try:
                normalized_option_id = int(option_id)
            except (TypeError, ValueError):
                continue
            if normalized_option_id > 0:
                option_ids.append(normalized_option_id)
        category_key = _normalized_text(category.get("category_key")) or f"category_{index}"
        category_name = _normalized_text(category.get("category_name")) or f"分类 {index}"
        if not option_ids or not category_key:
            continue
        categories.append(
            {
                "id": None,
                "category_key": category_key,
                "category_name": category_name,
                "description": _normalized_text(category.get("description")),
                "sort_order": index,
                "enabled": True,
                "option_ids": option_ids,
            }
        )
    return categories


def _setup_option_category_profile_bundle(
    *, program_id: int | None = None, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    setup_payload = dict(payload or _program_setup_segmentation_payload(program_id=program_id) or {})
    strategies = dict(setup_payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    questionnaire_id = int(setup_payload.get("questionnaire_id") or 0)
    question_id = int(normal.get("segmentation_question_id") or 0)
    categories = _setup_normal_question_categories(setup_payload)
    if not questionnaire_id or not question_id or not categories:
        return {
            "template": {},
            "questionnaire": {},
            "segmentation_question": {},
            "question_options": [],
            "categories": [],
            "validity": {
                "is_valid": False,
                "status": "empty",
                "reason_codes": ["setup_option_category_empty"],
                "reason_messages": ["当前方案尚未配置普通问卷选项分类。"],
                "enabled_category_count": 0,
                "mapping_count": 0,
            },
            "selection": {
                "strategy": "setup_option_category",
                "status": "empty",
                "invalid_enabled_templates": [],
            },
            "supports_standard_fallback": True,
        }
    questionnaire = workflow_repo.get_questionnaire_row(questionnaire_id) or {}
    question = workflow_repo.get_questionnaire_question_row(questionnaire_id, question_id) or {}
    question_options = workflow_repo.list_questionnaire_option_rows(question_id)
    mapping_count = sum(len(category.get("option_ids") or []) for category in categories)
    return {
        "template": {
            "id": None,
            "program_id": _effective_program_id(program_id),
            "template_code": "setup_question_option_category",
            "template_name": "普通问卷选项分类",
            "questionnaire_id": questionnaire_id,
            "segmentation_question_id": question_id,
            "enabled": True,
        },
        "questionnaire": questionnaire,
        "segmentation_question": question,
        "question_options": question_options,
        "categories": categories,
        "validity": {
            "is_valid": True,
            "status": "valid",
            "reason_codes": [],
            "reason_messages": [],
            "enabled_category_count": len(categories),
            "mapping_count": mapping_count,
        },
        "selection": {
            "strategy": "setup_option_category",
            "status": "selected",
            "invalid_enabled_templates": [],
        },
        "supports_standard_fallback": True,
    }


def _active_profile_segment_template_bundle(*, program_id: int | None = None) -> dict[str, Any]:
    setup_payload = _program_setup_segmentation_payload(program_id=program_id)
    setup_bundle = _setup_option_category_profile_bundle(program_id=program_id, payload=setup_payload)
    if bool((setup_bundle.get("validity") or {}).get("is_valid")):
        return setup_bundle
    return _latest_enabled_profile_segment_template_bundle(program_id=program_id)


def profile_segment_label_map_for_program(*, program_id: int | None = None) -> dict[str, str]:
    payload = _program_setup_segmentation_payload(program_id=program_id)
    label_map: dict[str, str] = {}
    for category in _setup_normal_question_categories(payload):
        key = _normalized_text(category.get("category_key"))
        if key:
            label_map[key] = _normalized_text(category.get("category_name")) or key
    strategies = dict(payload.get("strategies") or {})
    score_segments = dict(strategies.get("score_segments") or {})
    for item in list(score_segments.get("ranges") or []):
        key = _normalized_text(item.get("segment_key"))
        if key:
            label_map[key] = _normalized_text(item.get("segment_name")) or key
    for category in (_latest_enabled_profile_segment_template_bundle(program_id=program_id).get("categories") or []):
        if not bool(category.get("enabled")):
            continue
        key = _normalized_text(category.get("category_key"))
        if key and key not in label_map:
            label_map[key] = _normalized_text(category.get("category_name")) or key
    return label_map


def _resolve_score_segment_for_member(
    *,
    member: dict[str, Any],
    setup_segmentation_payload: dict[str, Any],
) -> dict[str, Any]:
    if _normalized_text(setup_segmentation_payload.get("default_strategy")) != "score_segments":
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "score_segments_not_selected",
            "submission_id": None,
            "total_score": None,
        }
    strategies = dict(setup_segmentation_payload.get("strategies") or {})
    score_segments = dict(strategies.get("score_segments") or {})
    if not bool(score_segments.get("enabled")):
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "score_segments_disabled",
            "submission_id": None,
            "total_score": None,
        }
    questionnaire_id = int(setup_segmentation_payload.get("questionnaire_id") or 0)
    if not questionnaire_id:
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "questionnaire_missing",
            "submission_id": None,
            "total_score": None,
        }
    submission = workflow_repo.get_latest_questionnaire_submission_row(
        questionnaire_id=questionnaire_id,
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
    )
    if not submission:
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "questionnaire_submission_missing",
            "submission_id": None,
            "total_score": None,
        }
    total_score = float(submission.get("total_score") or 0)
    for item in list(score_segments.get("ranges") or []):
        try:
            min_score = float(item.get("min_score"))
            max_score = float(item.get("max_score"))
        except (TypeError, ValueError):
            continue
        if min_score <= total_score <= max_score:
            key = _normalized_text(item.get("segment_key"))
            return {
                "matched": bool(key),
                "segment_key": key,
                "segment_label": _normalized_text(item.get("segment_name")) or key,
                "reason": "",
                "submission_id": int(submission.get("id") or 0) or None,
                "total_score": total_score,
            }
    return {
        "matched": False,
        "segment_key": "",
        "segment_label": "",
        "reason": "score_segment_not_matched",
        "submission_id": int(submission.get("id") or 0) or None,
        "total_score": total_score,
    }


def _resolve_profile_segment_for_member(
    *,
    member: dict[str, Any],
    profile_segment_template_bundle: dict[str, Any],
) -> dict[str, Any]:
    validity = dict(profile_segment_template_bundle.get("validity") or {})
    if validity and not bool(validity.get("is_valid")):
        reason_codes = [str(item).strip() for item in list(validity.get("reason_codes") or []) if str(item).strip()]
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": reason_codes[0] if reason_codes else "profile_segment_template_invalid",
            "submission_id": None,
            "selected_option_ids": [],
        }
    template = dict(profile_segment_template_bundle.get("template") or {})
    questionnaire_id = int(template.get("questionnaire_id") or 0)
    question_id = int(template.get("segmentation_question_id") or 0)
    if questionnaire_id <= 0 or question_id <= 0:
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "profile_segment_template_missing",
            "submission_id": None,
            "selected_option_ids": [],
        }
    submission = workflow_repo.get_latest_questionnaire_submission_row(
        questionnaire_id=questionnaire_id,
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
    )
    if not submission:
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "questionnaire_submission_missing",
            "submission_id": None,
            "selected_option_ids": [],
        }
    answer = next(
        (
            item
            for item in workflow_repo.list_questionnaire_submission_answer_rows(int(submission.get("id") or 0))
            if int(item.get("question_id") or 0) == question_id
        ),
        None,
    )
    if not answer:
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "segmentation_question_answer_missing",
            "submission_id": int(submission.get("id") or 0) or None,
            "selected_option_ids": [],
        }
    try:
        selected_option_ids = {int(option_id) for option_id in json.loads(_normalized_text(answer.get("selected_option_ids")) or "[]")}
    except (TypeError, ValueError, json.JSONDecodeError):
        selected_option_ids = set()
    if not selected_option_ids:
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "selected_option_ids_empty",
            "submission_id": int(submission.get("id") or 0) or None,
            "selected_option_ids": [],
        }
    matched_categories = [
        {
            "category_key": _normalized_text(category.get("category_key")),
            "category_name": _normalized_text(category.get("category_name")),
        }
        for category in profile_segment_template_bundle.get("categories") or []
        if bool(category.get("enabled")) and set(int(option_id) for option_id in (category.get("option_ids") or [])) & selected_option_ids
    ]
    if len(matched_categories) != 1:
        return {
            "matched": False,
            "segment_key": "",
            "segment_label": "",
            "reason": "multiple_or_zero_profile_categories",
            "submission_id": int(submission.get("id") or 0) or None,
            "selected_option_ids": sorted(selected_option_ids),
            "matched_categories": matched_categories,
        }
    matched_category = dict(matched_categories[0])
    return {
        "matched": True,
        "segment_key": _normalized_text(matched_category.get("category_key")),
        "segment_label": _normalized_text(matched_category.get("category_name")),
        "reason": "",
        "submission_id": int(submission.get("id") or 0) or None,
        "selected_option_ids": sorted(selected_option_ids),
    }


def _build_dashboard_member_detail_item(
    row: dict[str, Any],
    *,
    message_activity_counts_by_match_key: dict[str, int],
    profile_segment_template_bundle: dict[str, Any],
    setup_segmentation_payload: dict[str, Any],
    audience_meta_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    from .service import resolve_member_questionnaire_truth

    member = dict(row.get("member") or {})
    audience_code = _normalized_text(member.get("current_audience_code") or row.get("audience_code"))
    external_contact_id = _normalized_text(member.get("external_contact_id"))
    questionnaire = resolve_member_questionnaire_truth(
        external_contact_ids=[external_contact_id] if external_contact_id else [],
        phone=_normalized_text(member.get("phone")),
        member=member,
    )
    questionnaire_status = _normalized_text(questionnaire.get("questionnaire_status"))
    activation_status = _normalized_text(member.get("activation_status"))
    message_activity = _message_activity_for_phone(
        member.get("phone"),
        counts_by_match_key=message_activity_counts_by_match_key,
        audience_code=audience_code,
    )
    message_count = int(message_activity.get("message_count") or 0)
    behavior_tier = _behavior_tier_for_count(message_count) if bool(message_activity.get("available")) else {}
    if _normalized_text(setup_segmentation_payload.get("default_strategy")) == "score_segments":
        profile_segment = _resolve_score_segment_for_member(
            member=member,
            setup_segmentation_payload=setup_segmentation_payload,
        )
    else:
        profile_segment = _resolve_profile_segment_for_member(
            member=member,
            profile_segment_template_bundle=profile_segment_template_bundle,
        )
    payload = {
        "member_id": int(member.get("id") or 0) or None,
        "external_contact_id": external_contact_id,
        "phone": _normalized_text(member.get("phone")),
        "customer_name": _normalized_text(member.get("customer_name")),
        "audience_code": audience_code,
        "audience_label": _normalized_text((audience_meta_map.get(audience_code) or {}).get("label")),
        "questionnaire_status": questionnaire_status,
        "questionnaire_status_label": _questionnaire_status_label(questionnaire_status),
        "profile_segment_key": _normalized_text(profile_segment.get("segment_key")),
        "profile_segment_label": _normalized_text(profile_segment.get("segment_label")),
        "behavior_segment_key": _normalized_text(behavior_tier.get("tier_code")),
        "behavior_segment_label": _normalized_text(behavior_tier.get("label")),
        "conversation_count": message_count,
    }
    if audience_code == AUDIENCE_OPERATING and _normalized_text(member.get("current_pool")) != AUDIENCE_OPERATING:
        payload["activation_status"] = activation_status
        payload["activation_status_label"] = _activation_status_label(activation_status)
    return payload


def _maybe_persist_member_segment_keys(
    *, row: dict[str, Any], item: dict[str, Any], refreshed_at: str
) -> None:
    member = dict(row.get("member") or {})
    member_id = int(member.get("id") or 0)
    if not member_id:
        return
    new_profile_key = _normalized_text(item.get("profile_segment_key"))
    new_behavior_key = _normalized_text(item.get("behavior_segment_key"))
    old_profile_key = _normalized_text(member.get("profile_segment_key"))
    old_behavior_key = _normalized_text(member.get("behavior_tier_key"))
    if new_profile_key == old_profile_key and new_behavior_key == old_behavior_key:
        return
    try:
        workflow_repo.update_member_segment_keys(
            member_id,
            profile_segment_key=new_profile_key,
            behavior_tier_key=new_behavior_key,
            refreshed_at=refreshed_at,
        )
    except Exception:
        # Persistence is best-effort; the dashboard render must still succeed
        # if a single UPDATE fails (e.g. concurrent modification).
        pass


def _build_dashboard_audience_member_details(*, program_id: int | None = None) -> dict[str, Any]:
    audience_definitions = list_supported_conversion_audiences()
    audience_meta_map = _conversion_audience_meta_map()
    effective_program_id = _effective_program_id(program_id)
    default_program_id = program_service.get_default_automation_program_id()
    include_unscoped = effective_program_id == default_program_id
    rows_by_audience: dict[str, list[dict[str, Any]]] = {}
    for definition in audience_definitions:
        audience_code = _normalized_text(definition.get("audience_code"))
        rows = workflow_repo.list_current_member_audience_rows(
            audience_code,
            program_id=effective_program_id,
            include_unscoped=include_unscoped,
        )
        rows_by_audience[audience_code] = rows
    message_activity_counts_by_match_key = _message_activity_count_map_by_phone_match_key()
    setup_segmentation_payload = _program_setup_segmentation_payload(program_id=effective_program_id)
    profile_segment_template_bundle = _active_profile_segment_template_bundle(program_id=effective_program_id)
    groups: list[dict[str, Any]] = []
    total = 0
    refreshed_at_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for definition in audience_definitions:
        audience_code = _normalized_text(definition.get("audience_code"))
        rows = rows_by_audience.get(audience_code) or []
        items: list[dict[str, Any]] = []
        for row in rows:
            item = _build_dashboard_member_detail_item(
                row,
                message_activity_counts_by_match_key=message_activity_counts_by_match_key,
                profile_segment_template_bundle=profile_segment_template_bundle,
                setup_segmentation_payload=setup_segmentation_payload,
                audience_meta_map=audience_meta_map,
            )
            items.append(item)
            _maybe_persist_member_segment_keys(
                row=row,
                item=item,
                refreshed_at=refreshed_at_value,
            )
        total += len(items)
        groups.append(
            {
                "audience_code": audience_code,
                "audience_label": _normalized_text(definition.get("label")),
                "audience_description": _normalized_text(definition.get("description")),
                "count": len(items),
                "items": items,
            }
        )
    try:
        get_db().commit()
    except Exception:
        pass
    template = dict(profile_segment_template_bundle.get("template") or {})
    validity = dict(profile_segment_template_bundle.get("validity") or {})
    selection = dict(profile_segment_template_bundle.get("selection") or {})
    return {
        "groups": groups,
        "total": total,
        "profile_segment_template": {
            "id": int(template.get("id") or 0) or None,
            "template_name": _normalized_text(template.get("template_name")),
            "enabled": bool(template),
            "valid": bool(validity.get("is_valid")),
            "validity_status": _normalized_text(validity.get("status")),
            "reason_messages": list(validity.get("reason_messages") or []),
            "selection_strategy": _normalized_text(selection.get("strategy")) or "latest_valid_enabled",
            "selection_status": _normalized_text(selection.get("status")) or ("selected" if template else "no_enabled_template"),
            "skipped_invalid_enabled_template_count": len(list(selection.get("invalid_enabled_templates") or [])),
            "skipped_invalid_enabled_templates": list(selection.get("invalid_enabled_templates") or []),
        },
    }


def apply_dashboard_signup_tag(*, operator_id: str = "", program_id: int | None = None) -> dict[str, Any]:
    effective_program_id = _effective_program_id(program_id)
    default_program_id = program_service.get_default_automation_program_id()
    include_unscoped = effective_program_id == default_program_id
    signup_rules = list(tags_service.get_signup_tag_rules_config().get("items") or [])
    target_rule = next(
        (
            dict(item)
            for item in signup_rules
            if _normalized_text(item.get("tag_name")) == _OVERVIEW_SIGNUP_TAG_NAME
            and _normalized_text(item.get("tag_id"))
        ),
        None,
    )
    if not target_rule:
        raise ValueError(f"未找到已启用的报名标签规则：{_OVERVIEW_SIGNUP_TAG_NAME}")
    target_tag_id = _normalized_text(target_rule.get("tag_id"))
    target_tag_name = _normalized_text(target_rule.get("tag_name")) or _OVERVIEW_SIGNUP_TAG_NAME
    remove_tag_ids = sorted(
        {
            _normalized_text(item.get("tag_id"))
            for item in signup_rules
            if _normalized_text(item.get("tag_id")) and _normalized_text(item.get("tag_id")) != target_tag_id
        }
    )
    deduped_targets: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for definition in list_supported_conversion_audiences():
        audience_code = _normalized_text(definition.get("audience_code"))
        for row in workflow_repo.list_current_member_audience_rows(
            audience_code,
            program_id=effective_program_id,
            include_unscoped=include_unscoped,
        ):
            member = dict(row.get("member") or {})
            external_contact_id = _normalized_text(member.get("external_contact_id"))
            owner_staff_id = _normalized_text(member.get("owner_staff_id"))
            if not external_contact_id or not owner_staff_id:
                deduped_targets.append(
                    {
                        "audience_code": audience_code,
                        "external_contact_id": external_contact_id,
                        "owner_staff_id": owner_staff_id,
                        "skipped_reason": "missing_external_or_owner",
                    }
                )
                continue
            pair = (external_contact_id, owner_staff_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            deduped_targets.append(
                {
                    "audience_code": audience_code,
                    "external_contact_id": external_contact_id,
                    "owner_staff_id": owner_staff_id,
                }
            )
    client = get_app_runtime_client()
    attempted = 0
    success_count = 0
    skipped_count = 0
    failed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for item in deduped_targets:
        external_contact_id = _normalized_text(item.get("external_contact_id"))
        owner_staff_id = _normalized_text(item.get("owner_staff_id"))
        if not external_contact_id or not owner_staff_id:
            skipped_count += 1
            skipped.append(
                {
                    "audience_code": _normalized_text(item.get("audience_code")),
                    "external_contact_id": external_contact_id,
                    "owner_staff_id": owner_staff_id,
                    "reason": _normalized_text(item.get("skipped_reason")) or "missing_external_or_owner",
                }
            )
            continue
        attempted += 1
        try:
            client.mark_external_contact_tags(
                external_userid=external_contact_id,
                follow_user_userid=owner_staff_id,
                add_tags=[target_tag_id],
                remove_tags=remove_tag_ids,
            )
            tags_repo.save_tag_snapshot(
                owner_staff_id,
                external_contact_id,
                [target_tag_id],
                {target_tag_id: target_tag_name},
            )
            if remove_tag_ids:
                tags_repo.remove_tag_snapshot(owner_staff_id, external_contact_id, remove_tag_ids)
            success_count += 1
        except (WeComClientError, AttributeError, ValueError) as exc:
            failed.append(
                {
                    "audience_code": _normalized_text(item.get("audience_code")),
                    "external_contact_id": external_contact_id,
                    "owner_staff_id": owner_staff_id,
                    "error": str(exc),
                }
            )
    return {
        "ok": not failed,
        "operator_id": _normalized_text(operator_id),
        "target_tag_id": target_tag_id,
        "target_tag_name": target_tag_name,
        "remove_tag_ids": remove_tag_ids,
        "attempted_count": attempted,
        "success_count": success_count,
        "skipped_count": skipped_count,
        "failed_count": len(failed),
        "failed": failed,
        "skipped": skipped,
        "message": (
            f"已处理 {attempted} 个用户，成功打标 {success_count} 个，"
            f"跳过 {skipped_count} 个，失败 {len(failed)} 个。"
        ),
    }


def get_conversion_dashboard_payload(*, program_id: int | None = None) -> dict[str, Any]:
    effective_program_id = _effective_program_id(program_id)
    default_program_id = program_service.get_default_automation_program_id()
    audience_counts = workflow_repo.get_current_audience_member_counts(
        program_id=effective_program_id,
        include_unscoped=effective_program_id == default_program_id,
    )
    workflow_execution_summary = [
        _build_workflow_execution_summary_item(item)
        for item in workflow_repo.list_workflow_execution_summary_rows(program_id=effective_program_id)
    ]
    return {
        "audience_overview": {
            "pending_questionnaire_count": int(audience_counts.get(AUDIENCE_PENDING_QUESTIONNAIRE) or 0),
            "operating_count": int(audience_counts.get(AUDIENCE_OPERATING) or 0),
            "converted_count": int(audience_counts.get(AUDIENCE_CONVERTED) or 0),
            "total_count": sum(int(value or 0) for value in audience_counts.values()),
        },
        "active_workflow_count": workflow_repo.count_workflow_rows(status=WORKFLOW_STATUS_ACTIVE, program_id=effective_program_id),
        "audience_member_details": _build_dashboard_audience_member_details(program_id=effective_program_id),
        "task_execution_summary": {
            "items": workflow_execution_summary,
            "total": len(workflow_execution_summary),
        },
    }


def get_conversion_workflow_detail_summary(workflow_id: int) -> dict[str, Any]:
    bundle = get_conversion_workflow_model_bundle(int(workflow_id))
    recent_executions = [
        _build_execution_payload(item)
        for item in workflow_repo.list_workflow_execution_rows(workflow_id=int(workflow_id), limit=5)
    ]
    latest_execution = dict(recent_executions[0]) if recent_executions else {}
    bindings_summary = [
        {
            "binding_scope": _normalized_text(item.get("binding_scope")),
            "segment_key": _normalized_text(item.get("segment_key")),
            "agent_code": _normalized_text(item.get("agent_code") or (item.get("agent") or {}).get("agent_code")),
            "agent_name": _normalized_text((item.get("agent") or {}).get("agent_name")),
            "status": _normalized_text((item.get("agent") or {}).get("status")),
        }
        for item in bundle.get("agent_bindings") or []
    ]
    return {
        "workflow_id": int((bundle.get("workflow") or {}).get("id") or 0),
        "node_count": len(bundle.get("nodes") or []),
        "enabled_node_count": sum(1 for item in bundle.get("nodes") or [] if bool(item.get("enabled"))),
        "latest_execution_at": _normalized_text((latest_execution.get("scheduled_for") or latest_execution.get("updated_at"))),
        "latest_execution": latest_execution,
        "recent_execution_summary": {
            "items": recent_executions,
            "total": len(recent_executions),
        },
        "agent_binding_summary": bindings_summary,
    }


def list_conversion_profile_segment_template_options(*, enabled_only: bool = True, program_id: int | None = None) -> dict[str, Any]:
    bundles = [
        _build_profile_segment_template_bundle(item)
        for item in workflow_repo.list_profile_segment_template_rows(
            enabled_only=enabled_only,
            program_id=_effective_program_id(program_id),
        )
    ]
    if enabled_only:
        bundles = [item for item in bundles if _profile_segment_template_is_valid(item)]
    items = [
        {
            "id": int(((item.get("template") or {}).get("id")) or 0),
            "template_code": _normalized_text(((item.get("template") or {}).get("template_code"))),
            "template_name": _normalized_text(((item.get("template") or {}).get("template_name"))),
            "questionnaire_id": int((((item.get("template") or {}).get("questionnaire_id")) or 0)) or None,
            "segmentation_question_id": int((((item.get("template") or {}).get("segmentation_question_id")) or 0)) or None,
            "enabled": bool(((item.get("template") or {}).get("enabled"))),
            "valid": bool((item.get("validity") or {}).get("is_valid")),
            "updated_at": _normalized_text(((item.get("template") or {}).get("updated_at"))),
        }
        for item in bundles
    ]
    return {"items": items, "total": len(items)}


def list_conversion_workflow_execution_records(
    *,
    workflow_id: int | None = None,
    node_id: int | None = None,
    program_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    execution_rows = workflow_repo.list_workflow_execution_rows(
        workflow_id=workflow_id,
        node_id=node_id,
        program_id=_effective_program_id(program_id),
        limit=limit,
    )
    item_count_map = workflow_repo.get_workflow_execution_item_count_map([int(item.get("id") or 0) for item in execution_rows])
    items = [
        _build_execution_payload(item, item_count_map.get(int(item.get("id") or 0)))
        for item in execution_rows
    ]
    return {"items": items, "total": len(items)}


def get_conversion_workflow_execution_detail(execution_row_id: int) -> dict[str, Any]:
    execution = workflow_repo.get_workflow_execution_row(int(execution_row_id))
    if not execution:
        raise LookupError("workflow execution not found")
    items = [
        _build_execution_item_payload(item)
        for item in workflow_repo.list_workflow_execution_item_rows(int(execution_row_id))
    ]
    item_summary = {
        "total_count": len(items),
        "success_count": sum(1 for item in items if _normalized_text(item.get("status")) == "sent"),
        "failed_count": sum(1 for item in items if _normalized_text(item.get("status")) == "failed"),
        "skipped_count": sum(1 for item in items if _normalized_text(item.get("status")) == "skipped"),
    }
    if not items:
        item_summary = _execution_count_payload(execution)
    return {
        "execution": _build_execution_payload(execution, item_summary),
        "summary": {
            "hit_count": int(item_summary.get("total_count") or 0),
            "success_count": int(item_summary.get("success_count") or 0),
            "failed_count": int(item_summary.get("failed_count") or 0),
            "skipped_count": int(item_summary.get("skipped_count") or 0),
        },
        "items": items,
    }


def list_conversion_workflow_execution_items(execution_row_id: int) -> dict[str, Any]:
    execution = workflow_repo.get_workflow_execution_row(int(execution_row_id))
    if not execution:
        raise LookupError("workflow execution not found")
    items = [
        _build_execution_item_payload(item)
        for item in workflow_repo.list_workflow_execution_item_rows(int(execution_row_id))
    ]
    return {"execution": _build_execution_payload(execution), "items": items, "total": len(items)}


def get_conversion_workflow_execution_item_detail(execution_item_id: int) -> dict[str, Any]:
    item = workflow_repo.get_workflow_execution_item_row(int(execution_item_id))
    if not item:
        raise LookupError("workflow execution item not found")
    execution = workflow_repo.get_workflow_execution_row(int(item.get("execution_id") or 0)) or {}
    return {
        "execution": _build_execution_payload(execution) if execution else {},
        "item": _build_execution_item_payload(item, include_send_record_detail=True),
    }


def _compute_bazhuayu_sign(secret: str, timestamp: str) -> str:
    normalized_secret = _normalized_text(secret)
    normalized_timestamp = _normalized_text(timestamp)
    if not normalized_secret:
        raise ValueError("bazhuayu signing secret is not configured")
    if not normalized_timestamp:
        raise ValueError("bazhuayu timestamp is required")
    string_to_sign = f"{normalized_timestamp}\n{normalized_secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _send_text_via_bazhuayu(
    *,
    userid: str,
    text: str,
    operator_id: str = "",
    result_id_key: str,
    result_id_value: Any,
) -> dict[str, Any]:
    if not userid:
        raise ValueError("missing external_contact_id")
    if not text:
        raise ValueError("rendered content is empty")

    webhook_url = _setting_text("BAZHUAYU_WEBHOOK_URL", default=_BAZHUAYU_DEFAULT_WEBHOOK_URL)
    signing_secret = _setting_text("BAZHUAYU_SIGNING_SECRET", default=_BAZHUAYU_DEFAULT_SIGNING_SECRET)
    specified_bot = _setting_text("BAZHUAYU_SPECIFIED_BOT")
    timeout_seconds = _setting_int(
        "BAZHUAYU_TIMEOUT_SECONDS",
        default=_BAZHUAYU_DEFAULT_TIMEOUT_SECONDS,
        minimum=1,
    )
    timestamp = str(int(time.time()))
    payload = {
        "sign": _compute_bazhuayu_sign(signing_secret, timestamp),
        "params": {
            "userid": userid,
            "text": text,
        },
        "timestamp": timestamp,
    }
    if specified_bot:
        payload["SpecifiedBot"] = specified_bot

    from ...infra.http_client import OutboundHttpError, get_outbound_client

    bazhuayu_client = get_outbound_client(
        "bazhuayu_webhook",
        timeout=float(timeout_seconds),
        retry_max=2,
    )
    try:
        response = bazhuayu_client.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    except OutboundHttpError as exc:
        original_message = str(exc.cause) if exc.cause else str(exc)
        raise requests.RequestException(original_message) from exc
    raw_body = response.text or ""
    try:
        response_payload = response.json() if raw_body else {}
    except ValueError:
        response_payload = raw_body
    if not response.ok:
        if isinstance(response_payload, dict) and _normalized_text(response_payload.get("description")):
            message = _normalized_text(response_payload.get("description"))
        elif isinstance(response_payload, dict) and _normalized_text(response_payload.get("message")):
            message = _normalized_text(response_payload.get("message"))
        else:
            message = raw_body.strip() or f"bazhuayu webhook failed: HTTP {response.status_code}"
        raise requests.RequestException(message)

    return {
        "ok": True,
        result_id_key: result_id_value,
        "requested_by": _normalized_text(operator_id) or "crm_console",
        "request": {
            "userid": userid,
            "text": text,
            "timestamp": timestamp,
            "specified_bot": specified_bot,
        },
        "response": response_payload if isinstance(response_payload, dict) else {"raw": raw_body},
    }


def send_text_via_bazhuayu_webhook(
    *,
    userid: str,
    text: str,
    operator_id: str = "",
    result_id_key: str,
    result_id_value: Any,
) -> dict[str, Any]:
    return _send_text_via_bazhuayu(
        userid=userid,
        text=text,
        operator_id=operator_id,
        result_id_key=result_id_key,
        result_id_value=result_id_value,
    )


def send_conversion_execution_item_via_bazhuayu(execution_item_id: int, *, operator_id: str = "") -> dict[str, Any]:
    detail = get_conversion_workflow_execution_item_detail(int(execution_item_id))
    item = dict(detail.get("item") or {})
    member = dict(item.get("member") or {})
    userid = _normalized_text(item.get("external_contact_id")) or _normalized_text(member.get("external_contact_id"))
    text = _normalized_text(item.get("rendered_content_text"))
    if not userid:
        raise ValueError("execution item missing external_contact_id")
    if not text:
        raise ValueError("execution item rendered content is empty")
    return _send_text_via_bazhuayu(
        userid=userid,
        text=text,
        operator_id=operator_id,
        result_id_key="execution_item_id",
        result_id_value=int(item.get("id") or 0),
    )


def send_agent_reply_output_via_bazhuayu(output_id: str, *, operator_id: str = "") -> dict[str, Any]:
    row = orchestration_repo.get_agent_output_row(_normalized_text(output_id))
    if not row:
        raise LookupError("未找到对应话术输出")
    output = orchestration_repo.deserialize_agent_output_row(row)
    userid = _normalized_text(output.get("external_contact_id"))
    text = _normalized_text(output.get("rendered_output_text"))
    if not userid:
        raise ValueError("reply output missing external_contact_id")
    if not text:
        raise ValueError("reply output rendered content is empty")
    return _send_text_via_bazhuayu(
        userid=userid,
        text=text,
        operator_id=operator_id,
        result_id_key="output_id",
        result_id_value=_normalized_text(output.get("output_id")),
    )
