from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import quote

from werkzeug.security import check_password_hash

from aicrm_next.admin_shell import admin_path_for


SESSION_COOKIE = "aicrm_next_admin_session"
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
        "wecom_auth_mode": "next_safe_mode",
        "wecom_corp_id": normalize_text(os.getenv("WECOM_CORP_ID")),
        "wecom_agent_id": normalize_text(os.getenv("WECOM_AGENT_ID")),
        "admin_user_count": admin_user_count(),
        "break_glass_enabled": break_glass_enabled(),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": False,
        "url_for": _login_url_for,
    }


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
    password_hash = normalize_text(os.getenv("ADMIN_BREAK_GLASS_PASSWORD_HASH"))
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


def _secret() -> bytes:
    return (normalize_text(os.getenv("SECRET_KEY")) or "aicrm-next-admin-auth-local-secret").encode("utf-8")


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
