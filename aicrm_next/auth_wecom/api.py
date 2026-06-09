from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse

from aicrm_next.admin_auth.service import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, safe_next_path, sign_session

from .service import (
    auth_route_headers,
    blocked_payload,
    build_authorize_url,
    consume_state,
    diagnostics_payload,
    get_wecom_admin_auth_adapter,
    get_wecom_admin_auth_config,
    is_live_mode,
    lookup_admin_user,
    not_configured_payload,
    record_admin_login_success,
    session_payload_for_admin,
    should_use_secure_cookie,
    WeComAdminAuthError,
)

router = APIRouter()


def _response(payload: dict, *, token_exchange_executed: bool = False) -> JSONResponse:
    status_code = int(payload.pop("status_code", 200) or 200)
    return JSONResponse(jsonable_encoder(payload), status_code=status_code, headers=auth_route_headers(token_exchange_executed=token_exchange_executed))


def _error_payload(*, error_code: str, status_code: int, message: str, **extra: object) -> dict:
    return {
        "ok": False,
        "error": error_code,
        "error_code": error_code,
        "message": message,
        "route_owner": "ai_crm_next",
        "source_status": error_code,
        "fallback_used": False,
        "real_external_call_executed": False,
        "wecom_token_exchange_executed": False,
        "status_code": status_code,
        **extra,
    }


def _deprecated_payload(*, route: str, replacement_route: str = "") -> dict:
    return {
        "ok": False,
        "error": "auth_route_deprecated",
        "error_code": "auth_route_deprecated",
        "message": "This historical auth route is deprecated and now has an explicit Next response.",
        "route": route,
        "replacement_route": replacement_route,
        "route_owner": "ai_crm_next",
        "source_status": "deprecated",
        "adapter_mode": "blocked",
        "fallback_used": False,
        "real_external_call_executed": False,
        "status_code": 410,
    }


@router.api_route("/auth/wecom/start", methods=["GET", "OPTIONS"])
def auth_wecom_start(request: Request):
    if request.method == "OPTIONS":
        return _response(diagnostics_payload("/auth/wecom/start"))

    config = get_wecom_admin_auth_config()
    if not is_live_mode(config):
        return _response(blocked_payload(auth_step="wecom_sso_start"))
    missing_keys = config.missing_live_keys
    if missing_keys:
        return _response(not_configured_payload(missing_keys))

    mode = request.query_params.get("mode") or "qr"
    next_path = safe_next_path(request.query_params.get("next"))
    authorize_url = build_authorize_url(mode=mode, next_path=next_path, config=config)
    return RedirectResponse(authorize_url, status_code=302, headers=auth_route_headers())


@router.api_route("/auth/wecom/callback", methods=["GET", "OPTIONS"])
def auth_wecom_callback(request: Request):
    if request.method == "OPTIONS":
        return _response(diagnostics_payload("/auth/wecom/callback"))

    code = request.query_params.get("code")
    state_token = request.query_params.get("state")
    if not code:
        return _response(_error_payload(error_code="missing_wecom_code", status_code=400, message="Missing WeCom code."))
    state = consume_state(state_token or "")
    if state is None:
        return _response(_error_payload(error_code="invalid_or_expired_state", status_code=400, message="Invalid or expired WeCom login state."))

    config = get_wecom_admin_auth_config()
    if not is_live_mode(config):
        return _response(blocked_payload(auth_step="wecom_sso_callback"))
    missing_keys = config.missing_live_keys
    if missing_keys:
        return _response(not_configured_payload(missing_keys))

    try:
        identity = get_wecom_admin_auth_adapter(config).exchange_code(code)
    except WeComAdminAuthError as exc:
        return _response(
            _error_payload(
                error_code="wecom_code_exchange_failed",
                status_code=exc.status_code if exc.status_code in {502, 503} else 502,
                message="WeCom code exchange failed.",
                adapter_mode="live",
            ),
            token_exchange_executed=True,
        )

    user = lookup_admin_user(wecom_userid=identity.wecom_userid, wecom_corpid=identity.wecom_corpid)
    if user is None or not user.is_active or not user.login_enabled:
        return _response(
            _error_payload(
                error_code="admin_login_denied",
                status_code=403,
                message="WeCom user is not allowed to login as an admin.",
                adapter_mode="live",
            ),
            token_exchange_executed=True,
        )

    record_admin_login_success(user.id)
    response = RedirectResponse(state.next_path, status_code=302, headers=auth_route_headers(token_exchange_executed=True))
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(session_payload_for_admin(user, login_type=state.login_kind)),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=should_use_secure_cookie(request, config),
        path="/",
    )
    return response


@router.options("/auth/wecom/unknown")
def auth_wecom_unknown_options():
    return _response(diagnostics_payload("/auth/wecom/unknown"))


@router.get("/auth/wecom/unknown")
def auth_wecom_unknown():
    return _response(_deprecated_payload(route="/auth/wecom/unknown", replacement_route="/auth/wecom/start"))


@router.options("/api/h5/wechat/oauth/unknown")
def h5_wechat_oauth_unknown_options():
    return _response(diagnostics_payload("/api/h5/wechat/oauth/unknown"))


@router.get("/api/h5/wechat/oauth/unknown")
def h5_wechat_oauth_unknown():
    return _response(_deprecated_payload(route="/api/h5/wechat/oauth/unknown", replacement_route="/api/h5/wechat/oauth/start"))
