from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import quote

from werkzeug.security import check_password_hash

from aicrm_next.admin_shell import admin_path_for
from aicrm_next.shared.runtime import require_signing_secret
from aicrm_next.shared.runtime_settings import runtime_setting


SESSION_COOKIE = "aicrm_next_admin_session"
CSRF_COOKIE = "aicrm_next_csrf"
CSRF_SESSION_KEY = "csrf_token"
SESSION_ID_KEY = "sid"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60
DEFAULT_NEXT_PATH = "/admin"


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    error: str = ""
    username: str = ""
    session_payload: dict[str, Any] | None = None


def reset_admin_auth_fixture_state() -> None:
    return None


def route_headers() -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": "false",
        "X-AICRM-WeCom-Token-Exchange-Executed": "false",
    }


def diagnostics_payload(route: str) -> dict[str, Any]:
    return {
        "ok": True,
        "route": route,
        "route_owner": "ai_crm_next",
        "source_status": "next_admin_auth",
        "fallback_used": False,
        "real_external_call_executed": False,
        "wecom_token_exchange_executed": False,
        "allowed_methods": ["GET", "POST", "OPTIONS"] if route == "/login" else ["GET", "OPTIONS"],
    }


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def safe_next_path(value: Any, *, default: str = DEFAULT_NEXT_PATH) -> str:
    raw = normalize_text(value)
    if not raw:
        return default
    if raw.startswith("//") or "://" in raw or raw.startswith("\\"):
        return default
    if not raw.startswith("/"):
        return default
    if raw.startswith(("/static", "/api/", "/auth/wecom/callback")):
        return default
    return raw


def wecom_login_links(next_path: str) -> dict[str, str]:
    encoded = quote(safe_next_path(next_path), safe="/")
    return {
        "qr": f"/auth/wecom/start?mode=qr&next={encoded}",
        "oauth": f"/auth/wecom/start?mode=oauth&next={encoded}",
    }


def break_glass_enabled() -> bool:
    return normalize_text(os.getenv("ADMIN_BREAK_GLASS_LOGIN_ENABLED")).lower() in {"1", "true", "yes", "on"}


def wecom_auth_mode_label() -> str:
    explicit_gate = normalize_text(os.getenv("AICRM_WECOM_ADMIN_AUTH_ENABLE_REAL"))
    if explicit_gate:
        return "live" if _truthy_env(explicit_gate) else "next_safe_mode"
    if normalize_text(os.getenv("AICRM_NEXT_WECOM_ADMIN_AUTH_MODE")).lower() == "live":
        return "live"
    return "next_safe_mode"


def admin_user_count() -> int:
    value = normalize_text(os.getenv("AICRM_NEXT_ADMIN_AUTH_USER_COUNT"))
    try:
        return max(0, int(value))
    except ValueError:
        return 0


def login_context(*, request: Any, next_path: Any = "", page_error: str = "", page_notice: str = "") -> dict[str, Any]:
    safe_next = safe_next_path(next_path)
    return {
        "request": request,
        "page_title": "后台登录",
        "page_notice": page_notice,
        "page_error": page_error,
        "next_path": safe_next,
        "login_links": wecom_login_links(safe_next),
        "wecom_auth_mode": wecom_auth_mode_label(),
        "wecom_corp_id": normalize_text(os.getenv("WECOM_CORP_ID")),
        "wecom_agent_id": normalize_text(os.getenv("WECOM_AGENT_ID")),
        "admin_user_count": admin_user_count(),
        "break_glass_enabled": break_glass_enabled(),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": False,
        "url_for": _login_url_for,
    }


def _truthy_env(value: Any) -> bool:
    return normalize_text(value).lower() in {"1", "true", "yes", "on"}


