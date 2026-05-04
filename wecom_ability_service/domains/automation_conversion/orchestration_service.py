from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from xml.sax.saxutils import escape as xml_escape
from typing import Any

import requests
from flask import current_app

from ...customer_timeline.service import get_customer_timeline
from ...db import get_db
from ...infra.settings import mask_value
from ...services import get_recent_messages_by_user, get_signup_conversion_config
from . import local_projection, repo, workflow_repo
from .agents import (
    AGENT_OUTPUT_TYPE_OPTIONS,
    CHILD_AGENT_CONFIG_MAP,
    CHILD_AGENT_ORDER,
    ROUTER_ACK_SAMPLE,
    ROUTER_REQUEST_SAMPLE,
    ROUTER_RESPONSE_SAMPLE,
    ROUTER_FALLBACK_DEFAULT,
    SKILL_REGISTRY_ORDER,
    default_agent_config_payloads,
    default_agent_router_payload,
    default_skill_registry_payloads,
    call_deepseek_agent,
    get_deepseek_runtime_config,
)
from .service import apply_router_target_pool, ensure_agent_prompt_defaults, get_member_detail, get_stage_detail_payload

_EXPORT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-output-export")


class DraftVersionConflictError(ValueError):
    error_code = "draft_version_conflict"

    def __init__(self, *, agent_code: str, expected_draft_version: int, current_draft_version: int):
        self.agent_code = _normalized_text(agent_code)
        self.expected_draft_version = int(expected_draft_version)
        self.current_draft_version = int(current_draft_version)
        super().__init__(
            f"draft_version_conflict: agent_code={self.agent_code}, expected_draft_version={self.expected_draft_version}, "
            f"current_draft_version={self.current_draft_version}, please reload the latest draft before retrying"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "agent_code": self.agent_code,
            "expected_draft_version": self.expected_draft_version,
            "current_draft_version": self.current_draft_version,
            "suggestion": "请先重新拉取最新草稿配置后再重试保存或提交发布申请。",
        }

_POOL_TO_ROUTE_KEY = {
    local_projection.POOL_PENDING_QUESTIONNAIRE: "pending-questionnaire",
    local_projection.POOL_OPERATING: "operating",
    local_projection.POOL_CONVERTED: "converted",
    local_projection.POOL_NO_REPLY: "no-reply",
    local_projection.POOL_HUMAN_REPLY: "human-reply",
}

_ROUTER_SPECIAL_AGENT_CODES = {
    local_projection.POOL_NO_REPLY,
    local_projection.POOL_HUMAN_REPLY,
}

_DEFAULT_OUTPUT_HEADERS = [
    "时间",
    "request_id",
    "userid",
    "external_contact_id",
    "agent_code",
    "output_type",
    "target_agent_code",
    "target_pool",
    "confidence",
    "reason",
    "rendered_output_text",
    "applied_status",
]
_EXPORT_RATE_LIMIT_WINDOW_MINUTES = 10
_EXPORT_RATE_LIMIT_COUNT = 5
_ROUTER_ACK_HTTP_STATUS = 200
_ROUTER_MIN_CALLBACK_CONFIDENCE = 0.5
_CONSOLE_DATETIME_KEYS = {
    "created_at",
    "updated_at",
    "applied_at",
    "adopted_at",
    "completed_at",
    "last_touch_at",
    "last_modified_at",
    "last_called_at",
    "submitted_at",
    "published_at",
    "joined_at",
    "send_time",
    "last_activation_at",
    "oauth_at",
}
_APPLIED_STATUS_LABELS = {
    "": "未处理",
    "pending": "待处理",
    "queued": "已排队",
    "received": "已接收",
    "validated": "已校验",
    "pending_apply": "待执行",
    "pending_fallback": "待兜底处理",
    "generated": "已生成未采用",
    "applied": "已采用",
    "adopted": "已采用",
    "replayed": "已回放采用",
    "shadow_recorded": "仅观测记录",
    "suggested": "仅生成建议",
    "alerted": "已告警",
    "rejected": "已拒绝",
    "failed": "执行失败",
}
_OUTCOME_STATUS_LABELS = {
    "": "未闭环",
    "pending": "未闭环",
    "generated": "已生成",
    "applied": "已执行",
    "adopted": "已采用",
    "rejected": "已拒绝",
    "failed": "失败",
}
_REPLY_OUTPUT_TYPES = {"agent_reply_draft", "agent_reply_final"}
_REVIEW_DECISIONS = {"adopted", "rejected"}
_AGENT_CONTEXT_SOURCE_SPECS = (
    {
        "code": "questionnaire",
        "label": "问卷信息",
        "placeholder": "{{问卷信息}}",
        "variable_key": "questionnaire_info",
        "description": "问卷题目与答案摘要",
        "aliases": {"questionnaire", "questionnaire_info", "questionnaire_answers", "survey", "survey_answers"},
    },
    {
        "code": "recent_messages",
        "label": "最近20条聊天信息",
        "placeholder": "{{最近20条聊天信息}}",
        "variable_key": "recent_messages",
        "description": "最近 20 条聊天记录摘要",
        "aliases": {"recent_messages", "recent_message", "recent_chats", "messages", "chat_history"},
    },
    {
        "code": "user_tags",
        "label": "用户标签",
        "placeholder": "{{用户标签}}",
        "variable_key": "user_tags",
        "description": "客户当前标签摘要",
        "aliases": {"user_tags", "member_tags", "tags", "contact_tags"},
    },
    {
        "code": "activation_info",
        "label": "阶段信息",
        "placeholder": "{{阶段信息}}",
        "variable_key": "activation_info",
        "description": "当前池子、大人群、阶段与跟进方式",
        "aliases": {"activation_info", "stage_info", "current_pool", "current_stage", "current_audience", "activity"},
    },
)
_AGENT_CONTEXT_SOURCE_CODE_SET = {item["code"] for item in _AGENT_CONTEXT_SOURCE_SPECS}
_AGENT_CONTEXT_SOURCE_BY_CODE = {item["code"]: item for item in _AGENT_CONTEXT_SOURCE_SPECS}
_AGENT_CONTEXT_SOURCE_BY_ALIAS = {
    alias: item["code"]
    for item in _AGENT_CONTEXT_SOURCE_SPECS
    for alias in item["aliases"]
}
_FIXED_AGENT_OUTPUT_SCHEMA = [
    {
        "field_key": "draft_reply",
        "display_name": "草稿话术",
        "type": "string",
        "required": True,
        "description": "系统固定输出的一条话术。",
    }
]


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _slugify_agent_code(value: Any) -> str:
    text = _normalized_text(value).lower().replace("-", "_").replace(" ", "_")
    sanitized = "".join(ch if ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch == "_" else "_" for ch in text)
    sanitized = "_".join(part for part in sanitized.split("_") if part)
    return sanitized


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _normalize_int(value: Any, *, default: int, minimum: int = 0, maximum: int = 10_000) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = int(default)
    return max(minimum, min(maximum, resolved))


