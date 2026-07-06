from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .service import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    admin_cookie_secure,
    authenticate_break_glass,
    csrf_token_from_session,
    diagnostics_payload,
    login_context,
    login_error_message,
    normalize_text,
    route_headers,
    safe_next_path,
    session_payload_with_csrf,
    sign_session,
    verify_session,
)


router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.options("/login", name="api.admin_login_options")
def admin_login_options() -> JSONResponse:
    return JSONResponse(diagnostics_payload("/login"), headers=route_headers())


@router.get("/login", name="api.admin_login")
def admin_login_page(request: Request):
    next_path = safe_next_path(request.query_params.get("next"))
    if verify_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse(next_path, status_code=302, headers=route_headers())
    context = login_context(
        request=request,
        next_path=next_path,
        page_error=login_error_message(request.query_params.get("auth_error")),
    )
    return templates.TemplateResponse(request, "admin_console/login.html", context, headers=route_headers())


@router.post("/login", name="api.admin_login_submit")
async def admin_login_submit(request: Request):
    payload = await _form_payload(request)
    next_path = safe_next_path(payload.get("next") or request.query_params.get("next"))
    login_type = normalize_text(payload.get("login_type")) or "break_glass"
    if login_type != "break_glass":
        return _login_error(request, next_path=next_path, message="当前后台主登录方式为企业微信 SSO。")

    result = authenticate_break_glass(username=normalize_text(payload.get("username")), password=str(payload.get("password") or ""))
    if not result.ok or not result.session_payload:
        return _login_error(request, next_path=next_path, message="应急账号不可用，或用户名 / 密码错误。")

    session_payload = session_payload_with_csrf(result.session_payload)
    csrf_token = csrf_token_from_session(session_payload)
    secure_cookie = admin_cookie_secure()
    response = RedirectResponse(next_path, status_code=302, headers=route_headers())
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(session_payload),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,
        samesite="lax",
        secure=secure_cookie,
        path="/",
    )
    return response


@router.options("/logout", name="api.admin_logout_options")
def admin_logout_options() -> JSONResponse:
    return JSONResponse(diagnostics_payload("/logout"), headers=route_headers())


@router.get("/logout", name="api.admin_logout")
def admin_logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=302, headers=route_headers())
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


async def _form_payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        data = await request.json()
        return dict(data) if isinstance(data, dict) else {}
    body = (await request.body()).decode("utf-8", errors="ignore")
    return {key: values[-1] if values else "" for key, values in parse_qs(body, keep_blank_values=True).items()}


def _login_error(request: Request, *, next_path: str, message: str):
    context = login_context(request=request, next_path=next_path, page_error=message)
    return templates.TemplateResponse(request, "admin_console/login.html", context, status_code=401, headers=route_headers())
