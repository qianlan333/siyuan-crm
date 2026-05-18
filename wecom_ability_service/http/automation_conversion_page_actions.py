from __future__ import annotations

from flask import current_app, jsonify, redirect, request, url_for

from ..domains.automation_conversion.channel_service import generate_default_channel_qr as _generate_default_channel_qr
from ..domains.automation_conversion.focus_send_service import create_focus_send_batch
from ..domains.automation_conversion.manual_send_service import send_stage_manual_message
from ..domains.automation_conversion.message_activity_service import run_message_activity_sync as _run_message_activity_sync
from ..domains.automation_conversion.service import (
    get_overview_payload,
    save_settings as _save_settings,
)
from ..domains.automation_conversion.workflow_service import apply_dashboard_signup_tag as _apply_dashboard_signup_tag
from ._routes_helpers import (
    _load_program_or_404,
    _operator_from_request,
    _program_route,
    _program_route_or_main,
    _redirect_to_program,
    _request_program_id_or_default,
    _wants_json_response,
)
from .automation_conversion_compat import parent_patch
from .automation_conversion_render import (
    _render_flow_design_page,
    _render_member_ops_page,
    _render_overview_page,
)
from .automation_conversion_uploads import _stage_send_images_from_request
from .internal_auth import validate_admin_console_action_token as _validate_admin_console_action_token


def validate_admin_console_action_token():
    return parent_patch("validate_admin_console_action_token", _validate_admin_console_action_token)()


def save_settings(payload, *, program_id=None):
    return parent_patch("save_settings", _save_settings)(payload, program_id=program_id)


def generate_default_channel_qr(*, operator: str, program_id=None):
    return parent_patch("generate_default_channel_qr", _generate_default_channel_qr)(
        operator=operator,
        program_id=program_id,
    )


def run_message_activity_sync(*, operator_id: str, operator_type: str, trigger_source: str):
    return parent_patch("run_message_activity_sync", _run_message_activity_sync)(
        operator_id=operator_id,
        operator_type=operator_type,
        trigger_source=trigger_source,
    )


def apply_dashboard_signup_tag(*, operator_id: str):
    return parent_patch("apply_dashboard_signup_tag", _apply_dashboard_signup_tag)(operator_id=operator_id)


def admin_automation_conversion_save_settings():
    section = str(request.form.get("section") or "questionnaire").strip() or "questionnaire"
    program_id = _request_program_id_or_default()
    action_token_error = validate_admin_console_action_token()
    page_input = dict(request.form or {})
    if action_token_error:
        return _render_flow_design_page(page_error=action_token_error, page_input=page_input)
    try:
        save_settings(dict(request.form or {}), program_id=program_id)
    except ValueError as exc:
        return _render_flow_design_page(page_error=str(exc), page_input=page_input)
    return redirect(
        _program_route_or_main(
            "api.admin_automation_program_flow_design",
            program_id=program_id,
            section=section,
            pool=str(request.values.get("pool") or "").strip() or None,
            day=str(request.values.get("day") or "").strip() or None,
            saved=1,
        ),
        code=302,
    )


def admin_automation_conversion_generate_default_channel():
    program_id = _request_program_id_or_default()
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_flow_design_page(page_error=action_token_error, page_input=dict(request.form or {}))
    result = generate_default_channel_qr(operator=_operator_from_request(), program_id=program_id)
    if not result.get("generated"):
        return _render_flow_design_page(
            page_error=str(result.get("error") or "二维码生成失败"),
            page_input=dict(request.form or {}),
        )
    return redirect(
        _program_route_or_main(
            "api.admin_automation_program_flow_design",
            program_id=program_id,
            section="channel",
            pool=str(request.values.get("pool") or "").strip() or None,
            day=str(request.values.get("day") or "").strip() or None,
            saved=1,
        ),
        code=302,
    )


def _stage_send_member_ops_params(stage_key: str, **notice_params) -> dict[str, object]:
    params: dict[str, object] = {
        "stage": str(stage_key or "").strip(),
        "panel": "send",
    }
    for key in ("keyword", "external_contact_id", "member", "phone"):
        value = str(request.values.get(key) or "").strip()
        if value:
            params[key] = value
    params.update({key: value for key, value in notice_params.items() if value is not None and value != ""})
    return params


