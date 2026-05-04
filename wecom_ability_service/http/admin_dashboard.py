from __future__ import annotations

from flask import jsonify

from ..domains.admin_dashboard import (
    build_admin_shell_status,
    build_dashboard_cards,
    build_dashboard_summary,
    build_dashboard_todos,
    build_system_status_payload,
)


def admin_dashboard_shell_context():
    return jsonify(
        {
            "ok": True,
            "shell_status": build_admin_shell_status(),
            "dashboard_cards": build_dashboard_cards(),
        }
    )


def admin_dashboard_system_status():
    return jsonify(
        {
            "ok": True,
            "system_status": build_system_status_payload(),
        }
    )


def admin_dashboard_summary():
    return jsonify(
        {
            "ok": True,
            "summary": build_dashboard_summary(),
        }
    )


def admin_dashboard_todos():
    return jsonify(
        {
            "ok": True,
            "todos": build_dashboard_todos(),
        }
    )


def register_routes(bp):
    bp.route("/api/admin/dashboard/shell-context", methods=["GET"])(admin_dashboard_shell_context)
    bp.route("/api/admin/dashboard/system-status", methods=["GET"])(admin_dashboard_system_status)
    bp.route("/api/admin/dashboard/summary", methods=["GET"])(admin_dashboard_summary)
    bp.route("/api/admin/dashboard/todos", methods=["GET"])(admin_dashboard_todos)
