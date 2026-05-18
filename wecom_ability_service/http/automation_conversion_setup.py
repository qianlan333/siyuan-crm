from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.program_setup_service import (
    build_publish_check,
    create_program_customer_acquisition_link,
    get_program_setup_payload,
    publish_entry,
    publish_full,
    save_audience_entry_rule,
    save_entry_channel,
    save_segmentation,
    save_setup_basic,
)
from ._routes_helpers import _operator_from_request, _query_text


def api_admin_automation_program_setup(program_id: int):
    try:
        payload = get_program_setup_payload(int(program_id), step=_query_text("step") or "basic")
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "setup": payload})


def api_admin_automation_program_setup_basic(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_setup_basic(int(program_id), payload, operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_entry_channel(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_entry_channel(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_segmentation(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_segmentation(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_audience_entry_rule(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_audience_entry_rule(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_setup_publish_check(program_id: int):
    try:
        result = build_publish_check(int(program_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "publish_check": result})


def api_admin_automation_program_publish_entry(program_id: int):
    try:
        result = publish_entry(int(program_id), operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_publish_full(program_id: int):
    try:
        result = publish_full(int(program_id), operator_id=_operator_from_request())
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_program_customer_acquisition_links(program_id: int):
    if request.method == "GET":
        from ..domains.automation_conversion.customer_acquisition_service import list_customer_acquisition_links

        status = str(request.args.get("status") or "").strip()
        return jsonify({"ok": True, "links": list_customer_acquisition_links(status=status, program_id=int(program_id))})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_program_customer_acquisition_link(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **result}), 201
