from __future__ import annotations

from urllib.parse import quote

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for

from ..domains.admin_auth import (
    admin_role_can_access_module,
    count_admin_users,
    current_admin_operator,
    current_admin_role_codes,
    current_admin_user,
    ensure_admin_console_action_token,
    exchange_code_for_wecom_user,
    is_break_glass_login_enabled,
    require_admin_login,
    require_admin_roles,
)
from ..infra.internal_auth_runtime import require_internal_api_token_compat
from ..infra.settings import get_setting

ADMIN_AUTH_EXEMPT_PATHS = {
    "/login",
    "/logout",
    "/auth/wecom/start",
    "/auth/wecom/callback",
}
ADMIN_API_MODULE_PREFIXES = (
    ("/api/admin/attachment-library", "attachment_library"),
    ("/api/admin/config", "config"),
    ("/api/admin/hxc-dashboard", "user_ops_funnel"),
    ("/api/admin/image-library", "image_library"),
    ("/api/admin/jobs", "jobs"),
    ("/api/admin/marketing-automation", "config"),
    ("/api/admin/wechat-pay/products", "wechat_pay_products"),
    ("/api/admin/miniprogram-library", "miniprogram_library"),
    ("/api/admin/broadcast-jobs", "jobs"),
    ("/api/admin/user-ops", "user_ops_funnel"),
    ("/api/admin/wechat-pay", "wechat_pay_transactions"),
)
ADMIN_ROUTE_MODULE_PREFIXES = (
    ("/admin/automation-conversion", "automation_conversion"),
    ("/admin/attachment-library", "attachment_library"),
    ("/admin/broadcast-jobs", "jobs"),
    ("/admin/cloud-orchestrator", "cloud_orchestrator"),
    ("/admin/customers", "customers"),
    ("/admin/hxc-dashboard", "user_ops_funnel"),
    ("/admin/hxc-send-config", "user_ops_funnel"),
    ("/admin/image-library", "image_library"),
    ("/admin/jobs", "jobs"),
    ("/admin/miniprogram-library", "miniprogram_library"),
    ("/admin/questionnaires", "questionnaires"),
    ("/admin/wechat-pay/products", "wechat_pay_products"),
    ("/admin/wechat-pay", "wechat_pay_transactions"),
    ("/admin/wecom-tags", "wecom_tags"),
    ("/admin/config", "config"),
    ("/admin/api-docs", "api_docs"),
    ("/admin/mcp", "api_docs"),
    ("/admin", "automation_conversion"),
)
ADMIN_SUNSET_PAGE_PREFIXES = (
    "/admin/user-ops",
    "/admin/audit",
    "/admin/class-user-management",
)
REMOVED_ADMIN_CONFIG_PATHS = {
    "/admin/config/routing",
    "/admin/config/routing/owner-role",
    "/admin/config/routing/rule",
    "/admin/config/signup-tags",
    "/admin/config/signup-tags/save",
    "/admin/config/class-term-tags",
    "/admin/config/class-term-tags/save",
    "/api/admin/config/routing",
    "/api/admin/config/routing/owner-role",
    "/api/admin/config/routing/rule",
    "/api/admin/config/signup-tags",
    "/api/admin/config/class-term-tags",
}


def _normalized_text(value: object) -> str:
    return str(value or "").strip()


def require_internal_api_token(
    *,
    token_keys: tuple[str, ...] = (),
    legacy_header_names: tuple[str, ...] = (),
    require_configured: bool = False,
):
    return require_internal_api_token_compat(
        token_keys=token_keys,
        legacy_header_names=legacy_header_names,
        require_configured=require_configured,
    )


def current_admin_session_user() -> dict | None:
    return current_admin_user()


def _safe_next_path(value: object) -> str:
    next_path = _normalized_text(value)
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/admin/automation-conversion"
    if next_path in ADMIN_AUTH_EXEMPT_PATHS:
        return "/admin/automation-conversion"
    return next_path


def _request_is_admin_write() -> bool:
    return request.method.upper() not in {"GET", "HEAD", "OPTIONS"}


def _module_for_admin_path(path: str) -> str:
    normalized_path = _normalized_text(path)
    for prefix, module_key in ADMIN_ROUTE_MODULE_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
            return module_key
    return ""


def _module_for_admin_api_path(path: str) -> str:
    normalized_path = _normalized_text(path)
    for prefix, module_key in ADMIN_API_MODULE_PREFIXES:
        if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
            return module_key
    return ""


