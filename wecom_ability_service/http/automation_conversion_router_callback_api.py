from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.orchestration_service import (
    list_router_pending_callbacks,
    replay_router_callback,
    run_router_pending_callback_check,
)
from ._routes_helpers import _operator_from_request, _query_int
from .internal_auth import require_internal_api_token


def api_admin_automation_conversion_router_pending_callbacks():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = list_router_pending_callbacks(
        older_than_minutes=_query_int("older_than_minutes", default=15, minimum=1, maximum=24 * 60),
        limit=_query_int("limit", default=20, minimum=1, maximum=100),
        visibility="full",
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_router_callback_replay(run_id: str):
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    try:
        payload = replay_router_callback(run_id, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_router_pending_callback_check():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_router_pending_callback_check(
        older_than_minutes=payload.get("older_than_minutes"),
        limit=int(payload.get("limit") or 100),
        operator_id=_operator_from_request(),
    )
    return jsonify(result)
