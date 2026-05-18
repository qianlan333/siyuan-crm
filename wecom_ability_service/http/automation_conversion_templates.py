from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.action_template_service import (
    create_action_from_template,
    create_action_template,
    create_action_template_from_workflow,
    generate_action_template,
    list_action_templates,
)
from ..domains.automation_conversion.workflow_service import (
    create_conversion_profile_segment_template,
    get_conversion_profile_segment_template_bundle,
    list_conversion_profile_segment_catalog,
    list_conversion_profile_segment_template_options,
    list_conversion_profile_segment_templates,
    update_conversion_profile_segment_template,
)
from ._routes_helpers import _operator_from_request, _payload_program_id, _query_bool, _query_text, _request_program_id


def api_admin_automation_conversion_profile_segment_catalog():
    return jsonify({"ok": True, **list_conversion_profile_segment_catalog()})


def api_admin_automation_conversion_profile_segment_templates():
    payload = list_conversion_profile_segment_templates(
        enabled_only=_query_bool("enabled_only", default=False),
        program_id=_request_program_id(),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_profile_segment_template_detail(template_id: int):
    try:
        payload = get_conversion_profile_segment_template_bundle(int(template_id))
        program_id = _request_program_id()
        template_program_id = int(((payload.get("template") or {}).get("program_id")) or 0) or None
        if program_id and template_program_id != int(program_id):
            raise LookupError("profile segment template not found")
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "template_bundle": payload, **payload})


def api_admin_automation_conversion_profile_segment_template_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_profile_segment_template(
            payload,
            operator_id=_operator_from_request(),
            program_id=_payload_program_id(payload),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_profile_segment_template_update(template_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_profile_segment_template(
            int(template_id),
            payload,
            operator_id=_operator_from_request(),
            program_id=_payload_program_id(payload),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_profile_segment_template_options():
    return jsonify(
        {
            "ok": True,
            **list_conversion_profile_segment_template_options(
                enabled_only=_query_bool("enabled_only", default=True),
                program_id=_request_program_id(),
            ),
        }
    )


def api_admin_automation_conversion_action_templates():
    if request.method == "GET":
        try:
            payload = list_action_templates(
                template_source=_query_text("source") or _query_text("template_source"),
                category=_query_text("category"),
                keyword=_query_text("keyword"),
                include_archived=_query_bool("include_archived", default=False),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, **payload})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_action_template(payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_action_template_generate():
    payload = request.get_json(silent=True) or {}
    try:
        result = generate_action_template(payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_action_template_from_workflow():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_action_template_from_workflow(payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_program_action_from_template(program_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_action_from_template(int(program_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201
