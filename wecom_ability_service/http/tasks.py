from __future__ import annotations

from flask import jsonify, request

from ..domains.tasks.service import dispatch_wecom_task
from ..wecom_client import WeComClientError


def _handle_wecom_task(task_type: str, fn_name: str):
    payload = request.get_json(silent=True) or {}
    try:
        result = dispatch_wecom_task(task_type, fn_name, payload)
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except (WeComClientError, AttributeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


def create_private_message_task():
    return _handle_wecom_task("private_message", "create_private_message_task")


def create_moment_task():
    return _handle_wecom_task("moment", "create_moment_task")


def create_group_message_task():
    return _handle_wecom_task("group_message", "create_group_message_task")



def register_routes(bp):
    bp.route('/api/tasks/private-message', methods=['POST'])(create_private_message_task)
    bp.route('/api/tasks/moment', methods=['POST'])(create_moment_task)
    bp.route('/api/tasks/group-message', methods=['POST'])(create_group_message_task)
