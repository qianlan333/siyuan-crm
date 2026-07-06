from __future__ import annotations

import os
import secrets
from time import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse, Response

from aicrm_next.integration_gateway.wecom_jssdk_adapter import (
    SidebarJSSDKConfigError,
    SidebarJSSDKInputError,
    build_sidebar_jssdk_config,
    normalize_jssdk_url,
)
from aicrm_next.integration_gateway.wecom_admin_auth_client import (
    WeComAdminAuthClientError,
    build_wecom_admin_auth_client,
)
from aicrm_next.shared.runtime import production_environment
from aicrm_next.shared.signed_context import build_sidebar_owner_context_token, sidebar_owner_context_ttl_seconds
from aicrm_next.shared.signed_session import (
    ADMIN_SESSION_COOKIE,
    DEFAULT_SESSION_MAX_AGE_SECONDS,
    session_cookie_secure,
    sign_session_payload,
    sign_state_payload,
    verify_session_payload,
    verify_state_payload,
)

from .application import ListExternalContactOwnerCandidatesQuery


router = APIRouter()
DEFAULT_SIDEBAR_JSSDK_ALLOWED_HOSTS = {"youcangogogo.com", "www.youcangogogo.com"}
SIDEBAR_VIEWER_COOKIE = "aicrm_sidebar_viewer_session"
SIDEBAR_OAUTH_ENABLE_ENV = "AICRM_SIDEBAR_WECOM_OAUTH_ENABLE_REAL"
SIDEBAR_OAUTH_REDIRECT_URI_ENV = "AICRM_SIDEBAR_OAUTH_REDIRECT_URI"
ADMIN_AUTH_ENABLE_ENV = "AICRM_WECOM_ADMIN_AUTH_ENABLE_REAL"


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


@router.api_route("/api/sidebar/oauth/start", methods=["GET", "OPTIONS"])
def sidebar_oauth_start(request: Request) -> Response:
    if request.method == "OPTIONS":
        return JSONResponse(
            {
                "ok": True,
                "route": "/api/sidebar/oauth/start",
                "route_owner": "ai_crm_next",
                "source_status": "next_sidebar_oauth",
                "adapter_mode": "real_blocked",
                "fallback_used": False,
                "real_external_call_executed": False,
                "allowed_methods": ["GET", "OPTIONS"],
            },
            status_code=200,
        )

    external_userid = _external_userid_from_request(request) or _external_userid_from_path(
        str(request.query_params.get("next") or "")
    )
    next_path = _safe_sidebar_next_path(request.query_params.get("next"), external_userid=external_userid)
    oauth = _sidebar_oauth_config(request)
    if not external_userid:
        return _sidebar_oauth_error_response("external_userid_missing", next_path, status_code=400)
    if not oauth["enabled"]:
        return _sidebar_oauth_error_response("sidebar_oauth_not_enabled", next_path, status_code=503)
    missing = _sidebar_oauth_missing(oauth)
    if missing:
        return _sidebar_oauth_error_response("sidebar_oauth_config_missing", next_path, status_code=503)

    state = sign_state_payload(
        {
            "next": next_path,
            "external_userid": external_userid,
            "nonce": secrets.token_urlsafe(16),
            "iat": int(time()),
        }
    )
    query = urlencode(
        {
            "appid": oauth["corp_id"],
            "redirect_uri": oauth["redirect_uri"],
            "response_type": "code",
            "scope": "snsapi_base",
            "state": state,
        }
    )
    return RedirectResponse(
        f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect",
        status_code=302,
        headers=_sidebar_oauth_headers(real_external_call_executed=False),
    )


