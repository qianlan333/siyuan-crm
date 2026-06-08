from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_read_model.application import (
    GetAdminConfigPageQuery,
    GetAdminFunnelPageQuery,
    GetAdminProductsPageQuery,
    page_row_count,
)
from aicrm_next.frontend_compat.api_docs_view_model import build_api_docs_view_model
from aicrm_next.customer_read_model.application import GetAdminCustomerProfileQuery, ListCustomersQuery
from aicrm_next.customer_read_model.dto import ListCustomersRequest
from aicrm_next.admin_shell import (
    admin_path_for as _admin_path_for,
    shell_context as _shell_context,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
ADMIN_CUSTOMERS_UNAVAILABLE_MESSAGE = "客户列表暂不可用：生产客户读源正在同步或数据库连接繁忙，请稍后刷新。"

LEGACY_FRONTEND_ROUTES = [
    "/admin/customers",
    "/admin/user-ops/ui",
    "/admin/user-ops",
    "/admin/hxc-dashboard",
    "/admin/hxc-send-config",
    "/admin/cloud-orchestrator",
    "/admin/cloud-orchestrator/campaigns",
    "/admin/cloud-orchestrator/observability",
    "/admin/wechat-pay/products",
    "/admin/api-docs",
]


@router.get("/sidebar/bind-mobile", name="api.sidebar_bind_mobile_page")
async def sidebar_bind_mobile_page(request: Request):
    return templates.TemplateResponse(
        request,
        "sidebar_customer_workbench.html",
        {"request": request, "debug_enabled": False},
    )


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


def _admin_customer_payload_from_list_result(
    *,
    result: dict,
    keyword: str,
    owner: str,
    mobile: str,
    tag: str,
    limit: int,
    offset: int,
) -> tuple[dict, str]:
    unavailable = not result.get("ok", True) or result.get("source_status") == "production_unavailable"
    page_error = ADMIN_CUSTOMERS_UNAVAILABLE_MESSAGE if unavailable else ""
    customers = [] if unavailable else list(result.get("customers") or result.get("items") or [])
    total = 0 if unavailable else int(result.get("total") or result.get("count") or len(customers))
    return (
        {
            "filters": {"keyword": keyword, "owner": owner, "mobile": mobile, "tag": tag},
            "customers": customers,
            "pagination": {
                "total": total,
                "has_prev": offset > 0,
                "has_next": offset + limit < total,
                "prev_offset": max(offset - limit, 0),
                "next_offset": offset + limit,
            },
        },
        page_error,
    )


def _customer_profile_initial_section(tab: str) -> str:
    tab_map = {
        "tags": "customer-live-tags",
        "questionnaire": "customer-questionnaire-answers",
        "questionnaires": "customer-questionnaire-answers",
        "messages": "customer-message-records",
        "automation": "customer-automation-sidebar",
    }
    return tab_map.get(str(tab or "").strip().lower(), "")


def _customer_detail_payload_from_profile_result(result: dict, *, legacy_tab: str) -> dict | None:
    if not result.get("ok"):
        return None
    profile = dict(result.get("profile") or result.get("customer") or {})
    external_userid = str(profile.get("external_userid") or profile.get("user_id") or "").strip()
    if not external_userid:
        return None
    identity = dict(profile.get("identity") or {})
    profile["external_userid"] = external_userid
    profile["user_id"] = str(profile.get("user_id") or external_userid)
    profile["customer_name"] = str(profile.get("customer_name") or profile.get("remark") or external_userid)
    profile["mobile"] = str(profile.get("mobile") or identity.get("mobile") or "")
    profile["owner"] = str(profile.get("owner") or profile.get("owner_display_name") or profile.get("owner_userid") or "")
    profile["owner_userid"] = str(profile.get("owner_userid") or "")
    profile["unionid"] = str(profile.get("unionid") or identity.get("unionid") or "")
    return {
        "customer": profile,
        "lookup": dict(result.get("lookup") or {}),
        "initial_section": _customer_profile_initial_section(legacy_tab),
    }


def _customer_profile_urls(external_userid: str) -> dict[str, str]:
    query = urlencode({"external_userid": external_userid})
    return {
        "profile": f"/api/admin/customers/profile?{query}",
        "tags": f"/api/admin/customers/profile/tags?{query}",
        "questionnaire_answers": f"/api/admin/customers/profile/questionnaire-answers?{query}",
        "messages": f"/api/admin/customers/profile/messages?{query}",
        "automation_member": f"/api/admin/automation-conversion/member?{urlencode({'external_contact_id': external_userid})}",
        "automation_put_in_pool": "/api/admin/automation-conversion/member/put-in-pool",
        "automation_remove_from_pool": "/api/admin/automation-conversion/member/remove-from-pool",
        "automation_set_focus": "/api/admin/automation-conversion/member/set-focus",
        "automation_set_normal": "/api/admin/automation-conversion/member/set-normal",
        "automation_mark_won": "/api/admin/automation-conversion/member/mark-won",
        "automation_unmark_won": "/api/admin/automation-conversion/member/unmark-won",
        "automation_push_openclaw": "/api/admin/automation-conversion/member/push-openclaw",
    }


@router.get("/admin/customers", name="api.admin_console_customers")
def admin_customers(request: Request, keyword: str = "", owner: str = "", mobile: str = "", tag: str = "", offset: int = 0):
    limit = 50
    offset = max(int(offset or 0), 0)
    customer_query = ListCustomersRequest(
        owner_userid=owner or None,
        tag=tag or None,
        mobile=mobile or None,
        keyword=keyword or None,
        limit=limit,
        offset=offset,
    )
    result = ListCustomersQuery()(customer_query)
    customer_payload, page_error = _admin_customer_payload_from_list_result(
        result=result,
        keyword=keyword,
        owner=owner,
        mobile=mobile,
        tag=tag,
        limit=limit,
        offset=offset,
    )
    context = _shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="查看客户列表、筛选客户并打开客户档案。",
        active_endpoint="api.admin_console_customers",
    )
    context["page_error"] = page_error
    context["customer_payload"] = customer_payload
    return templates.TemplateResponse(request, "admin_console/customers.html", context)


