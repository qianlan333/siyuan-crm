from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_read_model.application import (
    GetAdminConfigPageQuery,
    GetAdminProductsPageQuery,
    page_row_count,
)
from aicrm_next.frontend_compat.api_docs_view_model import build_api_docs_view_model
from aicrm_next.admin_shell import (
    admin_path_for as _admin_path_for,
    shell_context as _shell_context,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

LEGACY_FRONTEND_ROUTES = [
    "/admin/hxc-dashboard",
    "/admin/hxc-send-config",
    "/admin/cloud-orchestrator",
    "/admin/cloud-orchestrator/campaigns",
    "/admin/cloud-orchestrator/observability",
    "/admin/wechat-pay/products",
    "/admin/api-docs",
]


def _real_data_context(context: dict, *, payload: dict, title: str, summary: str) -> dict:
    context.update(
        {
            "real_data_payload": payload,
            "data_title": title,
            "data_summary": summary,
            "real_data_row_count": page_row_count(payload),
        }
    )
    if payload.get("page_error"):
        context["page_error"] = payload["page_error"]
    return context


def _empty_hxc_dashboard_summary() -> dict:
    return {
        "total": 0,
        "funnel": {
            "member_and_user": 0,
            "only_member": 0,
            "user_no_member": 0,
            "inactive": 0,
        },
        "latest_refresh": {"started_at": "", "finished_at": "", "status": "local_contract_probe"},
    }


@router.get("/admin/hxc-dashboard", name="api.admin_hxc_dashboard_workspace")
def admin_hxc_dashboard(request: Request):
    context = _shell_context(
        request=request,
        page_title="用户激活漏斗看板",
        page_summary=(
            "CRM 三表手机号并集 × 黄小璨用户/会员/订阅/测评/成长目标/路径/任务/复盘/V6 角色评分 "
            "聚合, 每 30 分钟自动刷新. 列头可筛选, 表格右上角可导出 CSV / Excel."
        ),
        active_endpoint="api.admin_hxc_dashboard_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "用户激活漏斗看板"},
    ]
    context.update(
        {
            "dashboard_rows": [],
            "dashboard_summary": _empty_hxc_dashboard_summary(),
            "send_configs": [],
        }
    )
    return templates.TemplateResponse(request, "admin_console/hxc_dashboard.html", context)


@router.get("/admin/hxc-send-config", name="api.admin_hxc_send_config_page")
def admin_hxc_send_config(request: Request):
    context = _shell_context(
        request=request,
        page_title="群发发送人管理",
        page_summary="从企微通讯录选择群发发送人，设置优先级和启用状态。",
        active_endpoint="api.admin_hxc_dashboard_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "激活漏斗看板", "href": request.url_for("api.admin_hxc_dashboard_workspace")},
        {"label": "群发发送人管理"},
    ]
    context.update(
        {
            "directory_count": 0,
            "sender_count": 0,
            "active_sender_count": 0,
            "last_synced_at": "暂无",
            "members": [],
            "send_configs": [],
        }
    )
    return templates.TemplateResponse(request, "admin_console/hxc_send_config.html", context)


@router.get("/admin/cloud-orchestrator", name="api.admin_cloud_orchestrator_workspace")
def admin_cloud_orchestrator(request: Request):
    return RedirectResponse(
        url=_admin_path_for("api.admin_cloud_orchestrator_plans_workspace"),
        status_code=302,
    )


@router.get("/admin/cloud-orchestrator/campaigns", name="api.admin_cloud_orchestrator_campaigns_workspace")
def admin_cloud_orchestrator_campaigns(request: Request):
    context = _shell_context(
        request=request,
        page_title="AI 助手 · 运营计划审阅",
        page_summary="Agent 上架的多分层多步骤运营计划在这里审阅启动。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "AI 助手", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
        {"label": "运营计划审阅"},
    ]
    context["page_actions"] = [
        {
            "label": "可观察性",
            "href": "/admin/cloud-orchestrator/observability",
            "variant": "ghost",
        },
    ]
    return templates.TemplateResponse(request, "admin_console/cloud_campaigns_workspace.html", context)


@router.get("/admin/cloud-orchestrator/observability", name="api.admin_cloud_orchestrator_observability")
def admin_cloud_orchestrator_observability(request: Request):
    context = _shell_context(
        request=request,
        page_title="Cloud Orchestrator · 可观察性",
        page_summary="工单、审计、漏斗与 Tool 调用统计按 trace_id 串联排查。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "AI 助手", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
        {"label": "可观察性"},
    ]
    context["page_actions"] = [
        {
            "label": "返回助手",
            "href": request.url_for("api.admin_cloud_orchestrator_campaigns_workspace"),
            "variant": "primary",
        },
    ]
    return templates.TemplateResponse(request, "admin_console/cloud_observability.html", context)


@router.get("/admin/wechat-pay/products", name="api.admin_wechat_pay_products_page")
def admin_wechat_pay_products(request: Request):
    context = _shell_context(
        request=request,
        page_title="商品管理",
        page_summary="查看和维护生产商品配置；支付外部动作仍受安全边界保护。",
        active_endpoint="api.admin_wechat_pay_products_page",
    )
    _real_data_context(
        context,
        payload=GetAdminProductsPageQuery()(),
        title="商品管理",
        summary="生产 wechat_pay_products 与 page slices 只读列表。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/runtime-config", name="api.admin_runtime_config")
def admin_runtime_config(request: Request):
    context = _shell_context(
        request=request,
        page_title="运行配置",
        page_summary="查看 Next 运行时、发布和外部回调预检状态。",
        active_endpoint="api.admin_runtime_config",
    )
    _real_data_context(
        context,
        payload=GetAdminConfigPageQuery()(),
        title="运行配置",
        summary="展示数据库模式、release、callback fallback、OAuth、企微和支付配置预检状态；不展示 secrets。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/api-docs", name="api.admin_api_docs")
def admin_api_docs(request: Request):
    context = _shell_context(
        request=request,
        page_title="API 文档",
        page_summary="查看 AI-CRM 后台和外部集成 API 文档。",
        active_endpoint="api.admin_api_docs",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "API 文档"},
            ],
            **build_api_docs_view_model(frontend_router=router),
        }
    )
    return templates.TemplateResponse(request, "admin_console/api_docs.html", context)


@router.get("/api/frontend-compat/legacy-routes")
def legacy_routes_manifest() -> dict:
    return {
        "ok": True,
        "frontend_parity_policy": "1:1 replicate existing AI-CRM admin frontend; do not redesign",
        "routes": LEGACY_FRONTEND_ROUTES,
    }
