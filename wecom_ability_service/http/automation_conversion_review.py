from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.laohuang_chat_service import (
    list_recent_laohuang_review_outputs,
    send_laohuang_review_output_via_webhook,
    send_laohuang_review_output_via_wecom,
)
from ..domains.automation_conversion.orchestration_service import (
    build_rejected_feedback_clipboard_payload,
    review_agent_reply_output,
)
from ..domains.automation_conversion.workflow_service import AutomationConversionDispatchError, send_agent_reply_output_via_bazhuayu
from ._routes_helpers import _operator_from_request, _query_int, _query_text
from .automation_conversion_compat import parent_patch
from .internal_auth import validate_admin_console_action_token as _validate_admin_console_action_token


def validate_admin_console_action_token():
    return parent_patch("validate_admin_console_action_token", _validate_admin_console_action_token)()


def api_admin_automation_conversion_review_outputs():
    payload = list_recent_laohuang_review_outputs(
        limit=_query_int("limit", default=20, minimum=1, maximum=50),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_review_output(output_id: str):
    payload = request.get_json(silent=True) or {}
    decision = _query_text("decision") or str(payload.get("decision") or "").strip()
    review_note = str(payload.get("review_note") or request.values.get("review_note") or "").strip()
    normalized_decision = decision.lower()
    is_rejected = normalized_decision in {"reject", "rejected", "not_adopted", "declined"}
    if is_rejected and not review_note:
        return jsonify({"ok": False, "error": "review_note is required when decision is rejected"}), 400
    try:
        reviewed_output = review_agent_reply_output(
            output_id,
            decision=decision,
            operator_id=_operator_from_request(),
            review_note=review_note,
            source="automation_conversion_auto_reply",
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    response_payload = {
        "ok": True,
        "reviewed_output": reviewed_output,
    }
    if is_rejected:
        response_payload["clipboard_text"] = build_rejected_feedback_clipboard_payload(
            output_id,
            not_adopted_reason=review_note,
        )
    return jsonify(response_payload)


def api_admin_automation_conversion_review_output_send_via_bazhuayu(output_id: str):
    return api_admin_automation_conversion_review_output_send_via_webhook(output_id)


def api_admin_automation_conversion_review_output_send_via_webhook(output_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        if str(output_id or "").strip().startswith("lhjob-") or str(output_id or "").strip().isdigit():
            payload = send_laohuang_review_output_via_webhook(
                output_id,
                operator_id=_operator_from_request(),
            )
        else:
            payload = send_agent_reply_output_via_bazhuayu(
                output_id,
                operator_id=_operator_from_request(),
            )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except AutomationConversionDispatchError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify(payload)


def api_admin_automation_conversion_review_output_send_via_wecom(output_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        payload = send_laohuang_review_output_via_wecom(
            output_id,
            operator_id=_operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload), 200 if payload.get("ok") else 502
