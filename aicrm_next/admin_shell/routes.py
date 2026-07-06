from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.data_health.application import (
    data_health_summary,
    data_quality_checks,
    data_quality_groups,
    data_quality_summary,
)
from aicrm_next.delivery_lineage.application import (
    get_delivery_lineage,
    list_delivery_lineage,
    list_delivery_lineage_by_trace,
    list_delivery_lineage_by_unionid,
)
from aicrm_next.growth_orchestration.application import (
    list_growth_members,
    list_growth_programs,
    list_growth_tasks,
    list_growth_touchpoints,
)

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


@router.get("/admin/p1/group-ops-workspace", name="api.admin_p1_group_ops_workspace")
def admin_p1_group_ops_workspace(request: Request):
    context = shell_context(
        request=request,
        page_title="P1 Native Group Ops Workspace",
        page_summary="TS-native draft-only / preview-only 群运营工作台壳；不发送、不审批、不写生产。",
        active_endpoint="api.admin_p1_group_ops_workspace",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "P1 Group Ops Workspace", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "返回群运营计划",
                    "href": admin_path_for("api.admin_group_ops_ui"),
                    "variant": "secondary",
                },
            ],
        }
    )
    return templates.TemplateResponse(request, "admin_shell/p1_group_ops_workspace.html", context)


@router.get("/admin/data-health", name="api.admin_data_health_page")
def admin_data_health_page(request: Request):
    summary = data_health_summary()
    context = shell_context(
        request=request,
        page_title="数据健康",
        page_summary="查看 identity、schema drift、队列和事实归属检查的当前状态。",
        active_endpoint="api.admin_data_health_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "数据健康", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "查看 API",
                    "href": "/api/admin/data-health/summary",
                    "variant": "secondary",
                },
            ],
            "health_summary": summary,
            "health_cards": _data_health_cards(summary),
        }
    )
    return templates.TemplateResponse(request, "admin_shell/data_health.html", context)


@router.get("/admin/data-quality", name="api.admin_data_quality_page")
def admin_data_quality_page(request: Request):
    summary = data_quality_summary()
    groups = data_quality_groups()["groups"]
    checks = data_quality_checks()["checks"]
    grouped_checks = _data_quality_grouped_checks(groups, checks)
    context = shell_context(
        request=request,
        page_title="数据质量规则",
        page_summary="按运营可读分组查看 identity、支付、问卷、投递和客户投影的数据质量规则。",
        active_endpoint="api.admin_data_quality_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "数据质量规则", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "查看 API",
                    "href": "/api/admin/data-quality/summary",
                    "variant": "secondary",
                },
            ],
            "quality_summary": summary,
            "quality_cards": _data_quality_cards(summary),
            "quality_groups": grouped_checks,
        }
    )
    return templates.TemplateResponse(request, "admin_shell/data_quality.html", context)


@router.get("/admin/delivery-lineage", name="api.admin_delivery_lineage_page")
def admin_delivery_lineage_page(request: Request):
    filters = _delivery_lineage_filters(request)
    payload = _delivery_lineage_payload(filters)
    context = shell_context(
        request=request,
        page_title="投递排障",
        page_summary="按 unionid、broadcast job、external effect 或 trace 查询统一投递链路。",
        active_endpoint="api.admin_delivery_lineage_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "投递排障", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "查看 API",
                    "href": "/api/admin/delivery-lineage",
                    "variant": "secondary",
                },
            ],
            "filters": filters,
            "lineage_items": payload.get("items") or ([] if not payload.get("item") else [payload["item"]]),
            "lineage_error": payload.get("error_code", ""),
        }
    )
    return templates.TemplateResponse(request, "admin_shell/delivery_lineage.html", context)


@router.get("/admin/growth-orchestration", name="api.admin_growth_orchestration_page")
def admin_growth_orchestration_page(request: Request):
    payload = _growth_orchestration_payload()
    context = shell_context(
        request=request,
        page_title="增长运营",
        page_summary="统一查看 program、成员、任务和触达 read model；页面只读，不执行外部动作。",
        active_endpoint="api.admin_growth_orchestration_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "增长运营", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "Programs API",
                    "href": "/api/admin/growth-orchestration/programs",
                    "variant": "secondary",
                },
                {
                    "label": "Tasks API",
                    "href": "/api/admin/growth-orchestration/tasks",
                    "variant": "secondary",
                },
            ],
            **payload,
        }
    )
    return templates.TemplateResponse(request, "admin_shell/growth_orchestration.html", context)


@router.get("/admin/growth-orchestration/{program_key:path}", name="api.admin_growth_orchestration_detail_page")
def admin_growth_orchestration_detail_page(request: Request, program_key: str):
    payload = _growth_orchestration_payload(program_key=program_key)
    context = shell_context(
        request=request,
        page_title="增长运营详情",
        page_summary=f"查看 {program_key} 的成员、任务和触达 read model。",
        active_endpoint="api.admin_growth_orchestration_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "增长运营", "href": admin_path_for("api.admin_growth_orchestration_page")},
                {"label": program_key, "href": ""},
            ],
            "page_actions": [
                {
                    "label": "返回列表",
                    "href": admin_path_for("api.admin_growth_orchestration_page"),
                    "variant": "secondary",
                },
            ],
            "selected_program_key": program_key,
            **payload,
        }
    )
    return templates.TemplateResponse(request, "admin_shell/growth_orchestration.html", context)


