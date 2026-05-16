from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Any
from urllib.parse import quote

from flask import current_app, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash

from . import repo
from .service import (
    ROLE_LABELS,
    admin_role_can_access_module,
    admin_user_can_login,
    get_admin_user_by_id,
    get_admin_user_by_wecom_userid,
    is_break_glass_login_enabled,
)
from ...infra.settings import get_setting
from ...wecom_client import WeComClient, WeComClientError

ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY = "admin_console_action_token"
ADMIN_SESSION_USER_ID_KEY = "admin_session_user_id"
ADMIN_SESSION_WECOM_USERID_KEY = "admin_session_wecom_userid"
ADMIN_SESSION_ROLE_LIST_KEY = "admin_session_role_list"
ADMIN_SESSION_LOGIN_TYPE_KEY = "admin_session_login_type"
ADMIN_SESSION_DISPLAY_NAME_KEY = "admin_session_display_name"
ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY = "admin_session_break_glass_username"
ADMIN_READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _setting_or_config(key: str, default: str = "") -> str:
    return _normalized_text(get_setting(key)) or _normalized_text(current_app.config.get(key, default))


def admin_login_redirect_uri() -> str:
    configured = _setting_or_config("ADMIN_LOGIN_REDIRECT_URI")
    if configured:
        return configured
    trusted_domain = _setting_or_config("ADMIN_WECHAT_TRUSTED_DOMAIN")
    if trusted_domain:
        normalized_domain = trusted_domain.rstrip("/")
        if not normalized_domain.startswith("http://") and not normalized_domain.startswith("https://"):
            normalized_domain = f"https://{normalized_domain}"
        return f"{normalized_domain}{url_for('api.admin_wecom_callback')}"
    return url_for("api.admin_wecom_callback", _external=True)