def _normalize_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime_text(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _display_datetime_text(value: Any) -> str:
    text = _normalized_text(value)
    if not text:
        return ""
    parsed = _parse_datetime_text(text)
    if parsed is None:
        return text.split(".")[0] if "." in text else text
    return parsed.replace(tzinfo=None, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _decode_console_text(value: Any) -> str:
    text = _normalized_text(value)
    if not text or "\\u" not in text:
        return text
    try:
        decoded = text.encode("utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return text
    return decoded if decoded else text


def _console_value(value: Any, *, key: str = "") -> Any:
    normalized_key = _normalized_text(key).lower()
    if isinstance(value, dict):
        return {item_key: _console_value(item_value, key=item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_console_value(item, key=key) for item in value]
    if isinstance(value, str):
        text = _decode_console_text(value)
        if normalized_key in _CONSOLE_DATETIME_KEYS or normalized_key.endswith("_at"):
            return _display_datetime_text(text)
        return text
    return value


def _console_json_text(value: Any) -> str:
    return json.dumps(_console_value(value), ensure_ascii=False, indent=2, sort_keys=True)


def _console_text_or_json(value: Any) -> str:
    text = _decode_console_text(value)
    if not text:
        return ""
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError, json.JSONDecodeError):
            return text
        return _console_json_text(parsed)
    return text


def _status_label(value: Any, mapping: dict[str, str], *, default: str = "-") -> str:
    normalized = _normalized_text(value)
    if normalized in mapping:
        return mapping[normalized]
    return normalized or default


def _deserialize_json_object_text(value: Any) -> dict[str, Any]:
    text = _normalized_text(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _copy_json(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return copy.deepcopy(default)
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        return copy.deepcopy(default)


def _mask_phone(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) < 7:
        return text
    return f"{text[:3]}****{text[-4:]}"


def _mask_external_contact_id(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) <= 7:
        return text
    return f"{text[:4]}***{text[-3:]}"


def _mask_sensitive_value(key: str, value: Any) -> Any:
    normalized_key = _normalized_text(key).lower()
    if normalized_key in {"phone", "mobile"}:
        return _mask_phone(value)
    if normalized_key in {"external_contact_id", "external_userid", "userid"}:
        return _mask_external_contact_id(value)
    if normalized_key in {"signature_token", "signature_secret"}:
        return mask_value(key.upper(), _normalized_text(value))
    if isinstance(value, dict):
        return {item_key: _mask_sensitive_value(item_key, item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_mask_sensitive_value(key, item) for item in value]
    return value


def _redact_text_content(value: Any, *, max_length: int = 160) -> str:
    text = _normalized_text(value)
    if not text:
        return ""
    masked = text
    if len(masked) >= 7 and masked.isdigit():
        masked = _mask_phone(masked)
    if len(masked) > max_length:
        masked = f"{masked[:max_length]}..."
    return masked


def _mask_snapshot_by_visibility(key: str, value: Any, *, visibility: str) -> Any:
    if visibility == "full":
        return value
    normalized_key = _normalized_text(key).lower()
    if normalized_key in {"raw_output_text", "final_prompt_preview"}:
        return "敏感内容已隐藏，仅内部 API / Skill 可查看明文"
    if normalized_key in {"messages", "recent_messages", "newmessages"}:
        if isinstance(value, list):
            return {
                "count": len(value),
                "preview": [_redact_text_content(item if not isinstance(item, dict) else item.get("content") or item.get("text")) for item in value[:3]],
                "masked": True,
            }
        return {"count": 0, "preview": [], "masked": True}
    if normalized_key in {"content", "rendered_output_text"}:
        return _redact_text_content(value)
    if isinstance(value, dict):
        return {item_key: _mask_snapshot_by_visibility(item_key, item_value, visibility=visibility) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_mask_snapshot_by_visibility(key, item, visibility=visibility) for item in value]
    return _mask_sensitive_value(key, value)


def _visible_output_text(value: Any, *, visibility: str) -> str:
    text = _normalized_text(value)
    if visibility == "full":
        return text
    if not text:
        return ""
    return "敏感内容已隐藏，仅内部 API / Skill 可查看明文"


def _visible_rendered_text(value: Any, *, visibility: str) -> str:
    text = _normalized_text(value)
    if visibility in {"full", "console"}:
        return text
    return _redact_text_content(text)


def _quantile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(int(item) for item in values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round((len(ordered) - 1) * percentile))
    index = max(0, min(len(ordered) - 1, index))
    return ordered[index]


def _build_excel_xml(headers: list[str], rows: list[list[str]]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
        ' xmlns:o="urn:schemas-microsoft-com:office:office"',
        ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
        ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
        '<Worksheet ss:Name="AgentOutputs">',
        "<Table>",
    ]

    def _render_row(values: list[str]) -> str:
        return "<Row>" + "".join(
            f'<Cell><Data ss:Type="String">{xml_escape(str(value or ""))}</Data></Cell>'
            for value in values
        ) + "</Row>"

    lines.append(_render_row(headers))
    lines.extend(_render_row(item) for item in rows)
    lines.extend(["</Table>", "</Worksheet>", "</Workbook>"])
    return "\n".join(lines).encode("utf-8")


def _request_env_label() -> str:
    if current_app.config.get("TESTING"):
        return "test"
    if current_app.debug:
        return "dev"
    return "prod"


def ensure_agent_orchestration_defaults() -> None:
    ensure_agent_prompt_defaults()
    router_row = repo.get_agent_router_config()
    if not router_row:
        payload = default_agent_router_payload()
        repo.insert_agent_router_config(
            {
                **payload,
                "fallback_strategy_json": payload.get("fallback_strategy") or {},
                "request_sample_json": payload.get("request_sample") or {},
                "response_sample_json": payload.get("response_sample") or {},
                "updated_by": "system",
                "updated_source": "seed",
                "last_status": "never_called",
            }
        )
    else:
        existing = repo.deserialize_agent_router_config_row(router_row)
        expected_request_sample = dict(ROUTER_REQUEST_SAMPLE)
        expected_response_sample = dict(ROUTER_RESPONSE_SAMPLE)
        if (
            dict(existing.get("request_sample_json") or {}) != expected_request_sample
            or dict(existing.get("response_sample_json") or {}) != expected_response_sample
        ):
            repo.save_agent_router_config(
                {
                    "enabled": bool(existing.get("enabled")),
                    "webhook_url": _normalized_text(existing.get("webhook_url")),
                    "signature_token": _normalized_text(existing.get("signature_token")),
                    "signature_secret": _normalized_text(existing.get("signature_secret")),
                    "signature_header": _normalized_text(existing.get("signature_header")) or "X-Lobster-Signature",
                    "timeout_seconds": int(existing.get("timeout_seconds") or 8),
                    "retry_count": int(existing.get("retry_count") or 1),
                    "fallback_strategy_json": dict(existing.get("fallback_strategy_json") or {}),
                    "request_sample_json": expected_request_sample,
                    "response_sample_json": expected_response_sample,
                    "last_status": _normalized_text(existing.get("last_status")) or "never_called",
                    "last_error": _normalized_text(existing.get("last_error")),
                    "last_called_at": _normalized_text(existing.get("last_called_at")),
                    "updated_by": _normalized_text(existing.get("updated_by")) or "system",
                    "updated_source": _normalized_text(existing.get("updated_source")) or "seed",
                }
            )
    prompt_rows = {
        _normalized_text(item.get("agent_code")): repo.deserialize_agent_prompt_row(item)
        for item in repo.list_agent_prompt_rows()
    }
    existing_agent_codes = {
        _normalized_text(item.get("agent_code"))
        for item in repo.list_agent_config_rows()
        if _normalized_text(item.get("agent_code"))
    }
    for payload in default_agent_config_payloads():
        agent_code = _normalized_text(payload.get("agent_code"))
        if agent_code in existing_agent_codes:
            continue
        legacy_prompt = prompt_rows.get(agent_code, {})
        role_prompt = _normalized_text(payload.get("draft_role_prompt"))
        task_prompt = _normalized_text(legacy_prompt.get("prompt_text")) or _normalized_text(payload.get("draft_task_prompt"))
        display_name = _normalized_text(legacy_prompt.get("display_name")) or _normalized_text(payload.get("display_name"))
        repo.insert_agent_config_row(
            {
                **payload,
                "display_name": display_name,
                "draft_role_prompt": role_prompt,
                "draft_task_prompt": task_prompt,
                "published_role_prompt": role_prompt,
                "published_task_prompt": task_prompt,
                "enabled": legacy_prompt.get("enabled", payload.get("enabled", True)),
                "last_modified_at": _iso_now(),
                "last_modified_by": "system",
                "last_modified_source": "seed",
            }
        )
    existing_skill_codes = {
        _normalized_text(item.get("skill_code"))
        for item in repo.list_agent_skill_rows()
        if _normalized_text(item.get("skill_code"))
    }
    for payload in default_skill_registry_payloads():
        skill_code = _normalized_text(payload.get("skill_code"))
        if skill_code in existing_skill_codes:
            continue
        repo.insert_agent_skill_row(payload)
    get_db().commit()


def _serialize_router_config(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_router_config_row(row or {})
    fallback = _router_runtime_strategy(deserialized)
    return {
        "enabled": bool(deserialized.get("enabled")),
        "webhook_url": _normalized_text(deserialized.get("webhook_url")),
        "signature_token_masked": mask_value("ROUTER_SIGNATURE_TOKEN", _normalized_text(deserialized.get("signature_token"))),
        "signature_secret_masked": mask_value("ROUTER_SIGNATURE_SECRET", _normalized_text(deserialized.get("signature_secret"))),
        "signature_token_configured": bool(_normalized_text(deserialized.get("signature_token"))),
        "signature_secret_configured": bool(_normalized_text(deserialized.get("signature_secret"))),
        "signature_header": _normalized_text(deserialized.get("signature_header")) or "X-Lobster-Signature",
        "timeout_seconds": int(deserialized.get("timeout_seconds") or 8),
        "retry_count": int(deserialized.get("retry_count") or 1),
        "fallback_strategy": fallback,
        "last_status": _normalized_text(deserialized.get("last_status")) or "never_called",
        "last_error": _normalized_text(deserialized.get("last_error")),
        "last_called_at": _normalized_text(deserialized.get("last_called_at")) or "暂无记录",
        "updated_by": _normalized_text(deserialized.get("updated_by")) or "system",
        "updated_source": _normalized_text(deserialized.get("updated_source")) or "seed",
        # Always show the canonical async ingress/callback samples on the router page,
        # even if historical rows still contain legacy sync payload examples.
        "request_sample": dict(ROUTER_REQUEST_SAMPLE),
        "response_sample": dict(ROUTER_RESPONSE_SAMPLE),
    }


def _agent_diff_summary(item: dict[str, Any]) -> list[str]:
    draft = dict(item.get("draft") or {})
    published = dict(item.get("published") or {})
    results: list[str] = []
    if _normalized_text(draft.get("role_prompt")) != _normalized_text(published.get("role_prompt")):
        results.append("角色提示词草稿与已发布版本不同")
    if _normalized_text(draft.get("task_prompt")) != _normalized_text(published.get("task_prompt")):
        results.append("任务提示词草稿与已发布版本不同")
    if json.dumps(
        _normalize_enabled_context_sources(
            draft.get("enabled_context_sources"),
            default=_enabled_context_sources_from_variables(draft.get("variables") or []),
        ),
        ensure_ascii=False,
        sort_keys=True,
    ) != json.dumps(
        _normalize_enabled_context_sources(
            published.get("enabled_context_sources"),
            default=_enabled_context_sources_from_variables(published.get("variables") or []),
        ),
        ensure_ascii=False,
        sort_keys=True,
    ):
        results.append("上下文占位符草稿尚未发布")
    return results


def _serialize_agent_config(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_config_row(row or {})
    agent_code = _normalized_text(deserialized.get("agent_code"))
    draft_variables = list(deserialized.get("draft_variables_json") or [])
    published_variables = list(deserialized.get("published_variables_json") or [])
    draft_enabled_context_sources = _enabled_context_sources_from_variables(draft_variables)
    published_enabled_context_sources = _enabled_context_sources_from_variables(published_variables)
    has_unpublished_changes = bool(_agent_diff_summary({
        "draft": {
            "role_prompt": _normalized_text(deserialized.get("draft_role_prompt")),
            "task_prompt": _normalized_text(deserialized.get("draft_task_prompt")),
            "variables": draft_variables,
            "enabled_context_sources": draft_enabled_context_sources,
        },
        "published": {
            "role_prompt": _normalized_text(deserialized.get("published_role_prompt")),
            "task_prompt": _normalized_text(deserialized.get("published_task_prompt")),
            "variables": published_variables,
            "enabled_context_sources": published_enabled_context_sources,
        },
    }))
    payload = {
        "agent_code": agent_code,
        "display_name": _normalized_text(deserialized.get("display_name")) or _normalized_text(
            (CHILD_AGENT_CONFIG_MAP.get(agent_code) or {}).get("display_name")
        ),
        "pool_keys": list(deserialized.get("pool_keys_json") or []),
        "enabled": bool(deserialized.get("enabled")),
        "draft_version": int(deserialized.get("draft_version") or 1),
        "published_version": int(deserialized.get("published_version") or 0),
        "published_at": _normalized_text(deserialized.get("published_at")),
        "published_by": _normalized_text(deserialized.get("published_by")),
        "last_modified_at": _normalized_text(deserialized.get("last_modified_at")) or _normalized_text(deserialized.get("updated_at")),
        "last_modified_by": _normalized_text(deserialized.get("last_modified_by")) or "system",
        "last_modified_source": _normalized_text(deserialized.get("last_modified_source")) or "seed",
        "last_change_summary": _normalized_text(deserialized.get("last_change_summary")) or "暂无变更摘要",
        "has_unpublished_changes": has_unpublished_changes,
        "submitted_for_publish": bool(deserialized.get("submitted_for_publish")),
        "submitted_at": _normalized_text(deserialized.get("submitted_at")),
        "submitted_by": _normalized_text(deserialized.get("submitted_by")),
        "enabled_context_sources": draft_enabled_context_sources,
        "draft": {
            "role_prompt": _normalized_text(deserialized.get("draft_role_prompt")),
            "task_prompt": _normalized_text(deserialized.get("draft_task_prompt")),
            "variables": draft_variables,
            "enabled_context_sources": draft_enabled_context_sources,
            "output_schema": _fixed_agent_output_schema(),
        },
        "published": {
            "role_prompt": _normalized_text(deserialized.get("published_role_prompt")),
            "task_prompt": _normalized_text(deserialized.get("published_task_prompt")),
            "variables": published_variables,
            "enabled_context_sources": published_enabled_context_sources,
            "output_schema": _fixed_agent_output_schema(),
        },
    }
    payload["diff_summary"] = _agent_diff_summary(payload)
    return payload


def _serialize_skill_row(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_skill_row(row or {})
    return {
        "skill_code": _normalized_text(deserialized.get("skill_code")),
        "agent_code": _normalized_text(deserialized.get("agent_code")) or "shared",
        "pool_keys": list(deserialized.get("pool_keys_json") or []),
        "read_capabilities": list(deserialized.get("read_capabilities_json") or []),
        "write_capabilities": list(deserialized.get("write_capabilities_json") or []),
        "enabled": bool(deserialized.get("enabled")),
        "input_schema": dict(deserialized.get("input_schema_json") or {}),
        "output_schema": dict(deserialized.get("output_schema_json") or {}),
        "permission_notes": _normalized_text(deserialized.get("permission_notes")),
        "idempotency_notes": _normalized_text(deserialized.get("idempotency_notes")),
        "audit_notes": _normalized_text(deserialized.get("audit_notes")),
        "example_request": dict(deserialized.get("example_request_json") or {}),
        "example_response": dict(deserialized.get("example_response_json") or {}),
        "last_call_status": _normalized_text(deserialized.get("last_call_status")) or "never_called",
        "last_error": _normalized_text(deserialized.get("last_error")),
        "last_called_at": _normalized_text(deserialized.get("last_called_at")) or "暂无记录",
    }


def _serialize_agent_run(row: dict[str, Any] | None, *, visibility: str = "masked") -> dict[str, Any]:
    deserialized = repo.deserialize_agent_run_row(row or {})
    show_full_identity = visibility in {"full", "console"}
    input_snapshot = deserialized.get("input_snapshot_json") or {}
    variables_snapshot = deserialized.get("variables_snapshot_json") or {}
    return {
        "run_id": _normalized_text(deserialized.get("run_id")),
        "request_id": _normalized_text(deserialized.get("request_id")),
        "batch_id": _normalized_text(deserialized.get("batch_id")),
        "userid": _normalized_text(deserialized.get("userid")) if show_full_identity else _mask_external_contact_id(deserialized.get("userid")),
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")) if show_full_identity else _mask_external_contact_id(deserialized.get("external_contact_id")),
        "agent_code": _normalized_text(deserialized.get("agent_code")),
        "agent_type": _normalized_text(deserialized.get("agent_type")),
        "provider": _normalized_text(deserialized.get("provider")),
        "input_snapshot": _console_value(input_snapshot) if visibility == "console" else _mask_snapshot_by_visibility("input_snapshot_json", input_snapshot, visibility=visibility),
        "variables_snapshot": _console_value(variables_snapshot) if visibility == "console" else _mask_snapshot_by_visibility("variables_snapshot_json", variables_snapshot, visibility=visibility),
        "input_snapshot_pretty": _console_json_text(input_snapshot) if visibility == "console" else "",
        "variables_snapshot_pretty": _console_json_text(variables_snapshot) if visibility == "console" else "",
        "final_prompt_preview": _visible_output_text(deserialized.get("final_prompt_preview"), visibility=visibility),
        "role_prompt_version": _normalized_text(deserialized.get("role_prompt_version")),
        "task_prompt_version": _normalized_text(deserialized.get("task_prompt_version")),
        "status": _normalized_text(deserialized.get("status")),
        "error_code": _normalized_text(deserialized.get("error_code")),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "latency_ms": int(deserialized.get("latency_ms") or 0),
        "source": _normalized_text(deserialized.get("source")),
        "parent_run_id": _normalized_text(deserialized.get("parent_run_id")),
        "replay_of_run_id": _normalized_text(deserialized.get("replay_of_run_id")),
        "created_at": _display_datetime_text(deserialized.get("created_at")) if visibility == "console" else _normalized_text(deserialized.get("created_at")),
        "updated_at": _display_datetime_text(deserialized.get("updated_at")) if visibility == "console" else _normalized_text(deserialized.get("updated_at")),
    }


def _serialize_agent_output(row: dict[str, Any] | None, *, visibility: str = "masked") -> dict[str, Any]:
    deserialized = repo.deserialize_agent_output_row(row or {})
    normalized_output = dict(deserialized.get("normalized_output_json") or {})
    review_payload = _deserialize_json_object_text(deserialized.get("outcome_value"))
    show_full_identity = visibility in {"full", "console"}
    normalized_output_value = _console_value(normalized_output) if visibility == "console" else _mask_snapshot_by_visibility("normalized_output_json", normalized_output, visibility=visibility)
    raw_output_text = _console_text_or_json(deserialized.get("raw_output_text")) if visibility == "console" else _visible_output_text(deserialized.get("raw_output_text"), visibility=visibility)
    rendered_output_text = _decode_console_text(deserialized.get("rendered_output_text")) if visibility == "console" else _visible_rendered_text(deserialized.get("rendered_output_text"), visibility=visibility)
    reason_text = _decode_console_text(deserialized.get("reason")) if visibility == "console" else _normalized_text(deserialized.get("reason"))
    outcome_value = _console_text_or_json(deserialized.get("outcome_value")) if visibility == "console" else _visible_rendered_text(deserialized.get("outcome_value"), visibility=visibility)
    applied_status = _normalized_text(deserialized.get("applied_status")) or "pending"
    outcome_status = _normalized_text(deserialized.get("outcome_status"))
    review_note = _decode_console_text(review_payload.get("review_note")) if visibility == "console" else _normalized_text(review_payload.get("review_note"))
    review_decision = _normalized_text(review_payload.get("review_decision")) or outcome_status
    return {
        "output_id": _normalized_text(deserialized.get("output_id")),
        "run_id": _normalized_text(deserialized.get("run_id")),
        "request_id": _normalized_text(deserialized.get("request_id")),
        "userid": _normalized_text(deserialized.get("userid")) if show_full_identity else _mask_external_contact_id(deserialized.get("userid")),
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")) if show_full_identity else _mask_external_contact_id(deserialized.get("external_contact_id")),
        "agent_code": _normalized_text(deserialized.get("agent_code")),
        "output_type": _normalized_text(deserialized.get("output_type")),
        "raw_output_text": raw_output_text,
        "normalized_output": normalized_output_value,
        "normalized_output_pretty": _console_json_text(normalized_output) if visibility == "console" else "",
        "rendered_output_text": rendered_output_text,
        "target_agent_code": _normalized_text(deserialized.get("target_agent_code")),
        "target_pool": _normalized_text(deserialized.get("target_pool")),
        "confidence": round(_normalize_float(deserialized.get("confidence"), default=0), 4),
        "reason": reason_text,
        "need_human_review": bool(deserialized.get("need_human_review")),
        "applied_status": applied_status,
        "applied_status_label": _status_label(applied_status, _APPLIED_STATUS_LABELS),
        "applied_at": _display_datetime_text(deserialized.get("applied_at")) if visibility == "console" else _normalized_text(deserialized.get("applied_at")),
        "adopted_by": _normalized_text(deserialized.get("adopted_by")),
        "adopted_action": _normalized_text(deserialized.get("adopted_action")),
        "adopted_at": _display_datetime_text(deserialized.get("adopted_at")) if visibility == "console" else _normalized_text(deserialized.get("adopted_at")),
        "outcome_status": outcome_status,
        "outcome_status_label": _status_label(outcome_status, _OUTCOME_STATUS_LABELS, default="未闭环"),
        "outcome_value": outcome_value,
        "review_decision": review_decision,
        "review_note": review_note,
        "reviewed_at": _display_datetime_text(review_payload.get("reviewed_at")) if visibility == "console" else _normalized_text(review_payload.get("reviewed_at")),
        "reviewed_by": _normalized_text(review_payload.get("reviewed_by")),
        "is_reviewable": _normalized_text(deserialized.get("output_type")) in _REPLY_OUTPUT_TYPES,
        "revision_of_output_id": _normalized_text(deserialized.get("revision_of_output_id")),
        "error_code": _normalized_text(deserialized.get("error_code")),
        "error_message": _decode_console_text(deserialized.get("error_message")) if visibility == "console" else _normalized_text(deserialized.get("error_message")),
        "created_at": _display_datetime_text(deserialized.get("created_at")) if visibility == "console" else _normalized_text(deserialized.get("created_at")),
        "is_error": bool(_normalized_text(deserialized.get("error_code")) or _normalized_text(deserialized.get("error_message"))),
    }


def _serialize_export_job(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_output_export_job_row(row or {})
    return {
        "job_id": _normalized_text(deserialized.get("job_id")),
        "requested_by": _normalized_text(deserialized.get("requested_by")) or "system",
        "filters": dict(deserialized.get("filters_json") or {}),
        "status": _normalized_text(deserialized.get("status")),
        "total_count": int(deserialized.get("total_count") or 0),
        "exported_count": int(deserialized.get("exported_count") or 0),
        "file_name": _normalized_text(deserialized.get("file_name")),
        "has_file": bool(_normalized_text(deserialized.get("file_content_base64"))),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
    }


def _load_agent_list() -> list[dict[str, Any]]:
    ensure_agent_orchestration_defaults()
    rows = {
        _normalized_text(item.get("agent_code")): _serialize_agent_config(item)
        for item in repo.list_agent_config_rows()
    }
    items = [
        rows.get(agent_code) or _serialize_agent_config({"agent_code": agent_code, **CHILD_AGENT_CONFIG_MAP[agent_code]})
        for agent_code in CHILD_AGENT_ORDER
    ]
    for agent_code in sorted(code for code in rows.keys() if code and code not in CHILD_AGENT_CONFIG_MAP):
        items.append(rows[agent_code])
    return items


def _load_skill_list() -> list[dict[str, Any]]:
    ensure_agent_orchestration_defaults()
    rows = {
        _normalized_text(item.get("skill_code")): _serialize_skill_row(item)
        for item in repo.list_agent_skill_rows()
    }
    return [rows.get(skill_code) or _serialize_skill_row({"skill_code": skill_code}) for skill_code in SKILL_REGISTRY_ORDER]


def _agent_prompt_bundle_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    canonical_items = [
        {
            "agent_code": _normalized_text(item.get("agent_code")),
            "enabled": bool(item.get("enabled")),
            "draft_version": int(item.get("draft_version") or 1),
            "published_version": int(item.get("published_version") or 0),
            "last_modified_at": _normalized_text(item.get("last_modified_at")),
            "draft": {
                "role_prompt": _normalized_text(((item.get("draft") or {}).get("role_prompt"))),
                "task_prompt": _normalized_text(((item.get("draft") or {}).get("task_prompt"))),
                "enabled_context_sources": list(((item.get("draft") or {}).get("enabled_context_sources")) or []),
                "variables": list(((item.get("draft") or {}).get("variables")) or []),
                "output_schema": list(((item.get("draft") or {}).get("output_schema")) or []),
            },
            "published": {
                "role_prompt": _normalized_text(((item.get("published") or {}).get("role_prompt"))),
                "task_prompt": _normalized_text(((item.get("published") or {}).get("task_prompt"))),
                "enabled_context_sources": list(((item.get("published") or {}).get("enabled_context_sources")) or []),
                "variables": list(((item.get("published") or {}).get("variables")) or []),
                "output_schema": list(((item.get("published") or {}).get("output_schema")) or []),
            },
        }
        for item in sorted(items, key=lambda value: _normalized_text(value.get("agent_code")))
    ]
    version_payload = [
        {
            "agent_code": item["agent_code"],
            "draft_version": item["draft_version"],
            "published_version": item["published_version"],
            "last_modified_at": item["last_modified_at"],
            "enabled": item["enabled"],
        }
        for item in canonical_items
    ]
    version_text = json.dumps(version_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    bundle_text = json.dumps(canonical_items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    bundle_hash = hashlib.sha256(bundle_text.encode("utf-8")).hexdigest()
    bundle_version = f"bundle-{hashlib.sha256(version_text.encode('utf-8')).hexdigest()[:16]}"
    return {
        "bundle_version": bundle_version,
        "bundle_hash": bundle_hash,
        "generated_at": _iso_now(),
    }


def _build_member_variable_snapshot(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    from ..admin_console.customer_profile_service import (
        get_customer_profile_tags_payload,
        get_customer_questionnaire_answers_payload,
    )

    detail = get_member_detail(external_contact_id=external_contact_id, phone=phone)
    profile = dict(detail.get("profile") or {})
    member = dict(detail.get("member") or {})
    questionnaire = dict(detail.get("questionnaire") or {})
    recent_messages = get_recent_messages_by_user(_normalized_text(profile.get("external_contact_id")), limit=20) if _normalized_text(profile.get("external_contact_id")) else []
    tags_payload = get_customer_profile_tags_payload(external_userid=_normalized_text(profile.get("external_contact_id"))) if _normalized_text(profile.get("external_contact_id")) else {"tags": []}
    questionnaire_payload = get_customer_questionnaire_answers_payload(
        external_userid=_normalized_text(profile.get("external_contact_id")),
        mobile=_normalized_text(profile.get("phone")),
    )
    user_tags = [
        _normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))
        for item in tags_payload.get("tags") or []
        if _normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))
    ]
    questionnaire_answers = [
        {
            "question": _normalized_text(item.get("question")),
            "answer": _normalized_text(item.get("answer")),
        }
        for item in questionnaire_payload.get("answers") or []
        if _normalized_text(item.get("question")) or _normalized_text(item.get("answer"))
    ]
    return {
        "recent_messages": [str(item.get("content") or item.get("message_text") or item.get("text") or "") for item in recent_messages[:20]],
        "current_pool": _normalized_text(member.get("current_pool")),
        "current_stage": _normalized_text(member.get("current_stage")),
        "current_audience_code": _normalized_text(member.get("current_audience_code")),
        "questionnaire_answers": questionnaire_answers,
        "focus_reason": "、".join(questionnaire.get("matched_questions") or []),
        "owner_name": _normalized_text(profile.get("owner_display_name") or profile.get("owner_staff_id")),
        "last_touch_at": _normalized_text(member.get("updated_at")),
        "member_tags": user_tags,
        "activation_info": {
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_stage": _normalized_text(member.get("current_stage")),
            "current_audience_code": _normalized_text(member.get("current_audience_code")),
            "follow_type": _normalized_text(member.get("follow_type")),
        },
        "latest_agent_outputs": [
            item["rendered_output_text"] or item["reason"]
            for item in get_agent_outputs_by_user(_normalized_text(profile.get("external_contact_id")), limit=3).get("rows", [])
        ],
        "member_snapshot": {
            "external_contact_id": _normalized_text(profile.get("external_contact_id")),
            "phone": _normalized_text(profile.get("phone")),
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_stage": _normalized_text(member.get("current_stage")),
            "follow_type": _normalized_text(member.get("follow_type")),
        },
    }


def _enabled_child_agents() -> list[str]:
    return [
        item["agent_code"]
        for item in _load_agent_list()
        if item.get("agent_code") and bool(item.get("enabled"))
    ]


def _allowed_router_agent_codes() -> list[str]:
    ordered_codes = []
    for agent_code in [*_enabled_child_agents(), *sorted(_ROUTER_SPECIAL_AGENT_CODES)]:
        normalized_agent_code = _normalized_text(agent_code)
        if not normalized_agent_code or normalized_agent_code in ordered_codes:
            continue
        ordered_codes.append(normalized_agent_code)
    return ordered_codes


def _router_message_entry(message: dict[str, Any], *, external_contact_id: str) -> dict[str, Any]:
    sender = _normalized_text(message.get("sender") or message.get("from"))
    role = "customer" if sender == _normalized_text(external_contact_id) else "staff"
    return {
        "role": role,
        "content": _normalized_text(message.get("content")),
        "created_at": _normalized_text(message.get("send_time")),
    }


def _build_router_member_snapshot(detail: dict[str, Any]) -> dict[str, Any]:
    profile = dict(detail.get("profile") or {})
    member = dict(detail.get("member") or {})
    questionnaire = dict(detail.get("questionnaire") or {})
    return {
        "customer_name": _normalized_text(profile.get("customer_name")),
        "owner_staff_id": _normalized_text(profile.get("owner_staff_id")),
        "owner_display_name": _normalized_text(profile.get("owner_display_name")),
        "external_contact_id": _normalized_text(profile.get("external_contact_id") or member.get("external_contact_id")),
        "phone": _normalized_text(profile.get("phone") or member.get("phone")),
        "current_pool": _normalized_text(member.get("current_pool")),
        "current_stage": _normalized_text(member.get("current_stage")),
        "follow_type": _normalized_text(member.get("follow_type")),
        "questionnaire_status": _normalized_text(questionnaire.get("status")),
        "decision_source": _normalized_text(member.get("decision_source")),
        "in_pool": bool(member.get("in_pool")),
    }


def _router_signature_headers(config: dict[str, Any], *, body_text: str, created_at: str) -> dict[str, str]:
    header_name = _normalized_text(config.get("signature_header")) or "X-Lobster-Signature"
    token = _normalized_text(config.get("signature_token"))
    secret = _normalized_text(config.get("signature_secret"))
    headers = {
        "Content-Type": "application/json",
        "X-Lobster-Timestamp": created_at,
        "X-Shadow-Mode": "1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if secret:
        digest = hmac.new(secret.encode("utf-8"), body_text.encode("utf-8"), hashlib.sha256).hexdigest()
        headers[header_name] = f"sha256={digest}"
    return headers


def _touch_router_runtime_status(*, status: str, error_message: str = "", last_called_at: str = "") -> None:
    existing = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    if not existing:
        return
    repo.save_agent_router_config(
        {
            "enabled": bool(existing.get("enabled")),
            "webhook_url": _normalized_text(existing.get("webhook_url")),
            "signature_token": _normalized_text(existing.get("signature_token")),
            "signature_secret": _normalized_text(existing.get("signature_secret")),
            "signature_header": _normalized_text(existing.get("signature_header")) or "X-Lobster-Signature",
            "timeout_seconds": int(existing.get("timeout_seconds") or 8),
            "retry_count": int(existing.get("retry_count") or 1),
            "fallback_strategy_json": existing.get("fallback_strategy_json") or {},
            "request_sample_json": existing.get("request_sample_json") or {},
            "response_sample_json": existing.get("response_sample_json") or {},
            "last_status": _normalized_text(status),
            "last_error": _normalized_text(error_message),
            "last_called_at": _normalized_text(last_called_at),
            "updated_by": _normalized_text(existing.get("updated_by")) or "system",
            "updated_source": _normalized_text(existing.get("updated_source")) or "runtime",
        }
    )


def _normalize_json_list(value: Any) -> list[Any]:
    resolved = _copy_json(value, default=[])
    return resolved if isinstance(resolved, list) else []


def _normalize_json_dict(value: Any) -> dict[str, Any]:
    resolved = _copy_json(value, default={})
    return resolved if isinstance(resolved, dict) else {}


def _fixed_agent_output_schema() -> list[dict[str, Any]]:
    return [dict(item) for item in _FIXED_AGENT_OUTPUT_SCHEMA]


def _normalize_enabled_context_sources(value: Any, *, default: list[str] | None = None) -> list[str]:
    raw_items = list(value) if isinstance(value, list) else list(default or [])
    normalized_items: list[str] = []
    for item in raw_items:
        code = _normalized_text(item)
        if code not in _AGENT_CONTEXT_SOURCE_CODE_SET or code in normalized_items:
            continue
        normalized_items.append(code)
    return normalized_items


def _enabled_context_sources_from_variables(variables: Any) -> list[str]:
    normalized_items: list[str] = []
    for item in list(variables or []):
        if not isinstance(item, dict):
            continue
        candidates = [
            _normalized_text(item.get("source")).lower(),
            _normalized_text(item.get("variable_key")).lower(),
            _normalized_text(item.get("field_key")).lower(),
            _normalized_text(item.get("display_name")).lower(),
            _normalized_text(item.get("description")).lower(),
        ]
        resolved_code = ""
        for candidate in candidates:
            if candidate in _AGENT_CONTEXT_SOURCE_BY_ALIAS:
                resolved_code = _AGENT_CONTEXT_SOURCE_BY_ALIAS[candidate]
                break
        if not resolved_code or resolved_code in normalized_items:
            continue
        normalized_items.append(resolved_code)
    return normalized_items


def _enabled_context_sources_from_prompt_placeholders(*prompt_texts: Any) -> list[str]:
    combined_prompt = "\n".join(
        text for text in (_normalized_text(item) for item in prompt_texts) if text
    )
    if not combined_prompt:
        return []
    normalized_items: list[str] = []
    for item in _AGENT_CONTEXT_SOURCE_SPECS:
        code = _normalized_text(item.get("code"))
        placeholder = _normalized_text(item.get("placeholder"))
        if not code or not placeholder or placeholder not in combined_prompt or code in normalized_items:
            continue
        normalized_items.append(code)
    return normalized_items


def _resolve_effective_enabled_context_sources(
    *,
    role_prompt: Any,
    task_prompt: Any,
    enabled_context_sources: Any = None,
    variables: Any = None,
) -> list[str]:
    prompt_selected = _enabled_context_sources_from_prompt_placeholders(role_prompt, task_prompt)
    if prompt_selected:
        return prompt_selected
    if enabled_context_sources is not None:
        return _normalize_enabled_context_sources(enabled_context_sources)
    return _normalize_enabled_context_sources(
        None,
        default=_enabled_context_sources_from_variables(variables or []),
    )


def _variables_from_enabled_context_sources(enabled_context_sources: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code in _normalize_enabled_context_sources(enabled_context_sources):
        spec = _AGENT_CONTEXT_SOURCE_BY_CODE.get(code) or {}
        items.append(
            {
                "variable_key": _normalized_text(spec.get("variable_key")),
                "display_name": _normalized_text(spec.get("label")),
                "description": _normalized_text(spec.get("description")),
                "source": code,
                "enabled": True,
            }
        )
    return items


def _normalize_agent_config_variables(
    payload: dict[str, Any],
    *,
    role_prompt: Any = "",
    task_prompt: Any = "",
    default: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if "enabled_context_sources" in payload:
        return _variables_from_enabled_context_sources(payload.get("enabled_context_sources"))
    if "variables" in payload:
        resolved = _copy_json(payload.get("variables"), default=default or [])
        return resolved if isinstance(resolved, list) else list(default or [])
    return _variables_from_enabled_context_sources(
        _enabled_context_sources_from_prompt_placeholders(role_prompt, task_prompt)
    )


def _agent_context_source_sections(variable_snapshot: dict[str, Any], enabled_context_sources: Any) -> dict[str, str]:
    snapshot = dict(variable_snapshot or {})
    enabled_codes = _normalize_enabled_context_sources(enabled_context_sources)
    questionnaire_payload = dict(snapshot.get("questionnaire") or {})
    questionnaire_answers = list(questionnaire_payload.get("answers") or snapshot.get("questionnaire_answers") or [])
    recent_messages = list(snapshot.get("recent_messages") or snapshot.get("recent_chats") or [])
    user_tags = list(snapshot.get("user_tags") or snapshot.get("member_tags") or snapshot.get("tags") or [])
    activation_payload = dict(snapshot.get("activation_info") or {})
    if not activation_payload:
        activation_payload = {
            "current_pool": _normalized_text(snapshot.get("current_pool") or ((snapshot.get("member") or {}).get("current_pool"))),
            "current_stage": _normalized_text(snapshot.get("current_stage") or ((snapshot.get("member") or {}).get("current_stage"))),
            "current_audience_code": _normalized_text((snapshot.get("member") or {}).get("current_audience_code")),
            "follow_type": _normalized_text(snapshot.get("follow_type") or ((snapshot.get("member") or {}).get("follow_type"))),
        }

    questionnaire_lines: list[str] = []
    for answer in questionnaire_answers:
        if not isinstance(answer, dict):
            text = _normalized_text(answer)
            if text:
                questionnaire_lines.append(text)
            continue
        question_text = (
            _normalized_text(answer.get("question_title"))
            or _normalized_text(answer.get("question"))
            or _normalized_text(answer.get("question_label"))
        )
        answer_text = (
            _normalized_text(answer.get("answer_text"))
            or _normalized_text(answer.get("answer"))
            or _normalized_text(answer.get("option_text"))
            or _normalized_text(answer.get("free_text"))
        )
        if question_text and answer_text:
            questionnaire_lines.append(f"{question_text}：{answer_text}")
        elif question_text:
            questionnaire_lines.append(question_text)
        elif answer_text:
            questionnaire_lines.append(answer_text)

    recent_message_lines: list[str] = []
    for item in recent_messages[:20]:
        if isinstance(item, dict):
            role = _normalized_text(item.get("role")) or ("客户" if _normalized_text(item.get("sender")) == "customer" else "")
            time_text = _normalized_text(item.get("time") or item.get("send_time") or item.get("created_at"))
            content = _normalized_text(item.get("content") or item.get("text") or item.get("message_text"))
            prefix_parts = [part for part in [role, time_text] if part]
            prefix = " / ".join(prefix_parts)
            recent_message_lines.append(f"{prefix}：{content}" if prefix and content else content or prefix)
        else:
            text = _normalized_text(item)
            if text:
                recent_message_lines.append(text)

    normalized_tags = [item for item in (_normalized_text(tag) for tag in user_tags) if item]
    activation_lines = [
        f"当前池子：{_normalized_text(activation_payload.get('current_pool'))}" if _normalized_text(activation_payload.get("current_pool")) else "",
        f"当前阶段：{_normalized_text(activation_payload.get('current_stage'))}" if _normalized_text(activation_payload.get("current_stage")) else "",
        f"当前大人群：{_normalized_text(activation_payload.get('current_audience_code'))}" if _normalized_text(activation_payload.get("current_audience_code")) else "",
        f"跟进类型：{_normalized_text(activation_payload.get('follow_type'))}" if _normalized_text(activation_payload.get("follow_type")) else "",
    ]

    section_map = {
        "questionnaire": "\n".join(questionnaire_lines).strip(),
        "recent_messages": "\n".join(line for line in recent_message_lines if _normalized_text(line)).strip(),
        "user_tags": "、".join(normalized_tags).strip(),
        "activation_info": "\n".join(line for line in activation_lines if _normalized_text(line)).strip(),
    }
    return {code: section_map.get(code, "") for code in enabled_codes}


def _replace_agent_prompt_placeholders(prompt_text: Any, section_texts: dict[str, str]) -> str:
    resolved = _normalized_text(prompt_text)
    for code, spec in _AGENT_CONTEXT_SOURCE_BY_CODE.items():
        placeholder = _normalized_text(spec.get("placeholder"))
        label = _normalized_text(spec.get("label"))
        if not placeholder:
            continue
        resolved = resolved.replace(placeholder, f"【{label}】" if label else "")
    return resolved


def _router_decision_target_pool(decision: dict[str, Any]) -> str:
    structured_result = _normalize_json_dict(decision.get("structured_result"))
    target_pool = _normalized_text(structured_result.get("target_pool") or decision.get("target_pool"))
    if target_pool:
        return target_pool
    agent_code = _normalized_text(decision.get("agent_code"))
    if agent_code in _ROUTER_SPECIAL_AGENT_CODES:
        return agent_code
    return ""


def _router_runtime_strategy(router_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = repo.deserialize_agent_router_config_row(router_config or {})
    strategy = {**ROUTER_FALLBACK_DEFAULT, **dict(config.get("fallback_strategy_json") or {})}
    min_confidence = _normalize_float(strategy.get("min_confidence"), default=0.5)
    strategy["min_confidence"] = max(0.0, min(1.0, float(min_confidence)))
    pending_callback_timeout_minutes = _normalize_int(strategy.get("pending_callback_timeout_minutes"), default=10, minimum=1, maximum=24 * 60)
    strategy["pending_callback_timeout_minutes"] = pending_callback_timeout_minutes
    human_review_target_pool = _normalized_text(strategy.get("human_review_target_pool")) or local_projection.POOL_HUMAN_REPLY
    if human_review_target_pool not in _router_allowed_target_pools():
        human_review_target_pool = local_projection.POOL_HUMAN_REPLY
    strategy["human_review_target_pool"] = human_review_target_pool
    return strategy


def validate_router_callback_signature(*, body_text: str, headers: dict[str, Any] | None = None) -> tuple[bool, str]:
    from . import router_dispatch_service

    return router_dispatch_service.validate_router_callback_signature(body_text=body_text, headers=headers)


def _validated_router_callback_payload(
    data: Any,
    *,
    expected_request_id: str,
    expected_external_contact_id: str,
) -> tuple[dict[str, Any], str]:
    if not isinstance(data, dict):
        return {}, "invalid_schema_response"
    required_keys = {"request_id", "external_contact_id", "target_pool"}
    if not required_keys.issubset(set(data.keys())):
        return {}, "invalid_schema_response"
    agent_code = _normalized_text(data.get("agent_code"))
    need_human_review = _normalize_bool(data.get("need_human_review")) or agent_code == local_projection.POOL_HUMAN_REPLY
    normalized = {
        "request_id": _normalized_text(data.get("request_id")),
        "external_contact_id": _normalized_text(data.get("external_contact_id")),
        "agent_code": agent_code,
        "target_pool": _normalized_text(data.get("target_pool")) or (agent_code if agent_code in _ROUTER_SPECIAL_AGENT_CODES else ""),
        "confidence": _normalize_float(data.get("confidence"), default=0.0),
        "reason": _normalized_text(data.get("reason")) or agent_code,
        "need_human_review": need_human_review,
        "completed_at": _normalized_text(data.get("completed_at")),
        "trace_id": _normalized_text(data.get("trace_id")),
        "processing_latency_ms": _normalize_int(data.get("processing_latency_ms"), default=0, minimum=0, maximum=86400000),
        "prompt_version_used": _normalized_text(data.get("prompt_version_used")),
        "mcp_tools_used": [
            _normalized_text(item)
            for item in list(data.get("mcp_tools_used") or [])
            if _normalized_text(item)
        ],
        "next_action": _normalized_text(data.get("next_action")),
        "reply_draft": _normalized_text(data.get("reply_draft") or data.get("draft_reply")),
        "reply_final": _normalized_text(data.get("reply_final") or data.get("final_reply")),
        "structured_result": _normalize_json_dict(data.get("structured_result")),
    }
    structured_result = dict(normalized.get("structured_result") or {})
    if not normalized["next_action"]:
        normalized["next_action"] = _normalized_text(structured_result.get("next_action"))
    if not normalized["reply_draft"]:
        normalized["reply_draft"] = _normalized_text(structured_result.get("reply_draft") or structured_result.get("draft_reply"))
    if not normalized["reply_final"]:
        normalized["reply_final"] = _normalized_text(structured_result.get("reply_final") or structured_result.get("final_reply"))
    if (
        not normalized["request_id"]
        or not normalized["external_contact_id"]
        or not normalized["target_pool"]
    ):
        return {}, "invalid_schema_response"
    if normalized["request_id"] != _normalized_text(expected_request_id):
        return normalized, "request_id_mismatch"
    if normalized["external_contact_id"] != _normalized_text(expected_external_contact_id):
        return normalized, "external_contact_id_mismatch"
    return normalized, ""


def _router_fallback_payload(
    *,
    reason_code: str,
    error_message: str,
    router_config: dict[str, Any],
    request_payload: dict[str, Any],
    raw_response_text: str = "",
) -> dict[str, Any]:
    strategy = _router_runtime_strategy(router_config)
    default_pool = _normalized_text(strategy.get("default_pool")) or local_projection.POOL_PENDING_QUESTIONNAIRE
    return {
        "request_id": _normalized_text(request_payload.get("request_id")),
        "external_contact_id": _normalized_text(request_payload.get("external_contact_id")),
        "agent_code": _normalized_text(strategy.get("default_agent_code")) or "welcome_agent",
        "confidence": 0.0,
        "reason": error_message or reason_code,
        "need_human_review": bool(strategy.get("need_human_review")),
        "crm_reads": [],
        "script_actions": [],
        "structured_result": {
            "target_pool": default_pool,
            "fallback_reason_code": reason_code,
            "fallback_alert_channel": _normalized_text(strategy.get("alert_channel")) or "run_center",
            "fail_closed": bool(strategy.get("fail_closed")),
            "raw_response_text": raw_response_text,
            "min_confidence": strategy.get("min_confidence"),
            "human_review_target_pool": _normalized_text(strategy.get("human_review_target_pool")),
        },
    }


def _router_allowed_target_pools() -> set[str]:
    return {
        local_projection.POOL_PENDING_QUESTIONNAIRE,
        local_projection.POOL_OPERATING,
        local_projection.POOL_CONVERTED,
        local_projection.POOL_NO_REPLY,
        local_projection.POOL_HUMAN_REPLY,
    }


def _append_router_event_output(
    *,
    run_id: str,
    request_id: str,
    userid: str,
    external_contact_id: str,
    output_type: str,
    rendered_output_text: str,
    raw_output_text: str = "",
    normalized_output: dict[str, Any] | None = None,
    target_agent_code: str = "",
    target_pool: str = "",
    confidence: float = 0.0,
    reason: str = "",
    need_human_review: bool = False,
    applied_status: str = "",
    error_code: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    return append_agent_output(
        {
            "run_id": run_id,
            "request_id": request_id,
            "userid": userid,
            "external_contact_id": external_contact_id,
            "agent_code": "central_router_agent",
            "output_type": output_type,
            "raw_output_text": raw_output_text,
            "normalized_output": normalized_output or {},
            "rendered_output_text": rendered_output_text,
            "target_agent_code": target_agent_code,
            "target_pool": target_pool,
            "confidence": confidence,
            "reason": reason or rendered_output_text,
            "need_human_review": need_human_review,
            "applied_status": applied_status,
            "error_code": error_code,
            "error_message": error_message,
        }
    )


def _append_router_callback_rejected_output(
    *,
    run_id: str,
    request_id: str,
    userid: str,
    external_contact_id: str,
    raw_output_text: str,
    normalized_output: dict[str, Any] | None,
    reason: str,
    rendered_output_text: str,
) -> dict[str, Any]:
    return _append_router_event_output(
        run_id=run_id,
        request_id=request_id,
        userid=userid,
        external_contact_id=external_contact_id,
        output_type="callback_rejected",
        raw_output_text=raw_output_text,
        normalized_output=normalized_output or {},
        rendered_output_text=rendered_output_text,
        applied_status="rejected",
        reason=reason,
        error_code=reason,
        error_message=reason,
    )


def _child_reply_payload(
    *,
    agent_code: str,
    target_pool: str,
    confidence: float,
    reason: str,
    need_human_review: bool,
    next_action: str = "",
    reply_draft: str = "",
    reply_final: str = "",
    source: str = "",
    prompt_version_used: str = "",
    mcp_tools_used: list[str] | None = None,
    structured_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_output = {
        "agent_code": _normalized_text(agent_code),
        "target_pool": _normalized_text(target_pool),
        "confidence": round(_normalize_float(confidence, default=0.0), 4),
        "reason": _normalized_text(reason),
        "next_action": _normalized_text(next_action),
        "draft_reply": _normalized_text(reply_draft),
        "reply_final": _normalized_text(reply_final),
        "need_human_review": bool(need_human_review),
        "source": _normalized_text(source),
        "prompt_version_used": _normalized_text(prompt_version_used),
        "mcp_tools_used": [item for item in list(mcp_tools_used or []) if _normalized_text(item)],
        "structured_result": _normalize_json_dict(structured_result),
    }
    rendered_text = _normalized_text(reply_final) or _normalized_text(reply_draft)
    output_type = "agent_reply_final" if _normalized_text(reply_final) else "agent_reply_draft"
    return {
        "output_type": output_type,
        "rendered_output_text": rendered_text,
        "normalized_output": normalized_output,
    }


def _append_child_agent_reply_output(
    *,
    run_id: str,
    request_id: str,
    userid: str,
    external_contact_id: str,
    agent_code: str,
    target_pool: str,
    confidence: float,
    reason: str,
    need_human_review: bool,
    next_action: str = "",
    reply_draft: str = "",
    reply_final: str = "",
    source: str = "",
    prompt_version_used: str = "",
    mcp_tools_used: list[str] | None = None,
    structured_result: dict[str, Any] | None = None,
    applied_status: str = "generated",
) -> dict[str, Any]:
    reply_payload = _child_reply_payload(
        agent_code=agent_code,
        target_pool=target_pool,
        confidence=confidence,
        reason=reason,
        need_human_review=need_human_review,
        next_action=next_action,
        reply_draft=reply_draft,
        reply_final=reply_final,
        source=source,
        prompt_version_used=prompt_version_used,
        mcp_tools_used=mcp_tools_used,
        structured_result=structured_result,
    )
    return append_agent_output(
        {
            "run_id": run_id,
            "request_id": request_id,
            "userid": userid,
            "external_contact_id": external_contact_id,
            "agent_code": _normalized_text(agent_code),
            "output_type": reply_payload["output_type"],
            "raw_output_text": reply_payload["rendered_output_text"],
            "normalized_output": reply_payload["normalized_output"],
            "rendered_output_text": reply_payload["rendered_output_text"],
            "target_agent_code": _normalized_text(agent_code),
            "target_pool": _normalized_text(target_pool),
            "confidence": confidence,
            "reason": _normalized_text(reason),
            "need_human_review": bool(need_human_review),
            "applied_status": _normalized_text(applied_status) or "generated",
        }
    )


def _should_generate_child_reply(agent_code: str) -> bool:
    return _normalized_text(agent_code) in CHILD_AGENT_CONFIG_MAP


def _build_child_agent_generation_request(
    *,
    agent_code: str,
    external_contact_id: str,
    target_pool: str,
    reason: str,
    confidence: float,
    need_human_review: bool,
    structured_result: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    config = get_agent_config_detail(agent_code)
    published = dict(config.get("published") or {})
    role_prompt = _normalized_text(published.get("role_prompt"))
    task_prompt = _normalized_text(published.get("task_prompt"))
    enabled_context_sources = _resolve_effective_enabled_context_sources(
        role_prompt=role_prompt,
        task_prompt=task_prompt,
        enabled_context_sources=published.get("enabled_context_sources"),
        variables=published.get("variables") or [],
    )
    variable_snapshot = _build_member_variable_snapshot(external_contact_id=external_contact_id)
    recent_message_rows = get_recent_messages_by_user(_normalized_text(external_contact_id), limit=20)
    recent_messages = [_router_message_entry(item, external_contact_id=external_contact_id) for item in list(recent_message_rows or [])[:20]]
    variable_snapshot["recent_messages"] = recent_messages
    variable_snapshot["router_decision"] = {
        "agent_code": _normalized_text(agent_code),
        "target_pool": _normalized_text(target_pool),
        "confidence": round(_normalize_float(confidence, default=0.0), 4),
        "reason": _normalized_text(reason),
        "need_human_review": bool(need_human_review),
    }
    if structured_result:
        variable_snapshot["router_decision"]["structured_result"] = _normalize_json_dict(structured_result)
    section_texts = _agent_context_source_sections(variable_snapshot, enabled_context_sources)
    role_prompt = _replace_agent_prompt_placeholders(role_prompt, section_texts)
    task_prompt = _replace_agent_prompt_placeholders(task_prompt, section_texts)
    system_prompt = "\n\n".join(
        part
        for part in [
            role_prompt,
            "你只能基于提示词里实际引用到的信息来源生成一条话术，不要输出 markdown，不要输出额外解释。",
            "如果某类信息为空，就忽略它，不要编造。",
            "你必须只返回 JSON 对象。",
            'JSON 只允许包含字段：draft_reply。',
        ]
        if _normalized_text(part)
    )
    user_input = json.dumps(
        {
            "task_prompt": task_prompt,
            "enabled_context_sources": enabled_context_sources,
            "context_sections": section_texts,
            "variables": variable_snapshot,
            "required_output_schema": _fixed_agent_output_schema(),
        },
        ensure_ascii=False,
    )
    return system_prompt, user_input, variable_snapshot


def _generate_child_agent_reply_output(
    *,
    request_id: str,
    userid: str,
    external_contact_id: str,
    agent_code: str,
    target_pool: str,
    reason: str,
    confidence: float,
    need_human_review: bool,
    structured_result: dict[str, Any] | None = None,
    generation_source: str = "router_callback_child_generation",
) -> dict[str, Any]:
    runtime = get_deepseek_runtime_config()
    if not bool(runtime.get("enabled")) or not _normalized_text(runtime.get("api_key")):
        return {}
    system_prompt, user_input, variable_snapshot = _build_child_agent_generation_request(
        agent_code=agent_code,
        external_contact_id=external_contact_id,
        target_pool=target_pool,
        reason=reason,
        confidence=confidence,
        need_human_review=need_human_review,
        structured_result=structured_result,
    )
    result = call_deepseek_agent(
        agent_code=agent_code,
        system_prompt=system_prompt,
        user_input=user_input,
        json_output=True,
        request_id=request_id,
        userid=userid,
        external_contact_id=external_contact_id,
        input_snapshot={
            "source": generation_source,
            "router_request_id": request_id,
            "external_contact_id": external_contact_id,
            "target_pool": target_pool,
            "reason": reason,
            "confidence": confidence,
            "need_human_review": need_human_review,
            "structured_result": _normalize_json_dict(structured_result),
        },
        variables_snapshot=variable_snapshot,
        source=generation_source,
    )
    row = repo.get_latest_agent_output_row_by_request_id(
        _normalized_text(request_id),
        output_types=["agent_reply_draft", "agent_reply_final", "next_action_suggestion", "error_output"],
    )
    return _serialize_agent_output(row or {}, visibility="full") if row else {
        "run_id": result.get("run_id"),
        "request_id": request_id,
    }


def backfill_missing_child_agent_replies(
    *,
    operator_id: str,
    request_id: str = "",
    external_contact_id: str = "",
    limit: int = 200,
    dry_run: bool = False,
) -> dict[str, Any]:
    from . import router_dispatch_service

    return router_dispatch_service.backfill_missing_child_agent_replies(
        operator_id=operator_id,
        request_id=request_id,
        external_contact_id=external_contact_id,
        limit=limit,
        dry_run=dry_run,
    )


def _resolve_request_run(request_id: str) -> dict[str, Any] | None:
    row = repo.get_agent_run_row_by_request_id(_normalized_text(request_id))
    return repo.deserialize_agent_run_row(row or {}) if row else None


def _latest_request_output(request_id: str, *, output_types: list[str] | None = None) -> dict[str, Any]:
    row = repo.get_latest_agent_output_row_by_request_id(_normalized_text(request_id), output_types=output_types)
    return repo.deserialize_agent_output_row(row or {}) if row else {}


def _apply_router_decision(
    *,
    run_id: str,
    request_id: str,
    userid: str,
    external_contact_id: str,
    decision: dict[str, Any],
    output_id: str,
    adopted_by: str,
    adopted_action_prefix: str,
) -> dict[str, Any]:
    router_config = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    strategy = _router_runtime_strategy(router_config)
    target_pool = _router_decision_target_pool(decision)
    if target_pool not in _router_allowed_target_pools():
        update_agent_run_status(
            run_id,
            {
                "status": "rejected",
                "error_code": "invalid_target_pool",
                "error_message": f"invalid target_pool: {target_pool}",
            },
        )
        return record_agent_output_outcome(
            output_id,
            outcome_status="rejected",
            outcome_value=json.dumps(
                {
                    "request_id": request_id,
                    "external_contact_id": external_contact_id,
                    "target_pool": target_pool,
                    "reason": "invalid_target_pool",
                },
                ensure_ascii=False,
            ),
            applied_status="rejected",
        )

    final_target_pool = _normalized_text(strategy.get("human_review_target_pool")) if bool(decision.get("need_human_review")) else target_pool
    applied_result = apply_router_target_pool(
        external_contact_id=external_contact_id,
        target_pool=final_target_pool,
        operator_id=adopted_by,
        operator_type="system",
    )
    update_agent_run_status(
        run_id,
        {
            "status": "applied",
            "error_code": "",
            "error_message": "",
        },
    )
    return record_agent_output_outcome(
        output_id,
        outcome_status="applied",
        outcome_value=json.dumps(
            {
                "request_id": request_id,
                "external_contact_id": external_contact_id,
                "requested_target_pool": target_pool,
                "final_target_pool": final_target_pool,
                "member_id": ((applied_result.get("member") or {}).get("id")),
            },
            ensure_ascii=False,
        ),
        adopted_by=adopted_by,
        adopted_action=f"{adopted_action_prefix}:{final_target_pool}",
        adopted_at=_iso_now(),
        applied_status="applied",
    )


def run_agent_router_shadow_decision(
    *,
    external_contact_id: str,
    owner_userid: str = "",
    batch_id: str = "",
    source: str = "reply_monitor",
    recent_messages: list[dict[str, Any]] | None = None,
    member_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from . import router_dispatch_service

    return router_dispatch_service.run_agent_router_shadow_decision(
        external_contact_id=external_contact_id,
        owner_userid=owner_userid,
        batch_id=batch_id,
        source=source,
        recent_messages=recent_messages,
        member_detail=member_detail,
    )


def handle_agent_router_callback(payload: dict[str, Any]) -> dict[str, Any]:
    from . import router_dispatch_service

    return router_dispatch_service.handle_agent_router_callback(payload)


def record_agent_output_outcome(
    output_id: str,
    *,
    outcome_status: str,
    outcome_value: str = "",
    adopted_by: str = "",
    adopted_action: str = "",
    adopted_at: str = "",
    applied_status: str = "",
    applied_at: str = "",
) -> dict[str, Any]:
    from . import router_dispatch_service

    return router_dispatch_service.record_agent_output_outcome(
        output_id,
        outcome_status=outcome_status,
        outcome_value=outcome_value,
        adopted_by=adopted_by,
        adopted_action=adopted_action,
        adopted_at=adopted_at,
        applied_status=applied_status,
        applied_at=applied_at,
    )


def review_agent_reply_output(
    output_id: str,
    *,
    decision: str,
    operator_id: str,
    review_note: str = "",
    source: str = "admin_console",
) -> dict[str, Any]:
    from . import router_dispatch_service

    return router_dispatch_service.review_agent_reply_output(
        output_id,
        decision=decision,
        operator_id=operator_id,
        review_note=review_note,
        source=source,
    )


def _question_answer_text(answer_row: dict[str, Any]) -> str:
    option_texts = repo._json_loads((answer_row or {}).get("selected_option_texts_snapshot"), default=[])
    if isinstance(option_texts, list):
        normalized = [_normalized_text(item) for item in option_texts if _normalized_text(item)]
        if normalized:
            return " / ".join(normalized)
    text_value = _normalized_text((answer_row or {}).get("text_value"))
    return text_value or "未填写"


def _feedback_tags_from_member_snapshot(snapshot: dict[str, Any]) -> list[str]:
    stage = dict((snapshot or {}).get("stage") or {})
    tags: list[str] = []
    for value in (
        stage.get("current_pool_label"),
        stage.get("current_stage_label"),
        stage.get("current_target_label"),
        stage.get("follow_type"),
    ):
        text = _normalized_text(value)
        if text and text not in tags:
            tags.append(text)
    return tags


def _feedback_questionnaire_items(*, external_contact_id: str, phone: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    settings = get_signup_conversion_config()
    questionnaire_id = int(settings.get("questionnaire_id") or 0)
    if questionnaire_id > 0 and (_normalized_text(external_contact_id) or _normalized_text(phone)):
        submission = repo.get_latest_questionnaire_submission(
            questionnaire_id=questionnaire_id,
            external_contact_ids=[_normalized_text(external_contact_id)] if _normalized_text(external_contact_id) else None,
            phone=_normalized_text(phone),
        )
        if submission:
            return [
                {
                    "question": _normalized_text(item.get("question_title_snapshot")) or f"问题 {int(item.get('question_id') or 0)}",
                    "answer": _question_answer_text(item),
                }
                for item in repo.list_questionnaire_submission_answers(int(submission["id"]))
            ]
    questionnaire = dict((snapshot or {}).get("questionnaire") or {})
    fallback_items: list[dict[str, Any]] = []
    if _normalized_text(questionnaire.get("status_label")):
        fallback_items.append({"question": "问卷状态", "answer": _normalized_text(questionnaire.get("status_label"))})
    matched_questions = [str(item).strip() for item in list(questionnaire.get("matched_questions") or []) if str(item).strip()]
    if matched_questions:
        fallback_items.append({"question": "命中问题", "answer": " / ".join(matched_questions)})
    return fallback_items


def build_rejected_feedback_payload(output_id: str, *, not_adopted_reason: str) -> dict[str, Any]:
    row = repo.get_agent_output_row(_normalized_text(output_id))
    if not row:
        raise LookupError("未找到对应话术输出")
    output = repo.deserialize_agent_output_row(row)
    external_contact_id = _normalized_text(output.get("external_contact_id"))
    snapshot = crm_get_member_snapshot(external_contact_id=external_contact_id, phone="") if external_contact_id else {}
    basic = dict((snapshot or {}).get("basic") or {})
    resolved_phone = _normalized_text(basic.get("phone"))
    recent_message_rows = get_recent_messages_by_user(external_contact_id, limit=20) if external_contact_id else []
    recent_chats = [_router_message_entry(item, external_contact_id=external_contact_id) for item in list(recent_message_rows or [])[:20]]
    return {
        "recent_chats": recent_chats,
        "tags": _feedback_tags_from_member_snapshot(snapshot),
        "questionnaire": _feedback_questionnaire_items(
            external_contact_id=external_contact_id,
            phone=resolved_phone,
            snapshot=snapshot,
        ),
        "not_adopted_reason": _normalized_text(not_adopted_reason),
    }


def build_rejected_feedback_clipboard_payload(output_id: str, *, not_adopted_reason: str) -> str:
    return json.dumps(
        build_rejected_feedback_payload(
            output_id,
            not_adopted_reason=not_adopted_reason,
        ),
        ensure_ascii=False,
        indent=2,
    )


def list_recent_reviewable_agent_outputs(*, limit: int = 20) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    safe_limit = max(1, min(50, int(limit or 20)))
    scan_limit = min(200, max(50, safe_limit * 5))
    rows = repo.list_agent_output_rows(filters=None, limit=scan_limit, offset=0)
    items: list[dict[str, Any]] = []
    for row in rows:
        serialized = _serialize_agent_output(row, visibility="console")
        if not bool(serialized.get("is_reviewable")):
            continue
        items.append(
            {
                "output_id": _normalized_text(serialized.get("output_id")),
                "request_id": _normalized_text(serialized.get("request_id")),
                "external_contact_id": _normalized_text(serialized.get("external_contact_id")),
                "agent_code": _normalized_text(serialized.get("agent_code")),
                "output_type": _normalized_text(serialized.get("output_type")),
                "rendered_output_text": _normalized_text(serialized.get("rendered_output_text")),
                "rendered_content_preview": _normalized_text(serialized.get("rendered_output_text"))[:120],
                "reason": _normalized_text(serialized.get("reason")),
                "outcome_status": _normalized_text(serialized.get("outcome_status")),
                "outcome_status_label": _normalized_text(serialized.get("outcome_status_label")),
                "review_note": _normalized_text(serialized.get("review_note")),
                "reviewed_at": _normalized_text(serialized.get("reviewed_at")),
                "created_at": _normalized_text(serialized.get("created_at")),
                "is_reviewable": True,
            }
        )
        if len(items) >= safe_limit:
            break
    return {
        "rows": items,
        "total": len(items),
        "limit": safe_limit,
    }


def _resolve_member_detail_for_skill(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    if not _normalized_text(external_contact_id) and not _normalized_text(phone):
        raise ValueError("external_contact_id or phone is required")
    return get_member_detail(external_contact_id=_normalized_text(external_contact_id), phone=_normalized_text(phone))


def _script_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_code": _normalized_text(item.get("agent_code")),
        "display_name": _normalized_text(item.get("display_name")),
        "pool_keys": list(item.get("pool_keys") or []),
        "enabled": bool(item.get("enabled")),
        "draft_version": int(item.get("draft_version") or 0),
        "published_version": int(item.get("published_version") or 0),
        "last_modified_at": _normalized_text(item.get("last_modified_at")),
        "last_modified_by": _normalized_text(item.get("last_modified_by")),
        "last_modified_source": _normalized_text(item.get("last_modified_source")),
        "diff_summary": list(item.get("diff_summary") or []),
    }


def crm_get_member_basic(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    detail = _resolve_member_detail_for_skill(external_contact_id=external_contact_id, phone=phone)
    profile = dict(detail.get("profile") or {})
    member = dict(detail.get("member") or {})
    return {
        "member_exists": bool(detail.get("member_exists")),
        "basic": {
            "customer_name": _normalized_text(profile.get("customer_name")),
            "external_contact_id": _normalized_text(profile.get("external_contact_id") or member.get("external_contact_id")),
            "phone": _normalized_text(profile.get("phone") or member.get("phone")),
            "owner_staff_id": _normalized_text(profile.get("owner_staff_id") or member.get("owner_staff_id")),
            "owner_display_name": _normalized_text(profile.get("owner_display_name") or profile.get("owner_staff_id")),
            "unionid": _normalized_text(profile.get("unionid")),
        },
    }


def crm_get_member_stage(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    detail = _resolve_member_detail_for_skill(external_contact_id=external_contact_id, phone=phone)
    member = dict(detail.get("member") or {})
    return {
        "member_exists": bool(detail.get("member_exists")),
        "stage": {
            "external_contact_id": _normalized_text(member.get("external_contact_id")),
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_pool_label": _normalized_text(member.get("current_pool_label")),
            "current_stage": _normalized_text(member.get("current_stage")),
            "current_stage_label": _normalized_text(member.get("current_stage_label")),
            "current_target": _normalized_text(member.get("current_target")),
            "current_target_label": _normalized_text(member.get("current_target_label")),
            "follow_type": _normalized_text(member.get("follow_type")),
            "decision_source": _normalized_text(member.get("decision_source")),
            "in_pool": bool(member.get("in_pool")),
            "updated_at": _normalized_text(member.get("updated_at")),
        },
    }


def crm_get_member_questionnaire(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    detail = _resolve_member_detail_for_skill(external_contact_id=external_contact_id, phone=phone)
    questionnaire = dict(detail.get("questionnaire") or {})
    return {
        "member_exists": bool(detail.get("member_exists")),
        "questionnaire": {
            "status": _normalized_text(questionnaire.get("status")),
            "status_label": _normalized_text(questionnaire.get("status_label")),
            "hit_count": int(questionnaire.get("hit_count") or 0),
            "matched_questions": list(questionnaire.get("matched_questions") or []),
            "submitted_at": _normalized_text(questionnaire.get("submitted_at")),
        },
    }


def crm_get_member_recent_events(*, external_contact_id: str = "", phone: str = "", limit: int = 20) -> dict[str, Any]:
    detail = _resolve_member_detail_for_skill(external_contact_id=external_contact_id, phone=phone)
    resolved_external_contact_id = _normalized_text((detail.get("profile") or {}).get("external_contact_id"))
    safe_limit = max(1, min(100, int(limit or 20)))
    timeline = (
        get_customer_timeline(
            resolved_external_contact_id,
            {
                "limit": safe_limit,
                "offset": 0,
                "normalized_limit": safe_limit,
                "normalized_offset": 0,
            },
        )
        if resolved_external_contact_id
        else None
    )
    return {
        "member_exists": bool(detail.get("member_exists")),
        "external_contact_id": resolved_external_contact_id,
        "events": list((timeline or {}).get("items") or []),
        "total": int((timeline or {}).get("total") or 0),
    }


def crm_get_member_recent_outputs(*, external_contact_id: str = "", phone: str = "", limit: int = 20) -> dict[str, Any]:
    detail = _resolve_member_detail_for_skill(external_contact_id=external_contact_id, phone=phone)
    resolved_external_contact_id = _normalized_text((detail.get("profile") or {}).get("external_contact_id"))
    safe_limit = max(1, min(100, int(limit or 20)))
    outputs = (
        get_agent_outputs_by_user(resolved_external_contact_id, limit=safe_limit, visibility="full")
        if resolved_external_contact_id
        else {"rows": []}
    )
    return {
        "member_exists": bool(detail.get("member_exists")),
        "external_contact_id": resolved_external_contact_id,
        "rows": list(outputs.get("rows") or []),
        "total": len(list(outputs.get("rows") or [])),
    }


def crm_get_member_snapshot(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    detail = _resolve_member_detail_for_skill(external_contact_id=external_contact_id, phone=phone)
    profile = dict(detail.get("profile") or {})
    member = dict(detail.get("member") or {})
    questionnaire = dict(detail.get("questionnaire") or {})
    return {
        "member_exists": bool(detail.get("member_exists")),
        "basic": {
            "customer_name": _normalized_text(profile.get("customer_name")),
            "external_contact_id": _normalized_text(profile.get("external_contact_id") or member.get("external_contact_id")),
            "phone": _normalized_text(profile.get("phone") or member.get("phone")),
            "owner_staff_id": _normalized_text(profile.get("owner_staff_id") or member.get("owner_staff_id")),
            "owner_display_name": _normalized_text(profile.get("owner_display_name") or profile.get("owner_staff_id")),
            "unionid": _normalized_text(profile.get("unionid")),
        },
        "stage": {
            "external_contact_id": _normalized_text(member.get("external_contact_id")),
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_pool_label": _normalized_text(member.get("current_pool_label")),
            "current_stage": _normalized_text(member.get("current_stage")),
            "current_stage_label": _normalized_text(member.get("current_stage_label")),
            "current_target": _normalized_text(member.get("current_target")),
            "current_target_label": _normalized_text(member.get("current_target_label")),
            "follow_type": _normalized_text(member.get("follow_type")),
            "decision_source": _normalized_text(member.get("decision_source")),
            "in_pool": bool(member.get("in_pool")),
            "updated_at": _normalized_text(member.get("updated_at")),
        },
        "questionnaire": {
            "status": _normalized_text(questionnaire.get("status")),
            "status_label": _normalized_text(questionnaire.get("status_label")),
            "hit_count": int(questionnaire.get("hit_count") or 0),
            "matched_questions": list(questionnaire.get("matched_questions") or []),
            "submitted_at": _normalized_text(questionnaire.get("submitted_at")),
        },
        "latest_manual_action": dict(detail.get("latest_manual_action") or {}),
        "last_ai_push_at": _normalized_text(detail.get("last_ai_push_at")),
        "ai_cooldown_until": _normalized_text(detail.get("ai_cooldown_until")),
    }


def script_list_items(*, query: str = "") -> dict[str, Any]:
    normalized_query = _normalized_text(query).lower()
    rows = []
    for item in _load_agent_list():
        haystack = " ".join(
            [
                _normalized_text(item.get("agent_code")),
                _normalized_text(item.get("display_name")),
                " ".join(str(pool_key) for pool_key in item.get("pool_keys") or []),
            ]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        rows.append(_script_item_summary(item))
    return {"total": len(rows), "rows": rows}


def script_get_item(agent_code: str) -> dict[str, Any]:
    return {
        "item": get_agent_config_detail(agent_code),
        "publish_mode": "manual_publish_required",
    }


def script_search_items(keyword: str) -> dict[str, Any]:
    return script_list_items(query=keyword)


def script_create_draft(agent_code: str, *, operator_id: str, from_version: str = "published", change_summary: str = "") -> dict[str, Any]:
    existing = get_agent_config_detail(agent_code)
    source_key = "draft" if _normalized_text(from_version) == "draft" else "published"
    source_payload = dict(existing.get(source_key) or {})
    saved = save_agent_config_draft(
        agent_code,
        {
            "display_name": existing.get("display_name"),
            "enabled": bool(existing.get("enabled")),
            "role_prompt": source_payload.get("role_prompt"),
            "task_prompt": source_payload.get("task_prompt"),
            "variables": list(source_payload.get("variables") or []),
            "output_schema": list(source_payload.get("output_schema") or []),
            "change_summary": _normalized_text(change_summary) or f"基于 {source_key} 版本创建 Lobster 草稿",
        },
        operator_id=operator_id,
        source="lobster_mcp_script_create",
    )
    return {
        "created": True,
        "source_version": source_key,
        "agent": saved.get("agent") or {},
    }


def script_update_draft(
    agent_code: str,
    *,
    operator_id: str,
    display_name: str | None = None,
    enabled: Any = None,
    role_prompt: str | None = None,
    task_prompt: str | None = None,
    variables: Any = None,
    output_schema: Any = None,
    change_summary: str = "",
) -> dict[str, Any]:
    existing = get_agent_config_detail(agent_code)
    current_draft = dict(existing.get("draft") or {})
    payload = {
        "display_name": _normalized_text(display_name) or existing.get("display_name"),
        "enabled": bool(existing.get("enabled")) if enabled is None else _normalize_bool(enabled),
        "role_prompt": _normalized_text(role_prompt) or current_draft.get("role_prompt"),
        "task_prompt": _normalized_text(task_prompt) or current_draft.get("task_prompt"),
        "variables": list(current_draft.get("variables") or []) if variables is None else _normalize_json_list(variables),
        "output_schema": list(current_draft.get("output_schema") or []) if output_schema is None else _normalize_json_list(output_schema),
        "change_summary": _normalized_text(change_summary) or "Lobster MCP 更新话术草稿",
    }
    saved = save_agent_config_draft(
        agent_code,
        payload,
        operator_id=operator_id,
        source="lobster_mcp_script_update",
    )
    return {"updated": True, "agent": saved.get("agent") or {}}


def script_diff_draft(agent_code: str) -> dict[str, Any]:
    item = get_agent_config_detail(agent_code)
    draft = dict(item.get("draft") or {})
    published = dict(item.get("published") or {})
    return {
        "item": _script_item_summary(item),
        "diff_summary": list(item.get("diff_summary") or []),
        "fields": {
            "role_prompt_changed": _normalized_text(draft.get("role_prompt")) != _normalized_text(published.get("role_prompt")),
            "task_prompt_changed": _normalized_text(draft.get("task_prompt")) != _normalized_text(published.get("task_prompt")),
            "variables_changed": json.dumps(draft.get("variables") or [], ensure_ascii=False, sort_keys=True)
            != json.dumps(published.get("variables") or [], ensure_ascii=False, sort_keys=True),
            "output_schema_changed": json.dumps(draft.get("output_schema") or [], ensure_ascii=False, sort_keys=True)
            != json.dumps(published.get("output_schema") or [], ensure_ascii=False, sort_keys=True),
        },
        "draft": draft,
        "published": published,
    }


def script_submit_for_publish(agent_code: str, *, operator_id: str, change_summary: str = "", expected_draft_version: Any = None) -> dict[str, Any]:
    existing = get_agent_config_detail(agent_code)
    if expected_draft_version not in (None, ""):
        expected_version = _normalize_int(expected_draft_version, default=int(existing.get("draft_version") or 1), minimum=1, maximum=1000000)
        current_version = int(existing.get("draft_version") or 1)
        if expected_version != current_version:
            raise DraftVersionConflictError(
                agent_code=agent_code,
                expected_draft_version=expected_version,
                current_draft_version=current_version,
            )
    current = repo.deserialize_agent_config_row(repo.get_agent_config_row(_normalized_text(agent_code)) or {})
    saved = repo.update_agent_config_row(
        _normalized_text(agent_code),
        {
            "display_name": _normalized_text(current.get("display_name")),
            "pool_keys": list(current.get("pool_keys_json") or []),
            "enabled": bool(current.get("enabled")),
            "draft_role_prompt": _normalized_text(current.get("draft_role_prompt")),
            "draft_task_prompt": _normalized_text(current.get("draft_task_prompt")),
            "draft_variables": list(current.get("draft_variables_json") or []),
            "draft_output_schema": list(current.get("draft_output_schema_json") or []),
            "published_role_prompt": _normalized_text(current.get("published_role_prompt")),
            "published_task_prompt": _normalized_text(current.get("published_task_prompt")),
            "published_variables": list(current.get("published_variables_json") or []),
            "published_output_schema": list(current.get("published_output_schema_json") or []),
            "draft_version": int(current.get("draft_version") or 1),
            "published_version": int(current.get("published_version") or 0),
            "published_at": _normalized_text(current.get("published_at")),
            "published_by": _normalized_text(current.get("published_by")),
            "submitted_for_publish": True,
            "submitted_at": _iso_now(),
            "submitted_by": operator_id,
            "last_modified_at": _normalized_text(current.get("last_modified_at")) or _iso_now(),
            "last_modified_by": _normalized_text(current.get("last_modified_by")) or operator_id,
            "last_modified_source": "lobster_mcp_submit_for_publish",
            "last_change_summary": _normalized_text(change_summary) or _normalized_text(current.get("last_change_summary")) or f"提交人工发布申请 v{int(current.get('draft_version') or 1)}",
        },
    )
    get_db().commit()
    return {
        "submitted": True,
        "status": "pending_manual_publish",
        "message": "当前仅提交发布申请，仍需人工在运行中心完成正式发布。",
        "agent": saved.get("agent") or {},
    }


def script_list_drafts(*, changed_only: bool = True) -> dict[str, Any]:
    rows = []
    for item in _load_agent_list():
        if changed_only and not list(item.get("diff_summary") or []):
            continue
        rows.append(_script_item_summary(item))
    return {"total": len(rows), "rows": rows, "changed_only": bool(changed_only)}


def get_agent_orchestration_metrics(*, date_from: str = "", date_to: str = "") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    run_filters = {
        "agent_code": "central_router_agent",
        "date_from": _normalized_text(date_from) or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": _normalized_text(date_to),
    }
    router_runs = [
        repo.deserialize_agent_run_row(item)
        for item in repo.list_agent_run_rows(filters=run_filters, limit=5000, offset=0)
        if _normalized_text(item.get("provider")) == "lobster_shadow"
    ]
    router_run_ids = {_normalized_text(item.get("run_id")) for item in router_runs if _normalized_text(item.get("run_id"))}
    raw_outputs = [
        repo.deserialize_agent_output_row(item)
        for item in repo.list_agent_output_rows(
            filters={
                "agent_code": "central_router_agent",
                "date_from": run_filters["date_from"],
                "date_to": run_filters["date_to"],
            },
            limit=5000,
            offset=0,
        )
        if _normalized_text(item.get("run_id")) in router_run_ids
    ]
    decision_outputs = [item for item in raw_outputs if _normalized_text(item.get("output_type")) in {"route_decision", "fallback_decision"}]
    success_count = sum(1 for item in router_runs if _normalized_text(item.get("status")) in {"acked", "completed", "applied"})
    fallback_count = sum(1 for item in decision_outputs if _normalized_text(item.get("output_type")) == "fallback_decision")
    invalid_schema_count = sum(
        1
        for item in router_runs
        if _normalized_text(item.get("error_code")) in {"invalid_schema_response", "invalid_target_pool"}
    )
    latency_values = [int(item.get("latency_ms") or 0) for item in router_runs if int(item.get("latency_ms") or 0) > 0]
    agent_hits: dict[str, int] = {}
    confidence_buckets = {"0.00-0.49": 0, "0.50-0.69": 0, "0.70-0.84": 0, "0.85-1.00": 0}
    adopted_outputs = [
        item for item in decision_outputs if _normalized_text(item.get("applied_status")) in {"applied", "adopted", "replayed"}
    ]
    won_external_ids = {
        external_id
        for external_id in {
            _normalized_text(item.get("external_contact_id")) for item in adopted_outputs if _normalized_text(item.get("external_contact_id"))
        }
        if _normalized_text((repo.get_member_by_external_contact_id(external_id) or {}).get("current_pool")) in {"won", "converted"}
    }
    error_counts: dict[str, int] = {}
    for item in decision_outputs:
        target_agent = _normalized_text(item.get("target_agent_code")) or "unassigned"
        agent_hits[target_agent] = agent_hits.get(target_agent, 0) + 1
        confidence = _normalize_float(item.get("confidence"), default=0.0)
        if confidence < 0.5:
            confidence_buckets["0.00-0.49"] += 1
        elif confidence < 0.7:
            confidence_buckets["0.50-0.69"] += 1
        elif confidence < 0.85:
            confidence_buckets["0.70-0.84"] += 1
        else:
            confidence_buckets["0.85-1.00"] += 1
    for item in router_runs:
        error_key = _normalized_text(item.get("error_code")) or _normalized_text(item.get("error_message"))
        if error_key:
            error_counts[error_key] = error_counts.get(error_key, 0) + 1
    total_runs = len(router_runs)
    total_decisions = len(decision_outputs)
    adopted_conversion_count = sum(
        1 for item in adopted_outputs if _normalized_text(item.get("external_contact_id")) in won_external_ids
    )
    return {
        "window": {
            "date_from": run_filters["date_from"],
            "date_to": run_filters["date_to"] or "",
        },
        "call_volume": total_runs,
        "success_rate": round(success_count / total_runs, 4) if total_runs else 0.0,
        "fallback_rate": round(fallback_count / total_decisions, 4) if total_decisions else 0.0,
        "invalid_schema_rate": round(invalid_schema_count / total_runs, 4) if total_runs else 0.0,
        "latency": {
            "avg_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
            "p95_ms": _quantile(latency_values, 0.95),
        },
        "agent_hit_distribution": [
            {"agent_code": key, "count": value}
            for key, value in sorted(agent_hits.items(), key=lambda item: (-item[1], item[0]))
        ],
        "confidence_distribution": [
            {"bucket": key, "count": value}
            for key, value in confidence_buckets.items()
        ],
        "adoption_rate": round(len(adopted_outputs) / total_decisions, 4) if total_decisions else 0.0,
        "adoption_conversion_rate": round(adopted_conversion_count / len(adopted_outputs), 4) if adopted_outputs else 0.0,
        "top_errors": [
            {"error": key, "count": value}
            for key, value in sorted(error_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ],
        "notes": [
            "当前 metrics 基于异步 ingress + callback 账本统计；ingress 只看 ack，真实分池采用以 callback 应用结果为准。",
            "采纳率当前只统计真正进入 applied / adopted / replayed 的输出；仅 ack 未 callback 的请求不会被算作采纳。",
        ],
    }


def get_agent_orchestration_payload(
    *,
    subtab: str = "router",
    agent_code: str = "",
    skill_code: str = "",
    output_id: str = "",
    run_id: str = "",
    request_id: str = "",
    external_contact_id: str = "",
    userid: str = "",
    date_from: str = "",
    date_to: str = "",
    output_type: str = "",
    target_pool: str = "",
    applied_status: str = "",
    batch_id: str = "",
    current_pool: str = "",
    min_confidence: str = "",
    max_confidence: str = "",
    has_error: str = "",
    scripts_only: bool = False,
    page: int = 1,
    page_size: int = 20,
    export_job_id: str = "",
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    router_row = repo.get_agent_router_config() or {}
    agent_items = _load_agent_list()
    skill_items = _load_skill_list()
    selected_agent_code = _normalized_text(agent_code) or (agent_items[0]["agent_code"] if agent_items else "")
    selected_skill_code = _normalized_text(skill_code) or (skill_items[0]["skill_code"] if skill_items else "")
    selected_agent = next((item for item in agent_items if item["agent_code"] == selected_agent_code), agent_items[0] if agent_items else {})
    selected_skill = next((item for item in skill_items if item["skill_code"] == selected_skill_code), skill_items[0] if skill_items else {})

    output_filters = {
        "request_id": request_id,
        "batch_id": batch_id,
        "external_contact_id": external_contact_id,
        "userid": userid,
        "agent_code": agent_code if subtab == "outputs" and agent_code else "",
        "output_type": output_type,
        "current_pool": current_pool,
        "target_pool": target_pool,
        "applied_status": applied_status,
        "date_from": date_from,
        "date_to": date_to,
        "min_confidence": min_confidence,
        "max_confidence": max_confidence,
        "has_error": has_error,
        "scripts_only": bool(scripts_only),
    }
    resolved_page = max(1, int(page or 1))
    resolved_page_size = max(1, min(100, int(page_size or 20)))
    total_outputs = repo.count_agent_output_rows(output_filters)
    output_rows = [_serialize_agent_output(item, visibility="console") for item in repo.list_agent_output_rows(filters=output_filters, limit=resolved_page_size, offset=(resolved_page - 1) * resolved_page_size)]
    selected_output = (
        get_agent_output_detail(_normalized_text(output_id), visibility="console")
        if _normalized_text(output_id)
        else {}
    )

    replay_payload = get_agent_replay_payload(
        run_id=run_id,
        request_id=request_id,
        external_contact_id=external_contact_id,
        userid=userid,
        date_from=date_from,
        date_to=date_to,
        visibility="masked",
    )

    route_outputs = repo.list_agent_output_rows(filters={"agent_code": "central_router_agent"}, limit=20, offset=0)
    shadow_route_outputs = [
        item
        for item in route_outputs
        if _normalized_text((repo.get_agent_run_row(_normalized_text(item.get("run_id"))) or {}).get("provider")) == "lobster_shadow"
    ]
    fallback_outputs = sum(1 for item in shadow_route_outputs if _normalized_text(item.get("output_type")) == "fallback_decision")
    export_job = get_agent_output_export_job(_normalized_text(export_job_id)) if _normalized_text(export_job_id) else {}
    last_route_output = next(
        (
            _serialize_agent_output(item, visibility="masked")
            for item in shadow_route_outputs
            if _normalized_text(item.get("output_type")) in {"route_decision", "fallback_decision"}
        ),
        {},
    )
    router_strategy = _router_runtime_strategy(router_row)
    pending_timeout_minutes = int(router_strategy.get("pending_callback_timeout_minutes") or 10)
    pending_callbacks = list_router_pending_callbacks(older_than_minutes=pending_timeout_minutes, limit=10, visibility="masked")
    pending_alert_total = repo.count_agent_output_rows({"agent_code": "central_router_agent", "output_type": "pending_callback_alert"})
    pending_alert_rows = [
        _serialize_agent_output(item, visibility="masked")
        for item in repo.list_agent_output_rows(
            filters={"agent_code": "central_router_agent", "output_type": "pending_callback_alert"},
            limit=10,
            offset=0,
        )
    ]
    pending_publish = list_pending_agent_prompt_publish_requests(page=1, page_size=10)
    bundle = _agent_prompt_bundle_payload(agent_items)
    metrics_payload = get_agent_orchestration_metrics(date_from=date_from, date_to=date_to)

    return {
        "subtab": _normalized_text(subtab) or "router",
        "router": {
            "config": _serialize_router_config(router_row),
            "input_protocol": dict(ROUTER_REQUEST_SAMPLE),
            "ack_protocol": dict(ROUTER_ACK_SAMPLE),
            "output_protocol": dict(ROUTER_RESPONSE_SAMPLE),
            "special_routes": sorted(_ROUTER_SPECIAL_AGENT_CODES),
            "last_route_output": last_route_output,
            "fallback_count": int(fallback_outputs),
            "pending_callbacks": pending_callbacks,
            "pending_callback_alerts": {
                "count": pending_alert_total,
                "rows": pending_alert_rows,
            },
            "notes": [
                "中央路由不再作为普通 Prompt Agent 配置，而是一个外部 webhook / 龙虾路由接入配置。",
                "当前 ingress 只发送 request_id、external_contact_id 与 recent_messages；CRM 与话术库上下文由龙虾通过 MCP 主动拉取。",
                "龙虾同步只回 HTTP 200 表示已收到；真实分池结果必须通过 callback 回传 request_id、external_contact_id、target_pool。",
                "其中 no_reply / human_reply 会作为特殊池子结果入账；need_human_review=true 时会直接落到当前配置的人工复核目标池。",
                "当 ingress 超时、请求失败或 callback 非法时，会按 fallback 策略或拒绝路径入账，不再依赖同步回包做分池。",
            ],
        },
        "skills": {
            "items": skill_items,
            "selected": selected_skill,
            "notes": [
                "Skill 按只读、草稿写入和建议能力分层；当前未开放高风险直接改池能力。",
                "每次 skill 调用都会写入审计表，并刷新最近调用状态。",
            ],
        },
        "agents": {
            "items": agent_items,
            "selected": selected_agent,
            "bundle_version": bundle["bundle_version"],
            "bundle_hash": bundle["bundle_hash"],
            "generated_at": bundle["generated_at"],
            "pending_publish": pending_publish,
            "notes": [
                "子 Agent 配置已拆成角色提示词、任务提示词与上下文占位符。",
                "当前支持草稿态与已发布态；回滚仍是最小结构占位，不伪装成完整版本系统。",
            ],
        },
        "outputs": {
            "filters": output_filters,
            "rows": output_rows,
            "page": resolved_page,
            "page_size": resolved_page_size,
            "total": total_outputs,
            "selected": selected_output,
            "export_job": export_job,
            "notes": [
                "所有结构化输出采用追加式入账；是否采用与输出本身分离。",
                "小量导出同步完成，大量导出会进入异步任务。",
            ],
        },
        "replay": replay_payload,
        "metrics": metrics_payload,
    }


def save_agent_router_settings(payload: dict[str, Any], *, operator_id: str, source: str = "admin_console") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    existing = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    webhook_url = _normalized_text(payload.get("webhook_url"))
    if webhook_url and not webhook_url.startswith(("http://", "https://")):
        raise ValueError("router webhook_url must start with http:// or https://")
    timeout_seconds = _normalize_int(payload.get("timeout_seconds"), default=8, minimum=1, maximum=60)
    retry_count = _normalize_int(payload.get("retry_count"), default=1, minimum=0, maximum=5)
    fallback_strategy = _router_runtime_strategy({"fallback_strategy_json": _copy_json(payload.get("fallback_strategy") or {}, default={})})
    default_agent_code = _normalized_text(fallback_strategy.get("default_agent_code"))
    if default_agent_code and default_agent_code not in CHILD_AGENT_CONFIG_MAP:
        raise ValueError("fallback default_agent_code is invalid")
    human_review_target_pool = _normalized_text(fallback_strategy.get("human_review_target_pool")) or local_projection.POOL_HUMAN_REPLY
    if human_review_target_pool not in _router_allowed_target_pools():
        raise ValueError("fallback human_review_target_pool is invalid")
    fallback_strategy["human_review_target_pool"] = human_review_target_pool
    fallback_strategy["pending_callback_timeout_minutes"] = _normalize_int(
        fallback_strategy.get("pending_callback_timeout_minutes"),
        default=10,
        minimum=1,
        maximum=24 * 60,
    )
    signature_token = _normalized_text(payload.get("signature_token")) or _normalized_text(existing.get("signature_token"))
    signature_secret = _normalized_text(payload.get("signature_secret")) or _normalized_text(existing.get("signature_secret"))
    saved = repo.save_agent_router_config(
        {
            "enabled": _normalize_bool(payload.get("enabled")),
            "webhook_url": webhook_url,
            "signature_token": signature_token,
            "signature_secret": signature_secret,
            "signature_header": _normalized_text(payload.get("signature_header")) or "X-Lobster-Signature",
            "timeout_seconds": timeout_seconds,
            "retry_count": retry_count,
            "fallback_strategy_json": fallback_strategy,
            "request_sample_json": dict(ROUTER_REQUEST_SAMPLE),
            "response_sample_json": dict(ROUTER_RESPONSE_SAMPLE),
            "last_status": _normalized_text(existing.get("last_status")) or "configured",
            "last_error": _normalized_text(existing.get("last_error")),
            "last_called_at": _normalized_text(existing.get("last_called_at")),
            "updated_by": operator_id,
            "updated_source": source,
        }
    )
    get_db().commit()
    return {"router": _serialize_router_config(saved)}


def get_agent_config_detail(agent_code: str) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    row = repo.get_agent_config_row(_normalized_text(agent_code))
    if not row:
        raise LookupError("agent config not found")
    return _serialize_agent_config(row)


def list_agent_configs(*, enabled_only: bool = False) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    items = [item for item in _load_agent_list() if not enabled_only or bool(item.get("enabled"))]
    bundle = _agent_prompt_bundle_payload(items)
    return {
        "total": len(items),
        "items": items,
        "bundle_version": bundle["bundle_version"],
        "bundle_hash": bundle["bundle_hash"],
        "generated_at": bundle["generated_at"],
    }


def get_all_agent_prompts(*, enabled_only: bool = False) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    items = []
    for item in _load_agent_list():
        if enabled_only and not bool(item.get("enabled")):
            continue
        items.append(
            {
                "agent_code": _normalized_text(item.get("agent_code")),
                "display_name": _normalized_text(item.get("display_name")),
                "enabled": bool(item.get("enabled")),
                "draft_version": int(item.get("draft_version") or 1),
                "published_version": int(item.get("published_version") or 0),
                "draft": dict(item.get("draft") or {}),
                "published": dict(item.get("published") or {}),
                "diff_summary": list(item.get("diff_summary") or []),
                "last_modified_at": _normalized_text(item.get("last_modified_at")),
                "last_modified_by": _normalized_text(item.get("last_modified_by")),
                "last_change_summary": _normalized_text(item.get("last_change_summary")),
            }
        )
    bundle = _agent_prompt_bundle_payload(items)
    return {
        "total": len(items),
        "items": items,
        "bundle_version": bundle["bundle_version"],
        "bundle_hash": bundle["bundle_hash"],
        "generated_at": bundle["generated_at"],
    }


def diff_agent_prompt(agent_code: str) -> dict[str, Any]:
    return script_diff_draft(agent_code)


def submit_agent_prompt_for_publish(agent_code: str, *, operator_id: str, change_summary: str = "", expected_draft_version: Any = None) -> dict[str, Any]:
    return script_submit_for_publish(
        agent_code,
        operator_id=operator_id,
        change_summary=change_summary,
        expected_draft_version=expected_draft_version,
    )


def list_pending_agent_prompt_publish_requests(
    *,
    agent_code: str = "",
    enabled_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    normalized_agent_code = _normalized_text(agent_code)
    items = []
    for item in _load_agent_list():
        if normalized_agent_code and _normalized_text(item.get("agent_code")) != normalized_agent_code:
            continue
        if enabled_only and not bool(item.get("enabled")):
            continue
        if not bool(item.get("has_unpublished_changes")) and not bool(item.get("submitted_for_publish")):
            continue
        items.append(
            {
                "agent_code": _normalized_text(item.get("agent_code")),
                "display_name": _normalized_text(item.get("display_name")),
                "draft_version": int(item.get("draft_version") or 1),
                "published_version": int(item.get("published_version") or 0),
                "last_modified_at": _normalized_text(item.get("last_modified_at")),
                "last_modified_by": _normalized_text(item.get("last_modified_by")),
                "last_change_summary": _normalized_text(item.get("last_change_summary")),
                "has_unpublished_changes": bool(item.get("has_unpublished_changes")),
                "submitted_for_publish": bool(item.get("submitted_for_publish")),
                "submitted_at": _normalized_text(item.get("submitted_at")),
                "submitted_by": _normalized_text(item.get("submitted_by")),
                "enabled": bool(item.get("enabled")),
            }
        )
    items.sort(key=lambda value: (_normalized_text(value.get("submitted_at")) or _normalized_text(value.get("last_modified_at")), _normalized_text(value.get("agent_code"))), reverse=True)
    resolved_page = max(1, int(page or 1))
    resolved_page_size = max(1, min(100, int(page_size or 20)))
    start = (resolved_page - 1) * resolved_page_size
    end = start + resolved_page_size
    return {
        "total": len(items),
        "page": resolved_page,
        "page_size": resolved_page_size,
        "items": items[start:end],
    }


def create_agent_config(payload: dict[str, Any], *, operator_id: str, source: str = "admin_console") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    display_name = _normalized_text(payload.get("display_name"))
    if not display_name:
        raise ValueError("display_name is required")
    normalized_agent_code = _slugify_agent_code(payload.get("agent_code") or display_name)
    if not normalized_agent_code:
        raise ValueError("agent_code is required")
    if repo.get_agent_config_row(normalized_agent_code):
        raise ValueError("agent_code already exists")
    role_prompt = _normalized_text(payload.get("role_prompt"))
    task_prompt = _normalized_text(payload.get("task_prompt"))
    if not role_prompt:
        raise ValueError("role_prompt is required")
    if not task_prompt:
        raise ValueError("task_prompt is required")
    variables = _normalize_agent_config_variables(
        payload,
        role_prompt=role_prompt,
        task_prompt=task_prompt,
        default=[],
    )
    output_schema = _fixed_agent_output_schema()
    enabled = _normalize_bool(payload.get("enabled", True))
    summary = _normalized_text(payload.get("change_summary")) or "新建 Agent 草稿"
    saved = repo.insert_agent_config_row(
        {
            "agent_code": normalized_agent_code,
            "display_name": display_name,
            "pool_keys": [],
            "enabled": enabled,
            "draft_role_prompt": role_prompt,
            "draft_task_prompt": task_prompt,
            "draft_variables": variables,
            "draft_output_schema": output_schema,
            "published_role_prompt": "",
            "published_task_prompt": "",
            "published_variables": [],
            "published_output_schema": _fixed_agent_output_schema(),
            "draft_version": 1,
            "published_version": 0,
            "published_at": "",
            "published_by": "",
            "last_modified_at": _iso_now(),
            "last_modified_by": operator_id,
            "last_modified_source": source,
            "last_change_summary": summary,
            "submitted_for_publish": False,
            "submitted_at": "",
            "submitted_by": "",
        }
    )
    repo.insert_agent_prompt_row(
        {
            "agent_code": normalized_agent_code,
            "display_name": display_name,
            "prompt_text": task_prompt,
            "enabled": enabled,
            "version": 1,
        }
    )
    get_db().commit()
    return {"agent": _serialize_agent_config(saved)}


def create_agent_config_draft_via_mcp(
    payload: dict[str, Any],
    *,
    operator_id: str,
) -> dict[str, Any]:
    created = create_agent_config(
        payload,
        operator_id=operator_id,
        source="lobster_mcp_create_agent",
    )
    return {
        "created": True,
        "agent": created.get("agent") or {},
    }


def save_agent_config_draft(agent_code: str, payload: dict[str, Any], *, operator_id: str, source: str = "admin_console") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    normalized_agent_code = _normalized_text(agent_code)
    existing = repo.deserialize_agent_config_row(repo.get_agent_config_row(normalized_agent_code) or {})
    if not existing and normalized_agent_code not in CHILD_AGENT_CONFIG_MAP:
        raise LookupError("agent config not found")
    if not existing:
        raise LookupError("agent config not found")
    expected_draft_version = payload.get("expected_draft_version")
    if expected_draft_version not in (None, ""):
        expected_version = _normalize_int(expected_draft_version, default=int(existing.get("draft_version") or 1), minimum=1, maximum=1000000)
        current_version = int(existing.get("draft_version") or 1)
        if expected_version != current_version:
            raise DraftVersionConflictError(
                agent_code=normalized_agent_code,
                expected_draft_version=expected_version,
                current_draft_version=current_version,
            )
    next_display_name = _normalized_text(payload.get("display_name")) or _normalized_text(existing.get("display_name"))
    next_role_prompt = _normalized_text(payload.get("role_prompt")) if payload.get("role_prompt") is not None else _normalized_text(existing.get("draft_role_prompt"))
    next_task_prompt = _normalized_text(payload.get("task_prompt")) if payload.get("task_prompt") is not None else _normalized_text(existing.get("draft_task_prompt"))
    if not next_role_prompt:
        raise ValueError("role_prompt is required")
    if not next_task_prompt:
        raise ValueError("task_prompt is required")
    next_variables = _normalize_agent_config_variables(
        payload,
        role_prompt=next_role_prompt,
        task_prompt=next_task_prompt,
        default=list(existing.get("draft_variables_json") or []),
    )
    next_output_schema = _fixed_agent_output_schema()
    changed = json.dumps(
        {
            "display_name": next_display_name,
            "role_prompt": next_role_prompt,
            "task_prompt": next_task_prompt,
            "enabled_context_sources": _enabled_context_sources_from_variables(next_variables),
            "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
        },
        ensure_ascii=False,
        sort_keys=True,
    ) != json.dumps(
        {
            "display_name": _normalized_text(existing.get("display_name")),
            "role_prompt": _normalized_text(existing.get("draft_role_prompt")),
            "task_prompt": _normalized_text(existing.get("draft_task_prompt")),
            "enabled_context_sources": _enabled_context_sources_from_variables(list(existing.get("draft_variables_json") or [])),
            "enabled": bool(existing.get("enabled")),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    next_draft_version = int(existing.get("draft_version") or 1) + (1 if changed else 0)
    summary = _normalized_text(payload.get("change_summary")) or (
        "更新角色提示词、任务提示词与上下文占位符草稿" if changed else _normalized_text(existing.get("last_change_summary"))
    )
    saved = repo.update_agent_config_row(
        normalized_agent_code,
        {
            "display_name": next_display_name,
            "pool_keys": list(existing.get("pool_keys_json") or []),
            "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
            "draft_role_prompt": next_role_prompt,
            "draft_task_prompt": next_task_prompt,
            "draft_variables": next_variables,
            "draft_output_schema": next_output_schema,
            "published_role_prompt": _normalized_text(existing.get("published_role_prompt")),
            "published_task_prompt": _normalized_text(existing.get("published_task_prompt")),
            "published_variables": list(existing.get("published_variables_json") or []),
            "published_output_schema": _fixed_agent_output_schema(),
            "draft_version": next_draft_version,
            "published_version": int(existing.get("published_version") or 0),
            "published_at": _normalized_text(existing.get("published_at")),
            "published_by": _normalized_text(existing.get("published_by")),
            "submitted_for_publish": False,
            "submitted_at": "",
            "submitted_by": "",
            "last_modified_at": _iso_now(),
            "last_modified_by": operator_id,
            "last_modified_source": source,
            "last_change_summary": summary,
        },
    )
    legacy_prompt = repo.get_agent_prompt_row(normalized_agent_code)
    if legacy_prompt:
        repo.update_agent_prompt_row(
            normalized_agent_code,
            {
                "display_name": next_display_name,
                "prompt_text": next_task_prompt,
                "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
                "version": int(legacy_prompt.get("version") or 1) + (1 if changed else 0),
            },
        )
    else:
        repo.insert_agent_prompt_row(
            {
                "agent_code": normalized_agent_code,
                "display_name": next_display_name,
                "prompt_text": next_task_prompt,
                "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
                "version": 1,
            }
        )
    get_db().commit()
    return {"agent": _serialize_agent_config(saved)}


def publish_agent_config(agent_code: str, *, operator_id: str) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    normalized_agent_code = _normalized_text(agent_code)
    existing = repo.deserialize_agent_config_row(repo.get_agent_config_row(normalized_agent_code) or {})
    if not existing:
        raise LookupError("agent config not found")
    saved = repo.update_agent_config_row(
        normalized_agent_code,
        {
            "display_name": _normalized_text(existing.get("display_name")),
            "pool_keys": list(existing.get("pool_keys_json") or []),
            "enabled": bool(existing.get("enabled")),
            "draft_role_prompt": _normalized_text(existing.get("draft_role_prompt")),
            "draft_task_prompt": _normalized_text(existing.get("draft_task_prompt")),
            "draft_variables": list(existing.get("draft_variables_json") or []),
            "draft_output_schema": _fixed_agent_output_schema(),
            "published_role_prompt": _normalized_text(existing.get("draft_role_prompt")),
            "published_task_prompt": _normalized_text(existing.get("draft_task_prompt")),
            "published_variables": list(existing.get("draft_variables_json") or []),
            "published_output_schema": _fixed_agent_output_schema(),
            "draft_version": int(existing.get("draft_version") or 1),
            "published_version": int(existing.get("draft_version") or 1),
            "published_at": _iso_now(),
            "published_by": operator_id,
            "submitted_for_publish": False,
            "submitted_at": "",
            "submitted_by": "",
            "last_modified_at": _iso_now(),
            "last_modified_by": operator_id,
            "last_modified_source": "publish",
            "last_change_summary": f"发布草稿版本 v{int(existing.get('draft_version') or 1)}",
        },
    )
    get_db().commit()
    return {"agent": _serialize_agent_config(saved)}


def delete_agent_config(agent_code: str, *, operator_id: str, source: str = "admin_console") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    normalized_agent_code = _normalized_text(agent_code)
    existing = repo.deserialize_agent_config_row(repo.get_agent_config_row(normalized_agent_code) or {})
    if not existing:
        raise LookupError("agent config not found")
    if normalized_agent_code in CHILD_AGENT_CONFIG_MAP:
        raise ValueError("系统预置 Agent 不支持删除；删除后会被默认配置自动补回。")

    workflow_references = workflow_repo.list_workflow_agent_binding_reference_rows(normalized_agent_code)
    if workflow_references:
        reference_labels = []
        for item in workflow_references[:5]:
            workflow_label = _normalized_text(item.get("workflow_name")) or _normalized_text(item.get("workflow_code")) or f"#{int(item.get('workflow_id') or 0)}"
            node_label = _normalized_text(item.get("node_name")) or _normalized_text(item.get("node_code"))
            reference_labels.append(f"{workflow_label} / {node_label}" if node_label else workflow_label)
        if len(workflow_references) > 5:
            reference_labels.append(f"等 {len(workflow_references)} 处引用")
        raise ValueError(f"当前 Agent 已被任务流引用，暂不能删除：{'；'.join(reference_labels)}")

    skill_references = [
        repo.deserialize_agent_skill_row(item)
        for item in repo.list_agent_skill_rows_for_agent(normalized_agent_code)
    ]
    if skill_references:
        skill_labels = [
            _normalized_text(item.get("skill_code")) or f"#{index + 1}"
            for index, item in enumerate(skill_references[:5])
        ]
        if len(skill_references) > 5:
            skill_labels.append(f"等 {len(skill_references)} 项")
        raise ValueError(f"当前 Agent 已被其他技能配置引用，暂不能删除：{'、'.join(skill_labels)}")

    repo.delete_agent_prompt_row(normalized_agent_code)
    repo.delete_agent_config_row(normalized_agent_code)
    get_db().commit()
    return {
        "deleted": True,
        "agent_code": normalized_agent_code,
        "message": f"Agent {normalized_agent_code} 已删除",
        "operator_id": _normalized_text(operator_id),
        "source": _normalized_text(source),
    }


def create_agent_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = repo.insert_agent_run(payload)
    get_db().commit()
    return _serialize_agent_run(row)


def update_agent_run_status(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = repo.deserialize_agent_run_row(repo.get_agent_run_row(run_id) or {})
    if not existing:
        raise LookupError("agent run not found")
    row = repo.update_agent_run(
        run_id,
        {
            "request_id": payload.get("request_id", existing.get("request_id")),
            "batch_id": payload.get("batch_id", existing.get("batch_id")),
            "userid": payload.get("userid", existing.get("userid")),
            "external_contact_id": payload.get("external_contact_id", existing.get("external_contact_id")),
            "agent_code": payload.get("agent_code", existing.get("agent_code")),
            "agent_type": payload.get("agent_type", existing.get("agent_type")),
            "provider": payload.get("provider", existing.get("provider")),
            "input_snapshot": payload.get("input_snapshot", existing.get("input_snapshot_json") or {}),
            "variables_snapshot": payload.get("variables_snapshot", existing.get("variables_snapshot_json") or {}),
            "final_prompt_preview": payload.get("final_prompt_preview", existing.get("final_prompt_preview")),
            "role_prompt_version": payload.get("role_prompt_version", existing.get("role_prompt_version")),
            "task_prompt_version": payload.get("task_prompt_version", existing.get("task_prompt_version")),
            "status": payload.get("status", existing.get("status")),
            "error_code": payload.get("error_code", existing.get("error_code")),
            "error_message": payload.get("error_message", existing.get("error_message")),
            "latency_ms": payload.get("latency_ms", existing.get("latency_ms")),
            "source": payload.get("source", existing.get("source")),
            "parent_run_id": payload.get("parent_run_id", existing.get("parent_run_id")),
            "replay_of_run_id": payload.get("replay_of_run_id", existing.get("replay_of_run_id")),
        },
    )
    get_db().commit()
    return _serialize_agent_run(row)


def append_agent_output(payload: dict[str, Any]) -> dict[str, Any]:
    output_id = _normalized_text(payload.get("output_id")) or f"aout-{uuid.uuid4().hex}"
    row = repo.insert_agent_output({**payload, "output_id": output_id})
    get_db().commit()
    return _serialize_agent_output(row, visibility="full")


def list_agent_outputs(
    filters: dict[str, Any] | None = None,
    *,
    page: int = 1,
    page_size: int = 20,
    visibility: str = "masked",
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    resolved_page = max(1, int(page or 1))
    resolved_page_size = max(1, min(100, int(page_size or 20)))
    total = repo.count_agent_output_rows(filters or {})
    rows = [
        _serialize_agent_output(item, visibility=visibility)
        for item in repo.list_agent_output_rows(filters=filters or {}, limit=resolved_page_size, offset=(resolved_page - 1) * resolved_page_size)
    ]
    return {
        "page": resolved_page,
        "page_size": resolved_page_size,
        "total": total,
        "rows": rows,
    }


def get_agent_output_detail(output_id: str, *, visibility: str = "masked") -> dict[str, Any]:
    row = repo.get_agent_output_row(_normalized_text(output_id))
    if not row:
        return {}
    serialized = _serialize_agent_output(row, visibility=visibility)
    run = get_agent_run_detail(serialized.get("run_id"), visibility=visibility)
    return {
        "output": serialized,
        "run": run,
    }


def get_agent_run_detail(run_id: str, *, visibility: str = "masked") -> dict[str, Any]:
    row = repo.get_agent_run_row(_normalized_text(run_id))
    if not row:
        return {}
    serialized = _serialize_agent_run(row, visibility=visibility)
    serialized["outputs"] = [_serialize_agent_output(item, visibility=visibility) for item in repo.list_agent_outputs_by_run_id(serialized["run_id"])]
    return serialized


def get_agent_outputs_by_request(request_id: str, *, visibility: str = "masked") -> dict[str, Any]:
    return list_agent_outputs({"request_id": request_id}, page=1, page_size=50, visibility=visibility)


def get_agent_outputs_by_user(userid: str, limit: int = 20, *, visibility: str = "masked") -> dict[str, Any]:
    normalized_user = _normalized_text(userid)
    if not normalized_user:
        resolved_page_size = min(100, max(1, int(limit or 20)))
        return {"page": 1, "page_size": resolved_page_size, "total": 0, "rows": []}
    external_match = list_agent_outputs(
        {"external_contact_id": normalized_user},
        page=1,
        page_size=min(100, max(1, int(limit or 20))),
        visibility=visibility,
    )
    if int(external_match.get("total") or 0) > 0:
        return external_match
    return list_agent_outputs(
        {"userid": normalized_user},
        page=1,
        page_size=min(100, max(1, int(limit or 20))),
        visibility=visibility,
    )


def _build_export_rows(filters: dict[str, Any]) -> tuple[list[str], list[list[str]], int]:
    total = repo.count_agent_output_rows(filters)
    rows = [
        _serialize_agent_output(item, visibility="export")
        for item in repo.list_agent_output_rows(filters=filters, limit=max(1, total or 1), offset=0)
    ]
    rendered_rows = [
        [
            item["created_at"],
            item["request_id"],
            item["userid"],
            item["external_contact_id"],
            item["agent_code"],
            item["output_type"],
            item["target_agent_code"],
            item["target_pool"],
            str(item["confidence"]),
            item["reason"],
            item["rendered_output_text"],
            item["applied_status"],
        ]
        for item in rows
    ]
    return _DEFAULT_OUTPUT_HEADERS, rendered_rows, total


def _complete_export_job(job_id: str) -> None:
    job = repo.deserialize_agent_output_export_job_row(repo.get_agent_output_export_job(job_id) or {})
    if not job:
        return
    filters = dict(job.get("filters_json") or {})
    headers, rows, total = _build_export_rows(filters)
    content = _build_excel_xml(headers, rows)
    repo.update_agent_output_export_job(
        job_id,
        {
            "requested_by": _normalized_text(job.get("requested_by")),
            "filters": filters,
            "status": "completed",
            "total_count": total,
            "exported_count": len(rows),
            "file_name": _normalized_text(job.get("file_name")) or f"agent-outputs-{job_id}.xls",
            "file_content_base64": base64.b64encode(content).decode("ascii"),
            "error_message": "",
            "finished_at": _iso_now(),
        },
    )
    get_db().commit()


def create_agent_output_export_job(filters: dict[str, Any], *, requested_by: str, async_threshold: int = 500) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    window_start = (datetime.utcnow() - timedelta(minutes=_EXPORT_RATE_LIMIT_WINDOW_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    recent_count = repo.count_recent_agent_output_export_jobs(requested_by, since_text=window_start)
    if recent_count >= _EXPORT_RATE_LIMIT_COUNT:
        raise ValueError("export rate limited, please retry later")
    total = repo.count_agent_output_rows(filters or {})
    job_id = f"aexp-{uuid.uuid4().hex}"
    file_name = f"agent-outputs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xls"
    job_row = repo.insert_agent_output_export_job(
        {
            "job_id": job_id,
            "requested_by": requested_by,
            "filters": filters or {},
            "status": "queued",
            "total_count": total,
            "exported_count": 0,
            "file_name": file_name,
        }
    )
    get_db().commit()
    app = current_app._get_current_object()
    if total <= async_threshold:
        with app.app_context():
            _complete_export_job(job_id)
    else:
        def _worker() -> None:
            with app.app_context():
                try:
                    _complete_export_job(job_id)
                except Exception as exc:  # pragma: no cover - async fallback path
                    repo.update_agent_output_export_job(
                        job_id,
                        {
                            "requested_by": requested_by,
                            "filters": filters or {},
                            "status": "failed",
                            "total_count": total,
                            "exported_count": 0,
                            "file_name": file_name,
                            "error_message": str(exc),
                            "finished_at": _iso_now(),
                        },
                    )
                    get_db().commit()

        _EXPORT_EXECUTOR.submit(_worker)
    return get_agent_output_export_job(job_id)


def get_agent_output_export_job(job_id: str) -> dict[str, Any]:
    row = repo.get_agent_output_export_job(_normalized_text(job_id))
    if not row:
        return {}
    return _serialize_export_job(row)


def get_agent_output_export_file(job_id: str) -> dict[str, Any]:
    row = repo.deserialize_agent_output_export_job_row(repo.get_agent_output_export_job(_normalized_text(job_id)) or {})
    if not row:
        return {}
    content_base64 = _normalized_text(row.get("file_content_base64"))
    return {
        "job": _serialize_export_job(row),
        "file_name": _normalized_text(row.get("file_name")),
        "content_bytes": base64.b64decode(content_base64) if content_base64 else b"",
    }


def get_agent_replay_payload(
    *,
    run_id: str = "",
    request_id: str = "",
    external_contact_id: str = "",
    userid: str = "",
    date_from: str = "",
    date_to: str = "",
    visibility: str = "masked",
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    filters = {
        "run_id": run_id,
        "request_id": request_id,
        "external_contact_id": external_contact_id,
        "userid": userid,
        "date_from": date_from,
        "date_to": date_to,
    }
    run_filters = {key: value for key, value in filters.items() if key in {"request_id", "external_contact_id", "userid", "date_from", "date_to"} and _normalized_text(value)}
    selected_row = repo.get_agent_run_row(_normalized_text(run_id)) if _normalized_text(run_id) else None
    candidate_rows = repo.list_agent_run_rows(filters=run_filters, limit=20, offset=0)
    if not selected_row and candidate_rows:
        selected_row = candidate_rows[0]
    selected_run = _serialize_agent_run(selected_row, visibility=visibility) if selected_row else {}
    outputs = [_serialize_agent_output(item, visibility=visibility) for item in repo.list_agent_outputs_by_run_id(selected_run.get("run_id", ""))] if selected_run else []
    previous_rows = [item for item in candidate_rows if _normalized_text(item.get("run_id")) != _normalized_text(selected_run.get("run_id"))]
    previous_run = _serialize_agent_run(previous_rows[0], visibility=visibility) if previous_rows else {}
    previous_outputs = [_serialize_agent_output(item, visibility=visibility) for item in repo.list_agent_outputs_by_run_id(previous_run.get("run_id", ""))] if previous_run else []
    diff_items: list[str] = []
    if selected_run and previous_run:
        if _normalized_text(selected_run.get("agent_code")) != _normalized_text(previous_run.get("agent_code")):
            diff_items.append("当前回放与上一条 run 的 agent_code 不同")
        if _normalized_text(selected_run.get("status")) != _normalized_text(previous_run.get("status")):
            diff_items.append("当前回放与上一条 run 的状态不同")
        if json.dumps([item.get("output_type") for item in outputs], ensure_ascii=False) != json.dumps(
            [item.get("output_type") for item in previous_outputs], ensure_ascii=False
        ):
            diff_items.append("输出类型集合与上一条 run 不同")
    router_output = next((item for item in outputs if item.get("output_type") in {"route_decision", "fallback_decision"}), {})
    final_output = next((item for item in outputs if item.get("applied_status") in {"applied", "replayed"}), outputs[0] if outputs else {})
    return {
        "filters": filters,
        "runs": [_serialize_agent_run(item, visibility=visibility) for item in candidate_rows],
        "selected_run": selected_run,
        "selected_outputs": outputs,
        "router_output": router_output,
        "final_output": final_output,
        "previous_run": previous_run,
        "diff_items": diff_items,
        "notes": [
            "当前 replay 基于已记录输入快照、变量快照和输出账本重建上下文，不会重新请求外部 webhook。",
            "可以按 request_id 或用户查看最近一次 run，并区分“生成了什么”和“最终采用了什么”。",
        ],
    }


def list_router_pending_callbacks(*, older_than_minutes: int = 15, limit: int = 20, visibility: str = "masked") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    threshold_minutes = max(1, min(24 * 60, int(older_than_minutes or 15)))
    threshold = datetime.now() - timedelta(minutes=threshold_minutes)
    candidates = repo.list_agent_run_rows(
        filters={"agent_code": "central_router_agent"},
        limit=max(int(limit or 20) * 20, 200),
        offset=0,
    )
    rows: list[dict[str, Any]] = []
    for item in candidates:
        row = repo.deserialize_agent_run_row(item)
        if _normalized_text(row.get("provider")) != "lobster_shadow":
            continue
        if _normalized_text(row.get("status")) != "acked":
            continue
        last_ack_at = _parse_datetime_text(_normalized_text(row.get("updated_at")) or _normalized_text(row.get("created_at")))
        if not last_ack_at or last_ack_at > threshold:
            continue
        outputs = [repo.deserialize_agent_output_row(output) for output in repo.list_agent_outputs_by_run_id(_normalized_text(row.get("run_id")))]
        if any(_normalized_text(output.get("output_type")) in {"callback_received", "callback_validated", "callback_rejected", "route_decision"} for output in outputs):
            continue
        waited_minutes = max(0, int((datetime.now() - last_ack_at).total_seconds() // 60))
        rows.append(
            {
                "run": _serialize_agent_run(row, visibility=visibility),
                "waited_minutes": waited_minutes,
                "acked_at": last_ack_at.strftime("%Y-%m-%d %H:%M:%S"),
                "latest_ingress_output": _serialize_agent_output(
                    next(
                        (output for output in reversed(outputs) if _normalized_text(output.get("output_type")) == "route_ingress_acked"),
                        {},
                    ),
                    visibility=visibility,
                ) if outputs else {},
            }
        )
        if len(rows) >= max(1, min(100, int(limit or 20))):
            break
    return {
        "older_than_minutes": threshold_minutes,
        "total": len(rows),
        "rows": rows,
    }


def run_router_pending_callback_check(
    *,
    older_than_minutes: int | None = None,
    limit: int = 100,
    operator_id: str = "system",
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    router_config = repo.get_agent_router_config() or {}
    runtime_strategy = _router_runtime_strategy(router_config)
    threshold_minutes = (
        max(1, min(24 * 60, int(older_than_minutes)))
        if older_than_minutes is not None
        else int(runtime_strategy.get("pending_callback_timeout_minutes") or 10)
    )
    pending = list_router_pending_callbacks(older_than_minutes=threshold_minutes, limit=max(1, min(500, int(limit or 100))), visibility="full")
    alert_channel = _normalized_text(runtime_strategy.get("alert_channel")) or "run_center"
    alerted_rows: list[dict[str, Any]] = []
    existing_alert_count = 0
    checked_count = int(pending.get("total") or 0)
    for item in pending.get("rows") or []:
        run_payload = dict(item.get("run") or {})
        run_id = _normalized_text(run_payload.get("run_id"))
        if not run_id:
            continue
        existing_outputs = [
            repo.deserialize_agent_output_row(output)
            for output in repo.list_agent_outputs_by_run_id(run_id)
        ]
        if any(_normalized_text(output.get("output_type")) == "pending_callback_alert" for output in existing_outputs):
            existing_alert_count += 1
            continue
        waited_minutes = int(item.get("waited_minutes") or 0)
        alert_reason = f"request_id={run_payload.get('request_id') or '-'} 已 ack {waited_minutes} 分钟仍未收到 callback"
        alert_output = _append_router_event_output(
            run_id=run_id,
            request_id=_normalized_text(run_payload.get("request_id")),
            userid=_normalized_text(run_payload.get("userid")),
            external_contact_id=_normalized_text(run_payload.get("external_contact_id")),
            output_type="pending_callback_alert",
            rendered_output_text=alert_reason,
            raw_output_text=alert_reason,
            normalized_output={
                "event": "pending_callback_alert",
                "threshold_minutes": threshold_minutes,
                "waited_minutes": waited_minutes,
                "alert_channel": alert_channel,
                "operator_id": operator_id,
            },
            target_pool="",
            confidence=0.0,
            reason=alert_reason,
            need_human_review=False,
            applied_status="alerted",
        )
        alerted_rows.append(_serialize_agent_output(alert_output, visibility="masked"))
    return {
        "ok": True,
        "status": "checked",
        "threshold_minutes": threshold_minutes,
        "checked_count": checked_count,
        "alerted_count": len(alerted_rows),
        "existing_alert_count": existing_alert_count,
        "rows": alerted_rows,
    }


def replay_agent_run(run_id: str, *, operator_id: str) -> dict[str, Any]:
    existing = repo.deserialize_agent_run_row(repo.get_agent_run_row(_normalized_text(run_id)) or {})
    if not existing:
        raise LookupError("agent run not found")
    new_run_id = f"arun-{uuid.uuid4().hex}"
    copied_run = repo.insert_agent_run(
        {
            "run_id": new_run_id,
            "request_id": _normalized_text(existing.get("request_id")),
            "batch_id": _normalized_text(existing.get("batch_id")),
            "userid": _normalized_text(existing.get("userid")),
            "external_contact_id": _normalized_text(existing.get("external_contact_id")),
            "agent_code": _normalized_text(existing.get("agent_code")),
            "agent_type": _normalized_text(existing.get("agent_type")),
            "provider": _normalized_text(existing.get("provider")) or "replay",
            "input_snapshot": existing.get("input_snapshot_json") or {},
            "variables_snapshot": existing.get("variables_snapshot_json") or {},
            "final_prompt_preview": _normalized_text(existing.get("final_prompt_preview")),
            "role_prompt_version": _normalized_text(existing.get("role_prompt_version")),
            "task_prompt_version": _normalized_text(existing.get("task_prompt_version")),
            "status": "replayed",
            "error_code": "",
            "error_message": "",
            "latency_ms": 0,
            "source": f"replay:{operator_id}",
            "parent_run_id": _normalized_text(existing.get("run_id")),
            "replay_of_run_id": _normalized_text(existing.get("run_id")),
        }
    )
    copied_outputs: list[dict[str, Any]] = []
    for item in repo.list_agent_outputs_by_run_id(_normalized_text(existing.get("run_id"))):
        output = repo.deserialize_agent_output_row(item)
        copied_outputs.append(
            _serialize_agent_output(
                repo.insert_agent_output(
                    {
                        "output_id": f"aout-{uuid.uuid4().hex}",
                        "run_id": new_run_id,
                        "request_id": _normalized_text(output.get("request_id")),
                        "userid": _normalized_text(output.get("userid")),
                        "external_contact_id": _normalized_text(output.get("external_contact_id")),
                        "agent_code": _normalized_text(output.get("agent_code")),
                        "output_type": _normalized_text(output.get("output_type")),
                        "raw_output_text": _normalized_text(output.get("raw_output_text")),
                        "normalized_output": output.get("normalized_output_json") or {},
                        "rendered_output_text": _normalized_text(output.get("rendered_output_text")),
                        "target_agent_code": _normalized_text(output.get("target_agent_code")),
                        "target_pool": _normalized_text(output.get("target_pool")),
                        "confidence": output.get("confidence") or 0,
                        "reason": _normalized_text(output.get("reason")),
                        "need_human_review": bool(output.get("need_human_review")),
                        "applied_status": "replayed",
                        "applied_at": _iso_now(),
                        "revision_of_output_id": _normalized_text(output.get("output_id")),
                        "error_code": _normalized_text(output.get("error_code")),
                        "error_message": _normalized_text(output.get("error_message")),
                    }
                )
            )
        )
    get_db().commit()
    return {
        "run": _serialize_agent_run(copied_run),
        "outputs": copied_outputs,
    }


def replay_router_callback(run_id: str, *, operator_id: str) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    existing = repo.deserialize_agent_run_row(repo.get_agent_run_row(_normalized_text(run_id)) or {})
    if not existing:
        raise LookupError("agent run not found")
    if _normalized_text(existing.get("agent_code")) != "central_router_agent":
        raise ValueError("callback replay only supports central_router_agent")
    outputs = [repo.deserialize_agent_output_row(item) for item in repo.list_agent_outputs_by_run_id(_normalized_text(run_id))]
    callback_output = next(
        (
            item
            for item in reversed(outputs)
            if _normalized_text(item.get("output_type")) in {"callback_received", "callback_validated", "callback_rejected"}
        ),
        {},
    )
    callback_payload = _normalize_json_dict(callback_output.get("normalized_output_json"))
    if not callback_payload:
        try:
            callback_payload = json.loads(_normalized_text(callback_output.get("raw_output_text")) or "{}")
        except ValueError:
            callback_payload = {}
    if not isinstance(callback_payload, dict) or not _normalized_text(callback_payload.get("external_contact_id")):
        raise ValueError("callback payload not found for replay")
    replay_request_id = f"{_normalized_text(existing.get('request_id'))}-callback-replay-{uuid.uuid4().hex[:8]}"
    replay_run_id = f"arun-{uuid.uuid4().hex}"
    replay_variables = dict(existing.get("variables_snapshot_json") or {})
    replay_variables["callback_replay"] = {
        "source_run_id": _normalized_text(existing.get("run_id")),
        "requested_by": _normalized_text(operator_id),
        "replay_request_id": replay_request_id,
    }
    repo.insert_agent_run(
        {
            "run_id": replay_run_id,
            "request_id": replay_request_id,
            "batch_id": _normalized_text(existing.get("batch_id")),
            "userid": _normalized_text(existing.get("userid")),
            "external_contact_id": _normalized_text(existing.get("external_contact_id")),
            "agent_code": _normalized_text(existing.get("agent_code")),
            "agent_type": _normalized_text(existing.get("agent_type")) or "router",
            "provider": _normalized_text(existing.get("provider")) or "lobster_shadow",
            "input_snapshot": existing.get("input_snapshot_json") or {},
            "variables_snapshot": replay_variables,
            "final_prompt_preview": _normalized_text(existing.get("final_prompt_preview")),
            "role_prompt_version": _normalized_text(existing.get("role_prompt_version")),
            "task_prompt_version": _normalized_text(existing.get("task_prompt_version")),
            "status": "acked",
            "error_code": "",
            "error_message": "",
            "latency_ms": int(existing.get("latency_ms") or 0),
            "source": f"callback_replay:{operator_id}",
            "parent_run_id": _normalized_text(existing.get("run_id")),
            "replay_of_run_id": _normalized_text(existing.get("run_id")),
        }
    )
    replay_payload = {
        **callback_payload,
        "request_id": replay_request_id,
        "external_contact_id": _normalized_text(callback_payload.get("external_contact_id")) or _normalized_text(existing.get("external_contact_id")),
    }
    result = handle_agent_router_callback(replay_payload)
    replay_run = repo.get_agent_run_row(replay_run_id) or {}
    replay_outputs = [_serialize_agent_output(item) for item in repo.list_agent_outputs_by_run_id(replay_run_id)]
    return {
        "replayed": True,
        "request_id": replay_request_id,
        "source_run_id": _normalized_text(existing.get("run_id")),
        "run": _serialize_agent_run(replay_run),
        "result": result,
        "callback_payload": replay_payload,
        "outputs": replay_outputs,
    }


def get_pool_snapshot(pool_key: str, *, limit: int = 10) -> dict[str, Any]:
    route_key = _POOL_TO_ROUTE_KEY.get(_normalized_text(pool_key))
    if not route_key:
        raise ValueError("invalid pool_key")
    payload = get_stage_detail_payload(route_key=route_key, keyword="", offset=0, limit=max(1, min(50, int(limit or 10))))
    return {
        "pool_key": _normalized_text(pool_key),
        "stage": dict(payload.get("stage") or {}),
        "pagination": dict(payload.get("pagination") or {}),
        "filters": dict(payload.get("filters") or {}),
        "member_count": int((payload.get("pagination") or {}).get("total") or 0),
        "sample_members": list(payload.get("customers") or []),
    }


def suggest_pool_action(*, external_contact_id: str = "", phone: str = "", operator_id: str = "skill") -> dict[str, Any]:
    detail = get_member_detail(external_contact_id=external_contact_id, phone=phone)
    member = dict(detail.get("member") or {})
    questionnaire = dict(detail.get("questionnaire") or {})
    current_pool = _normalized_text(member.get("current_pool"))
    next_action = "keep_followup"
    target_pool = current_pool
    reason = "当前阶段无需额外改池，建议继续按照现有跟进节奏推进。"
    if not bool(member.get("in_pool")):
        next_action = "put_in_pool"
        target_pool = local_projection.POOL_PENDING_QUESTIONNAIRE
        reason = "成员当前不在自动化池内，建议先重新入池。"
    elif _normalized_text(questionnaire.get("status")) == "pending":
        next_action = "wait_questionnaire"
        target_pool = local_projection.POOL_PENDING_QUESTIONNAIRE
        reason = "成员尚未完成问卷，应继续停留在未填问卷人群等待分层。"
    elif current_pool == local_projection.POOL_CONVERTED:
        next_action = "no_action"
        target_pool = local_projection.POOL_CONVERTED
        reason = "成员已经标记成交，不建议自动改池。"
    run_id = f"arun-{uuid.uuid4().hex}"
    request_id = f"skill-{uuid.uuid4().hex}"
    create_agent_run(
        {
            "run_id": run_id,
            "request_id": request_id,
            "userid": _normalized_text((detail.get("profile") or {}).get("owner_staff_id")),
            "external_contact_id": _normalized_text((detail.get("profile") or {}).get("external_contact_id")),
            "agent_code": "suggest_pool_action",
            "agent_type": "skill",
            "provider": "skill_registry",
            "input_snapshot": {"member": detail},
            "variables_snapshot": _build_member_variable_snapshot(external_contact_id, phone),
            "final_prompt_preview": "Skill suggestion only",
            "role_prompt_version": "skill",
            "task_prompt_version": "skill",
            "status": "success",
            "source": f"skill:{operator_id}",
        }
    )
    output = append_agent_output(
        {
            "run_id": run_id,
            "request_id": request_id,
            "userid": _normalized_text((detail.get("profile") or {}).get("owner_staff_id")),
            "external_contact_id": _normalized_text((detail.get("profile") or {}).get("external_contact_id")),
            "agent_code": "suggest_pool_action",
            "output_type": "pool_change_suggestion",
            "raw_output_text": reason,
            "normalized_output": {
                "next_action": next_action,
                "target_pool": target_pool,
                "reason": reason,
                "need_human_review": next_action == "human_review",
            },
            "rendered_output_text": reason,
            "target_pool": target_pool,
            "confidence": 0.61,
            "reason": reason,
            "need_human_review": next_action == "human_review",
            "applied_status": "suggested",
        }
    )
    return {
        "ok": True,
        "run_id": run_id,
        "request_id": request_id,
        "member_exists": bool(detail.get("member_exists")),
        "next_action": next_action,
        "target_pool": target_pool,
        "reason": reason,
        "output": output,
    }


def audit_agent_skill_call(
    *,
    skill_code: str,
    source: str,
    permissions_scope: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    status: str,
    error_code: str = "",
    error_message: str = "",
    latency_ms: int = 0,
    idempotency_key: str = "",
) -> dict[str, Any]:
    call_id = f"askill-{uuid.uuid4().hex}"
    row = repo.insert_agent_skill_call_audit(
        {
            "call_id": call_id,
            "skill_code": skill_code,
            "source": source,
            "permissions_scope": permissions_scope,
            "idempotency_key": idempotency_key,
            "request_payload": request_payload,
            "response_payload": response_payload,
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "latency_ms": latency_ms,
        }
    )
    skill_row = repo.deserialize_agent_skill_row(repo.get_agent_skill_row(skill_code) or {})
    if skill_row:
        repo.update_agent_skill_row(
            skill_code,
            {
                "agent_code": _normalized_text(skill_row.get("agent_code")),
                "pool_keys": list(skill_row.get("pool_keys_json") or []),
                "read_capabilities": list(skill_row.get("read_capabilities_json") or []),
                "write_capabilities": list(skill_row.get("write_capabilities_json") or []),
                "enabled": bool(skill_row.get("enabled")),
                "input_schema": dict(skill_row.get("input_schema_json") or {}),
                "output_schema": dict(skill_row.get("output_schema_json") or {}),
                "permission_notes": _normalized_text(skill_row.get("permission_notes")),
                "idempotency_notes": _normalized_text(skill_row.get("idempotency_notes")),
                "audit_notes": _normalized_text(skill_row.get("audit_notes")),
                "example_request": dict(skill_row.get("example_request_json") or {}),
                "example_response": dict(skill_row.get("example_response_json") or {}),
                "last_call_status": status,
                "last_error": error_message,
                "last_called_at": _iso_now(),
            }
        )
    get_db().commit()
    return repo.deserialize_agent_skill_call_audit_row(row)
