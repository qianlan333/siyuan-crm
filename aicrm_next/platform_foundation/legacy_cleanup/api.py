from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from aicrm_next.admin_jobs.routes import validate_admin_action_token
from aicrm_next.shared.runtime_settings import runtime_setting

from . import CAPABILITY_OWNER, ROUTE_OWNER
from .service import LegacyWebhookCleanupService

router = APIRouter()


def _text(value: Any) -> str:
    return str(value or "").strip()


async def _payload(request: Request) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception:
        return {}
    return dict(raw or {}) if isinstance(raw, dict) else {}


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    payload.setdefault("route_owner", ROUTE_OWNER)
    payload.setdefault("capability_owner", CAPABILITY_OWNER)
    payload.setdefault("real_external_call_executed", False)
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={
            "X-AICRM-Route-Owner": ROUTE_OWNER,
            "X-AICRM-Real-External-Call-Executed": "true" if bool(payload.get("real_external_call_executed")) else "false",
        },
    )


def _int(value: Any, *, default: int = 50, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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


@router.get("/api/admin/legacy-webhook-cleanup/status")
def legacy_webhook_cleanup_status(
    legacy_key: str = "",
    legacy_type: str = "",
    legacy_module: str = "",
    status: str = "",
    delete_status: str = "",
) -> JSONResponse:
    payload = LegacyWebhookCleanupService().status(
        {
            "legacy_key": legacy_key,
            "legacy_type": legacy_type,
            "legacy_module": legacy_module,
            "status": status,
            "delete_status": delete_status,
        }
    )
    return _json(payload)


@router.post("/api/admin/legacy-webhook-cleanup/deprecations/mark")
async def legacy_webhook_cleanup_mark_deprecated(request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    result = LegacyWebhookCleanupService().mark_default_deprecations(operator=_text(payload.get("operator")) or "api")
    return _json(result)


@router.post("/api/admin/legacy-webhook-cleanup/run-due/preview")
async def legacy_webhook_cleanup_preview(request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    result = LegacyWebhookCleanupService().preview_due(limit=_int(payload.get("limit"), default=50))
    return _json(result)


@router.post("/api/admin/legacy-webhook-cleanup/run-due")
async def legacy_webhook_cleanup_run_due(request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    dry_run = _bool(payload.get("dry_run"), default=True)
    result = LegacyWebhookCleanupService().run_due(
        dry_run=dry_run,
        limit=_int(payload.get("limit"), default=50),
        operator=_text(payload.get("operator")) or "api",
    )
    return _json(result)


@router.post("/api/admin/legacy-webhook-cleanup/deprecations/retire-now")
async def legacy_webhook_cleanup_retire_now(request: Request) -> JSONResponse:
    payload = await _payload(request)
    token_error = _action_or_internal_token_error(request, payload)
    if token_error:
        return _json({"ok": False, "error": token_error}, status_code=401)
    dry_run = _bool(payload.get("dry_run"), default=True)
    result = LegacyWebhookCleanupService().retire_now(
        dry_run=dry_run,
        limit=_int(payload.get("limit"), default=50),
        operator=_text(payload.get("operator")) or "api",
    )
    return _json(result)
