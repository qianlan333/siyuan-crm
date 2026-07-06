from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from aicrm_next.admin_auth.guards import admin_api_auth_error, current_admin_session
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError

from .draft_service import GroupOpsWorkspaceDraftService


router = APIRouter()

_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
}


def _safe_error(error: str, detail: str, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": error,
            "detail": detail,
            "route_owner": "ai_crm_next",
            "capability_owner": "automation_engine",
            "preview_only": True,
            "production_write": False,
            "ready_for_review": False,
            "approved": False,
            "real_external_call": False,
            "real_external_call_executed": False,
            "push_center_job_created": False,
            "external_effect_job_created": False,
            "broadcast_job_created": False,
            "internal_event_created": False,
            "can_claim_pass_90_plus": False,
            "execution_status": "not_execution",
        },
        status_code=status_code,
        headers=_HEADERS,
    )


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")
    return dict(payload)


def _service_result(callable_result) -> JSONResponse:
    try:
        payload = callable_result()
        return JSONResponse(jsonable_encoder(payload), status_code=200, headers=_HEADERS)
    except NotFoundError as exc:
        return _safe_error("not_found", str(exc), status_code=404)
    except ContractError as exc:
        message = str(exc)
        if "conflict" in message:
            return _safe_error("conflict", message, status_code=409)
        return _safe_error("contract_error", message, status_code=400)
    except RepositoryProviderError as exc:
        return _safe_error("draft_repository_unavailable", str(exc), status_code=503)


def _admin_actor_or_response(request: Request) -> dict[str, Any] | JSONResponse:
    if auth := admin_api_auth_error(request):
        return auth
    return current_admin_session(request) or {}


@router.get("/api/admin/p1/group-ops-workspace/drafts", name="api.admin_p1_group_ops_workspace_drafts")
def list_group_ops_workspace_drafts(
    request: Request,
    status: str = "",
    source_plan_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _service_result(lambda: GroupOpsWorkspaceDraftService().list_drafts({"status": status, "source_plan_id": source_plan_id, "limit": limit, "offset": offset}))


@router.get("/api/admin/p1/group-ops-workspace/drafts/{draft_id}", name="api.admin_p1_group_ops_workspace_draft_detail")
def get_group_ops_workspace_draft(draft_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _service_result(lambda: GroupOpsWorkspaceDraftService().get_draft(draft_id))


@router.post("/api/admin/p1/group-ops-workspace/drafts", name="api.admin_p1_group_ops_workspace_draft_create")
async def create_group_ops_workspace_draft(request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceDraftService().create_draft(payload, actor=actor))


@router.patch("/api/admin/p1/group-ops-workspace/drafts/{draft_id}", name="api.admin_p1_group_ops_workspace_draft_update")
async def update_group_ops_workspace_draft(draft_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceDraftService().update_draft(draft_id, payload, actor=actor))


@router.post("/api/admin/p1/group-ops-workspace/drafts/{draft_id}/archive", name="api.admin_p1_group_ops_workspace_draft_archive")
async def archive_group_ops_workspace_draft(draft_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceDraftService().archive_draft(draft_id, payload, actor=actor))


@router.post(
    "/api/admin/p1/group-ops-workspace/drafts/{draft_id}/request-review",
    name="api.admin_p1_group_ops_workspace_draft_request_review",
)
async def request_review_group_ops_workspace_draft(draft_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceDraftService().request_review(draft_id, payload, actor=actor))