def build_wecom_qr_login_url(*, next_path: str, state_token: str) -> str:
    corp_id = _setting_or_config("WECOM_CORP_ID")
    agent_id = _setting_or_config("WECOM_AGENT_ID")
    if not corp_id or not agent_id:
        raise ValueError("企业微信登录未配置 WECOM_CORP_ID / WECOM_AGENT_ID")
    repo.create_admin_sso_state(
        state_token=state_token,
        login_kind="wecom_qr",
        next_path=next_path,
        expires_at=(datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    redirect_uri = quote(admin_login_redirect_uri(), safe="")
    return (
        "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
        f"?appid={quote(corp_id)}&agentid={quote(agent_id)}&redirect_uri={redirect_uri}&state={quote(state_token)}"
    )


def build_wecom_oauth_login_url(*, next_path: str, state_token: str) -> str:
    corp_id = _setting_or_config("WECOM_CORP_ID")
    agent_id = _setting_or_config("WECOM_AGENT_ID")
    if not corp_id or not agent_id:
        raise ValueError("企业微信登录未配置 WECOM_CORP_ID / WECOM_AGENT_ID")
    repo.create_admin_sso_state(
        state_token=state_token,
        login_kind="wecom_oauth",
        next_path=next_path,
        expires_at=(datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    redirect_uri = quote(admin_login_redirect_uri(), safe="")
    return (
        "https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={quote(corp_id)}&redirect_uri={redirect_uri}&response_type=code&scope=snsapi_base"
        f"&agentid={quote(agent_id)}&state={quote(state_token)}#wechat_redirect"
    )


def consume_admin_sso_state(state_token: str) -> dict[str, Any] | None:
    normalized_state = _normalized_text(state_token)
    if not normalized_state:
        return None
    repo.purge_expired_admin_sso_states(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    state_row = repo.get_admin_sso_state(normalized_state)
    repo.delete_admin_sso_state(normalized_state)
    return state_row


def exchange_code_for_wecom_user(code: str) -> dict[str, Any]:
    normalized_code = _normalized_text(code)
    if not normalized_code:
        raise ValueError("missing wecom code")
    client = WeComClient.from_app()
    identity_payload = client.get("/cgi-bin/user/getuserinfo", {"code": normalized_code})
    user_id = _normalized_text(identity_payload.get("userid")) or _normalized_text(identity_payload.get("UserId"))
    if not user_id:
        raise ValueError("wecom callback did not return UserId")
    display_name = user_id
    try:
        user_detail = client.get("/cgi-bin/user/get", {"userid": user_id})
        display_name = _normalized_text(user_detail.get("name")) or display_name
    except WeComClientError:
        pass
    return {
        "wecom_userid": user_id,
        "display_name": display_name,
        "wecom_corpid": _setting_or_config("WECOM_CORP_ID"),
        "raw_identity": identity_payload,
    }


def login_admin_session(user: dict[str, Any], *, login_type: str) -> None:
    roles = list(user.get("roles") or [])
    session[ADMIN_SESSION_USER_ID_KEY] = int(user.get("id") or 0)
    session[ADMIN_SESSION_WECOM_USERID_KEY] = _normalized_text(user.get("wecom_userid"))
    session[ADMIN_SESSION_ROLE_LIST_KEY] = roles
    session[ADMIN_SESSION_LOGIN_TYPE_KEY] = _normalized_text(login_type) or "wecom_sso"
    session[ADMIN_SESSION_DISPLAY_NAME_KEY] = _normalized_text(user.get("display_name"))
    session.pop(ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY, None)
    session.pop(ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY, None)
    session.modified = True
    g._current_admin_session_user = user


def login_break_glass_session(*, username: str) -> None:
    user = {
        "id": 0,
        "wecom_userid": "",
        "display_name": username,
        "roles": ["super_admin"],
        "role_labels": [ROLE_LABELS["super_admin"]],
        "is_active": True,
        "login_enabled": True,
        "admin_level": "super_admin",
        "auth_source": "break_glass",
        "login_type": "break_glass",
    }
    session[ADMIN_SESSION_USER_ID_KEY] = 0
    session[ADMIN_SESSION_WECOM_USERID_KEY] = ""
    session[ADMIN_SESSION_ROLE_LIST_KEY] = ["super_admin"]
    session[ADMIN_SESSION_LOGIN_TYPE_KEY] = "break_glass"
    session[ADMIN_SESSION_DISPLAY_NAME_KEY] = username
    session[ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY] = username
    session.pop(ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY, None)
    session.modified = True
    g._current_admin_session_user = user


def logout_admin_session() -> None:
    for key in (
        ADMIN_SESSION_USER_ID_KEY,
        ADMIN_SESSION_WECOM_USERID_KEY,
        ADMIN_SESSION_ROLE_LIST_KEY,
        ADMIN_SESSION_LOGIN_TYPE_KEY,
        ADMIN_SESSION_DISPLAY_NAME_KEY,
        ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY,
        ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY,
    ):
        session.pop(key, None)
    session.modified = True
    g._current_admin_session_user = None


def current_admin_user() -> dict[str, Any] | None:
    cached = getattr(g, "_current_admin_session_user", None)
    if cached is not None:
        return cached

    login_type = _normalized_text(session.get(ADMIN_SESSION_LOGIN_TYPE_KEY))
    if login_type == "break_glass":
        username = _normalized_text(session.get(ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY))
        if not username:
            logout_admin_session()
            return None
        roles = [
            _normalized_text(role_code)
            for role_code in list(session.get(ADMIN_SESSION_ROLE_LIST_KEY) or [])
            if _normalized_text(role_code)
        ] or ["super_admin"]
        is_super_admin = "super_admin" in roles
        user = {
            "id": 0,
            "wecom_userid": "",
            "display_name": username,
            "roles": roles,
            "role_labels": [ROLE_LABELS.get(role_code, role_code) for role_code in roles],
            "is_active": True,
            "login_enabled": True,
            "admin_level": "super_admin" if is_super_admin else "admin",
            "auth_source": "break_glass",
            "login_type": "break_glass",
        }
        g._current_admin_session_user = user
        return user

    user_id = int(session.get(ADMIN_SESSION_USER_ID_KEY) or 0)
    if user_id <= 0:
        g._current_admin_session_user = None
        return None
    user = get_admin_user_by_id(user_id)
    if not admin_user_can_login(user):
        logout_admin_session()
        return None
    session[ADMIN_SESSION_ROLE_LIST_KEY] = list(user.get("roles") or [])
    session[ADMIN_SESSION_DISPLAY_NAME_KEY] = _normalized_text(user.get("display_name"))
    session[ADMIN_SESSION_WECOM_USERID_KEY] = _normalized_text(user.get("wecom_userid"))
    session.modified = True
    g._current_admin_session_user = user
    return user


def ensure_admin_console_action_token() -> str:
    token = _normalized_text(session.get(ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY))
    if token:
        return token
    token = secrets.token_urlsafe(24)
    session[ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY] = token
    session.modified = True
    return token


def current_admin_role_codes() -> list[str]:
    user = current_admin_user()
    return list((user or {}).get("roles") or [])


def current_admin_operator() -> str:
    user = current_admin_user()
    if not user:
        return "crm_console"
    return (
        _normalized_text(user.get("wecom_userid"))
        or _normalized_text(user.get("display_name"))
        or _normalized_text(session.get(ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY))
        or "crm_console"
    )


def require_admin_login(view):
    @wraps(view)
    def _wrapped(*args, **kwargs):
        if current_admin_user():
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "admin login required"}), 401
        next_path = quote(request.full_path.rstrip("?") or request.path, safe="/?=&")
        return redirect(f"{url_for('api.admin_login')}?next={next_path}", code=302)

    return _wrapped


def require_admin_roles(*role_codes: str, allow_super_admin: bool = True):
    normalized_roles = {_normalized_text(role_code) for role_code in role_codes if _normalized_text(role_code)}

    def _decorator(view):
        @wraps(view)
        def _wrapped(*args, **kwargs):
            user = current_admin_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "error": "admin login required"}), 401
                next_path = quote(request.full_path.rstrip("?") or request.path, safe="/?=&")
                return redirect(f"{url_for('api.admin_login')}?next={next_path}", code=302)
            roles = set(current_admin_role_codes())
            if allow_super_admin and "super_admin" in roles:
                return view(*args, **kwargs)
            if normalized_roles and roles.intersection(normalized_roles):
                return view(*args, **kwargs)
            return jsonify({"ok": False, "error": "permission denied"}), 403

        return _wrapped

    return _decorator


def authenticate_break_glass_user(*, username: str, password: str) -> bool:
    if not is_break_glass_login_enabled():
        return False
    expected_username = _setting_or_config("ADMIN_BREAK_GLASS_USERNAME")
    password_hash = _setting_or_config("ADMIN_BREAK_GLASS_PASSWORD_HASH")
    if not expected_username or not password_hash:
        return False
    return _normalized_text(username) == expected_username and check_password_hash(password_hash, str(password or ""))


def resolve_admin_user_from_wecom_identity(identity: dict[str, Any]) -> dict[str, Any] | None:
    return get_admin_user_by_wecom_userid(
        _normalized_text(identity.get("wecom_userid")),
        wecom_corpid=_normalized_text(identity.get("wecom_corpid")),
    )


def admin_user_can_access(module_key: str, *, write: bool = False) -> bool:
    return admin_role_can_access_module(current_admin_role_codes(), module_key, write=write)
