from __future__ import annotations

from typing import Any

from ...db import get_db
from ...infra.settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_EXECUTION_MODEL,
    DEFAULT_DEEPSEEK_REASONER_MODEL,
    DEFAULT_DEEPSEEK_ROUTER_MODEL,
    DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
    mask_value,
    set_settings,
)
from . import repo
from .agents import (
    AGENT_PROMPT_DEFINITION_MAP,
    AGENT_PROMPT_ORDER,
    CHILD_AGENT_CONFIG_MAP,
    DeepSeekClientError,
    default_agent_prompt_payloads,
    get_deepseek_runtime_config,
    test_deepseek_connection,
)
from .service import (
    DEEPSEEK_SETTING_KEYS,
    _normalize_bool,
    _normalized_text,
    _setting_text_value,
)


def ensure_agent_prompt_defaults() -> None:
    existing_codes = {
        _normalized_text(item.get("agent_code"))
        for item in repo.list_agent_prompt_rows()
        if _normalized_text(item.get("agent_code"))
    }
    for payload in default_agent_prompt_payloads():
        agent_code = _normalized_text(payload.get("agent_code"))
        if agent_code in existing_codes:
            continue
        repo.insert_agent_prompt_row(payload)


def _serialize_agent_prompt_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    definition = AGENT_PROMPT_DEFINITION_MAP.get(_normalized_text(row.get("agent_code")), {})
    deserialized = repo.deserialize_agent_prompt_row(dict(row))
    return {
        "id": int(deserialized.get("id") or 0),
        "agent_code": _normalized_text(deserialized.get("agent_code")),
        "display_name": _normalized_text(deserialized.get("display_name")) or _normalized_text(definition.get("display_name")),
        "prompt_text": _normalized_text(deserialized.get("prompt_text")),
        "enabled": _normalize_bool(deserialized.get("enabled")),
        "version": int(deserialized.get("version") or 1),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "created_at": _normalized_text(deserialized.get("created_at")),
    }


def _serialize_agent_llm_call_log(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": int(row.get("id") or 0),
        "agent_code": _normalized_text(row.get("agent_code")),
        "model_name": _normalized_text(row.get("model_name")),
        "request_id": _normalized_text(row.get("request_id")),
        "status": _normalized_text(row.get("status")),
        "latency_ms": int(row.get("latency_ms") or 0),
        "error_message": _normalized_text(row.get("error_message")),
        "created_at": _normalized_text(row.get("created_at")),
    }


def _deepseek_settings_payload() -> dict[str, Any]:
    config = get_deepseek_runtime_config()
    setting_rows = repo.list_app_setting_rows(list(DEEPSEEK_SETTING_KEYS))
    latest_updated_at = _normalized_text(setting_rows[0].get("updated_at")) if setting_rows else ""
    api_key = _normalized_text(config.get("api_key"))
    return {
        "enabled": bool(config.get("enabled")),
        "api_key_configured": bool(api_key),
        "api_key_masked": mask_value("DEEPSEEK_API_KEY", api_key),
        "base_url": _normalized_text(config.get("base_url")) or DEFAULT_DEEPSEEK_BASE_URL,
        "router_model": _normalized_text(config.get("router_model")) or DEFAULT_DEEPSEEK_ROUTER_MODEL,
        "execution_model": _normalized_text(config.get("execution_model")) or DEFAULT_DEEPSEEK_EXECUTION_MODEL,
        "reasoner_model": _normalized_text(config.get("reasoner_model")) or DEFAULT_DEEPSEEK_REASONER_MODEL,
        "timeout_seconds": int(config.get("timeout_seconds") or DEFAULT_DEEPSEEK_TIMEOUT_SECONDS),
        "updated_at": latest_updated_at,
    }


def get_model_infra_payload(*, limit_logs: int = 20) -> dict[str, Any]:
    ensure_agent_prompt_defaults()
    db = get_db()
    db.commit()
    prompt_rows = {
        _normalized_text(item.get("agent_code")): _serialize_agent_prompt_row(item)
        for item in repo.list_agent_prompt_rows()
    }
    prompts = [
        prompt_rows.get(agent_code)
        or _serialize_agent_prompt_row({"agent_code": agent_code, **AGENT_PROMPT_DEFINITION_MAP[agent_code]})
        for agent_code in AGENT_PROMPT_ORDER
    ]
    logs = [_serialize_agent_llm_call_log(item) for item in repo.list_recent_agent_llm_call_logs(limit=limit_logs)]
    return {
        "deepseek": _deepseek_settings_payload(),
        "prompts": prompts,
        "logs": logs,
    }


