from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.operation_task_service import (
    activate_operation_task,
    copy_operation_task,
    create_operation_task,
    create_task_group,
    delete_operation_task,
    delete_task_group,
    get_operation_task,
    list_operation_tasks,
    list_task_groups,
    pause_operation_task,
    preview_operation_task_audience,
    run_due_operation_tasks,
    update_operation_task,
    update_task_group,
)
from ._routes_helpers import _operator_from_request, _query_int, _query_text, _request_program_id_or_default


def _task_program_id_from_request() -> int:
    return _query_int("program_id", default=0, minimum=0, maximum=100000000) or _request_program_id_or_default()


def api_admin_automation_conversion_task_groups():
    program_id = _task_program_id_from_request()
    if request.method == "GET":
        return jsonify({"ok": True, **list_task_groups(int(program_id))})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_task_group(int(program_id), payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_task_group_update(group_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_task_group(int(group_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_group_delete(group_id: int):
    try:
        result = delete_task_group(int(group_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_tasks():
    program_id = _task_program_id_from_request()
    if request.method == "GET":
        payload = list_operation_tasks(
            int(program_id),
            group_id=_query_int("group_id", default=0, minimum=0, maximum=100000000) or None,
            keyword=_query_text("keyword"),
            status=_query_text("status"),
        )
        return jsonify({"ok": True, **payload})
    payload = request.get_json(silent=True) or {}
    try:
        result = create_operation_task(int(program_id), payload, operator_id=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_task_detail(task_id: int):
    if request.method == "GET":
        try:
            return jsonify({"ok": True, **get_operation_task(int(task_id))})
        except LookupError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
    payload = request.get_json(silent=True) or {}
    try:
        result = update_operation_task(int(task_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_copy(task_id: int):
    try:
        result = copy_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_task_activate(task_id: int):
    try:
        result = activate_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_pause(task_id: int):
    try:
        result = pause_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_delete(task_id: int):
    try:
        result = delete_operation_task(int(task_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_task_preview_audience(task_id: int):
    payload = request.get_json(silent=True) or {}
    program_id = int(payload.get("program_id") or _task_program_id_from_request())
    try:
        if int(task_id or 0):
            task = get_operation_task(int(task_id))["task"]
            payload = {**task, **payload}
        result = preview_operation_task_audience(int(program_id), payload)
    except (LookupError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_tasks_run_due():
    payload = request.get_json(silent=True) or {}
    try:
        result = run_due_operation_tasks(
            program_id=int(payload.get("program_id") or 0) or (_query_int("program_id", default=0, minimum=0, maximum=100000000) or None),
            operator_id=str(payload.get("operator") or _operator_from_request() or "operation_task_runner").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})
