from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_jobs.routes import ensure_admin_action_token, validate_admin_action_token
from aicrm_next.admin_shell import admin_path_for, shell_context

from .application import (
    AdminConfigReadService,
    AdminConfigWriteCommand,
    LoginAccessSaveCommand,
    McpToolSettingSaveCommand,
    SetupWizardSaveCommand,
    SetupWizardStateService,
    SignupConversionConfigSaveCommand,
    _bool,
    _text,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def _operator_from_request(request: Request, payload: dict[str, Any] | None = None, form: Any | None = None) -> str:
    return (
        _text(request.headers.get("X-Admin-Operator"))
        or _text((form or {}).get("operator") if form is not None else "")
        or _text((payload or {}).get("operator") if payload else "")
        or "crm_console"
    )


def _config_context(
    request: Request,
    *,
    active_tab: str,
    page_title: str,
    page_summary: str,
    page_notice: str = "",
    page_error: str = "",
    **extra: Any,
) -> dict[str, Any]:
    read_service = AdminConfigReadService()
    context = shell_context(
        request=request,
        page_title=page_title,
        page_summary=page_summary,
        active_endpoint="api.admin_config",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": "/admin"},
                {"label": "配置中心", "href": "/admin/config"},
                {"label": page_title, "href": ""},
            ],
            "config_tabs": read_service.config_tabs(active_tab),
            "page_notice": page_notice,
            "page_error": page_error,
            "admin_action_token": ensure_admin_action_token(),
            "url_for": admin_path_for,
        }
    )
    context.update(extra)
    return context


def _redirect(url: str, **query: Any) -> RedirectResponse:
    if query:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode({key: value for key, value in query.items() if _text(value)})}"
    return RedirectResponse(url=url, status_code=302)


async def _form_dict(request: Request) -> dict[str, Any]:
    form = await request.form()
    payload: dict[str, Any] = {}
    for key, value in form.multi_items():
        if key in payload:
            existing = payload[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                payload[key] = [existing, value]
        else:
            payload[key] = value
    return payload


async def _token_error_from_form(request: Request) -> tuple[str, dict[str, Any]]:
    form = await _form_dict(request)
    return validate_admin_action_token(_text(form.get("admin_action_token"))), form


@router.get("/admin/config", name="api.admin_config", response_class=HTMLResponse)
def admin_config_home(request: Request):
    payload = AdminConfigReadService().build_home_payload()
    return templates.TemplateResponse(
        request,
        "admin_console/config_overview.html",
        _config_context(
            request,
            active_tab="overview",
            page_title="配置中心",
            page_summary="在这里维护渠道与分配规则、标签班期规则、系统设置，以及登录与权限。",
            overview_cards=payload["cards"],
        ),
    )


@router.get("/admin/config/wecom-tags", name="api.admin_config_wecom_tags", response_class=HTMLResponse)
def admin_config_wecom_tags():
    return _redirect("/admin/wecom-tags")


@router.get("/admin/config/app-settings", name="api.admin_config_app_settings", response_class=HTMLResponse)
def admin_config_app_settings(request: Request):
    query = _text(request.query_params.get("q"))
    scope = _text(request.query_params.get("scope"))
    payload = AdminConfigReadService().list_app_settings(query=query, scope=scope)
    rows = payload["rows"]
    return templates.TemplateResponse(
        request,
        "admin_console/config_app_settings.html",
        _config_context(
            request,
            active_tab="app_settings",
            page_title="系统设置",
            page_summary="集中查看和修改系统级参数；敏感信息仅显示掩码。",
            page_notice="保存成功" if _bool(request.query_params.get("saved")) else "",
            page_error=_text(request.query_params.get("error")),
            filters={"q": query, "scope": scope},
            rows=rows,
            editable_rows=[row for row in rows if row.get("mode") == "editable"],
            masked_rows=[row for row in rows if row.get("mode") == "masked"],
            summary_cards=payload["summary_cards"],
            audit_entries=payload["audit_entries"],
        ),
    )


@router.post("/admin/config/app-settings/save", name="api.admin_config_save_app_settings", response_class=HTMLResponse)
async def admin_config_save_app_settings(request: Request):
    token_error, form = await _token_error_from_form(request)
    if token_error:
        return _redirect("/admin/config/app-settings", error=token_error)
    if not _bool(form.get("confirm")):
        return _redirect("/admin/config/app-settings", error="confirm is required before saving app settings")
    settings = {key[len("setting__") :]: value for key, value in form.items() if key.startswith("setting__")}
    try:
        AdminConfigWriteCommand().execute(settings, operator=_operator_from_request(request, form=form))
    except ValueError as exc:
        return _redirect("/admin/config/app-settings", error=str(exc))
    return _redirect("/admin/config/app-settings", saved=1)


@router.get("/api/admin/config/overview", name="api.admin_config_overview")
def api_admin_config_overview() -> dict[str, Any]:
    return {"ok": True, "overview": AdminConfigReadService().build_home_payload(), "source_status": "next_read_model", "fallback_used": False}


@router.get("/api/admin/config/app-settings", name="api.admin_config_app_settings_resource")
def api_admin_config_app_settings(request: Request) -> dict[str, Any]:
    return {
        "ok": True,
        "config": AdminConfigReadService().list_app_settings(
            query=_text(request.query_params.get("q")),
            scope=_text(request.query_params.get("scope")),
        ),
        "source_status": "next_read_model",
        "fallback_used": False,
    }


@router.get("/admin/config/mcp-tools", name="api.admin_config_mcp_tools", response_class=HTMLResponse)
def admin_config_mcp_tools():
    return _redirect("/admin/api-docs")


@router.post("/admin/config/mcp-tools/save", name="api.admin_config_save_mcp_tool", response_class=HTMLResponse)
def admin_config_save_mcp_tool():
    return _redirect("/admin/api-docs")


@router.get("/api/admin/config/mcp-tools", name="api.admin_config_mcp_tools_resource")
def api_admin_config_mcp_tools(request: Request) -> dict[str, Any]:
    return {
        "ok": True,
        "config": AdminConfigReadService().list_mcp_tool_settings(
            query=_text(request.query_params.get("q")),
            enabled_only=_bool(request.query_params.get("enabled_only")),
        ),
        "source_status": "next_read_model",
        "fallback_used": False,
    }


@router.post("/api/admin/config/mcp-tools", name="api.admin_config_save_mcp_tool_resource")
async def api_admin_config_save_mcp_tool(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "payload must be an object"}, status_code=400)
    try:
        saved = McpToolSettingSaveCommand().execute(payload, operator=_operator_from_request(request, payload=payload))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {
        "ok": True,
        "item": saved,
        "source_status": "next_command",
        "fallback_used": False,
        "real_external_call_executed": False,
    }


