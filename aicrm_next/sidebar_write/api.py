from __future__ import annotations

from typing import Any, Type
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from .application import (
    SidebarWriteConflictError,
    SidebarWriteInputError,
    SidebarWriteNotFoundError,
    SidebarWriteProductionUnavailableError,
    execute_sidebar_write,
)
from .commands import (
    BindMobileCommand,
    MarkEnrolledCommand,
    MarkSignupTagCommand,
    PlanMaterialSendCommand,
    SetFollowupSegmentCommand,
    SidebarWriteCommand,
    UnmarkEnrolledCommand,
    UpdateSidebarProfileCommand,
    UpsertLeadPoolClassTermCommand,
)

router = APIRouter()


@router.api_route("/api/sidebar/bind-mobile", methods=["POST", "OPTIONS"])
async def bind_mobile(request: Request):
    return await _execute(request, BindMobileCommand)


@router.api_route("/api/sidebar/lead-pool/upsert-class-term", methods=["POST", "OPTIONS"])
async def upsert_lead_pool_class_term(request: Request):
    return await _execute(request, UpsertLeadPoolClassTermCommand)


@router.api_route("/api/sidebar/signup-tags/mark", methods=["POST", "OPTIONS"])
async def mark_signup_tag(request: Request):
    return await _execute(request, MarkSignupTagCommand)


@router.api_route("/api/sidebar/marketing-status/set-followup-segment", methods=["POST", "OPTIONS"])
async def set_followup_segment(request: Request):
    return await _execute(request, SetFollowupSegmentCommand)


@router.api_route("/api/sidebar/marketing-status/mark-enrolled", methods=["POST", "OPTIONS"])
async def mark_enrolled(request: Request):
    return await _execute(request, MarkEnrolledCommand)


@router.api_route("/api/sidebar/marketing-status/unmark-enrolled", methods=["POST", "OPTIONS"])
async def unmark_enrolled(request: Request):
    return await _execute(request, UnmarkEnrolledCommand)


@router.api_route("/api/sidebar/v2/profile", methods=["PUT", "OPTIONS"])
async def update_sidebar_v2_profile(request: Request):
    return await _execute(request, UpdateSidebarProfileCommand)


@router.api_route("/api/sidebar/v2/materials/send", methods=["POST", "OPTIONS"])
async def plan_material_send(request: Request):
    return await _execute(request, PlanMaterialSendCommand)


async def _execute(request: Request, command_type: Type[SidebarWriteCommand]) -> Response:
    if request.method == "OPTIONS":
        return Response(status_code=204)
    try:
        body = await _json_body(request)
        command = command_type(
            idempotency_key=_idempotency_key(request, body),
            actor_id=str(body.get("actor_id") or request.headers.get("X-AICRM-Actor-Id") or "sidebar_operator"),
            actor_type=str(body.get("actor_type") or request.headers.get("X-AICRM-Actor-Type") or "user"),
            external_userid=str(body.get("external_userid") or "").strip(),
            payload={key: value for key, value in body.items() if key not in {"actor_id", "actor_type", "external_userid", "idempotency_key", "dry_run", "trace_id"}},
            dry_run=_as_bool(body.get("dry_run")),
            source_route=request.url.path,
            trace_id=str(body.get("trace_id") or request.headers.get("X-Request-Id") or uuid4().hex),
        )
        payload = execute_sidebar_write(command)
        return JSONResponse(jsonable_encoder(payload), status_code=200)
    except SidebarWriteInputError as exc:
        return _error(str(exc), status_code=400, source_status="input_error", write_model_status="input_error")
    except SidebarWriteConflictError as exc:
        return _error(str(exc), status_code=409, source_status="conflict", write_model_status="conflict")
    except SidebarWriteNotFoundError as exc:
        return _error(str(exc), status_code=404, source_status="not_found", write_model_status="not_found")
    except SidebarWriteProductionUnavailableError as exc:
        return _error(str(exc), status_code=503, source_status="production_unavailable", write_model_status="unavailable", degraded=True)


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise SidebarWriteInputError("json object body is required")
    return payload


def _idempotency_key(request: Request, body: dict[str, Any]) -> str:
    return str(request.headers.get("Idempotency-Key") or body.get("idempotency_key") or "").strip()


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _error(
    message: str,
    *,
    status_code: int,
    source_status: str,
    write_model_status: str,
    degraded: bool = False,
) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": message,
            "source_status": source_status,
            "write_model_status": write_model_status,
            "route_owner": "ai_crm_next",
            "fallback_used": False,
            "real_external_call_executed": False,
            "degraded": degraded,
        },
        status_code=status_code,
    )
