from __future__ import annotations

from flask import jsonify

from ..domains.automation_conversion.workflow_service import (
    AutomationConversionDispatchError,
    send_conversion_execution_item_via_bazhuayu,
)
from ._routes_helpers import _operator_from_request
from .automation_conversion_compat import parent_patch
from .internal_auth import validate_admin_console_action_token as _validate_admin_console_action_token


def validate_admin_console_action_token():
    return parent_patch("validate_admin_console_action_token", _validate_admin_console_action_token)()


def api_admin_automation_conversion_execution_item_send_via_bazhuayu(execution_item_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        payload = send_conversion_execution_item_via_bazhuayu(
            int(execution_item_id),
            operator_id=_operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except AutomationConversionDispatchError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify(payload)
