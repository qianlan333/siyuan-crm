from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_read_model.application import GetAdminFunnelPageQuery, page_row_count
from aicrm_next.admin_shell import shell_context

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


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


@router.get("/admin/user-ops/ui", name="api.admin_user_ops_ui")
def admin_user_ops_ui(request: Request):
    context = shell_context(
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
        summary="生产客户、问卷、订单和 AI 人群包统计。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/user-ops", name="api.admin_user_ops")
def admin_user_ops_page(request: Request):
    context = shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="User Ops 读模型与预览能力由 Next-native API 提供。",
        active_endpoint="api.admin_console_customers",
    )
    context.update({"admin_action_token": "", "action_result": {}})
    return templates.TemplateResponse(request, "admin_console/user_ops.html", context)
