from __future__ import annotations

import json
import time
import uuid
from typing import Any

import requests
from flask import current_app

from ....db import get_db
from ....infra.settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_EXECUTION_MODEL,
    DEFAULT_DEEPSEEK_ROUTER_MODEL,
    DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
    get_setting,
)
from .registry import CHILD_AGENT_CONFIG_MAP
from .. import repo


class DeepSeekClientError(RuntimeError):
    pass


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _setting_text(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _setting_bool(key: str, *, default: bool) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _setting_int(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def get_deepseek_runtime_config() -> dict[str, Any]:
    return {
        "enabled": _setting_bool("DEEPSEEK_ENABLED", default=False),
        "api_key": _setting_text("DEEPSEEK_API_KEY"),
        "base_url": _setting_text("DEEPSEEK_BASE_URL", default=DEFAULT_DEEPSEEK_BASE_URL) or DEFAULT_DEEPSEEK_BASE_URL,
        "router_model": _setting_text("DEEPSEEK_ROUTER_MODEL", default=DEFAULT_DEEPSEEK_ROUTER_MODEL) or DEFAULT_DEEPSEEK_ROUTER_MODEL,
        "execution_model": _setting_text("DEEPSEEK_EXECUTION_MODEL", default=DEFAULT_DEEPSEEK_EXECUTION_MODEL)
        or DEFAULT_DEEPSEEK_EXECUTION_MODEL,
        "timeout_seconds": _setting_int(
            "DEEPSEEK_TIMEOUT_SECONDS",
            default=DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
            minimum=1,
        ),
    }


def _selected_model(agent_code: str, *, explicit_model: str = "") -> str:
    normalized_explicit = _normalized_text(explicit_model)
    if normalized_explicit:
        return normalized_explicit
    config = get_deepseek_runtime_config()
    if _normalized_text(agent_code) == "central_router_agent":
        return _normalized_text(config["router_model"]) or DEFAULT_DEEPSEEK_ROUTER_MODEL
    return _normalized_text(config["execution_model"]) or DEFAULT_DEEPSEEK_EXECUTION_MODEL


def _request_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_normalized_text(api_key)}",
        "Content-Type": "application/json",
    }


def _uses_reply_output_types(agent_code: str) -> bool:
    return _normalized_text(agent_code) in CHILD_AGENT_CONFIG_MAP


def _log_call(
    *,
    agent_code: str,
    model_name: str,
    request_id: str,
    status: str,
    latency_ms: int,
    error_message: str = "",
) -> None:
    repo.insert_agent_llm_call_log(
        {
            "agent_code": _normalized_text(agent_code),
            "model_name": _normalized_text(model_name),
            "request_id": _normalized_text(request_id),
            "status": _normalized_text(status),
            "latency_ms": int(latency_ms),
            "error_message": _normalized_text(error_message),
        }
    )


def _agent_run_versions(agent_code: str) -> tuple[str, str]:
    config_row = repo.get_agent_config_row(agent_code)
    if config_row:
        deserialized = repo.deserialize_agent_config_row(config_row)
        role_version = f"published-v{int(deserialized.get('published_version') or 0)}"
        task_version = f"draft-v{int(deserialized.get('draft_version') or 1)}"
        return role_version, task_version
    prompt_row = repo.get_agent_prompt_row(agent_code)
    version = int((prompt_row or {}).get("version") or 1)
    return "", f"legacy-v{version}"


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