def _is_sunset_admin_path(path: str) -> bool:
    normalized_path = _normalized_text(path)
    return any(normalized_path == prefix or normalized_path.startswith(prefix + "/") for prefix in ADMIN_SUNSET_PAGE_PREFIXES)


def _can_access_admin_module(module_key: str, *, write: bool = False) -> bool:
    user = current_admin_session_user()
    if not user:
        return False
    return admin_role_can_access_module(current_admin_role_codes(), module_key, write=write)


def require_admin_module_access(module_key: str, *, write: bool = False) -> str:
    if _can_access_admin_module(module_key, write=write):
        return ""
    if not current_admin_session_user():
        return "请先登录后台账号"
    return "当前账号没有对应模块权限"


def validate_admin_console_action_token() -> str:
    expected = ensure_admin_console_action_token()
    json_payload = request.get_json(silent=True) or {}
    provided = (
        _normalized_text(request.form.get("admin_action_token"))
        or _normalized_text(request.values.get("admin_action_token"))
        or _normalized_text(json_payload.get("admin_action_token"))
    )
    if provided and provided == expected:
        return ""
    return "后台动作令牌无效，请刷新页面后重试"


def _record_sunset_access(path: str, *, action_type: str = "sunset_route_access") -> None:
    from ..domains.admin_audit import record_audit

    operator = current_admin_operator() if current_admin_session_user() else "anonymous"
    record_audit(
        operator=operator,
        action_type=action_type,
        target_type="sunset_route",
        target_id=_normalized_text(path),
        before={
            "path": _normalized_text(path),
            "method": request.method,
            "operator": operator,
        },
        after={
            "referrer": _normalized_text(request.referrer),
            "remote_addr": _normalized_text(request.headers.get("X-Forwarded-For")) or _normalized_text(request.remote_addr),
            "user_agent": _normalized_text(request.user_agent.string),
        },
    )


def _wecom_login_links(next_path: str) -> dict[str, str]:
    try:
        qr_url = url_for("api.admin_wecom_start", next=next_path, mode="qr")
        oauth_url = url_for("api.admin_wecom_start", next=next_path, mode="oauth")
    except RuntimeError:
        qr_url = "/auth/wecom/start?mode=qr"
        oauth_url = "/auth/wecom/start?mode=oauth"
    return {"qr": qr_url, "oauth": oauth_url}


def _render_admin_auth_page(*, page_notice: str = "", page_error: str = "", next_path: str = ""):
    safe_next = _safe_next_path(next_path)
    user_agent = _normalized_text(request.user_agent.string).lower()
    in_wecom = "wxwork" in user_agent
    return render_template(
        "admin_console/login.html",
        page_title="后台登录",
        page_notice=page_notice,
        page_error=page_error,
        next_path=safe_next,
        login_links=_wecom_login_links(safe_next),
        wecom_auth_mode=_normalized_text(get_setting("ADMIN_AUTH_MODE")) or _normalized_text(current_app.config.get("ADMIN_AUTH_MODE")) or "wecom_sso",
        wecom_corp_id=_normalized_text(get_setting("WECOM_CORP_ID")) or _normalized_text(current_app.config.get("WECOM_CORP_ID")),
        wecom_agent_id=_normalized_text(get_setting("WECOM_AGENT_ID")) or _normalized_text(current_app.config.get("WECOM_AGENT_ID")),
        in_wecom=in_wecom,
        break_glass_enabled=is_break_glass_login_enabled(),
        admin_user_count=count_admin_users(),
        current_admin_user=current_admin_session_user(),
    )


def _render_access_denied_page(module_key: str):
    from ..domains.admin_dashboard import build_admin_shell_status, list_admin_navigation

    return (
        render_template(
            "admin_console/placeholder.html",
            page_title="无权限访问",
            page_summary="当前账号没有这个后台模块的访问权限。",
            breadcrumbs=[
                {"label": "客户管理后台", "href": "/admin"},
                {"label": "权限不足", "href": ""},
            ],
            nav_items=list_admin_navigation(module_key or "automation_conversion"),
            shell_status=build_admin_shell_status(),
            show_shell_meta=True,
            show_page_header=True,
            page_notice="",
            page_error="当前账号没有这个模块权限，请联系超级管理员调整角色。",
            current_admin_user=current_admin_session_user(),
            admin_action_token=ensure_admin_console_action_token(),
            actions=[
                {"label": "进入自动化运营", "href": "/admin/automation-conversion", "variant": "primary"},
                {"label": "查看 API 文档", "href": "/admin/api-docs", "variant": "secondary"},
            ],
            state_title="权限不足",
            state_body="后台采用 企业微信 SSO + CRM 本地 RBAC，不同角色只能访问授权模块。",
            state_items=[
                "super_admin 可以访问全部后台模块",
                "viewer 只读访问，不允许执行写操作",
                "需要更高权限时请到 配置 > 登录与权限 调整",
            ],
            table_headers=[],
            table_rows=[],
        ),
        403,
    )


