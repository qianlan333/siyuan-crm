from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from aicrm_next.integration_gateway.wecom_jssdk_adapter import (
    SidebarJSSDKConfigError,
    SidebarJSSDKInputError,
    build_sidebar_jssdk_config,
    normalize_jssdk_url,
)
from aicrm_next.shared.runtime import production_environment
from aicrm_next.shared.signed_context import build_sidebar_owner_context_token, sidebar_owner_context_ttl_seconds

from .application import ListExternalContactOwnerCandidatesQuery


router = APIRouter()
DEFAULT_SIDEBAR_JSSDK_ALLOWED_HOSTS = {"youcangogogo.com", "www.youcangogogo.com"}


@router.api_route("/api/sidebar/jssdk-config", methods=["GET", "HEAD", "OPTIONS"])
async def sidebar_jssdk_config(request: Request) -> Response:
    if request.method == "HEAD":
        return Response(status_code=204)
    if request.method == "OPTIONS":
        return JSONResponse(
            {
                "ok": True,
                "source_status": "next_jssdk_adapter",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "adapter_mode": "real_blocked",
                "real_external_call_executed": False,
                "allowed_methods": ["GET", "HEAD", "OPTIONS"],
            },
            status_code=200,
        )

    params = request.query_params
    corp_context = {
        "corp_id": str(params.get("corp_id") or params.get("corpId") or params.get("corpid") or "").strip(),
        "agent_id": str(params.get("agent_id") or params.get("agentId") or params.get("agentid") or "").strip(),
    }
    corp_context = {key: value for key, value in corp_context.items() if value}
    debug = str(params.get("debug") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        _validate_jssdk_url_host(request, str(params.get("url") or ""))
        payload = build_sidebar_jssdk_config(
            url=str(params.get("url") or ""),
            debug=debug,
            corp_context=corp_context,
        )
        payload = _with_sidebar_owner_context(request, payload)
    except SidebarJSSDKInputError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
                "source_status": "input_error",
                "adapter_mode": "real_blocked",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "real_external_call_executed": False,
            },
            status_code=400,
        )
    except SidebarJSSDKConfigError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
                "source_status": "config_error",
                "adapter_mode": "real_enabled",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "real_external_call_executed": bool(getattr(exc, "real_external_call_executed", False)),
            },
            status_code=502,
        )
    return JSONResponse(jsonable_encoder(payload), status_code=200)


def _with_sidebar_owner_context(request: Request, payload: dict) -> dict:
    result = dict(payload)
    viewer_userid = _viewer_userid_from_request(request)
    external_userid = _external_userid_from_request(request)
    owner_candidates = _owner_userids_from_external_userid(external_userid)
    source = "sidebar_jssdk_request_context"
    status = "issued"
    if viewer_userid and owner_candidates and viewer_userid not in owner_candidates:
        return _without_sidebar_owner_token(
            result,
            status="viewer_not_in_contact_owner_scope",
            external_userid=external_userid,
            source="sidebar_jssdk_viewer_scope_rejected",
            owner_candidates_count=len(owner_candidates),
        )
    if not viewer_userid:
        viewer_userid = next(iter(owner_candidates)) if len(owner_candidates) == 1 else ""
        source = "sidebar_jssdk_identity_owner_fallback" if viewer_userid else "missing"
        status = "issued_identity_owner" if viewer_userid else "viewer_missing_multi_owner" if owner_candidates else "viewer_missing"
        if not viewer_userid:
            return _without_sidebar_owner_token(
                result,
                status=status,
                external_userid=external_userid,
                source="sidebar_jssdk_viewer_required" if owner_candidates else source,
                owner_candidates_count=len(owner_candidates),
            )
    ttl_seconds = sidebar_owner_context_ttl_seconds()
    result["sidebar_owner_token"] = build_sidebar_owner_context_token(
        viewer_userid=viewer_userid,
        corp_id=str(result.get("corp_id") or result.get("corpId") or ""),
        bind_by_userid=_bind_by_userid_from_request(request) or viewer_userid,
        ttl_seconds=ttl_seconds,
    )
    result["sidebar_owner_token_status"] = status
    result["sidebar_owner_context"] = {
        "viewer_userid": viewer_userid,
        "owner_userid": viewer_userid,
        "bind_by_userid": _bind_by_userid_from_request(request) or viewer_userid,
        "corp_id": str(result.get("corp_id") or result.get("corpId") or ""),
        "external_userid": _external_userid_from_request(request),
        "expires_in": ttl_seconds,
        "source": source,
        "owner_candidates_count": len(owner_candidates),
    }
    return result


def _without_sidebar_owner_token(
    payload: dict,
    *,
    status: str,
    external_userid: str = "",
    source: str = "missing",
    owner_candidates_count: int = 0,
) -> dict:
    result = dict(payload)
    result["sidebar_owner_token"] = ""
    result["sidebar_owner_token_status"] = status
    context = {"source": source, "owner_candidates_count": owner_candidates_count}
    if external_userid:
        context["external_userid"] = external_userid
    result["sidebar_owner_context"] = context
    return result


def _viewer_userid_from_request(request: Request) -> str:
    params = request.query_params
    for value in (
        params.get("viewer_userid"),
        params.get("viewerUserId"),
        params.get("operator_userid"),
        params.get("operatorUserId"),
        params.get("owner_userid"),
        params.get("ownerUserid"),
        params.get("userid"),
        request.headers.get("x-wecom-viewer-userid"),
        request.headers.get("x-wecom-userid"),
        request.headers.get("x-aicrm-sidebar-viewer-userid"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _bind_by_userid_from_request(request: Request) -> str:
    params = request.query_params
    for value in (
        params.get("bind_by_userid"),
        params.get("bindByUserid"),
        params.get("operator_userid"),
        params.get("operatorUserId"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _external_userid_from_request(request: Request) -> str:
    params = request.query_params
    for value in (
        params.get("external_userid"),
        params.get("externalUserid"),
        params.get("external_userId"),
        params.get("externalUserId"),
        params.get("user_id"),
        params.get("userId"),
        request.headers.get("x-wecom-external-userid"),
        request.headers.get("x-aicrm-sidebar-external-userid"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def _owner_userids_from_external_userid(external_userid: str) -> set[str]:
    normalized_external = str(external_userid or "").strip()
    if not normalized_external:
        return set()
    try:
        return ListExternalContactOwnerCandidatesQuery()(external_userid=normalized_external)
    except Exception:
        return set()


def _validate_jssdk_url_host(request: Request, raw_url: str) -> None:
    if not production_environment():
        return
    normalized_url = normalize_jssdk_url(raw_url)
    requested_host = str(urlparse(normalized_url).hostname or "").strip().lower()
    if not requested_host:
        raise SidebarJSSDKInputError("url host is required")
    allowed_hosts = _allowed_jssdk_hosts(request)
    if requested_host not in allowed_hosts:
        raise SidebarJSSDKInputError("url host is not allowed for sidebar jssdk signing")


def _allowed_jssdk_hosts(request: Request) -> set[str]:
    hosts = {
        *DEFAULT_SIDEBAR_JSSDK_ALLOWED_HOSTS,
        str(request.url.hostname or "").strip().lower(),
        str(request.headers.get("host") or "").split(":", 1)[0].strip().lower(),
    }
    configured = str(os.getenv("AICRM_SIDEBAR_JSSDK_ALLOWED_HOSTS") or "")
    hosts.update(item.strip().lower() for item in configured.split(",") if item.strip())
    return {host for host in hosts if host}
