from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .navigation import admin_path_for, shell_context
from .view_model import AdminShellApiClient

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/admin", name="api.admin_console_dashboard")
def admin_dashboard(request: Request):
    client = AdminShellApiClient(active_endpoint="api.admin_automation_conversion")
    context = shell_context(
        request=request,
        page_title="自动化运营",
        page_summary="AI-CRM Next 后台总览，生产数据通过 PostgreSQL 与兼容 facade 提供。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "system_status": {
                "cards": [
                    {"label": "FastAPI", "value": "ok", "description": "Next 后端可响应后台 shell。", "tone": "ok"},
                    {"label": "Frontend parity", "value": "live", "description": "后台 shell 已切换为分组导航与生产数据入口。", "tone": "ok"},
                ]
            },
            "dashboard_cards": client.dashboard_cards(),
            "todo_total": 0,
            "todo_groups": [],
            "quick_links": [
                {
                    "label": "客户激活 / 客户列表",
                    "description": "查看客户列表和激活状态。",
                    "href": admin_path_for("api.admin_console_customers"),
                },
                {
                    "label": "AI 助手",
                    "description": "进入 AI 助手兼容入口。",
                    "href": admin_path_for("api.admin_cloud_orchestrator_workspace"),
                },
            ],
            "loading_state": {"enabled": True, "label": "加载后台总览"},
            "empty_state": {"title": "暂无待处理事项", "body": "当前没有需要优先处理的问题。"},
            "error_state": {"title": "后台总览加载失败", "body": "请稍后刷新。"},
        }
    )
    return templates.TemplateResponse(request, "admin_shell/dashboard.html", context)


@router.get("/api/admin/dashboard/shell-context", name="api.admin_dashboard_shell_context")
def admin_dashboard_shell_context() -> dict:
    return AdminShellApiClient().shell_context_payload()


@router.get("/admin/logout", name="api.admin_logout_compat")
def admin_logout_compat() -> RedirectResponse:
    return RedirectResponse(admin_path_for("api.admin_logout"), status_code=302)