@router.get("/admin/customers/{external_userid}", name="api.admin_console_customer_detail")
def admin_customer_detail_page(request: Request, external_userid: str, tab: str = ""):
    result = GetAdminCustomerProfileQuery()(external_userid=external_userid)
    payload = _customer_detail_payload_from_profile_result(result, legacy_tab=tab)
    if not payload:
        status_code = int(result.get("status_code") or 404)
        page_error = str(result.get("page_error") or result.get("error") or "未找到客户")
        context = _shell_context(
            request=request,
            page_title="客户不存在",
            page_summary="当前客户编号没有查到对应客户。",
            active_endpoint="api.admin_console_customers",
        )
        context.update(
            {
                "breadcrumbs": [
                    {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                    {"label": "客户", "href": "/admin/customers"},
                    {"label": external_userid, "href": ""},
                ],
                "actions": [{"label": "返回客户列表", "href": "/admin/customers", "variant": "secondary"}],
                "state_title": "客户不存在",
                "state_body": "请确认客户编号是否正确，或稍后重试。",
                "state_items": ["检查客户编号是否输入正确", "确认当前环境已经同步到该客户数据"],
                "table_rows": [],
                "page_error": page_error,
            }
        )
        return templates.TemplateResponse(request, "admin_console/placeholder.html", context, status_code=status_code)

    customer = payload["customer"]
    customer_name = str(customer.get("customer_name") or external_userid)
    context = _shell_context(
        request=request,
        page_title=customer_name,
        page_summary="查看客户基础资料、实时标签、问卷问答和聊天记录。",
        active_endpoint="api.admin_console_customers",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "客户", "href": "/admin/customers"},
                {"label": customer_name, "href": ""},
            ],
            "customer_payload": payload,
            "page_error": str(result.get("page_error") or ""),
            "admin_action_token": "",
            "action_result": {},
            "customer_profile_urls": _customer_profile_urls(str(customer.get("external_userid") or external_userid)),
        }
    )
    return templates.TemplateResponse(request, "admin_console/customer_detail.html", context)


@router.get("/admin/user-ops/ui", name="api.admin_user_ops_ui")
def admin_user_ops_ui(request: Request):
    context = _shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="客户激活与运营入口读取生产客户、问卷、交易与自动化统计。",
        active_endpoint="api.admin_console_customers",
    )
    payload = GetAdminFunnelPageQuery()()
    _real_data_context(
        context,
        payload=payload,
        title="客户激活 / 客户列表",
        summary="生产客户、问卷、订单和自动化成员统计。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/user-ops", name="api.admin_user_ops")
def admin_user_ops_page(request: Request):
    context = _shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="User Ops 读模型与预览能力由 Next-native API 提供。",
        active_endpoint="api.admin_console_customers",
    )
    context.update({"admin_action_token": "", "action_result": {}})
    return templates.TemplateResponse(request, "admin_console/user_ops.html", context)


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