@router.get("/api/admin/config/marketing-automation/signup-conversion", name="api.admin_config_signup_conversion")
def api_admin_config_signup_conversion() -> dict[str, Any]:
    return {
        "ok": True,
        "config": AdminConfigReadService().get_signup_conversion_config(),
        "source_status": "next_read_model",
        "fallback_used": False,
    }


@router.put("/api/admin/config/marketing-automation/signup-conversion", name="api.admin_config_save_signup_conversion")
async def api_admin_config_save_signup_conversion(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "payload must be an object"}, status_code=400)
    try:
        saved = SignupConversionConfigSaveCommand().execute(payload, operator=_operator_from_request(request, payload=payload))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {
        "ok": True,
        "config": saved,
        "source_status": "next_command",
        "fallback_used": False,
        "real_external_call_executed": False,
    }


@router.get("/api/admin/config/routing", name="api.admin_config_routing")
def api_admin_config_routing():
    raise HTTPException(status_code=404, detail="admin config routing API is retired")


@router.post("/api/admin/config/routing/owner-role", name="api.admin_config_save_owner_role")
def api_admin_config_save_owner_role():
    raise HTTPException(status_code=404, detail="admin config owner-role API is retired")


@router.post("/api/admin/config/routing/rule", name="api.admin_config_save_routing_rule")
def api_admin_config_save_routing_rule():
    raise HTTPException(status_code=404, detail="admin config routing-rule API is retired")


@router.get("/api/admin/config/signup-tags", name="api.admin_config_signup_tags")
def api_admin_config_signup_tags():
    raise HTTPException(status_code=404, detail="admin config signup-tags API is retired")


@router.post("/api/admin/config/signup-tags", name="api.admin_config_save_signup_tag")
def api_admin_config_save_signup_tag():
    raise HTTPException(status_code=404, detail="admin config signup-tags API is retired")


@router.get("/api/admin/config/class-term-tags", name="api.admin_config_class_term_tags")
def api_admin_config_class_term_tags():
    raise HTTPException(status_code=404, detail="admin config class-term-tags API is retired")


@router.post("/api/admin/config/class-term-tags", name="api.admin_config_save_class_term_tag")
def api_admin_config_save_class_term_tag():
    raise HTTPException(status_code=404, detail="admin config class-term-tags API is retired")


@router.put("/api/admin/config/app-settings", name="api.admin_config_save_app_settings_resource")
async def api_admin_config_save_app_settings(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "payload must be an object"}, status_code=400)
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        return JSONResponse({"ok": False, "error": "settings must be an object"}, status_code=400)
    if not _bool(payload.get("confirm")):
        return JSONResponse({"ok": False, "error": "confirm is required before saving app settings"}, status_code=400)
    token = _text(request.headers.get("X-Admin-Action-Token")) or _text(payload.get("admin_action_token"))
    token_error = validate_admin_action_token(token)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=400)
    try:
        changed = AdminConfigWriteCommand().execute(settings, operator=_operator_from_request(request, payload=payload))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {
        "ok": True,
        "changed": changed,
        "changed_count": len(changed),
        "config": AdminConfigReadService().list_app_settings(query="", scope=""),
        "source_status": "next_command",
        "fallback_used": False,
        "real_external_call_executed": False,
    }


