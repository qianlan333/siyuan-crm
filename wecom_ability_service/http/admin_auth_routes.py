from __future__ import annotations

import secrets

from flask import redirect, request, url_for

from ..domains.admin_auth import (
    admin_user_can_login,
    authenticate_break_glass_user,
    build_wecom_oauth_login_url,
    build_wecom_qr_login_url,
    consume_admin_sso_state,
    count_admin_users,
    login_admin_session,
    login_break_glass_session,
    logout_admin_session,
    record_admin_login,
    resolve_admin_user_from_wecom_identity,
    touch_admin_user_login,
)
from ..wecom_client import WeComClientError
from . import internal_auth as _internal_auth
from .internal_auth import _login_audit_ip, _normalized_text, _render_admin_auth_page, _safe_next_path, current_admin_session_user


def admin_login():
    if current_admin_session_user():
        return redirect(_safe_next_path(request.args.get("next")), code=302)
    user_agent = _normalized_text(request.user_agent.string).lower()
    if "wxwork" in user_agent and _normalized_text(request.args.get("manual")) != "1":
        next_path = _safe_next_path(request.args.get("next"))
        return redirect(url_for("api.admin_wecom_start", next=next_path, mode="oauth"), code=302)
    return _render_admin_auth_page(
        page_notice=(
            "当前尚未授权任何后台企微成员；如需首次完成企微管理员绑定，可临时启用 break-glass 应急入口，但后台主认证仍是企业微信 SSO。"
            if count_admin_users() == 0
            else ""
        ),
        next_path=request.args.get("next"),
    )


def admin_login_submit():
    next_path = _safe_next_path(request.form.get("next") or request.args.get("next"))
    login_type = _normalized_text(request.form.get("login_type")) or "break_glass"
    if login_type != "break_glass":
        return _render_admin_auth_page(page_error="当前后台主登录方式为企业微信 SSO。", next_path=next_path)

    username = _normalized_text(request.form.get("username"))
    password = str(request.form.get("password") or "")
    if not authenticate_break_glass_user(username=username, password=password):
        record_admin_login(
            admin_user_id=None,
            login_type="break_glass",
            login_result="failed",
            ip=_login_audit_ip(),
            user_agent=_normalized_text(request.user_agent.string),
        )
        return _render_admin_auth_page(
            page_error="应急账号不可用，或用户名 / 密码错误。",
            next_path=next_path,
        )
    login_break_glass_session(username=username)
    record_admin_login(
        admin_user_id=None,
        login_type="break_glass",
        login_result="success",
        ip=_login_audit_ip(),
        user_agent=_normalized_text(request.user_agent.string),
    )
    return redirect(next_path, code=302)


def admin_wecom_start():
    next_path = _safe_next_path(request.args.get("next"))
    mode = _normalized_text(request.args.get("mode")).lower() or "auto"
    if mode == "auto":
        user_agent = _normalized_text(request.user_agent.string).lower()
        mode = "oauth" if "wxwork" in user_agent else "qr"
    if mode not in {"qr", "oauth"}:
        mode = "qr"
    state_token = secrets.token_urlsafe(24)
    try:
        redirect_url = (
            build_wecom_oauth_login_url(next_path=next_path, state_token=state_token)
            if mode == "oauth"
            else build_wecom_qr_login_url(next_path=next_path, state_token=state_token)
        )
    except ValueError as exc:
        return _render_admin_auth_page(page_error=str(exc), next_path=next_path), 503
    return redirect(redirect_url, code=302)


def admin_wecom_callback():
    code = _normalized_text(request.args.get("code"))
    state_token = _normalized_text(request.args.get("state"))
    next_path = "/admin/automation-conversion"
    state_row = consume_admin_sso_state(state_token)
    if state_row:
        next_path = _safe_next_path(state_row.get("next_path"))
    login_type = _normalized_text((state_row or {}).get("login_kind")) or "wecom_sso"
    if not code:
        record_admin_login(
            admin_user_id=None,
            login_type=login_type,
            login_result="failed_missing_code",
            ip=_login_audit_ip(),
            user_agent=_normalized_text(request.user_agent.string),
        )
        return _render_admin_auth_page(page_error="企微登录失败：缺少 code。", next_path=next_path), 400
    if not state_row:
        record_admin_login(
            admin_user_id=None,
            login_type=login_type,
            login_result="failed_invalid_state",
            ip=_login_audit_ip(),
            user_agent=_normalized_text(request.user_agent.string),
        )
        return _render_admin_auth_page(page_error="企微登录失败：state 无效或已过期。", next_path=next_path), 400

    try:
        identity = _internal_auth.exchange_code_for_wecom_user(code)
    except (ValueError, WeComClientError) as exc:
        record_admin_login(
            admin_user_id=None,
            login_type=login_type,
            login_result="failed_exchange",
            ip=_login_audit_ip(),
            user_agent=_normalized_text(request.user_agent.string),
        )
        return _render_admin_auth_page(page_error=f"企微登录失败：{exc}", next_path=next_path), 502

    user = resolve_admin_user_from_wecom_identity(identity)
    if not admin_user_can_login(user):
        record_admin_login(
            admin_user_id=int((user or {}).get("id") or 0) or None,
            login_type=login_type,
            login_result="failed_not_authorized",
            ip=_login_audit_ip(),
            user_agent=_normalized_text(request.user_agent.string),
        )
        return _render_admin_auth_page(
            page_error="当前企微成员尚未被授权登录后台，请联系超级管理员在 配置 > 登录与权限 中绑定。",
            next_path=next_path,
        ), 403

    login_admin_session(user, login_type=login_type)
    touch_admin_user_login(int(user.get("id") or 0))
    record_admin_login(
        admin_user_id=int(user.get("id") or 0) or None,
        login_type=login_type,
        login_result="success",
        ip=_login_audit_ip(),
        user_agent=_normalized_text(request.user_agent.string),
    )
    return redirect(next_path, code=302)


def admin_logout():
    logout_admin_session()
    return redirect(url_for("api.admin_login"), code=302)


def register_routes(bp):
    bp.route("/login", methods=["GET"])(admin_login)
    bp.route("/login", methods=["POST"])(admin_login_submit)
    bp.route("/logout", methods=["GET"])(admin_logout)
    bp.route("/auth/wecom/start", methods=["GET"])(admin_wecom_start)
    bp.route("/auth/wecom/callback", methods=["GET"])(admin_wecom_callback)
