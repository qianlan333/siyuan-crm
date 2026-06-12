from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell import shell_context

from .application import GetAdminCustomerProfileQuery, ListCustomersQuery
from .dto import ListCustomersRequest

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

ADMIN_CUSTOMERS_UNAVAILABLE_MESSAGE = "客户列表暂不可用：生产客户读源正在同步或数据库连接繁忙，请稍后刷新。"


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
    context = shell_context(
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
        context = shell_context(
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
    context = shell_context(
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
