from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.workflow_service import (
    AutomationConversionDispatchError,
    activate_conversion_workflow,
    create_conversion_workflow,
    create_conversion_workflow_node,
    delete_conversion_workflow,
    delete_conversion_workflow_node,
    get_conversion_dashboard_payload,
    get_conversion_workflow_detail_summary,
    get_conversion_workflow_execution_detail,
    get_conversion_workflow_execution_item_detail,
    get_conversion_workflow_model_bundle,
    list_conversion_workflow_execution_items,
    list_conversion_workflow_execution_records,
    list_conversion_workflow_nodes,
    list_conversion_workflow_registry,
    list_conversion_workflows,
    pause_conversion_workflow,
    send_conversion_execution_item_via_bazhuayu,
    update_conversion_workflow,
    update_conversion_workflow_node,
)
from ._routes_helpers import _operator_from_request, _query_bool, _query_int, _query_text
from .automation_conversion_compat import parent_patch
from .internal_auth import validate_admin_console_action_token as _validate_admin_console_action_token


def validate_admin_console_action_token():
    return parent_patch("validate_admin_console_action_token", _validate_admin_console_action_token)()


def api_admin_automation_conversion_workflow_registry():
    return jsonify({"ok": True, **list_conversion_workflow_registry()})


def api_admin_automation_conversion_workflows():
    payload = list_conversion_workflows(
        include_archived=_query_bool("include_archived", default=False),
        status=_query_text("status"),
        program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_workflow_detail(workflow_id: int):
    try:
        payload = get_conversion_workflow_model_bundle(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "workflow_bundle": payload})


def api_admin_automation_conversion_dashboard():
    return jsonify(
        {
            "ok": True,
            "dashboard": get_conversion_dashboard_payload(
                program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
            ),
        }
    )


def api_admin_automation_conversion_workflow_summary(workflow_id: int):
    try:
        payload = get_conversion_workflow_detail_summary(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "summary": payload})


def api_admin_automation_conversion_workflow_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_workflow(
            payload,
            operator_id=_operator_from_request(),
            program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_workflow_update(workflow_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_workflow(int(workflow_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_activate(workflow_id: int):
    try:
        result = activate_conversion_workflow(int(workflow_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_pause(workflow_id: int):
    try:
        result = pause_conversion_workflow(int(workflow_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_delete(workflow_id: int):
    try:
        result = delete_conversion_workflow(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_node_list(workflow_id: int):
    try:
        payload = list_conversion_workflow_nodes(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_workflow_node_create(workflow_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_workflow_node(int(workflow_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_workflow_node_update(node_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_workflow_node(int(node_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_node_delete(node_id: int):
    try:
        result = delete_conversion_workflow_node(int(node_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_execution_batches():
    try:
        payload = list_conversion_workflow_execution_records(
            workflow_id=_query_int("workflow_id", default=0, minimum=0, maximum=100000000) or None,
            node_id=_query_int("node_id", default=0, minimum=0, maximum=100000000) or None,
            program_id=_query_int("program_id", default=0, minimum=0, maximum=100000000) or None,
            limit=_query_int("limit", default=20, minimum=1, maximum=100),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_detail(execution_id: int):
    try:
        payload = get_conversion_workflow_execution_detail(int(execution_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_items(execution_id: int):
    try:
        payload = list_conversion_workflow_execution_items(int(execution_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_item_detail(execution_item_id: int):
    try:
        payload = get_conversion_workflow_execution_item_detail(int(execution_item_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


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
