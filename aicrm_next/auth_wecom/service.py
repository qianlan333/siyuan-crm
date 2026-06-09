from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import time
from typing import Any, Protocol
from urllib.parse import quote

import requests
from sqlalchemy import text

from aicrm_next.admin_auth.service import DEFAULT_NEXT_PATH, normalize_text, safe_next_path
from aicrm_next.shared.db_session import session_scope

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
STATE_TTL_MINUTES = 10
WECOM_API_BASE_DEFAULT = "https://qyapi.weixin.qq.com"


@dataclass(frozen=True)
class WeComAuthConfig:
    mode: str
    corp_id: str
    agent_id: str
    secret: str
    redirect_uri: str
    api_base: str
    timeout_seconds: float
    cookie_secure: str

    @property
    def missing_live_keys(self) -> list[str]:
        missing: list[str] = []
        if not self.corp_id:
            missing.append("WECOM_CORP_ID")
        if not self.agent_id:
            missing.append("WECOM_AGENT_ID")
        if not self.secret:
            missing.append("WECOM_SECRET")
        if not self.redirect_uri:
            missing.append("ADMIN_LOGIN_REDIRECT_URI")
        return missing


@dataclass(frozen=True)
class AdminSsoState:
    state_token: str
    login_kind: str
    next_path: str
    expires_at: datetime


@dataclass(frozen=True)
class WeComAdminIdentity:
    wecom_userid: str
    display_name: str
    wecom_corpid: str


@dataclass(frozen=True)
class AdminUser:
    id: int
    wecom_userid: str
    wecom_corpid: str
    display_name: str
    is_active: bool
    login_enabled: bool
    admin_level: str
    roles: list[str]


class WeComAdminAuthError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class WeComAdminAuthAdapter(Protocol):
    def exchange_code(self, code: str) -> WeComAdminIdentity:
        ...


_ADAPTER_OVERRIDE: WeComAdminAuthAdapter | None = None


def set_wecom_admin_auth_adapter_for_tests(adapter: WeComAdminAuthAdapter | None) -> None:
    global _ADAPTER_OVERRIDE
    _ADAPTER_OVERRIDE = adapter


def _env_text(name: str, default: str = "") -> str:
    return normalize_text(os.getenv(name, default))


