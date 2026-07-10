from __future__ import annotations

import os
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from aicrm_next.shared.runtime import production_data_ready, production_environment

from .service import CSRF_COOKIE, SESSION_COOKIE, csrf_token_from_session, normalize_text, route_headers, safe_next_path, verify_session


PROTECTED_ROUTE_PREFIXES = (
    "/admin",
    "/setup",
    "/api/admin",
    "/api/customers",
    "/api/users",
    "/api/messages",
    "/archive/messages",
)

PUBLIC_ROUTE_PREFIXES = (
    "/auth/wecom/",
    "/api/h5/",
    "/api/wecom/events",
    "/wecom/external-contact/callback",
    "/static/",
    "/mcp",
)

PUBLIC_EXACT_ROUTES = {
    "/health",
    "/api/system/health",
    "/login",
    "/logout",
    "/api/sidebar/jssdk-config",
    "/sidebar/bind-mobile",
}

ADMIN_PAGE_ROUTE_PREFIXES = ("/admin", "/setup")
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def current_admin_session(request: Request) -> dict | None:
    return verify_session(request.cookies.get(SESSION_COOKIE))


def admin_auth_enforcement_enabled() -> bool:
    value = normalize_text(os.getenv("AICRM_ADMIN_AUTH_ENFORCED")).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return not _admin_auth_disable_override_allowed()
    return _production_admin_auth_required()


def _production_admin_auth_required() -> bool:
    return production_environment() or production_data_ready()


def _admin_auth_disable_override_allowed() -> bool:
    if normalize_text(os.getenv("PYTEST_CURRENT_TEST")):
        return True
    if normalize_text(os.getenv("AICRM_NEXT_ENV")).lower() == "test":
        return True
    return not _production_admin_auth_required()


def is_protected_admin_path(path: str) -> bool:
    normalized = normalize_text(path) or "/"
    if normalized in PUBLIC_EXACT_ROUTES:
        return False
    if normalized.startswith(PUBLIC_ROUTE_PREFIXES):
        return False
    return normalized.startswith(PROTECTED_ROUTE_PREFIXES)


def admin_auth_required_response(request: Request) -> Response | None:
    if not admin_auth_enforcement_enabled():
        return None
    if not is_protected_admin_path(str(request.url.path or "/")):
        return None
    session = current_admin_session(request)
    if session:
        csrf_response = admin_csrf_required_response(request, session)
        if csrf_response is not None:
            return csrf_response
        return None
    if str(request.url.path or "").startswith(ADMIN_PAGE_ROUTE_PREFIXES):
        return admin_page_auth_redirect(request)
    return admin_api_auth_error(request)


def require_admin(request: Request) -> dict:
    session = current_admin_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="admin_auth_required")
    return session


def admin_api_auth_error(request: Request) -> JSONResponse | None:
    if not admin_auth_enforcement_enabled():
        return None
    if current_admin_session(request):
        return None
    return JSONResponse(
        {
            "ok": False,
            "error": "admin_auth_required",
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        },
        status_code=401,
        headers=route_headers(),
    )


def admin_csrf_required_response(request: Request, session: dict) -> JSONResponse | None:
    if str(request.method or "").upper() in CSRF_SAFE_METHODS:
        return None
    expected = csrf_token_from_session(session)
    actual = normalize_text(request.cookies.get(CSRF_COOKIE))
    if expected and actual and hmac_compare(expected, actual):
        return None
    return JSONResponse(
        {
            "ok": False,
            "error": "admin_csrf_required",
            "route_owner": "ai_crm_next",
            "real_external_call_executed": False,
        },
        status_code=403,
        headers=route_headers(),
    )


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


def admin_page_auth_redirect(request: Request) -> RedirectResponse | None:
    if not admin_auth_enforcement_enabled():
        return None
    if current_admin_session(request):
        return None
    next_path = safe_next_path(str(request.url.path or "/admin"))
    if request.url.query:
        next_path = safe_next_path(f"{next_path}?{request.url.query}")
    return RedirectResponse(
        f"/login?next={quote(next_path, safe='/?:=&')}",
        status_code=302,
        headers=route_headers(),
    )