def _render_sunset_page(path: str):
    from ..domains.admin_dashboard import build_admin_shell_status, list_admin_navigation

    _record_sunset_access(path)
    return (
        render_template(
            "admin_console/placeholder.html",
            page_title="模块已下线",
            page_summary="该后台模块已在第一阶段瘦身中下线，保留 7 天观察后再决定是否硬删。",
            breadcrumbs=[
                {"label": "客户管理后台", "href": "/admin"},
                {"label": "模块已下线", "href": ""},
            ],
            nav_items=list_admin_navigation("automation_conversion"),
            shell_status=build_admin_shell_status(),
            show_shell_meta=True,
            show_page_header=True,
            page_notice="旧页面访问已记录到后台操作日志，用于 7 天后删除判断。",
            page_error="",
            current_admin_user=current_admin_session_user(),
            admin_action_token=ensure_admin_console_action_token(),
            actions=[
                {"label": "进入自动化运营", "href": "/admin/automation-conversion", "variant": "primary"},
                {"label": "进入配置中心", "href": "/admin/config", "variant": "secondary"},
                {"label": "查看 API 文档", "href": "/admin/api-docs", "variant": "ghost"},
            ],
            state_title="模块已临时下线",
            state_body="第一阶段保留 自动化运营、客户、问卷、配置、API 文档 五个一级能力。",
            state_items=[
                f"本次访问路径：{_normalized_text(path)}",
                f"请求方法：{request.method}",
                "若 7 天内无人访问、无外部调用、无定时任务依赖，则进入第二阶段硬删。",
            ],
            table_headers=["保留入口", "状态", "说明"],
            table_rows=[
                ["/admin/automation-conversion", "保留", "自动化运营主入口"],
                ["/admin/customers", "恢复", "全量客户查询入口"],
                ["/admin/questionnaires", "保留", "问卷主入口"],
                ["/admin/config", "保留", "配置中心主入口"],
                ["/admin/api-docs", "新增", "后台内置 API 文档"],
            ],
        ),
        410,
    )


def _login_audit_ip() -> str:
    forwarded = _normalized_text(request.headers.get("X-Forwarded-For"))
    if forwarded:
        return forwarded.split(",")[0].strip()
    return _normalized_text(request.remote_addr)


def register_admin_request_guards(app) -> None:
    @app.before_request
    def _admin_request_guard():
        path = _normalized_text(request.path)
        if path in ADMIN_AUTH_EXEMPT_PATHS:
            return None
        if path in REMOVED_ADMIN_CONFIG_PATHS:
            if path.startswith("/api/"):
                return jsonify({"ok": False, "error": "not found"}), 404
            abort(404)

        api_module_key = _module_for_admin_api_path(path)
        if api_module_key:
            if not current_admin_session_user():
                return jsonify({"ok": False, "error": "admin login required"}), 401
            if not _can_access_admin_module(api_module_key, write=_request_is_admin_write()):
                return jsonify({"ok": False, "error": "permission denied"}), 403
            return None

        if not path.startswith("/admin"):
            return None

        if path == "/admin":
            return None

        if path == "/admin/mcp" or path.startswith("/admin/mcp/"):
            _record_sunset_access(path, action_type="legacy_mcp_redirect")
            return redirect(url_for("api.admin_console_api_docs"), code=302)

        if not current_admin_session_user():
            next_path = quote(_safe_next_path(request.full_path.rstrip("?") or path), safe="/?=&")
            return redirect(f"{url_for('api.admin_login')}?next={next_path}", code=302)

        if _is_sunset_admin_path(path):
            return _render_sunset_page(path)

        module_key = _module_for_admin_path(path)
        if module_key and not _can_access_admin_module(module_key, write=_request_is_admin_write()):
            return _render_access_denied_page(module_key)
        return None


__all__ = [
    "current_admin_operator",
    "current_admin_session_user",
    "ensure_admin_console_action_token",
    "register_admin_request_guards",
    "require_admin_login",
    "require_admin_module_access",
    "require_admin_roles",
    "validate_admin_console_action_token",
]
