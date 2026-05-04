from __future__ import annotations

from flask import Response, jsonify, request

from ..application.class_user.commands import MigrateClassUserStatusFromContactTagsCommand
from ..application.class_user.dto import (
    ExportClassUserManagementRecordsQueryDTO,
    ListClassUserManagementRecordsQueryDTO,
    ListClassUserStatusHistoryQueryDTO,
)
from ..application.class_user.queries import (
    ExportClassUserManagementRecordsQuery,
    ListClassUserManagementRecordsQuery,
    ListClassUserStatusHistoryQuery,
)
from ..wecom_client import WeComClientError
from .admin_support import _configured_signup_tag_rules_payload, _signup_tag_bootstrap_payload
from .common import _build_excel_xml, _deprecated_admin_redirect, _wecom_error_response


def admin_class_user_management_bootstrap():
    try:
        payload = _signup_tag_bootstrap_payload()
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **payload})


def admin_class_user_management_migrate():
    payload = MigrateClassUserStatusFromContactTagsCommand()()
    return jsonify({"ok": True, **payload})


def admin_class_user_management_list():
    signup_status = request.args.get("signup_status", "").strip()
    try:
        payload = ListClassUserManagementRecordsQuery()(
            ListClassUserManagementRecordsQueryDTO(signup_status=str(signup_status or "").strip())
        )
        payload["tag_initialization"] = _configured_signup_tag_rules_payload()
        payload["live_refresh"] = {}
        return jsonify({"ok": True, **payload})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def admin_class_user_management_export():
    configured = _configured_signup_tag_rules_payload()
    if not configured.get("initialized"):
        return jsonify({"ok": False, "error": "signup tags are not initialized"}), 400
    signup_status = request.args.get("signup_status", "").strip()
    try:
        export_payload = ExportClassUserManagementRecordsQuery()(
            ExportClassUserManagementRecordsQueryDTO(signup_status=str(signup_status or "").strip())
        )
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    return Response(
        content,
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename={export_payload['filename']}"},
    )


def admin_class_user_management_history():
    try:
        limit = int(request.args.get("limit", "100").strip() or "100")
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = ListClassUserStatusHistoryQuery()(ListClassUserStatusHistoryQueryDTO(limit=int(limit)))
    return jsonify({"ok": True, **payload})


def admin_class_user_management_ui():
    return _deprecated_admin_redirect("api.admin_console_class_users", replacement="/admin/class-users?tab=class-users")


def admin_class_user_backoffice_ui():
    return _deprecated_admin_redirect("api.admin_console_class_users", replacement="/admin/class-users?tab=class-users")



def register_routes(bp):
    bp.route('/api/admin/class-user-management/bootstrap', methods=['POST'])(admin_class_user_management_bootstrap)
    bp.route('/api/admin/class-user-management/migrate', methods=['POST'])(admin_class_user_management_migrate)
    bp.route('/api/admin/class-user-management', methods=['GET'])(admin_class_user_management_list)
    bp.route('/api/admin/class-user-management/export', methods=['GET'])(admin_class_user_management_export)
    bp.route('/api/admin/class-user-management/history', methods=['GET'])(admin_class_user_management_history)
    bp.route('/admin/class-user-management/ui', methods=['GET'])(admin_class_user_management_ui)
    bp.route('/admin/class-user-backoffice/ui', methods=['GET'])(admin_class_user_backoffice_ui)
