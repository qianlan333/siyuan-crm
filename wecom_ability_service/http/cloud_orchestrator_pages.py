from __future__ import annotations

from flask import Response, redirect, render_template

from ..domains.admin_dashboard.service import build_admin_shell_status, list_admin_navigation


def _cloud_shell_status():
    try:
        return build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        return None


def admin_cloud_orchestrator_workspace() -> Response:
    """旧 AI 对话页已删除 -> 重定向到 Campaign 审阅页。"""

    return redirect("/admin/cloud-orchestrator/campaigns", code=302)


def admin_cloud_orchestrator_observability() -> Response:
    return render_template(
        "admin_console/cloud_observability.html",
        page_title="Cloud Orchestrator · 可观察性",
        page_summary="工单 / 审计 / 漏斗 / Tool 调用统计。出问题时按 trace_id 一查到底。",
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "AI 助手", "href": "/admin/cloud-orchestrator"},
            {"label": "可观察性"},
        ],
        nav_items=list_admin_navigation("cloud_orchestrator"),
        shell_status=_cloud_shell_status(),
        show_shell_meta=False,
        show_page_header=True,
        page_actions=[
            {"label": "返回助手", "href": "/admin/cloud-orchestrator", "variant": "primary"},
        ],
    )


def admin_cloud_orchestrator_campaigns_workspace() -> Response:
    """Campaign 待审 / 审阅工作台。"""

    return render_template(
        "admin_console/cloud_campaigns_workspace.html",
        page_title="AI 助手 · 运营计划审阅",
        page_summary="Agent 上架的多分层多步骤运营计划在这里审阅启动。",
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "AI 助手", "href": "/admin/cloud-orchestrator"},
            {"label": "运营计划审阅"},
        ],
        nav_items=list_admin_navigation("cloud_orchestrator"),
        shell_status=_cloud_shell_status(),
        show_shell_meta=False,
        show_page_header=True,
        page_actions=[
            {"label": "可观察性", "href": "/admin/cloud-orchestrator/observability", "variant": "ghost"},
        ],
    )


def admin_cloud_orchestrator_integration() -> Response:
    """运营拿 MCP 接入凭证的页（演示版本，正式做需要绑定登录用户）。"""

    return render_template(
        "admin_console/cloud_integration_workspace.html",
        page_title="AI 助手 · 接入凭证",
        page_summary="Claude Code / Codex 等外部 Agent 接入 CRM 的 MCP 凭证。",
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "AI 助手", "href": "/admin/cloud-orchestrator"},
            {"label": "接入凭证"},
        ],
        nav_items=list_admin_navigation("cloud_orchestrator"),
        shell_status=_cloud_shell_status(),
        show_shell_meta=False,
        show_page_header=True,
        page_actions=[],
    )


__all__ = [
    "admin_cloud_orchestrator_campaigns_workspace",
    "admin_cloud_orchestrator_integration",
    "admin_cloud_orchestrator_observability",
    "admin_cloud_orchestrator_workspace",
]
