from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_jobs.routes import ensure_admin_action_token, validate_admin_action_token
from aicrm_next.admin_shell import admin_path_for, shell_context
from aicrm_next.platform_foundation.external_effects.service import ExternalEffectService

from . import CAPABILITY_OWNER, ROUTE_OWNER
from .repository import PushCenterRepository
from .view_model import (
    build_job_detail_payload,
    build_job_reconciliation_payload,
    build_jobs_payload,
    build_sections_payload,
    build_stats_payload,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FRONTEND_COMPAT_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=[_TEMPLATES_DIR, _FRONTEND_COMPAT_TEMPLATES_DIR])


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int = 0, minimum: int = 0, maximum: int = 10**12) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


async def _payload(request: Request) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception:
        return {}
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    payload.setdefault("route_owner", ROUTE_OWNER)
    payload.setdefault("real_external_call_executed", False)
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={
            "X-AICRM-Route-Owner": ROUTE_OWNER,
            "X-AICRM-Real-External-Call-Executed": "true" if bool(payload.get("real_external_call_executed")) else "false",
        },
    )


def _internal_token_error(request: Request) -> str:
    header = _text(request.headers.get("Authorization"))
    if not header.lower().startswith("bearer "):
        return "internal_token_required"
    expected = _text(os.getenv("AUTOMATION_INTERNAL_API_TOKEN"))
    if not expected:
        return "automation_internal_token_not_configured"
    actual = header.split(" ", 1)[1].strip()
    if not hmac.compare_digest(actual, expected):
        return "internal_token_required"
    return ""


def _action_or_internal_token_error(request: Request, payload: dict[str, Any]) -> str:
    internal_error = _internal_token_error(request)
    if not internal_error:
        return ""
    token = _text(request.headers.get("X-Admin-Action-Token")) or _text(payload.get("admin_action_token"))
    return validate_admin_action_token(token)


def _page_context(request: Request, *, page_notice: str = "", page_error: str = "", action_result: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = build_jobs_payload(dict(request.query_params), repository=PushCenterRepository())
    selected_job_id = _int(request.query_params.get("job_id"), default=0)
    selected_job = build_job_detail_payload(selected_job_id, repository=PushCenterRepository()) if selected_job_id else None
    context = shell_context(
        request=request,
        page_title="推送中心",
        page_summary="按业务板块查看推送任务、执行状态和 attempts。",
        active_endpoint="api.admin_push_center_page",
    )
    context.update(
        {
            "breadcrumbs": [{"label": "客户管理后台", "href": "/"}, {"label": "推送中心", "href": ""}],
            "push_center": payload,
            "selected_job": selected_job,
            "page_notice": page_notice,
            "page_error": page_error,
            "action_result": action_result or {},
            "page_actions": [
                {"label": "刷新", "href": "#refresh", "variant": "secondary"},
                {"label": "导出当前筛选", "href": "#export", "variant": "secondary"},
            ],
            "admin_action_token": ensure_admin_action_token(),
            "url_for": admin_path_for,
        }
    )
    return context


@router.get("/admin/push-center", name="api.admin_push_center_page", response_class=HTMLResponse)
def admin_push_center_page(request: Request):
    return templates.TemplateResponse(request, "admin_console/push_center.html", _page_context(request))


@router.get("/api/admin/push-center/sections")
def push_center_sections(
    section: str = "",
    effect_type: str = "",
    status: str = "",
    business_type: str = "",
    business_id: str = "",
    target_type: str = "",
    target_id: str = "",
    external_userid: str = "",
    owner_userid: str = "",
    trace_id: str = "",
    idempotency_key: str = "",
    source_module: str = "",
    source_route: str = "",
    created_from: str = "",
    created_to: str = "",
) -> dict[str, Any]:
    return build_sections_payload(locals(), repository=PushCenterRepository())


@router.get("/api/admin/push-center/jobs")
def push_center_jobs(
    section: str = "",
    effect_type: str = "",
    status: str = "",
    business_type: str = "",
    business_id: str = "",
    target_type: str = "",
    target_id: str = "",
    external_userid: str = "",
    owner_userid: str = "",
    trace_id: str = "",
    idempotency_key: str = "",
    source_module: str = "",
    source_route: str = "",
    created_from: str = "",
    created_to: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return build_jobs_payload(locals(), repository=PushCenterRepository())


@router.get("/api/admin/push-center/jobs/{job_id}")
def push_center_job_detail(job_id: str) -> JSONResponse:
    payload = build_job_detail_payload(job_id, repository=PushCenterRepository())
    if not payload:
        return _json({"ok": False, "error": "push_center_job_not_found"}, status_code=404)
    return _json(payload)


@router.get("/api/admin/push-center/jobs/{job_id}/reconciliation")
def push_center_job_reconciliation(job_id: str) -> JSONResponse:
    payload = build_job_reconciliation_payload(job_id, repository=PushCenterRepository())
    if not payload:
        return _json({"ok": False, "error": "push_center_job_not_found"}, status_code=404)
    return _json(payload)


@router.get("/api/admin/push-center/stats")
def push_center_stats(
    section: str = "",
    effect_type: str = "",
    status: str = "",
    business_type: str = "",
    business_id: str = "",
    target_type: str = "",
    target_id: str = "",
    external_userid: str = "",
    owner_userid: str = "",
    trace_id: str = "",
    idempotency_key: str = "",
    source_module: str = "",
    source_route: str = "",
    created_from: str = "",
    created_to: str = "",
) -> dict[str, Any]:
    payload = build_stats_payload(locals(), repository=PushCenterRepository())
    payload["capability_owner"] = CAPABILITY_OWNER
    return payload


@router.post("/api/admin/push-center/jobs/{job_id}/retry")
async def push_center_retry_job(job_id: int, request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    job = ExternalEffectService().retry(job_id)
    if not job:
        return _json({"ok": False, "error": "push_center_job_not_retryable"}, status_code=409)
    detail = build_job_detail_payload(job.id, repository=PushCenterRepository())
    return _json({"ok": True, "job": detail["job"] if detail else job.to_dict()})


@router.post("/api/admin/push-center/jobs/{job_id}/cancel")
async def push_center_cancel_job(job_id: int, request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    job = ExternalEffectService().cancel(job_id)
    if not job:
        return _json({"ok": False, "error": "push_center_job_not_cancellable"}, status_code=409)
    detail = build_job_detail_payload(job.id, repository=PushCenterRepository())
    return _json({"ok": True, "job": detail["job"] if detail else job.to_dict()})