@router.get("/api/admin/dashboard/shell-context", name="api.admin_dashboard_shell_context")
def admin_dashboard_shell_context() -> dict:
    return AdminShellApiClient().shell_context_payload()


@router.get("/admin/logout", name="api.admin_logout_compat")
def admin_logout_compat() -> RedirectResponse:
    return RedirectResponse(admin_path_for("api.admin_logout"), status_code=302)


def _data_health_cards(summary: dict) -> list[dict[str, str]]:
    counts = summary.get("counts") or {}
    fail_count = int(counts.get("fail") or 0)
    warn_count = int(counts.get("warn") or 0)
    ok_count = int(counts.get("ok") or 0)
    pending_count = int(counts.get("not_applicable") or 0)
    return [
        {
            "label": "红色",
            "value": str(fail_count),
            "description": "schema drift、runtime reference、orphan facts 等阻断项。",
            "tone": "danger" if fail_count else "ok",
        },
        {
            "label": "黄色",
            "value": str(warn_count),
            "description": "队列积压、投影延迟、缺 owner 等需关注项。",
            "tone": "warn" if warn_count else "ok",
        },
        {
            "label": "绿色",
            "value": str(ok_count),
            "description": "当前证据已经通过的治理检查。",
            "tone": "ok",
        },
        {
            "label": "待接入",
            "value": str(pending_count),
            "description": "未配置 DB 探针或仍待接生产安全读仓库的检查。",
            "tone": "neutral" if pending_count else "ok",
        },
    ]


def _data_quality_cards(summary: dict) -> list[dict[str, str]]:
    severity_counts = summary.get("severity_counts") or {}
    probe_status_counts = summary.get("probe_status_counts") or {}
    return [
        {
            "label": "规则总数",
            "value": str(int(summary.get("total_checks") or 0)),
            "description": "已注册为运营可读问题清单的数据质量规则。",
            "tone": "neutral",
        },
        {
            "label": "红色规则",
            "value": str(int(severity_counts.get("red") or 0)),
            "description": "后续探针命中后应阻断迁移或上线的规则。",
            "tone": "danger" if int(severity_counts.get("red") or 0) else "ok",
        },
        {
            "label": "黄色规则",
            "value": str(int(severity_counts.get("yellow") or 0)),
            "description": "命中后需要运营或工程关注的规则。",
            "tone": "warn" if int(severity_counts.get("yellow") or 0) else "ok",
        },
        {
            "label": "待接探针",
            "value": str(int(probe_status_counts.get("needs_probe") or 0)),
            "description": "当前只注册元数据，尚未接生产安全只读探针。",
            "tone": "neutral",
        },
    ]


def _data_quality_grouped_checks(groups: list[dict], checks: list[dict]) -> list[dict]:
    checks_by_group: dict[str, list[dict]] = {}
    for check in checks:
        checks_by_group.setdefault(str(check.get("group") or ""), []).append(check)
    return [
        {
            **group,
            "checks": checks_by_group.get(str(group.get("group") or ""), []),
        }
        for group in groups
    ]


def _delivery_lineage_filters(request: Request) -> dict[str, str]:
    params = request.query_params
    return {
        "unionid": str(params.get("unionid") or "").strip(),
        "broadcast_job_id": str(params.get("broadcast_job_id") or "").strip(),
        "external_effect_job_id": str(params.get("external_effect_job_id") or "").strip(),
        "trace_id": str(params.get("trace_id") or "").strip(),
    }


def _delivery_lineage_payload(filters: dict[str, str]) -> dict:
    if filters["broadcast_job_id"]:
        return get_delivery_lineage(f"broadcast:{filters['broadcast_job_id']}")
    if filters["external_effect_job_id"]:
        return get_delivery_lineage(f"external_effect:{filters['external_effect_job_id']}")
    if filters["unionid"]:
        return list_delivery_lineage_by_unionid(filters["unionid"])
    if filters["trace_id"]:
        return list_delivery_lineage_by_trace(filters["trace_id"])
    return list_delivery_lineage()


def _growth_orchestration_payload(*, program_key: str = "") -> dict:
    programs = list_growth_programs(limit=50).get("items") or []
    members = list_growth_members(limit=50).get("items") or []
    tasks = list_growth_tasks(limit=50).get("items") or []
    touchpoints = list_growth_touchpoints(limit=50).get("items") or []
    if program_key:
        programs = [item for item in programs if item.get("program_key") == program_key]
        members = [item for item in members if item.get("program_key") == program_key]
        tasks = [item for item in tasks if item.get("program_key") == program_key]
        touchpoints = [item for item in touchpoints if item.get("program_key") == program_key]
    return {
        "selected_program_key": program_key,
        "growth_programs": programs,
        "growth_members": members,
        "growth_tasks": tasks,
        "growth_touchpoints": touchpoints,
        "growth_summary_cards": [
            {"label": "Programs", "value": str(len(programs)), "description": "统一运营项目数量。"},
            {"label": "Members", "value": str(len(members)), "description": "按 unionid 关联的成员记录。"},
            {"label": "Tasks", "value": str(len(tasks)), "description": "执行任务 read model。"},
            {"label": "Touchpoints", "value": str(len(touchpoints)), "description": "触达记录 read model。"},
        ],
    }
