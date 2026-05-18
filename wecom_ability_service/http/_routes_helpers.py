"""Request and routing helpers for automation conversion HTTP handlers.

Extracted from automation_conversion.py to keep handler file focused.
All helpers are private (underscore-prefixed) — explicit re-export
via __all__ so callers can `from ._routes_helpers import (a, b, ...)`.
"""

from __future__ import annotations

from flask import abort, redirect, request, url_for

from ..domains.automation_conversion.program_service import get_automation_program, get_default_automation_program_id


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_int(name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    try:
        value = int(request.args.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _query_bool(name: str, *, default: bool = False) -> bool:
    raw_value = request.args.get(name)
    if raw_value is None:
        return bool(default)
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or "crm_console"
    )


def _coerce_program_id(program_id: object) -> int | None:
    try:
        normalized_program_id = int(program_id or 0)
    except (TypeError, ValueError):
        return None
    return normalized_program_id if normalized_program_id > 0 else None


def _request_program_id() -> int | None:
    return _coerce_program_id(request.values.get("program_id"))


def _request_program_id_or_default() -> int | None:
    return _request_program_id() or _default_program_id_or_none()


def _payload_program_id(payload: dict[str, object] | None = None) -> int | None:
    return _request_program_id() or _coerce_program_id((payload or {}).get("program_id")) or _default_program_id_or_none()


def _default_program_id_or_none() -> int | None:
    try:
        return _coerce_program_id(get_default_automation_program_id())
    except Exception:
        return None


def _program_route_or_main(endpoint: str, *, program_id: int | None = None, **params) -> str:
    normalized_program_id = _coerce_program_id(program_id) or _default_program_id_or_none()
    if not normalized_program_id:
        return url_for("api.admin_automation_conversion")
    compact_params = {key: value for key, value in params.items() if value is not None and value != ""}
    return url_for(endpoint, program_id=normalized_program_id, **compact_params)


def _redirect_to_program(endpoint: str, *, program_id: int | None = None, **params):
    return redirect(_program_route_or_main(endpoint, program_id=program_id, **params), code=302)


def _program_route(endpoint: str, program_id: int, **params) -> str:
    return url_for(endpoint, program_id=int(program_id), **params)


def _program_api_params(program_id: int | None = None) -> dict[str, int]:
    normalized_program_id = int(program_id or 0)
    return {"program_id": normalized_program_id} if normalized_program_id > 0 else {}


def _load_program_or_404(program_id: int) -> dict[str, object]:
    try:
        return get_automation_program(int(program_id))
    except LookupError:
        abort(404)


def _wants_json_response() -> bool:
    accept = str(request.headers.get("Accept") or "").lower()
    requested_with = str(request.headers.get("X-Requested-With") or "").strip()
    return "application/json" in accept or requested_with == "XMLHttpRequest"


def _json_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "_coerce_program_id",
    "_default_program_id_or_none",
    "_json_bool",
    "_load_program_or_404",
    "_operator_from_request",
    "_payload_program_id",
    "_program_api_params",
    "_program_route",
    "_program_route_or_main",
    "_query_bool",
    "_query_int",
    "_query_text",
    "_redirect_to_program",
    "_request_program_id",
    "_request_program_id_or_default",
    "_wants_json_response",
]
