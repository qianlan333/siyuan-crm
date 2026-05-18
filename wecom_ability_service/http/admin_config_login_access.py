from __future__ import annotations

from flask import redirect, request, url_for

from ..domains.admin_auth import build_admin_account_page_payload, save_admin_user, sync_admin_wecom_directory_members
from ..wecom_client import WeComClientError
from .admin_config import _operator_from_request, _query_bool, _query_text, _render_config_template
from .admin_console import _breadcrumb_items
from .internal_auth import (
    current_admin_session_user,
    require_admin_module_access,
    require_admin_roles,
    validate_admin_console_action_token,
)


def _login_access_page(*, page_error: str = ""):
    payload = build_admin_account_page_payload()
    edit_id = _query_text("edit_id")
    candidate_userid = _query_text("wecom_userid")
    directory_candidate = next(
        (row for row in payload["directory_members"] if row["wecom_userid"] == candidate_userid),
        None,
    )
    default_form_row = {
        "is_active": True,
        "login_enabled": True,
        "admin_level": "admin",
        "roles": ["viewer"],
        "wecom_corpid": payload.get("corp_id", ""),
    }
    if directory_candidate:
        default_form_row.update(
            {
                "wecom_userid": directory_candidate["wecom_userid"],
                "display_name": directory_candidate["display_name"],
                "wecom_corpid": directory_candidate["wecom_corpid"] or payload.get("corp_id", ""),
                "auth_source": "wecom_sso",
            }
        )
    form_row = next(
        (row for row in payload["rows"] if str(row["id"]) == edit_id),
        default_form_row,
    )
    page_notice = "保存成功" if _query_bool("saved") else ""
    if _query_text("directory_synced"):
        page_notice = f"已刷新企微通讯录：{_query_text('directory_synced')} 位成员"
    return _render_config_template(
        "config_login_access.html",
        active_tab="login_access",
        page_title="登录与权限",
        page_summary="在这里维护后台企微成员授权、角色分配、启停状态与最近登录审计。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("登录与权限", None),
        ),
        page_notice=page_notice,
        page_error=page_error,
        rows=payload["rows"],
        super_admin_rows=payload["super_admin_rows"],
        admin_rows=payload["admin_rows"],
        directory_members=payload["directory_members"],
        directory_summary=payload["directory_summary"],
        role_options=payload["assignable_role_options"],
        role_labels=payload["role_labels"],
        admin_level_labels=payload["admin_level_labels"],
        login_audit_rows=payload["login_audit_rows"],
        break_glass_enabled=payload["break_glass_enabled"],
        auth_mode=payload["auth_mode"],
        corp_id=payload["corp_id"],
        form_row=form_row,
        can_manage_accounts=require_admin_module_access("config", write=True) == "",
        can_manage_super_admin=(current_admin_session_user() or {}).get("admin_level") == "super_admin",
        can_manage_form=(
            require_admin_module_access("config", write=True) == ""
            and (
                (form_row or {}).get("admin_level") != "super_admin"
                or (current_admin_session_user() or {}).get("admin_level") == "super_admin"
            )
        ),
    )


def admin_config_login_access():
    return _login_access_page()


@require_admin_roles("config_admin")
def admin_config_refresh_login_access_directory():
    token_error = validate_admin_console_action_token()
    if token_error:
        return _login_access_page(page_error=token_error)
    try:
        result = sync_admin_wecom_directory_members(operator=_operator_from_request())
    except WeComClientError as exc:
        category = f"（{exc.category}）" if getattr(exc, "category", "") else ""
        return _login_access_page(page_error=f"企微通讯录刷新失败{category}：{exc}")
    return redirect(
        url_for(
            "api.admin_config_login_access",
            directory_synced=result.get("synced_count", 0),
        ),
        code=302,
    )


@require_admin_roles("config_admin")
def admin_config_save_login_access():
    token_error = validate_admin_console_action_token()
    if token_error:
        return _login_access_page(page_error=token_error)
    payload = request.form.to_dict(flat=False)
    payload = {
        **payload,
        "id": request.form.get("id"),
        "wecom_userid": request.form.get("wecom_userid"),
        "wecom_corpid": request.form.get("wecom_corpid"),
        "display_name": request.form.get("display_name"),
        "auth_source": request.form.get("auth_source"),
        "is_active": request.form.get("is_active"),
        "login_enabled": request.form.get("login_enabled"),
        "admin_level": request.form.get("admin_level"),
        "confirm_super_admin_transfer": request.form.get("confirm_super_admin_transfer"),
        "role_codes": request.form.getlist("role_codes"),
    }
    try:
        saved = save_admin_user(payload, operator=_operator_from_request(), actor_user=current_admin_session_user())
    except ValueError as exc:
        return _login_access_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_login_access", saved=1, edit_id=saved.get("id", "")), code=302)


def register_routes(bp):
    bp.route("/admin/config/login-access", methods=["GET"])(admin_config_login_access)
    bp.route("/admin/config/login-access/directory/refresh", methods=["POST"])(admin_config_refresh_login_access_directory)
    bp.route("/admin/config/login-access/save", methods=["POST"])(admin_config_save_login_access)
