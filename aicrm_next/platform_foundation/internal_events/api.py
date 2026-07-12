from __future__ import annotations

import hmac
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from aicrm_next.admin_jobs.routes import ensure_admin_action_token, validate_admin_action_token
from aicrm_next.admin_shell import admin_path_for, shell_context
from aicrm_next.shared.runtime_settings import runtime_setting

from .config import diagnostics_payload as config_diagnostics_payload, worker_batch_size
from .repository import build_internal_event_repository
from .service import InternalEventService
from .view_model import build_diagnostics_payload, build_event_detail_payload, build_events_payload
from .worker import InternalEventWorker

router = APIRouter()
ROUTE_OWNER = "ai_crm_next"
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_FRONTEND_COMPAT_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=[_TEMPLATES_DIR, _FRONTEND_COMPAT_TEMPLATES_DIR])


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bool(value: Any, *, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


async def _payload(request: Request) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception:
        return {}
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    payload.setdefault("route_owner", ROUTE_OWNER)
    payload.setdefault("real_external_call_executed", False)
    headers = {
        "X-AICRM-Route-Owner": ROUTE_OWNER,
        "X-AICRM-Real-External-Call-Executed": "true" if bool(payload.get("real_external_call_executed")) else "false",
    }
    return JSONResponse(_json_safe(payload), status_code=status_code, headers=headers)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if hasattr(value, "obj") and value.__class__.__module__.startswith("psycopg.types.json"):
        return _json_safe(value.obj)
    return value


def _internal_token_error(request: Request) -> str:
    header = _text(request.headers.get("Authorization"))
    if not header.lower().startswith("bearer "):
        return "internal_token_required"
    expected = _text(runtime_setting("AUTOMATION_INTERNAL_API_TOKEN"))
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
    return validate_admin_action_token(token, request=request)


def _service() -> InternalEventService:
    return InternalEventService(build_internal_event_repository())


def _csv(value: Any) -> list[str] | None:
    if isinstance(value, list):
        items = [_text(item) for item in value if _text(item)]
    else:
        items = [_text(item) for item in _text(value).split(",") if _text(item)]
    return items or None


def _page_context(request: Request) -> dict[str, Any]:
    payload = build_events_payload(dict(request.query_params), repository=build_internal_event_repository())
    selected_event_id = _text(request.query_params.get("event_id"))
    selected_event = build_event_detail_payload(selected_event_id, service=_service()) if selected_event_id else None
    context = shell_context(
        request=request,
        page_title="事件中心",
        page_summary="查看内部业务事实和每个消费者的执行状态。",
        active_endpoint="api.admin_internal_events_page",
    )
    context.update(
        {
            "breadcrumbs": [{"label": "客户管理后台", "href": "/"}, {"label": "事件中心", "href": ""}],
            "internal_events": payload,
            "selected_event": selected_event,
            "page_actions": [
                {"label": "刷新", "href": "#refresh", "variant": "secondary"},
                {"label": "导出当前筛选", "href": "#export", "variant": "secondary"},
            ],
            "admin_action_token": ensure_admin_action_token(),
            "url_for": admin_path_for,
        }
    )
    return context


@router.get("/admin/internal-events", name="api.admin_internal_events_page", response_class=HTMLResponse)
def admin_internal_events_page(request: Request):
    return templates.TemplateResponse(request, "admin_console/internal_events.html", _page_context(request))


@router.get("/api/admin/internal-events")
def list_internal_events(
    event_section: str = "",
    event_type: str = "",
    aggregate_type: str = "",
    aggregate_id: str = "",
    subject_type: str = "",
    subject_id: str = "",
    consumer_name: str = "",
    consumer_status: str = "",
    trace_id: str = "",
    trace_hash: str = "",
    original_trace_hash: str = "",
    source_module: str = "",
    created_from: str = "",
    created_to: str = "",
    idempotency_key: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    return build_events_payload(locals(), repository=build_internal_event_repository())


@router.get("/api/admin/internal-events/diagnostics")
def internal_events_diagnostics(
    event_section: str = "",
    event_type: str = "",
    consumer_name: str = "",
    consumer_status: str = "",
    trace_hash: str = "",
    original_trace_hash: str = "",
) -> dict[str, Any]:
    payload = build_diagnostics_payload(locals(), service=_service())
    payload["config"] = config_diagnostics_payload()
    payload.update(config_diagnostics_payload())
    return payload


@router.post("/api/admin/internal-events/run-due/preview")
async def preview_internal_event_run_due(request: Request) -> JSONResponse:
    token_error = _internal_token_error(request)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    payload = await _payload(request)
    result = await run_in_threadpool(
        InternalEventWorker(build_internal_event_repository()).preview_due,
        batch_size=_int(payload.get("batch_size") or payload.get("limit"), default=worker_batch_size(), minimum=1),
        event_types=_csv(payload.get("event_types")),
        consumer_names=_csv(payload.get("consumer_names")),
    )
    return _json(result)


@router.post("/api/admin/internal-events/run-due")
async def run_internal_event_due(request: Request) -> JSONResponse:
    token_error = _internal_token_error(request)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    payload = await _payload(request)
    result = await run_in_threadpool(
        InternalEventWorker(build_internal_event_repository()).run_due,
        batch_size=_int(payload.get("batch_size") or payload.get("limit"), default=worker_batch_size(), minimum=1),
        dry_run=_bool(payload.get("dry_run"), default=True),
        event_types=_csv(payload.get("event_types")),
        consumer_names=_csv(payload.get("consumer_names")),
    )
    return _json(result)


@router.get("/api/admin/internal-events/{event_id}")
def get_internal_event(event_id: str) -> JSONResponse:
    payload = build_event_detail_payload(event_id, service=_service())
    if not payload:
        return _json({"ok": False, "error": "internal_event_not_found"}, status_code=404)
    return _json(payload)


@router.get("/api/admin/internal-events/{event_id}/reconciliation")
def get_internal_event_reconciliation(event_id: str) -> JSONResponse:
    service = _service()
    if not service.get_event(event_id):
        return _json({"ok": False, "error": "internal_event_not_found"}, status_code=404)
    return _json(
        {
            "ok": True,
            "reconciliation": service.get_event_reconciliation(event_id),
            "route_owner": ROUTE_OWNER,
            "real_external_call_executed": False,
        }
    )


@router.post("/api/admin/internal-events/{event_id}/consumers/{consumer_name}/run")
async def run_internal_event_consumer(event_id: str, consumer_name: str, request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    result = await run_in_threadpool(
        InternalEventWorker(build_internal_event_repository()).dispatch_one_consumer,
        event_id,
        consumer_name,
        dry_run=_bool(payload.get("dry_run"), default=True),
        force=_bool(payload.get("force"), default=False),
        reason=_text(payload.get("reason")),
    )
    if result.get("ok"):
        return _json(result)
    error = _text(result.get("error"))
    status_code = 404 if error in {"consumer_run_not_found", "internal_event_not_found"} else 409
    return _json(result, status_code=status_code)


@router.post("/api/admin/internal-events/{event_id}/consumers/{consumer_name}/retry")
async def retry_internal_event_consumer(event_id: str, consumer_name: str, request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    run = _service().retry_consumer_run(event_id, consumer_name)
    if not run:
        return _json({"ok": False, "error": "internal_event_consumer_run_not_retryable"}, status_code=409)
    return _json({"ok": True, "consumer_run": run.to_dict()})


@router.post("/api/admin/internal-events/{event_id}/consumers/{consumer_name}/skip")
async def skip_internal_event_consumer(event_id: str, consumer_name: str, request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    skipped = _service().skip_consumer_run(event_id, consumer_name, reason=_text(payload.get("reason")))
    if not skipped:
        return _json({"ok": False, "error": "internal_event_consumer_run_not_skippable"}, status_code=409)
    run, attempt = skipped
    return _json({"ok": True, "consumer_run": run.to_dict(), "attempt": attempt.to_dict()})
