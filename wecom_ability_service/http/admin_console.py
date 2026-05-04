from __future__ import annotations

from flask import redirect, render_template, url_for

from ..domains.admin_audit import build_risk_control_rows, build_runbook_rows
from ..domains.admin_dashboard import (
    build_admin_shell_status,
    build_system_status_payload,
    list_admin_navigation,
)
from .common import _deprecated_admin_redirect


def _breadcrumb_items(*items: tuple[str, str | None]) -> list[dict[str, str]]:
    return [
        {"label": label, "href": href or ""}
        for label, href in items
    ]

def _render_admin_template(
    template_name: str,
    *,
    active_nav: str,
    page_title: str,
    page_summary: str,
    breadcrumbs: list[dict[str, str]],
    **extra,
):
    from .internal_auth import current_admin_session_user, ensure_admin_console_action_token

    return render_template(
        f"admin_console/{template_name}",
        page_title=page_title,
        page_summary=page_summary,
        breadcrumbs=breadcrumbs,
        nav_items=list_admin_navigation(active_nav),
        shell_status=build_admin_shell_status(),
        current_admin_user=current_admin_session_user(),
        admin_action_token=extra.pop("admin_action_token", ensure_admin_console_action_token()),
        show_shell_meta=extra.pop("show_shell_meta", True),
        show_page_header=extra.pop("show_page_header", True),
        **extra,
    )


def render_admin_user_ops_shell():
    return _render_admin_template(
        "user_ops.html",
        active_nav="operations",
        page_title="运营管理",
        page_summary="转化链路运营页。当前页只针对有班期标识的引流品用户做筛选、客户详情复用、批量群发、免打扰和发送记录。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("运营", None)),
    )


def admin_console_home():
    # Phase 1 shell slimming: admin root no longer renders the retired workbench.
    return redirect(url_for("api.admin_automation_conversion"), code=302)


def admin_console_system():
    return _render_admin_template(
        "system.html",
        active_nav="system",
        page_title="系统与帮助",
        page_summary="这里可以查看系统状态、常见入口和使用提醒。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("系统", None)),
        system_status=build_system_status_payload(),
        runbook_rows=build_runbook_rows(),
        risk_rows=build_risk_control_rows(),
    )


def admin_console_legacy_user_ops():
    return render_admin_user_ops_shell()


def admin_console_legacy_questionnaires():
    return _deprecated_admin_redirect("api.admin_console_questionnaires")


def admin_console_legacy_class_user_management():
    return render_template("admin_class_user_management.html")


def admin_console_legacy_class_user_backoffice():
    return render_template("admin_class_user_backoffice.html")


def register_routes(bp):
    bp.route("/admin", methods=["GET"])(admin_console_home)
    bp.route("/admin/system", methods=["GET"])(admin_console_system)
    bp.route("/admin/_legacy/user-ops", methods=["GET"])(admin_console_legacy_user_ops)
    bp.route("/admin/_legacy/questionnaires", methods=["GET"])(admin_console_legacy_questionnaires)
    bp.route("/admin/_legacy/class-user-management", methods=["GET"])(admin_console_legacy_class_user_management)
    bp.route("/admin/_legacy/class-user-backoffice", methods=["GET"])(admin_console_legacy_class_user_backoffice)
