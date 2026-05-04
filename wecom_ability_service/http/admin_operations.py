from __future__ import annotations

from flask import request, url_for

from ..domains.admin_console import build_operations_payload, execute_operations_action
from .admin_console import _breadcrumb_items, _render_admin_template, render_admin_user_ops_shell


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
        page_title="运营管理",
        page_summary="在这里处理运营名单、班期状态、导入记录和待处理作业。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("运营", None)),
        operations_payload=payload,
        page_notice=page_notice,
        page_error=page_error,
        action_result=action_result or {},
    )


def admin_console_user_ops():
    return render_admin_user_ops_shell()


def admin_console_class_users():
    return _render_operations_page(tab=str(request.args.get("tab") or "class-users").strip() or "class-users")


def admin_console_operations_action():
    try:
        payload = execute_operations_action(
            action=str(request.form.get("action") or "").strip(),
            form=request.form,
            files=request.files,
            operator=str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip(),
        )
        tab = str(request.form.get("return_tab") or request.args.get("tab") or "").strip()
        return _render_operations_page(
            tab=tab,
            page_notice="操作已完成，并已记录操作人和时间。",
            action_result=payload,
        )
    except Exception as exc:
        tab = str(request.form.get("return_tab") or request.args.get("tab") or "").strip()
        return _render_operations_page(
            tab=tab,
            page_error=str(exc),
        )


def register_routes(bp):
    bp.route("/admin/user-ops", methods=["GET"])(admin_console_user_ops)
    bp.route("/admin/class-users", methods=["GET"])(admin_console_class_users)
    bp.route("/admin/user-ops/actions", methods=["POST"])(admin_console_operations_action)
