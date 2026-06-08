from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell import admin_path_for, shell_context
from aicrm_next.automation_engine.channels_api import (
    list_program_channel_bindings_resource,
    list_program_entry_candidate_channels,
)
from aicrm_next.automation_engine.overview_read_model import AutomationOverviewReadModel, AutomationPoolReadModel
from aicrm_next.automation_engine.programs import (
    AutomationProgramDataUnavailable,
    SETUP_STEPS,
    copy_automation_program,
    get_automation_program_members_payload,
    get_automation_program_overview_payload,
    get_automation_program_setup_payload,
    get_automation_program_with_summary,
    list_automation_programs_payload,
    update_automation_program_basic_info,
    update_automation_program_status,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/admin/automation-conversion", name="api.admin_automation_conversion")
def admin_automation_conversion(request: Request):
    try:
        program_list_payload = list_automation_programs_payload()
    except AutomationProgramDataUnavailable:
        program_list_payload = {
            "items": [],
            "default_program": {},
            "total": 0,
            "source_status": "next_postgres_unavailable",
        }
    try:
        automation_overview_payload = AutomationOverviewReadModel().execute()
        automation_pool_payload = AutomationPoolReadModel().execute()
    except Exception:
        automation_overview_payload = AutomationOverviewReadModel(rows=[]).execute()
        automation_pool_payload = AutomationPoolReadModel(rows=[]).execute()
    context = shell_context(
        request=request,
        page_title="自动化运营",
        page_summary="查看自动化运营方案列表与当前方案人数；生产环境读取 PostgreSQL。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "program_list_payload": program_list_payload,
            "automation_overview_payload": automation_overview_payload,
            "automation_pool_payload": automation_pool_payload,
            "show_create_form": False,
            "admin_action_token": "",
            "action_urls": {"create": "/admin/automation-conversion"},
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_list.html", context)


def _automation_program_workspace_tabs(request: Request, program_id: int, active_key: str) -> list[dict[str, object]]:
    del request
    tabs = (
        ("overview", "数据概览", "api.admin_automation_program_overview"),
        ("setup", "配置向导", "api.admin_automation_program_setup"),
        ("entry_channels", "入口渠道", "api.admin_automation_program_entry_channels"),
    )
    return [
        {
            "key": key,
            "label": label,
            "summary": "",
            "href": admin_path_for(endpoint, program_id=int(program_id)),
            "active": key == active_key,
        }
        for key, label, endpoint in tabs
    ]


def _automation_program_context(request: Request, program: dict[str, object], *, active_key: str) -> dict[str, object]:
    del request
    program_id = int(program.get("id") or 0)
    return {
        "id": program_id,
        "program_code": str(program.get("program_code") or ""),
        "program_name": str(program.get("program_name") or ""),
        "description": str(program.get("description") or ""),
        "status": str(program.get("status") or "draft"),
        "list_href": admin_path_for("api.admin_automation_conversion"),
        "overview_href": admin_path_for("api.admin_automation_program_overview", program_id=program_id),
        "update_href": admin_path_for("api.admin_automation_program_update", program_id=program_id),
        "copy_href": admin_path_for("api.admin_automation_program_copy", program_id=program_id),
        "activate_href": admin_path_for("api.admin_automation_program_activate", program_id=program_id),
        "pause_href": admin_path_for("api.admin_automation_program_pause", program_id=program_id),
        "archive_href": admin_path_for("api.admin_automation_program_archive", program_id=program_id),
        "active_key": active_key,
    }


def _automation_program_not_found(request: Request, program_id: int) -> Response:
    context = shell_context(
        request=request,
        page_title="自动化运营方案不存在",
        page_summary="没有找到对应的自动化运营方案。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "自动化运营", "href": admin_path_for("api.admin_automation_conversion")},
                {"label": f"方案 {program_id}"},
            ],
            "state_title": "方案不存在",
            "state_body": f"没有找到 ID 为 {program_id} 的自动化运营方案。",
            "state_items": ["请从自动化运营方案列表重新进入", "生产环境直接读取 Next PostgreSQL 方案表"],
            "actions": [
                {
                    "label": "返回方案列表",
                    "href": admin_path_for("api.admin_automation_conversion"),
                    "variant": "primary",
                }
            ],
        }
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context, status_code=404)