def _env_float(name: str, default: float) -> float:
    value = _env_text(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_wecom_admin_auth_config() -> WeComAuthConfig:
    return WeComAuthConfig(
        mode=_env_text("AICRM_NEXT_WECOM_ADMIN_AUTH_MODE", "blocked").lower() or "blocked",
        corp_id=_env_text("WECOM_CORP_ID"),
        agent_id=_env_text("WECOM_AGENT_ID"),
        secret=_env_text("WECOM_SECRET"),
        redirect_uri=_env_text("ADMIN_LOGIN_REDIRECT_URI"),
        api_base=_env_text("WECOM_API_BASE", WECOM_API_BASE_DEFAULT).rstrip("/") or WECOM_API_BASE_DEFAULT,
        timeout_seconds=_env_float("AICRM_NEXT_WECOM_ADMIN_AUTH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        cookie_secure=_env_text("AICRM_NEXT_ADMIN_SESSION_COOKIE_SECURE"),
    )


def is_live_mode(config: WeComAuthConfig | None = None) -> bool:
    return (config or get_wecom_admin_auth_config()).mode == "live"


def auth_route_headers(*, token_exchange_executed: bool = False) -> dict[str, str]:
    return {
        "X-AICRM-Route-Owner": "ai_crm_next",
        "X-AICRM-Fallback-Used": "false",
        "X-AICRM-Real-External-Call-Executed": "true" if token_exchange_executed else "false",
        "X-AICRM-WeCom-Token-Exchange-Executed": "true" if token_exchange_executed else "false",
    }


def diagnostics_payload(route: str) -> dict[str, Any]:
    config = get_wecom_admin_auth_config()
    return {
        "ok": True,
        "route": route,
        "route_owner": "ai_crm_next",
        "source_status": "next_auth_wecom_exact",
        "adapter_mode": "live" if config.mode == "live" else "blocked",
        "fallback_used": False,
        "real_external_call_executed": False,
        "wecom_token_exchange_executed": False,
        "configured": not bool(config.missing_live_keys),
        "status_code": 200,
    }


def blocked_payload(*, auth_step: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "auth_wecom_blocked",
        "error_code": "auth_wecom_blocked",
        "message": "WeCom admin auth is blocked until AICRM_NEXT_WECOM_ADMIN_AUTH_MODE=live.",
        "auth_step": auth_step,
        "route_owner": "ai_crm_next",
        "source_status": "auth_wecom_blocked",
        "adapter_mode": "blocked",
        "fallback_used": False,
        "real_external_call_executed": False,
        "status_code": 503,
    }


def not_configured_payload(missing_keys: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "auth_wecom_not_configured",
        "error_code": "auth_wecom_not_configured",
        "message": "WeCom admin auth live mode is missing required configuration.",
        "missing_keys": missing_keys,
        "route_owner": "ai_crm_next",
        "source_status": "auth_wecom_not_configured",
        "adapter_mode": "live",
        "fallback_used": False,
        "real_external_call_executed": False,
        "status_code": 503,
    }


def build_authorize_url(*, mode: str, next_path: str, config: WeComAuthConfig | None = None) -> str:
    config = config or get_wecom_admin_auth_config()
    normalized_mode = normalize_text(mode).lower()
    login_kind = "wecom_oauth" if normalized_mode == "oauth" else "wecom_qr"
    state_token = secrets.token_urlsafe(32)
    create_state(
        state_token=state_token,
        login_kind=login_kind,
        next_path=safe_next_path(next_path),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES),
    )
    redirect_uri = quote(config.redirect_uri, safe="")
    if login_kind == "wecom_oauth":
        return (
            "https://open.weixin.qq.com/connect/oauth2/authorize"
            f"?appid={quote(config.corp_id)}&redirect_uri={redirect_uri}&response_type=code&scope=snsapi_base"
            f"&agentid={quote(config.agent_id)}&state={quote(state_token)}#wechat_redirect"
        )
    return (
        "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
        f"?appid={quote(config.corp_id)}&agentid={quote(config.agent_id)}&redirect_uri={redirect_uri}&state={quote(state_token)}"
    )


def should_use_secure_cookie(request: Any, config: WeComAuthConfig | None = None) -> bool:
    config = config or get_wecom_admin_auth_config()
    value = config.cookie_secure.lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    forwarded_proto = normalize_text(getattr(request, "headers", {}).get("x-forwarded-proto", "")).lower()
    if forwarded_proto:
        return forwarded_proto == "https"
    scheme = normalize_text(getattr(getattr(request, "url", None), "scheme", "")).lower()
    if scheme:
        return scheme == "https"
    return _env_text("APP_ENV").lower() == "production" or _env_text("DEPLOY_ENV").lower() == "production"


def session_payload_for_admin(user: AdminUser, *, login_type: str = "wecom_sso") -> dict[str, Any]:
    roles = [role for role in user.roles if role] or ([user.admin_level] if user.admin_level else ["viewer"])
    return {
        "auth_source": "wecom_sso",
        "login_type": login_type,
        "admin_user_id": user.id,
        "wecom_userid": user.wecom_userid,
        "wecom_corpid": user.wecom_corpid,
        "username": user.wecom_userid,
        "display_name": user.display_name or user.wecom_userid,
        "roles": roles,
        "admin_level": user.admin_level or ("super_admin" if "super_admin" in roles else "admin"),
        "iat": int(time()),
    }


def ensure_admin_sso_state_schema() -> None:
    with session_scope(commit=True) as session:
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS admin_sso_states (
                    state_token TEXT PRIMARY KEY,
                    login_kind TEXT NOT NULL DEFAULT 'wecom_qr',
                    next_path TEXT NOT NULL DEFAULT '/admin',
                    expires_at TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(text("CREATE INDEX IF NOT EXISTS ix_admin_sso_states_expires_at ON admin_sso_states (expires_at)"))


def create_state(*, state_token: str, login_kind: str, next_path: str, expires_at: datetime) -> None:
    ensure_admin_sso_state_schema()
    with session_scope(commit=True) as session:
        session.execute(
            text(
                """
                INSERT INTO admin_sso_states (state_token, login_kind, next_path, expires_at, created_at)
                VALUES (:state_token, :login_kind, :next_path, :expires_at, CURRENT_TIMESTAMP)
                """
        ),
            {
                "state_token": state_token,
                "login_kind": login_kind,
                "next_path": safe_next_path(next_path),
                "expires_at": expires_at.astimezone(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S"),
            },
        )


def consume_state(state_token: str) -> AdminSsoState | None:
    normalized_state = normalize_text(state_token)
    if not normalized_state:
        return None
    ensure_admin_sso_state_schema()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    now_text = now.strftime("%Y-%m-%d %H:%M:%S")
    with session_scope(commit=True) as session:
        session.execute(text("DELETE FROM admin_sso_states WHERE CAST(expires_at AS TEXT) <= :now"), {"now": now_text})
        row = (
            session.execute(
                text(
                    """
                    SELECT state_token, login_kind, next_path, expires_at
                    FROM admin_sso_states
                    WHERE state_token = :state_token
                    """
                ),
                {"state_token": normalized_state},
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        session.execute(text("DELETE FROM admin_sso_states WHERE state_token = :state_token"), {"state_token": normalized_state})
    expires_at = row["expires_at"]
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_at = now
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    if expires_at <= now:
        return None
    return AdminSsoState(
        state_token=normalize_text(row["state_token"]),
        login_kind=normalize_text(row["login_kind"]) or "wecom_qr",
        next_path=safe_next_path(row["next_path"], default=DEFAULT_NEXT_PATH),
        expires_at=expires_at,
    )


def lookup_admin_user(*, wecom_userid: str, wecom_corpid: str = "") -> AdminUser | None:
    normalized_userid = normalize_text(wecom_userid)
    normalized_corpid = normalize_text(wecom_corpid)
    if not normalized_userid:
        return None
    where = "wecom_userid = :wecom_userid"
    params: dict[str, Any] = {"wecom_userid": normalized_userid}
    if normalized_corpid:
        where = "wecom_userid = :wecom_userid AND wecom_corpid = :wecom_corpid"
        params["wecom_corpid"] = normalized_corpid
    with session_scope() as session:
        row = (
            session.execute(
                text(
                    f"""
                    SELECT id, wecom_userid, wecom_corpid, display_name, is_active, login_enabled, admin_level
                    FROM admin_users
                    WHERE {where}
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ),
                params,
            )
            .mappings()
            .first()
        )
        if row is None and normalized_corpid:
            row = (
                session.execute(
                    text(
                        """
                        SELECT id, wecom_userid, wecom_corpid, display_name, is_active, login_enabled, admin_level
                        FROM admin_users
                        WHERE wecom_userid = :wecom_userid
                        ORDER BY id ASC
                        LIMIT 1
                        """
                    ),
                    {"wecom_userid": normalized_userid},
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        role_rows = (
            session.execute(
                text("SELECT role_code FROM admin_user_roles WHERE admin_user_id = :admin_user_id ORDER BY role_code ASC"),
                {"admin_user_id": int(row["id"])},
            )
            .mappings()
            .all()
        )
    roles = [normalize_text(role["role_code"]) for role in role_rows if normalize_text(role["role_code"])]
    return AdminUser(
        id=int(row["id"]),
        wecom_userid=normalize_text(row["wecom_userid"]),
        wecom_corpid=normalize_text(row["wecom_corpid"]),
        display_name=normalize_text(row["display_name"]),
        is_active=_db_bool(row["is_active"]),
        login_enabled=_db_bool(row["login_enabled"]),
        admin_level=normalize_text(row["admin_level"]) or "admin",
        roles=roles,
    )


def record_admin_login_success(admin_user_id: int) -> None:
    with session_scope(commit=True) as session:
        session.execute(
            text(
                """
                UPDATE admin_users
                SET last_login_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {"id": int(admin_user_id)},
        )


def _db_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return normalize_text(value).lower() in {"1", "true", "t", "yes", "on"}


class RequestsWeComAdminAuthAdapter:
    def __init__(self, config: WeComAuthConfig | None = None) -> None:
        self.config = config or get_wecom_admin_auth_config()
        self._access_token: str | None = None

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        try:
            response = requests.get(
                f"{self.config.api_base}/cgi-bin/gettoken",
                params={"corpid": self.config.corp_id, "corpsecret": self.config.secret},
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - exercised through mocked adapter in unit tests
            LOGGER.warning("wecom admin auth token request failed: %s", _redacted_error(exc))
            raise WeComAdminAuthError("wecom token request failed", status_code=503) from exc
        if payload.get("errcode") != 0:
            LOGGER.warning("wecom admin auth token request returned nonzero errcode=%s", payload.get("errcode"))
            raise WeComAdminAuthError("wecom token request failed", status_code=503)
        token = normalize_text(payload.get("access_token"))
        if not token:
            raise WeComAdminAuthError("wecom token missing", status_code=503)
        self._access_token = token
        return token

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        token = self._get_access_token()
        try:
            response = requests.get(
                f"{self.config.api_base}{path}",
                params={"access_token": token, **params},
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - exercised through mocked adapter in unit tests
            LOGGER.warning("wecom admin auth request failed path=%s: %s", path, _redacted_error(exc))
            raise WeComAdminAuthError("wecom request failed", status_code=502) from exc
        if payload.get("errcode") not in (0, None):
            LOGGER.warning("wecom admin auth request nonzero path=%s errcode=%s", path, payload.get("errcode"))
            raise WeComAdminAuthError("wecom request failed", status_code=502)
        return payload

    def exchange_code(self, code: str) -> WeComAdminIdentity:
        normalized_code = normalize_text(code)
        if not normalized_code:
            raise WeComAdminAuthError("missing wecom code", status_code=400)
        identity_payload = self._get("/cgi-bin/user/getuserinfo", {"code": normalized_code})
        user_id = normalize_text(identity_payload.get("userid")) or normalize_text(identity_payload.get("UserId"))
        if not user_id:
            raise WeComAdminAuthError("wecom callback did not return userid", status_code=502)
        display_name = user_id
        try:
            detail_payload = self._get("/cgi-bin/user/get", {"userid": user_id})
            display_name = normalize_text(detail_payload.get("name")) or display_name
        except WeComAdminAuthError:
            pass
        return WeComAdminIdentity(wecom_userid=user_id, display_name=display_name, wecom_corpid=self.config.corp_id)


def get_wecom_admin_auth_adapter(config: WeComAuthConfig | None = None) -> WeComAdminAuthAdapter:
    if _ADAPTER_OVERRIDE is not None:
        return _ADAPTER_OVERRIDE
    return RequestsWeComAdminAuthAdapter(config)


def _redacted_error(exc: Exception) -> str:
    text = str(exc)
    if len(text) > 160:
        return text[:160] + "..."
    return text
