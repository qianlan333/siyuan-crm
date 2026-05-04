from __future__ import annotations

from flask import jsonify, request, url_for

from ..domains.admin_audit import build_admin_audit_payload
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_audit_logs():
    payload = build_admin_audit_payload(request.args)
    return _render_admin_template(
        "audit.html",
        active_nav="audit",
        page_title="操作记录",
        page_summary="这里可以查看谁在什么时间做了什么修改。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("操作记录", None)),
        audit_payload=payload,
    )


def api_admin_audit_logs():
    return jsonify({"ok": True, "audit": build_admin_audit_payload(request.args)})


def register_routes(bp):
    bp.route("/admin/audit", methods=["GET"])(admin_audit_logs)
    bp.route("/api/admin/audit/logs", methods=["GET"])(api_admin_audit_logs)
