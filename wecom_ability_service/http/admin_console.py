from __future__ import annotations

from flask import redirect, url_for

from ..domains.admin_dashboard import (
    build_admin_shell_status,
    list_admin_navigation,
)


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
    from flask import render_template

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


def register_routes(bp):
    bp.route("/admin", methods=["GET"])(admin_console_home)
