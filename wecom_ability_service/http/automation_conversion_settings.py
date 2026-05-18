from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.channel_service import (
    generate_default_channel_qr as _generate_default_channel_qr,
    get_default_channel_settings_payload,
    save_default_channel_settings,
)
from ..domains.automation_conversion.model_infra_service import (
    get_model_infra_payload,
    save_model_infra_settings,
    test_model_infra_connection,
)
from ..domains.automation_conversion.service import get_settings_payload, save_settings as _save_settings
from ._routes_helpers import _operator_from_request, _payload_program_id, _request_program_id_or_default
from .automation_conversion_compat import parent_patch
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


def api_admin_automation_conversion_default_channel_settings():
    return jsonify({"ok": True, **get_default_channel_settings_payload(program_id=_request_program_id_or_default())})


def api_admin_automation_conversion_settings_payload():
    return jsonify({"ok": True, "settings": get_settings_payload(program_id=_request_program_id_or_default())})


def api_admin_automation_conversion_settings_save():
    payload = request.get_json(silent=True) or {}
    try:
        result = save_settings(payload, program_id=_payload_program_id(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "settings": result})


def api_admin_automation_conversion_default_channel_settings_save():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = save_default_channel_settings(payload, program_id=_payload_program_id(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_default_channel_generate_qr():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    result = generate_default_channel_qr(operator=_operator_from_request(), program_id=_payload_program_id(payload))
    status_code = int(result.get("status_code") or (200 if result.get("generated") else 400))
    return jsonify({"ok": bool(result.get("generated")), **result}), status_code


def api_admin_automation_conversion_settings_default_channel_generate_qr():
    payload = request.get_json(silent=True) or {}
    result = generate_default_channel_qr(operator=_operator_from_request(), program_id=_payload_program_id(payload))
    status_code = int(result.get("status_code") or (200 if result.get("generated") else 400))
    return jsonify({"ok": bool(result.get("generated")), **result}), status_code


def api_admin_automation_conversion_model_settings():
    return jsonify({"ok": True, **get_model_infra_payload(limit_logs=10)})


def api_admin_automation_conversion_model_settings_save():
    payload = request.get_json(silent=True) or {}
    try:
        result = save_model_infra_settings(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "model_infra": result, **result})


def api_admin_automation_conversion_model_settings_test():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    result = test_model_infra_connection()
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code
