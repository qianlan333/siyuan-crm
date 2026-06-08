from __future__ import annotations

from flask import redirect, url_for
from werkzeug.routing import BuildError

from ..domains.admin_dashboard import (
    build_admin_shell_status,
    list_admin_navigation,
)


def _breadcrumb_items(*items: tuple[str, str | None]) -> list[dict[str, str]]:
    return [
        {"label": label, "href": href or ""}
        for label, href in items
    ]


_ADMIN_NAV_FALLBACK_HREFS = {
    "api.admin_automation_conversion": "/admin/automation-conversion",
    "api.admin_group_ops_ui": "/admin/automation-conversion/group-ops/ui",
    "api.admin_group_ops_plan_detail": "/admin/automation-conversion/group-ops/plans",
    "api.admin_group_ops_groups_ui": "/admin/automation-conversion/group-ops/groups/ui",
    "api.admin_channels_page": "/admin/channels",
    "api.admin_cloud_orchestrator_workspace": "/admin/cloud-orchestrator",
    "api.admin_console_customers": "/admin/customers",
    "api.admin_owner_migration_page": "/admin/owner-migration",
    "api.admin_owner_migration_action": "/admin/owner-migration",
    "api.admin_hxc_dashboard_workspace": "/admin/hxc-dashboard",
    "api.admin_console_questionnaires": "/admin/questionnaires",
    "api.admin_radar_links": "/admin/radar-links",
    "api.admin_radar_link_new": "/admin/radar-links/new",
    "api.admin_radar_link_edit": "/admin/radar-links",
    "api.admin_radar_link_detail": "/admin/radar-links",
    "api.admin_wecom_tags_page": "/admin/wecom-tags",
    "api.admin_wechat_pay_transactions_page": "/admin/wechat-pay/transactions",
    "api.admin_wechat_pay_products_page": "/admin/wechat-pay/products",
    "api.admin_image_library_workspace": "/admin/image-library",
    "api.admin_miniprogram_library_workspace": "/admin/miniprogram-library",
    "api.admin_attachment_library_workspace": "/admin/attachment-library",
    "api.admin_console_jobs": "/admin/jobs",
    "api.admin_config_home": "/admin/config",
    "api.admin_console_api_docs": "/admin/api-docs",
}


def _admin_nav_href(endpoint: str) -> str:
    try:
        return url_for(endpoint)
    except BuildError:
        return _ADMIN_NAV_FALLBACK_HREFS.get(endpoint, "#")


def _navigation_with_hrefs(active_nav: str) -> list[dict]:
    groups = []
    for group in list_admin_navigation(active_nav):
        items = [{**item, "href": _admin_nav_href(str(item.get("endpoint") or ""))} for item in group["items"]]
        groups.append({**group, "items": items})
    return groups


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
        nav_items=_navigation_with_hrefs(active_nav),
        shell_status=build_admin_shell_status(),
        current_admin_user=current_admin_session_user(),
        admin_action_token=extra.pop("admin_action_token", ensure_admin_console_action_token()),
        show_shell_meta=extra.pop("show_shell_meta", True),
        show_page_header=extra.pop("show_page_header", True),
        **extra,
    )


def admin_console_home():
    # Phase 1 shell slimming: admin root no longer renders the retired workbench.
    return redirect(url_for("api.admin_automation_conversion"), code=302)


def register_routes(bp):
    bp.route("/admin", methods=["GET"])(admin_console_home)