def _setup_workspace(request: Request, program: dict[str, object], summary: dict[str, object], *, step: str) -> dict[str, object]:
    del request
    program_id = int(program.get("id") or 0)
    normalized_step = step if step in {item["key"] for item in SETUP_STEPS} else "basic"
    try:
        workspace = get_automation_program_setup_payload(program_id, step=normalized_step)
    except AutomationProgramDataUnavailable:
        workspace = {
            "program": program,
            "summary": summary,
            "step": normalized_step,
            "steps": list(SETUP_STEPS),
            "is_default_program": str(program.get("program_code") or "") == "signup_conversion_v1",
            "basic": dict(program.get("config_json") or {}),
            "entry_channel": {},
            "entry": {"channels": [], "qrcode_channel": {}, "customer_acquisition_links": []},
            "segmentation": {},
            "audience_entry_rule": {},
            "operations": {"tasks": [], "active_count": 0},
            "publish_check": {},
        }
    workspace["program"] = workspace.get("program") or program
    workspace["summary"] = workspace.get("summary") or summary
    workspace["urls"] = {
        "base": admin_path_for("api.admin_automation_program_setup", program_id=program_id),
        "overview": admin_path_for("api.admin_automation_program_overview", program_id=program_id),
        "entry_channels": admin_path_for("api.admin_automation_program_entry_channels", program_id=program_id),
        "update": admin_path_for("api.admin_automation_program_update", program_id=program_id),
        "copy": admin_path_for("api.admin_automation_program_copy", program_id=program_id),
        "basic": admin_path_for("api.admin_automation_program_update", program_id=program_id),
        "segmentation": f"/api/admin/automation-conversion/programs/{program_id}/setup/segmentation",
        "audience_entry_rule": f"/api/admin/automation-conversion/programs/{program_id}/setup/audience-entry-rule",
        "publish_full": f"/api/admin/automation-conversion/programs/{program_id}/publish-full",
    }
    entry = dict(workspace.get("entry") or {})
    entry.setdefault(
        "api_urls",
        {
            "bindings": f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
            "binding_base": f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/0",
        },
    )
    if normalized_step == "entry" and "candidate_channels" not in entry:
        try:
            entry["candidate_channels"] = list_program_entry_candidate_channels(program_id)
        except Exception:
            entry["candidate_channels"] = []
    workspace["entry"] = entry
    workspace["operations_workspace"] = {
        "program_id": program_id,
        "api_urls": {
            "groups": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-task-groups",
            "task_groups": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-task-groups",
            "task_group_detail_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-task-groups/0",
            "tasks": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks",
            "operation_tasks": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks",
            "task_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0",
            "operation_task_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0",
            "task_detail_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0",
            "task_copy_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0/copy",
            "task_activate_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0/activate",
            "task_pause_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0/pause",
            "task_delete_base": f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0",
            "task_preview_audience_base": (
                f"/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/0/preview-audience"
            ),
            "profile_segment_templates_options": (
                f"/api/admin/automation-conversion/profile-segment-templates/options?program_id={program_id}"
            ),
            "profile_segment_template_detail_base": "/api/admin/automation-conversion/profile-segment-templates/0",
            "agents_options": f"/api/admin/automation-conversion/agents/options?program_id={program_id}&limit=200",
            "behavior_segment_rules": "/api/admin/automation-conversion/behavior-segment-rules",
        },
    }
    return workspace


def _overview_workspace(request: Request, program: dict[str, object], summary: dict[str, object]) -> dict[str, object]:
    del request
    program_id = int(program.get("id") or 0)
    try:
        workspace = get_automation_program_overview_payload(program_id)
    except AutomationProgramDataUnavailable as exc:
        workspace = {"program": program, "summary": summary, "page_error": str(exc)}
    workspace["program"] = workspace.get("program") or program
    workspace["summary"] = workspace.get("summary") or summary
    return workspace


