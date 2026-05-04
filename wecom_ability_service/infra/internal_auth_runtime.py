from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from flask import current_app, jsonify, request

from .settings import get_setting


@dataclass(frozen=True, slots=True)
class InternalAuthFailure:
    error: str
    status_code: int


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def _configured_internal_tokens(
    *token_keys: str,
    config: Mapping[str, Any] | None = None,
) -> list[str]:
    config_values = config if config is not None else current_app.config
    tokens: list[str] = []
    seen: set[str] = set()
    for key in ("AUTOMATION_INTERNAL_API_TOKEN", *token_keys):
        normalized_key = _normalized_text(key)
        if not normalized_key:
            continue
        token = _normalized_text(get_setting(normalized_key)) or _normalized_text(config_values.get(normalized_key))
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _provided_internal_token(
    *,
    legacy_header_names: Iterable[str] = (),
    headers: Mapping[str, Any] | None = None,
) -> str:
    header_values = headers if headers is not None else request.headers
    auth_header = _normalized_text(header_values.get("Authorization"))
    if auth_header.startswith("Bearer "):
        return _normalized_text(auth_header[7:])
    for header_name in legacy_header_names:
        token = _normalized_text(header_values.get(_normalized_text(header_name)))
        if token:
            return token
    return ""


def get_internal_auth_failure(
    *,
    token_keys: tuple[str, ...] = (),
    legacy_header_names: tuple[str, ...] = (),
    require_configured: bool = False,
    headers: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> InternalAuthFailure | None:
    expected_tokens = _configured_internal_tokens(*token_keys, config=config)
    if not expected_tokens:
        if require_configured:
            return InternalAuthFailure(error="internal token not configured", status_code=503)
        return None
    provided_token = _provided_internal_token(
        legacy_header_names=legacy_header_names,
        headers=headers,
    )
    if not provided_token:
        return InternalAuthFailure(error="missing internal token", status_code=401)
    if provided_token not in expected_tokens:
        return InternalAuthFailure(error="invalid internal token", status_code=401)
    return None


def require_internal_api_token_compat(
    *,
    token_keys: tuple[str, ...] = (),
    legacy_header_names: tuple[str, ...] = (),
    require_configured: bool = False,
):
    """Legacy-compatible auth delegate used by Wave 1 application and HTTP glue."""

    failure = get_internal_auth_failure(
        token_keys=token_keys,
        legacy_header_names=legacy_header_names,
        require_configured=require_configured,
    )
    if failure is None:
        return None
    return jsonify({"ok": False, "error": failure.error}), failure.status_code


__all__ = [
    "InternalAuthFailure",
    "get_internal_auth_failure",
    "require_internal_api_token_compat",
]
