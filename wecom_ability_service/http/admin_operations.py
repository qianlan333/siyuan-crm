from __future__ import annotations

from flask import request, url_for

from ..domains.admin_console import build_operations_payload
from .admin_console import _breadcrumb_items, _render_admin_template


def _render_operations_page(
    *,
    tab: str = "",
    page_notice: str = "",
    page_error: str = "",
    action_result: dict | None = None,
):
    args = request.args.to_dict(flat=True)
    if tab:
        args["tab"] = tab
    payload = build_operations_payload(args)
    return _render_admin_template(
        "operations.html",
        active_nav="operations",
        page_title="班级状态",
        page_summary="查看班级学员状态和状态变更历史。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("运营", None)),
        operations_payload=payload,
        page_notice=page_notice,
        page_error=page_error,
        action_result=action_result or {},
    )


def admin_console_class_users():
    return _render_operations_page(tab=str(request.args.get("tab") or "class-users").strip() or "class-users")

def register_routes(bp):
    bp.route("/admin/class-users", methods=["GET"])(admin_console_class_users)
