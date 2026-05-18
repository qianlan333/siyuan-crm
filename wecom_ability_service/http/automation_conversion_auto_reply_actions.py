from __future__ import annotations

from flask import jsonify, redirect, request, url_for

from ..domains.automation_conversion.reply_monitor_service import (
    run_due_reply_monitor as _run_due_reply_monitor,
    run_reply_monitor_capture as _run_reply_monitor_capture,
    save_reply_monitor_enabled as _save_reply_monitor_enabled,
)
from ._routes_helpers import _json_bool, _operator_from_request, _wants_json_response
from .automation_conversion_compat import parent_patch
from .automation_conversion_render import _render_auto_reply_page
from .internal_auth import validate_admin_console_action_token as _validate_admin_console_action_token


def validate_admin_console_action_token():
    return parent_patch("validate_admin_console_action_token", _validate_admin_console_action_token)()


def save_reply_monitor_enabled(*, enabled: bool, operator_id: str):
    return parent_patch("save_reply_monitor_enabled", _save_reply_monitor_enabled)(
        enabled=enabled,
        operator_id=operator_id,
    )


def run_reply_monitor_capture(*, operator_id: str, operator_type: str):
    return parent_patch("run_reply_monitor_capture", _run_reply_monitor_capture)(
        operator_id=operator_id,
        operator_type=operator_type,
    )


def run_due_reply_monitor(*, operator_id: str, operator_type: str):
    return parent_patch("run_due_reply_monitor", _run_due_reply_monitor)(
        operator_id=operator_id,
        operator_type=operator_type,
    )


def admin_automation_auto_reply_monitor_toggle():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    enabled = _json_bool(request.form.get("enabled") or request.values.get("enabled"))
    try:
        save_reply_monitor_enabled(enabled=enabled, operator_id=_operator_from_request())
    except ValueError as exc:
        if _wants_json_response():
            return jsonify({"ok": False, "error": str(exc)}), 400
        return _render_auto_reply_page(page_error=str(exc))
    status = "enabled" if enabled else "disabled"
    if _wants_json_response():
        return jsonify({"ok": True, "status": status, "message": "自动接话已开启" if enabled else "自动接话已关闭"})
    return redirect(
        url_for(
            "api.admin_automation_conversion_auto_reply",
            reply_monitor=status,
        ),
        code=302,
    )


def admin_automation_auto_reply_monitor_capture():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if _wants_json_response():
        status = str(result.get("status") or "").strip()
        ok = bool(result.get("ok")) or status in {"disabled", "idle", "throttled", "quiet_hours"}
        status_code = 200 if ok else 400
        return (
            jsonify(
                {
                    "ok": ok,
                    "status": status,
                    "message": str(result.get("message") or result.get("error") or "自动接话扫描已完成"),
                    "result": result,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_auto_reply", reply_monitor="captured"),
            code=302,
        )
    return _render_auto_reply_page(page_error=str(result.get("error") or "自动接话监控扫描失败"))


def admin_automation_auto_reply_monitor_run_due():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if _wants_json_response():
        status = str(result.get("status") or "").strip()
        ok = bool(result.get("ok")) or status in {"disabled", "idle", "throttled", "quiet_hours"}
        status_code = 200 if ok else 400
        return (
            jsonify(
                {
                    "ok": ok,
                    "status": status,
                    "message": str(result.get("message") or result.get("error") or "自动接话放行已完成"),
                    "result": result,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_auto_reply", reply_monitor="dispatched"),
            code=302,
        )
    return _render_auto_reply_page(page_error=str(result.get("error") or "自动接话监控放行失败"))
