from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.operation_task_service import run_due_operation_tasks
from ._routes_helpers import _operator_from_request, _query_int


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