@router.get("/admin/automation-conversion/programs/{program_id:int}/setup", name="api.admin_automation_program_setup")
def admin_automation_program_setup(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    summary = dict(data.get("summary") or {})
    context = shell_context(
        request=request,
        page_title="自动化运营方案",
        page_summary="按方案配置基础信息、入口渠道、分层规则、入池规则、运营编排和发布检查。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "自动化运营方案", "href": admin_path_for("api.admin_automation_conversion")},
                {
                    "label": str(program.get("program_name") or f"方案 {program_id}"),
                    "href": admin_path_for("api.admin_automation_program_overview", program_id=program_id),
                },
            ],
            "setup_workspace": _setup_workspace(
                request,
                program,
                summary,
                step=str(request.query_params.get("step") or "basic"),
            ),
            "page_header_tabs": _automation_program_workspace_tabs(request, program_id, "setup"),
            "workspace_tabs": _automation_program_workspace_tabs(request, program_id, "setup"),
            "program_context": _automation_program_context(request, program, active_key="setup"),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_setup_next.html", context)


@router.get("/admin/automation-conversion/programs/{program_id:int}/overview", name="api.admin_automation_program_overview")
def admin_automation_program_overview(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    summary = dict(data.get("summary") or {})
    context = shell_context(
        request=request,
        page_title="数据概览",
        page_summary="查看当前方案内总人数、分阶段人数与成员明细。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "自动化运营方案", "href": admin_path_for("api.admin_automation_conversion")},
                {"label": str(program.get("program_name") or f"方案 {program_id}")},
            ],
            "overview_workspace": _overview_workspace(request, program, summary),
            "page_header_tabs": _automation_program_workspace_tabs(request, program_id, "overview"),
            "workspace_tabs": _automation_program_workspace_tabs(request, program_id, "overview"),
            "program_context": _automation_program_context(request, program, active_key="overview"),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_overview_next.html", context)


@router.get("/admin/automation-conversion/programs/{program_id:int}/members", name="api.admin_automation_program_members")
def admin_automation_program_members(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    stage = str(request.query_params.get("stage") or "all")
    page = int(request.query_params.get("page") or 1)
    page_size = int(request.query_params.get("page_size") or 50)
    keyword = str(request.query_params.get("keyword") or "").strip()
    try:
        members_payload = get_automation_program_members_payload(
            int(program_id),
            stage_key=stage,
            page=page,
            page_size=page_size,
            keyword=keyword or None,
        )
    except AutomationProgramDataUnavailable as exc:
        members_payload = {
            "ok": False,
            "program_id": int(program_id),
            "program": dict(data.get("program") or {}),
            "stage_key": stage,
            "stage_label": "全部成员" if stage == "all" else stage,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "items": [],
            "pagination": {"has_prev": False, "has_next": False, "prev_url": "", "next_url": ""},
            "page_error": str(exc),
        }
    program = dict(members_payload.get("program") or data.get("program") or {})
    context = shell_context(
        request=request,
        page_title=f"{members_payload.get('stage_label') or '成员明细'}",
        page_summary="查看当前方案内的真实成员明细。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "自动化运营方案", "href": admin_path_for("api.admin_automation_conversion")},
                {
                    "label": str(program.get("program_name") or f"方案 {program_id}"),
                    "href": admin_path_for("api.admin_automation_program_overview", program_id=program_id),
                },
                {"label": str(members_payload.get("stage_label") or "成员明细")},
            ],
            "members_payload": members_payload,
            "page_header_tabs": _automation_program_workspace_tabs(request, program_id, "overview"),
            "workspace_tabs": _automation_program_workspace_tabs(request, program_id, "overview"),
            "program_context": _automation_program_context(request, program, active_key="overview"),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_members.html", context)


@router.get("/admin/automation-conversion/programs/{program_id:int}/copy", name="api.admin_automation_program_copy_form")
def admin_automation_program_copy_form(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    context = shell_context(
        request=request,
        page_title="复制自动化运营方案",
        page_summary="复制当前方案配置，不复制成员、执行记录和运行日志。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "自动化运营方案", "href": admin_path_for("api.admin_automation_conversion")},
                {"label": "复制方案"},
            ],
            "copy_source_program": program,
            "copy_action": admin_path_for("api.admin_automation_program_copy", program_id=program_id),
            "cancel_href": admin_path_for("api.admin_automation_program_overview", program_id=program_id),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_copy_next.html", context)


@router.post("/admin/automation-conversion/programs/{program_id:int}/copy", name="api.admin_automation_program_copy")
async def admin_automation_program_copy(request: Request, program_id: int) -> Response:
    form = await request.form()
    copied = copy_automation_program(
        int(program_id),
        operator_id="admin",
        payload={
            "program_name": form.get("program_name"),
            "program_code": form.get("program_code"),
        },
    )
    copied_program = dict(copied.get("program") or {})
    copied_id = int(copied_program.get("id") or 0)
    return RedirectResponse(
        admin_path_for("api.admin_automation_program_setup", program_id=copied_id, step="basic"),
        status_code=303,
    )


@router.post("/admin/automation-conversion/programs/{program_id:int}/update", name="api.admin_automation_program_update")
async def admin_automation_program_update(request: Request, program_id: int) -> Response:
    form = await request.form()
    update_automation_program_basic_info(
        int(program_id),
        {
            "program_name": form.get("program_name"),
            "program_code": form.get("program_code"),
            "description": form.get("description"),
            "status": form.get("status"),
        },
        operator_id="admin",
    )
    next_url = str(form.get("next") or "").strip()
    if not next_url or not next_url.startswith("/"):
        next_url = admin_path_for("api.admin_automation_program_setup", program_id=program_id, step="basic")
    return RedirectResponse(next_url, status_code=303)


async def _automation_program_status_redirect(request: Request, program_id: int, status: str) -> Response:
    form = await request.form()
    update_automation_program_status(int(program_id), status=status, operator_id="admin")
    next_url = str(form.get("next") or "").strip()
    if not next_url or not next_url.startswith("/"):
        next_url = admin_path_for("api.admin_automation_conversion")
    return RedirectResponse(next_url, status_code=303)


@router.post("/admin/automation-conversion/programs/{program_id:int}/pause", name="api.admin_automation_program_pause")
async def admin_automation_program_pause(request: Request, program_id: int) -> Response:
    return await _automation_program_status_redirect(request, program_id, "paused")


@router.post("/admin/automation-conversion/programs/{program_id:int}/activate", name="api.admin_automation_program_activate")
async def admin_automation_program_activate(request: Request, program_id: int) -> Response:
    return await _automation_program_status_redirect(request, program_id, "active")


@router.post("/admin/automation-conversion/programs/{program_id:int}/archive", name="api.admin_automation_program_archive")
async def admin_automation_program_archive(request: Request, program_id: int) -> Response:
    return await _automation_program_status_redirect(request, program_id, "archived")


@router.get(
    "/admin/automation-conversion/programs/{program_id:int}/entry-channels",
    name="api.admin_automation_program_entry_channels",
)
async def admin_automation_program_entry_channels(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    bindings = list_program_channel_bindings_resource(int(program_id))
    candidate_channels = list_program_entry_candidate_channels(int(program_id))
    context = shell_context(
        request=request,
        page_title="入口渠道",
        page_summary="在自动化运营方案内绑定已有渠道码；普通二维码和企微获客助手链接都可以作为入口。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "自动化运营", "href": admin_path_for("api.admin_automation_conversion")},
                {
                    "label": str(program.get("program_name") or f"方案 {program_id}"),
                    "href": admin_path_for("api.admin_automation_program_overview", program_id=program_id),
                },
                {"label": "入口渠道"},
            ],
            "page_header_tabs": _automation_program_workspace_tabs(request, program_id, "entry_channels"),
            "workspace_tabs": _automation_program_workspace_tabs(request, program_id, "entry_channels"),
            "program_context": _automation_program_context(request, program, active_key="entry_channels"),
            "entry_channels_payload": jsonable_encoder(
                {
                    "program": program,
                    "bindings": bindings,
                    "candidate_channels": candidate_channels,
                    "api_urls": {
                        "bindings": f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
                        "binding_base": f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/0",
                    },
                }
            ),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_conversion_entry_channels.html", context)