@router.get("/admin/config/login-access", name="api.admin_config_login_access", response_class=HTMLResponse)
def admin_config_login_access(request: Request):
    payload = AdminConfigReadService().build_login_access_payload()
    edit_id = _text(request.query_params.get("edit_id"))
    candidate_userid = _text(request.query_params.get("wecom_userid"))
    directory_candidate = next((row for row in payload["directory_members"] if row["wecom_userid"] == candidate_userid), None)
    default_form_row = {
        "is_active": True,
        "login_enabled": True,
        "admin_level": "admin",
        "roles": ["viewer"],
        "wecom_corpid": payload.get("corp_id", ""),
    }
    if directory_candidate:
        default_form_row.update(
            {
                "wecom_userid": directory_candidate["wecom_userid"],
                "display_name": directory_candidate["display_name"],
                "wecom_corpid": directory_candidate["wecom_corpid"] or payload.get("corp_id", ""),
                "auth_source": "wecom_sso",
            }
        )
    form_row = next((row for row in payload["rows"] if str(row["id"]) == edit_id), default_form_row)
    return templates.TemplateResponse(
        request,
        "admin_console/config_login_access.html",
        _config_context(
            request,
            active_tab="login_access",
            page_title="登录与权限",
            page_summary="在这里维护后台企微成员授权、角色分配、启停状态与最近登录审计。",
            page_notice="保存成功" if _bool(request.query_params.get("saved")) else _text(request.query_params.get("notice")),
            page_error=_text(request.query_params.get("error")),
            form_row=form_row,
            can_manage_accounts=True,
            can_manage_super_admin=True,
            can_manage_form=True,
            **payload,
        ),
    )


@router.post("/admin/config/login-access/directory/refresh", name="api.admin_config_refresh_login_access_directory")
async def admin_config_refresh_login_access_directory(request: Request):
    token_error, _form = await _token_error_from_form(request)
    if token_error:
        return _redirect("/admin/config/login-access", error=token_error)
    return _redirect("/admin/config/login-access", notice="通讯录刷新已跳过：Next 配置模块不会触发真实企微外呼")


@router.post("/admin/config/login-access/save", name="api.admin_config_save_login_access")
async def admin_config_save_login_access(request: Request):
    token_error, form = await _token_error_from_form(request)
    if token_error:
        return _redirect("/admin/config/login-access", error=token_error)
    try:
        saved = LoginAccessSaveCommand().execute(form, operator=_operator_from_request(request, form=form))
    except ValueError as exc:
        return _redirect("/admin/config/login-access", error=str(exc))
    return _redirect("/admin/config/login-access", saved=1, edit_id=saved.get("id", ""))


@router.get("/admin/config/checklist", name="api.admin_config_checklist", response_class=HTMLResponse)
def admin_config_checklist(request: Request):
    return templates.TemplateResponse(
        request,
        "admin_console/config_checklist.html",
        _config_context(
            request,
            active_tab="checklist",
            page_title="配置检查清单",
            page_summary="新客户接入时按照此清单逐项配置，必填项标红星，绿色表示已配置。",
            checklist=AdminConfigReadService().build_checklist(),
        ),
    )


@router.get("/setup/wizard", name="api.setup_wizard", response_class=HTMLResponse)
def setup_wizard(request: Request):
    context = shell_context(
        request=request,
        page_title="系统配置向导",
        page_summary="按步骤填写企业微信和系统配置信息。",
        active_endpoint="api.admin_config",
    )
    context.update({"url_for": admin_path_for, **SetupWizardStateService().build_state()})
    return templates.TemplateResponse(request, "admin_console/setup_wizard.html", context)


@router.post("/setup/wizard/save", name="api.setup_wizard_save", response_class=HTMLResponse)
async def setup_wizard_save(request: Request):
    token_error, form = await _token_error_from_form(request)
    state_service = SetupWizardStateService()
    context = shell_context(
        request=request,
        page_title="系统配置向导",
        page_summary="按步骤填写企业微信和系统配置信息。",
        active_endpoint="api.admin_config",
    )
    if token_error:
        state = state_service.build_state(
            validation_errors=[{"group": "后台安全", "field": "动作令牌", "key": "admin_action_token", "error": token_error}]
        )
        context.update({"url_for": admin_path_for, **state})
        return templates.TemplateResponse(request, "admin_console/setup_wizard.html", context)
    result = SetupWizardSaveCommand().execute(form, operator=_operator_from_request(request, form=form))
    state = state_service.build_state(validation_errors=result["validation_errors"], save_success=bool(result["ok"]))
    context.update({"url_for": admin_path_for, **state})
    return templates.TemplateResponse(request, "admin_console/setup_wizard.html", context)