def login_error_message(error_code: Any) -> str:
    code = normalize_text(error_code)
    messages = {
        "wecom_admin_auth_not_enabled": "企业微信扫码登录还未启用真实授权，请先使用应急入口或完成企微登录配置。",
        "wecom_admin_auth_config_missing": "企业微信登录配置不完整，请检查企业 ID、应用 ID、应用 Secret 与回调地址。",
        "invalid_state": "登录状态已过期，请重新发起企业微信登录。",
        "missing_code": "企业微信没有返回授权 code，请重新扫码。",
        "wecom_" + "access_" + "token_failed": "企业微信接口凭证获取失败，请检查应用 Secret。",
        "wecom_" + "access_" + "token_missing": "企业微信接口凭证返回为空，请检查应用配置。",
        "wecom_userinfo_failed": "企业微信用户身份获取失败，请重新扫码。",
        "wecom_userid_missing": "企业微信没有返回成员 UserId，当前账号无法进入后台。",
        "admin_user_not_authorized": "当前企微成员尚未被授权进入后台，请先在“后台访问”中添加该成员。",
        "admin_user_disabled": "当前后台成员已停用，无法登录。",
        "wecom_admin_auth_http_error": "企业微信登录请求失败，请稍后重试。",
        "wecom_admin_auth_response_invalid": "企业微信登录响应异常，请稍后重试。",
    }
    return messages.get(code, "")


def _login_url_for(name: str, **path_params: object) -> str:
    if name == "api.admin_login":
        return "/login"
    if name == "api.admin_logout":
        return "/logout"
    return admin_path_for(name, **path_params)


def authenticate_break_glass(*, username: str, password: str) -> AuthResult:
    if not break_glass_enabled():
        return AuthResult(ok=False, error="break_glass_disabled")
    expected_username = normalize_text(os.getenv("ADMIN_BREAK_GLASS_USERNAME"))
    password_hash = normalize_text(runtime_setting("ADMIN_BREAK_GLASS_PASSWORD_HASH"))
    if not expected_username or not password_hash:
        return AuthResult(ok=False, error="break_glass_not_configured")
    if normalize_text(username) != expected_username:
        return AuthResult(ok=False, error="invalid_credentials")
    if not check_password_hash(password_hash, str(password or "")):
        return AuthResult(ok=False, error="invalid_credentials")
    payload = {
        "auth_source": "break_glass",
        "login_type": "break_glass",
        "username": expected_username,
        "display_name": expected_username,
        "roles": ["super_admin"],
        "iat": int(time()),
    }
    return AuthResult(ok=True, username=expected_username, session_payload=payload)


def session_payload_with_csrf(payload: dict[str, Any]) -> dict[str, Any]:
    session_payload = dict(payload or {})
    session_payload[CSRF_SESSION_KEY] = normalize_text(session_payload.get(CSRF_SESSION_KEY)) or secrets.token_urlsafe(32)
    session_payload[SESSION_ID_KEY] = normalize_text(session_payload.get(SESSION_ID_KEY)) or secrets.token_urlsafe(24)
    return session_payload


def csrf_token_from_session(payload: dict[str, Any] | None) -> str:
    return normalize_text((payload or {}).get(CSRF_SESSION_KEY))


def admin_cookie_secure() -> bool:
    value = normalize_text(os.getenv("AICRM_ADMIN_SESSION_COOKIE_SECURE")).lower()
    if value:
        return value in {"1", "true", "yes", "on"}
    from aicrm_next.shared.runtime import production_environment

    return production_environment()


def _secret() -> bytes:
    return require_signing_secret("SECRET_KEY", local_fallback="aicrm-next-admin-auth-local-secret")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padded = data + ("=" * (-len(data) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def sign_session(payload: dict[str, Any]) -> str:
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify_session(cookie_value: str | None) -> dict[str, Any] | None:
    value = normalize_text(cookie_value)
    if "." not in value:
        return None
    body, signature = value.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_unb64(body).decode("utf-8"))
    except Exception:
        return None
    issued_at = int(payload.get("iat") or 0)
    if issued_at <= 0 or time() - issued_at > SESSION_MAX_AGE_SECONDS:
        return None
    return payload
