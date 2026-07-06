from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from aicrm_next.admin_auth.guards import admin_api_auth_error, current_admin_session
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError

from .governance_service import GroupOpsWorkspaceGovernanceService


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
            "approved": False,
            "ready_for_review": False,
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
        if (
            "conflict" in message
            or "active governance review exists" in message
            or "already transitioned" in message
            or "already expired" in message
            or "already bridged" in message
            or "mismatch" in message
        ):
            return _safe_error("conflict", message, status_code=409)
        return _safe_error("contract_error", message, status_code=400)
    except RepositoryProviderError as exc:
        return _safe_error("governance_repository_unavailable", str(exc), status_code=503)


def _admin_actor_or_response(request: Request) -> dict[str, Any] | JSONResponse:
    if auth := admin_api_auth_error(request):
        return auth
    return current_admin_session(request) or {}


@router.post(
    "/api/admin/p1/group-ops-workspace/drafts/{draft_id}/governance/request",
    name="api.admin_p1_group_ops_workspace_governance_request",
)
async def request_group_ops_workspace_governance(draft_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().request_governance(draft_id, payload, actor=actor))


@router.get(
    "/api/admin/p1/group-ops-workspace/governance/{review_id}",
    name="api.admin_p1_group_ops_workspace_governance_detail",
)
def get_group_ops_workspace_governance(review_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().get_review(review_id))


@router.get(
    "/api/admin/p1/group-ops-workspace/drafts/{draft_id}/governance",
    name="api.admin_p1_group_ops_workspace_draft_governance_list",
)
def list_group_ops_workspace_draft_governance(draft_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().list_reviews_for_draft(draft_id))


@router.post(
    "/api/admin/p1/group-ops-workspace/governance/{review_id}/steps/{step_id}/approve",
    name="api.admin_p1_group_ops_workspace_governance_step_approve",
)
async def approve_group_ops_workspace_governance_step(review_id: str, step_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().approve_step(review_id, step_id, payload, actor=actor))


@router.post(
    "/api/admin/p1/group-ops-workspace/governance/{review_id}/steps/{step_id}/reject",
    name="api.admin_p1_group_ops_workspace_governance_step_reject",
)
async def reject_group_ops_workspace_governance_step(review_id: str, step_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().reject_step(review_id, step_id, payload, actor=actor))


@router.post(
    "/api/admin/p1/group-ops-workspace/governance/{review_id}/expire",
    name="api.admin_p1_group_ops_workspace_governance_expire",
)
async def expire_group_ops_workspace_governance(review_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().expire_review(review_id, payload, actor=actor))


@router.post(
    "/api/admin/p1/group-ops-workspace/governance/{review_id}/bridge-push-center",
    name="api.admin_p1_group_ops_workspace_governance_bridge_push_center",
)
async def bridge_group_ops_workspace_governance_push_center(review_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    payload = await _json_body(request)
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().bridge_push_center(review_id, payload, actor=actor))


@router.get(
    "/api/admin/p1/group-ops-workspace/governance/{review_id}/push-center-bridge",
    name="api.admin_p1_group_ops_workspace_governance_push_center_bridge_detail",
)
def get_group_ops_workspace_governance_push_center_bridge(review_id: str, request: Request) -> JSONResponse:
    actor = _admin_actor_or_response(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _service_result(lambda: GroupOpsWorkspaceGovernanceService().get_push_center_bridge(review_id))