def _handle_stage_send_post(stage_key: str, *, program: dict[str, object]):
    program_id = int(program.get("id") or 0)
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_member_ops_page(page_error=action_token_error, program=program)
    try:
        images = _stage_send_images_from_request()
        route_key = str(stage_key or "").strip()
        if route_key in {"inactive-focus", "active-focus"}:
            result = create_focus_send_batch(
                route_key=route_key,
                operator_id=_operator_from_request(),
                operator_type="user",
            )
            redirect_url = _program_route(
                "api.admin_automation_program_member_ops",
                program_id=program_id,
                **_stage_send_member_ops_params(
                    route_key,
                    focus_batch_notice="created",
                    focus_batch_id=int((result.get("batch") or {}).get("id") or 0),
                ),
            )
            if _wants_json_response():
                return jsonify({"ok": True, "redirect_url": redirect_url, "result": result})
            return redirect(redirect_url, code=302)
        result = send_stage_manual_message(
            route_key=route_key,
            content=str(request.form.get("content") or "").strip(),
            images=images,
            operator_id=_operator_from_request(),
        )
        redirect_url = _program_route(
            "api.admin_automation_program_member_ops",
            program_id=program_id,
            **_stage_send_member_ops_params(
                route_key,
                manual_send_notice="sent",
                record_id=int(result.get("record_id") or 0),
            ),
        )
        if _wants_json_response():
            return jsonify({"ok": True, "redirect_url": redirect_url, "result": result})
        return redirect(redirect_url, code=302)
    except ValueError as exc:
        if _wants_json_response():
            return jsonify({"ok": False, "error": str(exc)}), 400
        return _render_member_ops_page(page_error=str(exc), program=program)
    except Exception as exc:
        current_app.logger.exception("stage send failed: stage_key=%s program_id=%s", stage_key, program_id)
        error_message = f"发送任务异常: {type(exc).__name__}: {exc}"
        if _wants_json_response():
            return jsonify({"ok": False, "error": error_message}), 500
        return _render_member_ops_page(page_error=error_message, program=program)


def admin_automation_program_member_ops_stage_send(program_id: int, stage_key: str):
    program = _load_program_or_404(program_id)
    return _handle_stage_send_post(stage_key, program=program)


def admin_automation_program_overview_message_activity_sync_run(program_id: int):
    _load_program_or_404(program_id)
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="user",
        trigger_source="manual",
    )
    if _wants_json_response():
        overview_payload = get_overview_payload()
        message_activity_sync = dict(overview_payload.get("message_activity_sync") or {})
        status_code = 200 if result.get("ok") else 400
        return (
            jsonify(
                {
                    "ok": bool(result.get("ok")),
                    "message": "消息活跃同步已完成" if result.get("ok") else str(result.get("error") or "消息活跃同步失败"),
                    "run": result.get("run") or {},
                    "message_activity_sync": message_activity_sync,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            _program_route_or_main("api.admin_automation_program_overview", program_id=program_id, message_activity_sync=1),
            code=302,
        )
    return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)


def admin_automation_program_overview_signup_tag_apply(program_id: int):
    _load_program_or_404(program_id)
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    try:
        result = apply_dashboard_signup_tag(operator_id=_operator_from_request())
    except ValueError as exc:
        if _wants_json_response():
            return jsonify({"ok": False, "error": str(exc)}), 400
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    status_code = 200 if result.get("ok") else 502
    if _wants_json_response():
        return jsonify(result), status_code
    if result.get("ok"):
        return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    return _redirect_to_program("api.admin_automation_program_overview", program_id=program_id)
    if result.get("status") == "not_configured":
        missing_keys = "、".join(result.get("missing_keys") or [])
        return _render_overview_page(page_error=f"消息库尚未配置，请先补齐 {missing_keys}")
    return _render_overview_page(page_error=str(result.get("error") or "消息活跃同步失败"))