@router.api_route("/api/sidebar/oauth/callback", methods=["GET", "OPTIONS"])
def sidebar_oauth_callback(request: Request) -> Response:
    if request.method == "OPTIONS":
        return JSONResponse(
            {
                "ok": True,
                "route": "/api/sidebar/oauth/callback",
                "route_owner": "ai_crm_next",
                "source_status": "next_sidebar_oauth",
                "adapter_mode": "real_blocked",
                "fallback_used": False,
                "real_external_call_executed": False,
                "allowed_methods": ["GET", "OPTIONS"],
            },
            status_code=200,
        )

    state_payload = verify_state_payload(str(request.query_params.get("state") or ""))
    external_userid = str((state_payload or {}).get("external_userid") or "").strip()
    next_path = _safe_sidebar_next_path((state_payload or {}).get("next"), external_userid=external_userid)
    if not state_payload:
        return _sidebar_oauth_error_redirect(next_path, "invalid_state")
    if not str(request.query_params.get("code") or "").strip():
        return _sidebar_oauth_error_redirect(next_path, "missing_code")
    oauth = _sidebar_oauth_config(request)
    if not oauth["enabled"]:
        return _sidebar_oauth_error_redirect(next_path, "sidebar_oauth_not_enabled")
    if _sidebar_oauth_missing(oauth):
        return _sidebar_oauth_error_redirect(next_path, "sidebar_oauth_config_missing")

    client = build_wecom_admin_auth_client()
    try:
        token_payload = client.fetch_access_token(corp_id=oauth["corp_id"], corp_secret=oauth["corp_secret"])
        if _wecom_errcode(token_payload):
            return _sidebar_oauth_error_redirect(next_path, "wecom_access_token_failed")
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            return _sidebar_oauth_error_redirect(next_path, "wecom_access_token_missing")
        user_payload = client.fetch_user_info(access_token=access_token, code=str(request.query_params.get("code") or "").strip())
        if _wecom_errcode(user_payload):
            return _sidebar_oauth_error_redirect(next_path, "wecom_userinfo_failed")
    except WeComAdminAuthClientError as exc:
        return _sidebar_oauth_error_redirect(next_path, exc.error_code or "wecom_sidebar_oauth_failed")

    viewer_userid = str(user_payload.get("UserId") or user_payload.get("userid") or user_payload.get("user_id") or "").strip()
    if not viewer_userid:
        return _sidebar_oauth_error_redirect(next_path, "wecom_userid_missing")
    owner_candidates = _owner_userids_from_external_userid(external_userid)
    if owner_candidates and viewer_userid not in owner_candidates:
        return _sidebar_oauth_error_redirect(next_path, "viewer_not_in_contact_owner_scope")

    response = RedirectResponse(
        _append_query(next_path, {"sidebar_oauth": "1"}),
        status_code=302,
        headers=_sidebar_oauth_headers(real_external_call_executed=True),
    )
    response.set_cookie(
        SIDEBAR_VIEWER_COOKIE,
        sign_session_payload(
            {
                "auth_source": "wecom_sidebar_oauth",
                "wecom_userid": viewer_userid,
                "external_userid": external_userid,
                "iat": int(time()),
            }
        ),
        max_age=DEFAULT_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=session_cookie_secure(),
        path="/",
    )
    return response