def save_model_infra_settings(payload: dict[str, Any]) -> dict[str, Any]:
    next_enabled = _normalize_bool(payload.get("enabled"))
    next_api_key = _normalized_text(payload.get("api_key"))
    if not next_api_key:
        next_api_key = _setting_text_value("DEEPSEEK_API_KEY")
    next_base_url = _normalized_text(payload.get("base_url")) or DEFAULT_DEEPSEEK_BASE_URL
    if next_base_url and not next_base_url.startswith(("http://", "https://")):
        raise ValueError("DEEPSEEK_BASE_URL must start with http:// or https://")
    next_router_model = _normalized_text(payload.get("router_model")) or DEFAULT_DEEPSEEK_ROUTER_MODEL
    next_execution_model = _normalized_text(payload.get("execution_model")) or DEFAULT_DEEPSEEK_EXECUTION_MODEL
    next_reasoner_model = _normalized_text(payload.get("reasoner_model")) or DEFAULT_DEEPSEEK_REASONER_MODEL
    try:
        next_timeout_seconds = max(1, int(payload.get("timeout_seconds") or DEFAULT_DEEPSEEK_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        raise ValueError("DEEPSEEK_TIMEOUT_SECONDS must be a positive integer") from None
    set_settings(
        {
            "DEEPSEEK_ENABLED": "true" if next_enabled else "false",
            "DEEPSEEK_API_KEY": next_api_key,
            "DEEPSEEK_BASE_URL": next_base_url,
            "DEEPSEEK_ROUTER_MODEL": next_router_model,
            "DEEPSEEK_EXECUTION_MODEL": next_execution_model,
            "DEEPSEEK_REASONER_MODEL": next_reasoner_model,
            "DEEPSEEK_TIMEOUT_SECONDS": str(next_timeout_seconds),
        }
    )
    return get_model_infra_payload()


def save_model_infra_prompt(*, agent_code: str, display_name: str, prompt_text: str, enabled: bool) -> dict[str, Any]:
    normalized_agent_code = _normalized_text(agent_code)
    if normalized_agent_code not in AGENT_PROMPT_DEFINITION_MAP:
        raise ValueError("invalid agent_code")
    next_display_name = _normalized_text(display_name) or _normalized_text(AGENT_PROMPT_DEFINITION_MAP[normalized_agent_code].get("display_name"))
    next_prompt_text = _normalized_text(prompt_text)
    if not next_prompt_text:
        raise ValueError("prompt_text is required")
    existing = repo.get_agent_prompt_row(normalized_agent_code)
    if existing:
        changed = (
            _normalized_text(existing.get("display_name")) != next_display_name
            or _normalized_text(existing.get("prompt_text")) != next_prompt_text
            or _normalize_bool(existing.get("enabled")) != bool(enabled)
        )
        next_version = int(existing.get("version") or 1) + (1 if changed else 0)
        saved = repo.update_agent_prompt_row(
            normalized_agent_code,
            {
                "display_name": next_display_name,
                "prompt_text": next_prompt_text,
                "enabled": bool(enabled),
                "version": next_version,
            },
        )
    else:
        saved = repo.insert_agent_prompt_row(
            {
                "agent_code": normalized_agent_code,
                "display_name": next_display_name,
                "prompt_text": next_prompt_text,
                "enabled": bool(enabled),
                "version": 1,
            }
        )
    if normalized_agent_code in CHILD_AGENT_CONFIG_MAP:
        from .orchestration_service import get_agent_config_detail, save_agent_config_draft

        current_config = get_agent_config_detail(normalized_agent_code)
        save_agent_config_draft(
            normalized_agent_code,
            {
                "display_name": next_display_name,
                "enabled": bool(enabled),
                "role_prompt": str(((current_config.get("draft") or {}).get("role_prompt")) or ""),
                "task_prompt": next_prompt_text,
                "variables": list(((current_config.get("draft") or {}).get("variables")) or []),
                "output_schema": list(((current_config.get("draft") or {}).get("output_schema")) or []),
                "change_summary": "从 legacy Prompt Registry 同步任务提示词",
            },
            operator_id="legacy_model_infra",
            source="legacy_prompt_registry",
        )
    get_db().commit()
    return _serialize_agent_prompt_row(saved)


def test_model_infra_connection() -> dict[str, Any]:
    try:
        result = test_deepseek_connection()
        return {
            "ok": True,
            "request_id": _normalized_text(result.get("request_id")),
            "model_name": _normalized_text(result.get("model_name")),
            "latency_ms": int(result.get("latency_ms") or 0),
            "parsed_output": result.get("parsed_output") if isinstance(result.get("parsed_output"), dict) else {},
        }
    except DeepSeekClientError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "deepseek": _deepseek_settings_payload(),
        }

