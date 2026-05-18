from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.laohuang_chat_service import handle_laohuang_chat_result_callback
from ..domains.automation_conversion.message_activity_service import run_message_activity_sync as _run_message_activity_sync
from ..domains.automation_conversion.orchestration_service import (
    handle_agent_router_callback,
    validate_router_callback_signature,
)
from ..domains.automation_conversion.reply_monitor_service import (
    run_due_reply_monitor as _run_due_reply_monitor,
    run_reply_monitor_capture as _run_reply_monitor_capture,
    run_router_test_dispatch as _run_router_test_dispatch,
)
from ..domains.automation_conversion.service import run_registered_due_jobs
from ._routes_helpers import _json_bool, _operator_from_request
from .automation_conversion_compat import parent_patch
from .internal_auth import require_internal_api_token


def run_message_activity_sync(*, operator_id: str, operator_type: str, trigger_source: str):
    return parent_patch("run_message_activity_sync", _run_message_activity_sync)(
        operator_id=operator_id,
        operator_type=operator_type,
        trigger_source=trigger_source,
    )


def run_reply_monitor_capture(*, operator_id: str, operator_type: str, limit: int | None = None):
    kwargs = {"operator_id": operator_id, "operator_type": operator_type}
    if limit is not None:
        kwargs["limit"] = limit
    return parent_patch("run_reply_monitor_capture", _run_reply_monitor_capture)(**kwargs)


def run_due_reply_monitor(*, operator_id: str, operator_type: str, limit: int | None = None):
    kwargs = {"operator_id": operator_id, "operator_type": operator_type}
    if limit is not None:
        kwargs["limit"] = limit
    return parent_patch("run_due_reply_monitor", _run_due_reply_monitor)(**kwargs)


def run_router_test_dispatch(**kwargs):
    return parent_patch("run_router_test_dispatch", _run_router_test_dispatch)(**kwargs)


def api_admin_automation_conversion_run_message_activity_sync():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="system",
        trigger_source=str(payload.get("trigger_source") or request.values.get("trigger_source") or "scheduled").strip() or "scheduled",
    )
    if result.get("ok"):
        status_code = 200
    elif result.get("status") == "not_configured":
        status_code = 400
    else:
        status_code = 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_capture():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 500),
    )
    status_code = 200 if result.get("ok") or result.get("status") == "disabled" else 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 20),
    )
    status_code = 200 if result.get("ok") or result.get("status") in {"disabled", "idle", "throttled", "quiet_hours"} else 502
    return jsonify(result), status_code


def api_internal_automation_conversion_lobster_results():
    auth_failure = require_internal_api_token(token_keys=("AUTOMATION_LOBSTER_CALLBACK_TOKEN",), require_configured=True)
    if auth_failure is not None:
        return auth_failure
    body_text = request.get_data(cache=True, as_text=True) or ""
    signature_ok, signature_error = validate_router_callback_signature(body_text=body_text, headers=dict(request.headers))
    if not signature_ok:
        return jsonify({"ok": False, "error": signature_error}), 401
    payload = request.get_json(silent=True) or {}
    result = handle_agent_router_callback(payload)
    if result.get("ok") and result.get("status") in {"applied", "idempotent"}:
        return jsonify(result), 200
    if result.get("status") == "rejected":
        status_code = 404 if result.get("error") == "request_not_found" else 409
        return jsonify(result), status_code
    return jsonify(result), 400


def api_internal_automation_conversion_laohuang_chat_results():
    payload = request.get_json(silent=True) or {}
    result = handle_laohuang_chat_result_callback(payload)
    if result.get("ok"):
        return jsonify(result), 200
    return jsonify(result), 400


def api_internal_automation_conversion_router_test_dispatch():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_router_test_dispatch(
        external_contact_id=str(payload.get("external_contact_id") or request.values.get("external_contact_id") or "").strip(),
        phone=str(payload.get("phone") or request.values.get("phone") or "").strip(),
        operator_id=str(payload.get("operator") or _operator_from_request() or "").strip(),
        mode=str(payload.get("mode") or request.values.get("mode") or "").strip(),
        force_capture=_json_bool(payload.get("force_capture")) or str(request.values.get("force_capture") or "").strip().lower() in {"1", "true", "yes", "on"},
        force_run_due=_json_bool(payload.get("force_run_due")) or str(request.values.get("force_run_due") or "").strip().lower() in {"1", "true", "yes", "on"},
    )
    status_code = 200 if result.get("ok") else (404 if result.get("error") == "member_not_found" else 409)
    return jsonify(result), status_code


def api_admin_automation_conversion_jobs_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    try:
        result = run_registered_due_jobs(
            job_codes=list(payload.get("jobs") or []),
            operator_id=_operator_from_request(),
            operator_type="system",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)