def call_deepseek_agent(
    *,
    agent_code: str,
    system_prompt: str,
    user_input: str,
    json_output: bool = False,
    model_name: str = "",
    request_id: str = "",
    run_id: str = "",
    userid: str = "",
    external_contact_id: str = "",
    input_snapshot: dict[str, Any] | None = None,
    variables_snapshot: dict[str, Any] | None = None,
    source: str = "llm_client",
) -> dict[str, Any]:
    request_id = _normalized_text(request_id) or uuid.uuid4().hex
    run_id = _normalized_text(run_id) or f"arun-{uuid.uuid4().hex}"
    started_at = time.perf_counter()
    config = get_deepseek_runtime_config()
    selected_model = _selected_model(agent_code, explicit_model=model_name)
    role_prompt_version, task_prompt_version = _agent_run_versions(agent_code)
    resolved_input_snapshot = (
        input_snapshot
        if isinstance(input_snapshot, dict)
        else {
            "system_prompt": _normalized_text(system_prompt),
            "user_input": _normalized_text(user_input),
            "json_output": bool(json_output),
            "model_name": selected_model,
        }
    )
    resolved_variables_snapshot = variables_snapshot if isinstance(variables_snapshot, dict) else {}
    final_prompt_preview = f"[system]\\n{_normalized_text(system_prompt)}\\n\\n[user]\\n{_normalized_text(user_input)}"
    repo.insert_agent_run(
        {
            "run_id": run_id,
            "request_id": request_id,
            "userid": _normalized_text(userid),
            "external_contact_id": _normalized_text(external_contact_id),
            "agent_code": _normalized_text(agent_code),
            "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
            "provider": "deepseek",
            "input_snapshot_json": resolved_input_snapshot,
            "variables_snapshot_json": resolved_variables_snapshot,
            "final_prompt_preview": final_prompt_preview,
            "role_prompt_version": role_prompt_version,
            "task_prompt_version": task_prompt_version,
            "status": "pending",
            "source": _normalized_text(source) or "llm_client",
        }
    )
    if not config["enabled"]:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=request_id,
            status="disabled",
            latency_ms=latency_ms,
            error_message="deepseek_disabled",
        )
        repo.update_agent_run(
            run_id,
            {
                "request_id": request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
                "provider": "deepseek",
                "input_snapshot_json": resolved_input_snapshot,
                "variables_snapshot_json": resolved_variables_snapshot,
                "final_prompt_preview": final_prompt_preview,
                "role_prompt_version": role_prompt_version,
                "task_prompt_version": task_prompt_version,
                "status": "disabled",
                "error_code": "deepseek_disabled",
                "error_message": "deepseek_disabled",
                "latency_ms": latency_ms,
                "source": _normalized_text(source) or "llm_client",
            },
        )
        repo.insert_agent_output(
            {
                "output_id": f"aout-{uuid.uuid4().hex}",
                "run_id": run_id,
                "request_id": request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "output_type": "error_output",
                "raw_output_text": "",
                "normalized_output_json": {"error": "deepseek_disabled"},
                "rendered_output_text": "deepseek_disabled",
                "error_code": "deepseek_disabled",
                "error_message": "deepseek_disabled",
                "applied_status": "not_applied",
            }
        )
        if _normalized_text(agent_code) == "central_router_agent":
            _touch_router_runtime_status(status="disabled", error_message="deepseek_disabled")
        get_db().commit()
        raise DeepSeekClientError("deepseek_disabled")
    if not _normalized_text(config["api_key"]):
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=request_id,
            status="not_configured",
            latency_ms=latency_ms,
            error_message="deepseek_api_key_not_configured",
        )
        repo.update_agent_run(
            run_id,
            {
                "request_id": request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
                "provider": "deepseek",
                "input_snapshot_json": resolved_input_snapshot,
                "variables_snapshot_json": resolved_variables_snapshot,
                "final_prompt_preview": final_prompt_preview,
                "role_prompt_version": role_prompt_version,
                "task_prompt_version": task_prompt_version,
                "status": "not_configured",
                "error_code": "deepseek_api_key_not_configured",
                "error_message": "deepseek_api_key_not_configured",
                "latency_ms": latency_ms,
                "source": _normalized_text(source) or "llm_client",
            },
        )
        repo.insert_agent_output(
            {
                "output_id": f"aout-{uuid.uuid4().hex}",
                "run_id": run_id,
                "request_id": request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "output_type": "error_output",
                "raw_output_text": "",
                "normalized_output_json": {"error": "deepseek_api_key_not_configured"},
                "rendered_output_text": "deepseek_api_key_not_configured",
                "error_code": "deepseek_api_key_not_configured",
                "error_message": "deepseek_api_key_not_configured",
                "applied_status": "not_applied",
            }
        )
        if _normalized_text(agent_code) == "central_router_agent":
            _touch_router_runtime_status(status="not_configured", error_message="deepseek_api_key_not_configured")
        get_db().commit()
        raise DeepSeekClientError("deepseek_api_key_not_configured")

    request_payload: dict[str, Any] = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": _normalized_text(system_prompt)},
            {"role": "user", "content": _normalized_text(user_input)},
        ],
        "stream": False,
    }
    if json_output:
        request_payload["response_format"] = {"type": "json_object"}

    from ....infra.http_client import OutboundHttpError, get_outbound_client

    llm_client = get_outbound_client(
        "deepseek_llm",
        timeout=float(config["timeout_seconds"]),
        retry_max=2,
    )
    try:
        try:
            response = llm_client.post(
                f"{_normalized_text(config['base_url']).rstrip('/')}/chat/completions",
                headers=_request_headers(_normalized_text(config["api_key"])),
                json=request_payload,
            )
        except OutboundHttpError as exc:
            # Preserve the original cause's message so existing error logs /
            # tests continue to assert against the upstream-provided text
            # rather than the wrapper's prefix.
            original_message = str(exc.cause) if exc.cause else str(exc)
            raise requests.RequestException(original_message) from exc
        latency_ms = int((time.perf_counter() - started_at) * 1000)
    except requests.RequestException as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=request_id,
            status="request_error",
            latency_ms=elapsed_ms,
            error_message=str(exc),
        )
        repo.update_agent_run(
            run_id,
            {
                "request_id": request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
                "provider": "deepseek",
                "input_snapshot_json": resolved_input_snapshot,
                "variables_snapshot_json": resolved_variables_snapshot,
                "final_prompt_preview": final_prompt_preview,
                "role_prompt_version": role_prompt_version,
                "task_prompt_version": task_prompt_version,
                "status": "request_error",
                "error_code": "request_error",
                "error_message": str(exc),
                "latency_ms": elapsed_ms,
                "source": _normalized_text(source) or "llm_client",
            },
        )
        repo.insert_agent_output(
            {
                "output_id": f"aout-{uuid.uuid4().hex}",
                "run_id": run_id,
                "request_id": request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "output_type": "error_output",
                "raw_output_text": "",
                "normalized_output_json": {"error": str(exc)},
                "rendered_output_text": str(exc),
                "error_code": "request_error",
                "error_message": str(exc),
                "applied_status": "not_applied",
            }
        )
        if _normalized_text(agent_code) == "central_router_agent":
            _touch_router_runtime_status(status="request_error", error_message=str(exc))
        get_db().commit()
        raise DeepSeekClientError(str(exc)) from exc

    response_request_id = _normalized_text(getattr(response, "headers", {}).get("x-request-id")) or request_id
    try:
        response_data = response.json()
    except ValueError as exc:
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=response_request_id,
            status="invalid_response",
            latency_ms=latency_ms,
            error_message="invalid_json_response",
        )
        repo.update_agent_run(
            run_id,
            {
                "request_id": response_request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
                "provider": "deepseek",
                "input_snapshot_json": resolved_input_snapshot,
                "variables_snapshot_json": resolved_variables_snapshot,
                "final_prompt_preview": final_prompt_preview,
                "role_prompt_version": role_prompt_version,
                "task_prompt_version": task_prompt_version,
                "status": "invalid_response",
                "error_code": "invalid_json_response",
                "error_message": "invalid_json_response",
                "latency_ms": latency_ms,
                "source": _normalized_text(source) or "llm_client",
            },
        )
        repo.insert_agent_output(
            {
                "output_id": f"aout-{uuid.uuid4().hex}",
                "run_id": run_id,
                "request_id": response_request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "output_type": "error_output",
                "raw_output_text": _normalized_text(response.text),
                "normalized_output_json": {"error": "invalid_json_response"},
                "rendered_output_text": "invalid_json_response",
                "error_code": "invalid_json_response",
                "error_message": "invalid_json_response",
                "applied_status": "not_applied",
            }
        )
        if _normalized_text(agent_code) == "central_router_agent":
            _touch_router_runtime_status(status="invalid_response", error_message="invalid_json_response")
        get_db().commit()
        raise DeepSeekClientError("invalid_json_response") from exc

    if int(response.status_code) >= 400:
        error_message = _normalized_text((response_data.get("error") or {}).get("message")) or _normalized_text(response.text)
        _log_call(
            agent_code=agent_code,
            model_name=selected_model,
            request_id=response_request_id,
            status="http_error",
            latency_ms=latency_ms,
            error_message=error_message or f"http_status_{int(response.status_code)}",
        )
        repo.update_agent_run(
            run_id,
            {
                "request_id": response_request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
                "provider": "deepseek",
                "input_snapshot_json": resolved_input_snapshot,
                "variables_snapshot_json": resolved_variables_snapshot,
                "final_prompt_preview": final_prompt_preview,
                "role_prompt_version": role_prompt_version,
                "task_prompt_version": task_prompt_version,
                "status": "http_error",
                "error_code": f"http_status_{int(response.status_code)}",
                "error_message": error_message or f"http_status_{int(response.status_code)}",
                "latency_ms": latency_ms,
                "source": _normalized_text(source) or "llm_client",
            },
        )
        repo.insert_agent_output(
            {
                "output_id": f"aout-{uuid.uuid4().hex}",
                "run_id": run_id,
                "request_id": response_request_id,
                "userid": _normalized_text(userid),
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": _normalized_text(agent_code),
                "output_type": "error_output",
                "raw_output_text": _normalized_text(response.text),
                "normalized_output_json": {"error": error_message or f"http_status_{int(response.status_code)}"},
                "rendered_output_text": error_message or f"http_status_{int(response.status_code)}",
                "error_code": f"http_status_{int(response.status_code)}",
                "error_message": error_message or f"http_status_{int(response.status_code)}",
                "applied_status": "not_applied",
            }
        )
        if _normalized_text(agent_code) == "central_router_agent":
            _touch_router_runtime_status(status="http_error", error_message=error_message or f"http_status_{int(response.status_code)}")
        get_db().commit()
        raise DeepSeekClientError(error_message or f"http_status_{int(response.status_code)}")

    message = dict(((response_data.get("choices") or [{}])[0].get("message") or {}))
    content = _normalized_text(message.get("content"))
    parsed_output: Any = None
    if json_output:
        try:
            parsed_output = json.loads(content or "{}")
        except ValueError as exc:
            _log_call(
                agent_code=agent_code,
                model_name=selected_model,
                request_id=response_request_id,
                status="parse_error",
                latency_ms=latency_ms,
                error_message="invalid_json_output",
            )
            repo.update_agent_run(
                run_id,
                {
                    "request_id": response_request_id,
                    "userid": _normalized_text(userid),
                    "external_contact_id": _normalized_text(external_contact_id),
                    "agent_code": _normalized_text(agent_code),
                    "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
                    "provider": "deepseek",
                    "input_snapshot_json": resolved_input_snapshot,
                    "variables_snapshot_json": resolved_variables_snapshot,
                    "final_prompt_preview": final_prompt_preview,
                    "role_prompt_version": role_prompt_version,
                    "task_prompt_version": task_prompt_version,
                    "status": "parse_error",
                    "error_code": "invalid_json_output",
                    "error_message": "invalid_json_output",
                    "latency_ms": latency_ms,
                    "source": _normalized_text(source) or "llm_client",
                },
            )
            repo.insert_agent_output(
                {
                    "output_id": f"aout-{uuid.uuid4().hex}",
                    "run_id": run_id,
                    "request_id": response_request_id,
                    "userid": _normalized_text(userid),
                    "external_contact_id": _normalized_text(external_contact_id),
                    "agent_code": _normalized_text(agent_code),
                    "output_type": "error_output",
                    "raw_output_text": content,
                    "normalized_output_json": {"error": "invalid_json_output"},
                    "rendered_output_text": "invalid_json_output",
                    "error_code": "invalid_json_output",
                    "error_message": "invalid_json_output",
                    "applied_status": "not_applied",
                }
            )
            if _normalized_text(agent_code) == "central_router_agent":
                _touch_router_runtime_status(status="parse_error", error_message="invalid_json_output")
            get_db().commit()
            raise DeepSeekClientError("invalid_json_output") from exc

    _log_call(
        agent_code=agent_code,
        model_name=selected_model,
        request_id=response_request_id,
        status="success",
        latency_ms=latency_ms,
    )
    output_type = "agent_reply_draft"
    target_agent_code = ""
    target_pool = ""
    confidence = 0
    reason = ""
    need_human_review = False
    if json_output and isinstance(parsed_output, dict):
        if _normalized_text(agent_code) == "central_router_agent":
            output_type = "route_decision"
            target_agent_code = _normalized_text(parsed_output.get("agent_code") or parsed_output.get("route"))
            target_pool = _normalized_text(parsed_output.get("target_pool"))
            confidence = float(parsed_output.get("confidence") or 0)
            reason = _normalized_text(parsed_output.get("reason"))
            need_human_review = bool(parsed_output.get("need_human_review"))
        else:
            draft_reply = _normalized_text(parsed_output.get("draft_reply") or parsed_output.get("draftText") or parsed_output.get("reply_draft"))
            final_reply = _normalized_text(parsed_output.get("reply_final") or parsed_output.get("final_reply"))
            explicit_output_type = _normalized_text(parsed_output.get("output_type"))
            if explicit_output_type in {"agent_reply_draft", "agent_reply_final"} and not _uses_reply_output_types(agent_code):
                output_type = "next_action_suggestion"
            elif explicit_output_type in {"agent_reply_draft", "agent_reply_final", "next_action_suggestion"}:
                output_type = explicit_output_type
            elif final_reply and _uses_reply_output_types(agent_code):
                output_type = "agent_reply_final"
            elif draft_reply and _uses_reply_output_types(agent_code):
                output_type = "agent_reply_draft"
            else:
                output_type = "next_action_suggestion"
            target_pool = _normalized_text(parsed_output.get("target_pool"))
            confidence = float(parsed_output.get("confidence") or 0)
            reason = _normalized_text(parsed_output.get("reason"))
            need_human_review = bool(parsed_output.get("need_human_review"))
    elif not json_output:
        output_type = "agent_reply_final"
    rendered_output_text = content
    if isinstance(parsed_output, dict) and output_type in {"agent_reply_draft", "agent_reply_final"}:
        rendered_output_text = (
            _normalized_text(parsed_output.get("reply_final") or parsed_output.get("final_reply"))
            if output_type == "agent_reply_final"
            else _normalized_text(parsed_output.get("draft_reply") or parsed_output.get("draftText") or parsed_output.get("reply_draft"))
        ) or content
    repo.update_agent_run(
        run_id,
        {
            "request_id": response_request_id,
            "userid": _normalized_text(userid),
            "external_contact_id": _normalized_text(external_contact_id),
            "agent_code": _normalized_text(agent_code),
            "agent_type": "router" if _normalized_text(agent_code) == "central_router_agent" else "child_agent",
            "provider": "deepseek",
            "input_snapshot_json": resolved_input_snapshot,
            "variables_snapshot_json": resolved_variables_snapshot,
            "final_prompt_preview": final_prompt_preview,
            "role_prompt_version": role_prompt_version,
            "task_prompt_version": task_prompt_version,
            "status": "success",
            "error_code": "",
            "error_message": "",
            "latency_ms": latency_ms,
            "source": _normalized_text(source) or "llm_client",
        },
    )
    repo.insert_agent_output(
        {
            "output_id": f"aout-{uuid.uuid4().hex}",
            "run_id": run_id,
            "request_id": response_request_id,
            "userid": _normalized_text(userid),
            "external_contact_id": _normalized_text(external_contact_id),
            "agent_code": _normalized_text(agent_code),
            "output_type": output_type,
            "raw_output_text": content,
            "normalized_output_json": parsed_output if isinstance(parsed_output, dict) else {},
            "rendered_output_text": rendered_output_text,
            "target_agent_code": target_agent_code,
            "target_pool": target_pool,
            "confidence": confidence,
            "reason": reason,
            "need_human_review": need_human_review,
            "applied_status": "generated",
        }
    )
    if _normalized_text(agent_code) == "central_router_agent":
        _touch_router_runtime_status(status="success", error_message="", last_called_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    get_db().commit()
    return {
        "ok": True,
        "run_id": run_id,
        "request_id": response_request_id,
        "model_name": selected_model,
        "content": content,
        "parsed_output": parsed_output,
        "latency_ms": latency_ms,
        "response_json": response_data,
    }


def test_deepseek_connection() -> dict[str, Any]:
    return call_deepseek_agent(
        agent_code="central_router_agent",
        system_prompt="You are a health check assistant. Return a JSON object with ok=true.",
        user_input='Please return {"ok": true, "message": "deepseek connected"}',
        json_output=True,
        model_name="",
    )