def _with_sidebar_owner_context(request: Request, payload: dict) -> dict:
    result = dict(payload)
    viewer_userid = _viewer_userid_from_request(request)
    external_userid = _external_userid_from_request(request)
    owner_candidates = _owner_userids_from_external_userid(external_userid)
    source = "sidebar_jssdk_request_context"
    status = "issued"
    if viewer_userid and owner_candidates and viewer_userid not in owner_candidates:
        return _without_sidebar_owner_token(
            request,
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
                request,
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
    request: Request,
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
    oauth = _sidebar_oauth_metadata(request, external_userid)
    if oauth["status"]:
        context["sidebar_oauth_status"] = oauth["status"]
    if oauth["url"]:
        result["sidebar_oauth_url"] = oauth["url"]
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
    session = verify_session_payload(request.cookies.get(ADMIN_SESSION_COOKIE))
    session_userid = str((session or {}).get("wecom_userid") or "").strip()
    if session_userid:
        return session_userid
    sidebar_session = verify_session_payload(request.cookies.get(SIDEBAR_VIEWER_COOKIE))
    sidebar_session_userid = str((sidebar_session or {}).get("wecom_userid") or "").strip()
    if sidebar_session_userid:
        return sidebar_session_userid
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


def _sidebar_oauth_metadata(request: Request, external_userid: str) -> dict[str, str]:
    normalized_external = str(external_userid or "").strip()
    if not normalized_external:
        return {"status": "external_userid_missing", "url": ""}
    oauth = _sidebar_oauth_config(request)
    if not oauth["enabled"]:
        return {"status": "disabled", "url": ""}
    if _sidebar_oauth_missing(oauth):
        return {"status": "config_missing", "url": ""}
    next_path = _safe_sidebar_next_path(str(request.query_params.get("url") or ""), external_userid=normalized_external)
    return {
        "status": "ready",
        "url": _append_query(
            "/api/sidebar/oauth/start",
            {"external_userid": normalized_external, "next": next_path},
        ),
    }


def _sidebar_oauth_config(request: Request) -> dict[str, Any]:
    request_base = f"{request.url.scheme}://{request.url.netloc}"
    return {
        "enabled": _truthy(os.getenv(SIDEBAR_OAUTH_ENABLE_ENV)) or _truthy(os.getenv(ADMIN_AUTH_ENABLE_ENV)),
        "corp_id": str(os.getenv("WECOM_CORP_ID") or "").strip(),
        "corp_secret": str(os.getenv("WECOM_SECRET") or "").strip(),
        "redirect_uri": str(os.getenv(SIDEBAR_OAUTH_REDIRECT_URI_ENV) or "").strip()
        or f"{request_base.rstrip('/')}/api/sidebar/oauth/callback",
    }


def _sidebar_oauth_missing(config: dict[str, Any]) -> list[str]:
    missing = []
    if not str(config.get("corp_id") or "").strip():
        missing.append("WECOM_CORP_ID")
    if not str(config.get("corp_secret") or "").strip():
        missing.append("WECOM_SECRET")
    if not str(config.get("redirect_uri") or "").strip():
        missing.append(SIDEBAR_OAUTH_REDIRECT_URI_ENV)
    return missing


def _sidebar_oauth_error_response(error_code: str, next_path: str, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": error_code,
            "error_code": error_code,
            "next": _append_query(next_path, {"sidebar_oauth_error": error_code}),
            "route_owner": "ai_crm_next",
            "source_status": "next_sidebar_oauth",
            "fallback_used": False,
            "real_external_call_executed": False,
        },
        status_code=status_code,
        headers=_sidebar_oauth_headers(real_external_call_executed=False),
    )


def _sidebar_oauth_error_redirect(next_path: str, error_code: str) -> RedirectResponse:
    return RedirectResponse(
        _append_query(next_path, {"sidebar_oauth_error": error_code}),
        status_code=302,
        headers=_sidebar_oauth_headers(real_external_call_executed=False),
    )


def _sidebar_oauth_headers(*, real_external_call_executed: bool) -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": "true" if real_external_call_executed else "false",
    }


def _safe_sidebar_next_path(value: Any, *, external_userid: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return _append_query("/sidebar/bind-mobile", {"external_userid": external_userid} if external_userid else {})
    if "://" in raw:
        parsed = urlparse(raw)
        raw = urlunparse(("", "", parsed.path or "", "", parsed.query or "", ""))
    if raw.startswith("//") or raw.startswith("\\") or not raw.startswith("/"):
        raw = "/sidebar/bind-mobile"
    parsed = urlparse(raw)
    if parsed.path != "/sidebar/bind-mobile":
        raw = "/sidebar/bind-mobile"
        parsed = urlparse(raw)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in {"sidebar_oauth_error"}]
    cleaned = urlunparse(("", "", parsed.path, "", urlencode(query), ""))
    return _append_query(cleaned or "/sidebar/bind-mobile", {"external_userid": external_userid} if external_userid and "external_userid=" not in cleaned else {})


def _external_userid_from_path(value: str) -> str:
    parsed = urlparse(str(value or ""))
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key in ("external_userid", "externalUserid", "externalUserId", "user_id", "userId"):
        normalized = str(params.get(key) or "").strip()
        if normalized:
            return normalized
    return ""


def _append_query(path: str, params: dict[str, str]) -> str:
    parsed = urlparse(str(path or "/sidebar/bind-mobile"))
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in params]
    for key, value in (params or {}).items():
        normalized = str(value or "").strip()
        if normalized:
            query.append((key, normalized))
    return urlunparse(("", "", parsed.path or "/sidebar/bind-mobile", "", urlencode(query), ""))


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _wecom_errcode(payload: dict[str, Any]) -> bool:
    errcode = payload.get("errcode")
    return errcode not in (None, 0, "0")


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
