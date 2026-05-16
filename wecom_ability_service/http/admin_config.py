from __future__ import annotations

from flask import jsonify, redirect, request, url_for

from ..application.automation_engine.commands import (
    RecomputeSignupConversionCustomersCommand,
    SaveSignupConversionConfigCommand,
)
from ..application.automation_engine.dto import (
    SignupConversionConfigCommandDTO,
    SignupConversionConfigQueryDTO,
    SignupConversionPreviewQueryDTO,
    SignupConversionRecomputeCommandDTO,
)
from ..application.automation_engine.queries import (
    GetSignupConversionConfigQuery,
    ListAutomationConversionDispatchHistoryQuery,
    PreviewSignupConversionCustomerQuery,
)
from ..domains.admin_auth import build_admin_account_page_payload, save_admin_user, sync_admin_wecom_directory_members
from ..domains.admin_config import (
    build_config_home_payload,
    config_tabs,
    list_admin_app_settings,
    list_mcp_tool_settings,
    save_admin_app_settings,
    save_mcp_tool_setting,
)
from .internal_auth import (
    current_admin_session_user,
    current_admin_operator,
    require_admin_module_access,
    require_admin_roles,
    validate_admin_console_action_token,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from ..wecom_client import WeComClientError


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or current_admin_operator()
    )


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_bool(name: str) -> bool:
    return str(request.args.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _query_int(name: str, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        value = int(request.args.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _request_confirmed() -> bool:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.values.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
        or str(json_payload.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
    )


def _render_config_template(
    template_name: str,
    *,
    active_tab: str,
    page_title: str,
    page_summary: str,
    breadcrumbs: list[dict[str, str]],
    page_notice: str = "",
    page_error: str = "",
    active_nav: str = "config",
    **extra,
):
    return _render_admin_template(
        template_name,
        active_nav=active_nav,
        page_title=page_title,
        page_summary=page_summary,
        breadcrumbs=breadcrumbs,
        config_tabs=config_tabs(active_tab),
        page_notice=page_notice,
        page_error=page_error,
        **extra,
    )


def admin_config_home():
    payload = build_config_home_payload()
    return _render_config_template(
        "config_overview.html",
        active_tab="overview",
        page_title="配置中心",
        page_summary="在这里维护系统设置、登录与权限，以及配置检查清单。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("配置中心", None)),
        overview_cards=payload["cards"],
    )


def admin_wecom_tags_page():
    return _render_admin_template(
        "config_wecom_tags.html",
        page_title="企微标签管理",
        page_summary="集中管理企业客户标签：同步、搜索、新增、编辑、删除和复制 tag_id。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("企微标签管理", None),
        ),
        show_shell_meta=False,
        active_nav="wecom_tags",
    )


def admin_config_wecom_tags_redirect():
    return redirect(url_for("api.admin_wecom_tags_page"), code=302)


def _app_settings_page(*, page_error: str = ""):
    query = _query_text("q")
    scope = _query_text("scope")
    payload = list_admin_app_settings(query=query, scope=scope)
    editable_rows = [row for row in payload["rows"] if row["mode"] == "editable"]
    masked_rows = [row for row in payload["rows"] if row["mode"] == "masked"]
    return _render_config_template(
        "config_app_settings.html",
        active_tab="app_settings",
        page_title="系统设置",
        page_summary="在这里维护系统参数；涉及敏感信息的内容只显示掩码。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("系统设置", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "scope": scope},
        rows=payload["rows"],
        editable_rows=editable_rows,
        masked_rows=masked_rows,
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
    )


def admin_config_app_settings():
    return _app_settings_page()


def _extract_setting_form_payload() -> dict[str, str]:
    settings: dict[str, str] = {}
    for key, value in request.form.items():
        if not key.startswith("setting__"):
            continue
        settings[key.split("setting__", 1)[1]] = str(value or "")
    return settings


def admin_config_save_app_settings():
    token_error = validate_admin_console_action_token()
    if token_error:
        return _app_settings_page(page_error=token_error)
    if not _request_confirmed():
        return _app_settings_page(page_error="保存前请先确认本次修改。")
    try:
        save_admin_app_settings(_extract_setting_form_payload(), operator=_operator_from_request())
    except ValueError as exc:
        return _app_settings_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_app_settings", saved=1), code=302)


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


def admin_config_mcp_tools():
    return redirect(url_for("api.admin_console_api_docs"), code=302)


def admin_config_save_mcp_tool():
    return redirect(url_for("api.admin_console_api_docs"), code=302)


def _automation_conversion_status_cards(config: dict[str, object], selected_questionnaire: dict[str, object] | None) -> list[dict[str, str]]:
    questionnaire_name = "还没选择问卷"
    if selected_questionnaire:
        questionnaire_name = str(
            selected_questionnaire.get("title")
            or selected_questionnaire.get("name")
            or questionnaire_name
        ).strip() or questionnaire_name
    elif config.get("questionnaire_missing"):
        missing_id = int(config.get("missing_questionnaire_id") or 0)
        questionnaire_name = f"已失效的问卷 #{missing_id}" if missing_id > 0 else "已失效的问卷"
    thresholds = dict(config.get("silent_threshold_days_by_pool") or {})
    silent_summary = " / ".join(
        [
            f"新{int(thresholds.get('new_user') or 7)}天",
            f"未普{int(thresholds.get('inactive_normal') or 7)}天",
            f"未重{int(thresholds.get('inactive_focus') or 7)}天",
            f"激普{int(thresholds.get('active_normal') or 7)}天",
            f"激重{int(thresholds.get('active_focus') or 7)}天",
        ]
    )
    return [
        {
            "label": "问卷初判开关",
            "value": "已开启" if config.get("enabled") else "已暂停",
            "description": "当前页面只配置自动化转化的问卷初判和首次分流。",
        },
        {
            "label": "当前问卷",
            "value": questionnaire_name,
            "description": "系统会按这份问卷做首次分流，问卷里必须直接收集必填手机号。",
        },
        {
            "label": "重点跟进门槛",
            "value": f"命中 {int(config.get('core_threshold') or 0)} 题",
            "description": "问卷初判只输出普通跟进 / 重点跟进，更细的后续池子不在这里判断。",
        },
        {
            "label": "沉默池规则",
            "value": silent_summary,
            "description": "新用户池、未激活普通/重点、激活普通/重点都可单独配置停留天数；超时自动进入沉默池，沉默池只做留存。",
        },
        {
            "label": "夜间暂停",
            "value": f"{int(config.get('quiet_hour_start') or 23)}:00 后暂停启动",
            "description": f"按 {str(config.get('timezone') or 'Asia/Shanghai').strip() or 'Asia/Shanghai'} 时区执行，夜间不会新启动自动化转化。",
        },
    ]


def admin_marketing_automation_ui():
    target = url_for("api.admin_automation_conversion")
    query_string = request.query_string.decode("utf-8").strip()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target, code=302)


def api_admin_config_overview():
    return jsonify({"ok": True, "overview": build_config_home_payload()})


def api_admin_config_app_settings():
    return jsonify({"ok": True, "config": list_admin_app_settings(query=_query_text("q"), scope=_query_text("scope"))})


def api_admin_config_save_app_settings():
    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        return jsonify({"ok": False, "error": "settings must be an object"}), 400
    if not _request_confirmed():
        return jsonify({"ok": False, "error": "confirm is required before saving app settings"}), 400
    try:
        changed = save_admin_app_settings(settings, operator=_operator_from_request())
        return jsonify({"ok": True, "changed": changed, "config": list_admin_app_settings(query="", scope="")})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_config_mcp_tools():
    return jsonify({"ok": True, "config": list_mcp_tool_settings(query=_query_text("q"), enabled_only=_query_bool("enabled_only"))})


def api_admin_config_save_mcp_tool():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_mcp_tool_setting(payload, operator=_operator_from_request())
        return jsonify({"ok": True, "item": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_config():
    try:
        return jsonify(
            {
                "ok": True,
                "config": GetSignupConversionConfigQuery()(SignupConversionConfigQueryDTO()),
            }
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_save_config():
    payload = request.get_json(silent=True) or {}
    try:
        saved = SaveSignupConversionConfigCommand()(
            SignupConversionConfigCommandDTO(payload=dict(payload or {}))
        )
        return jsonify({"ok": True, "config": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_preview():
    payload = request.get_json(silent=True) or {}
    try:
        preview = PreviewSignupConversionCustomerQuery()(
            SignupConversionPreviewQueryDTO(
                external_userid=str(payload.get("external_userid", "") or ""),
                person_id=payload.get("person_id"),
            )
        )
        return jsonify({"ok": True, "preview": preview})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def api_admin_marketing_automation_recompute():
    payload = request.get_json(silent=True) or {}
    try:
        result = RecomputeSignupConversionCustomersCommand()(
            SignupConversionRecomputeCommandDTO(
                external_userid=str(payload.get("external_userid", "") or ""),
                person_id=payload.get("person_id"),
                external_userids=payload.get("external_userids") or [],
                person_ids=payload.get("person_ids") or [],
            )
        )
        return jsonify({"ok": True, "recompute": result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def api_admin_marketing_automation_dispatch_history():
    return jsonify(
        {
            "ok": True,
            "dispatch_history": ListAutomationConversionDispatchHistoryQuery()(
                status=_query_text("status"),
                limit=_query_int("limit", default=50, minimum=1, maximum=200),
            ),
        }
    )


def api_admin_config_signup_conversion():
    return api_admin_marketing_automation_config()


def api_admin_config_save_signup_conversion():
    return api_admin_marketing_automation_save_config()


def register_routes(bp):
    bp.route("/admin/config", methods=["GET"])(admin_config_home)
    bp.route("/admin/wecom-tags", methods=["GET"])(admin_wecom_tags_page)
    bp.route("/admin/config/wecom-tags", methods=["GET"])(admin_config_wecom_tags_redirect)
    bp.route("/admin/marketing-automation/ui", methods=["GET"])(admin_marketing_automation_ui)
    bp.route("/admin/config/app-settings", methods=["GET"])(admin_config_app_settings)
    bp.route("/admin/config/app-settings/save", methods=["POST"])(admin_config_save_app_settings)
    bp.route("/admin/config/login-access", methods=["GET"])(admin_config_login_access)
    bp.route("/admin/config/login-access/directory/refresh", methods=["POST"])(admin_config_refresh_login_access_directory)
    bp.route("/admin/config/login-access/save", methods=["POST"])(admin_config_save_login_access)
    bp.route("/admin/config/mcp-tools", methods=["GET"])(admin_config_mcp_tools)
    bp.route("/admin/config/mcp-tools/save", methods=["POST"])(admin_config_save_mcp_tool)

    bp.route("/api/admin/config/overview", methods=["GET"])(api_admin_config_overview)
    bp.route("/api/admin/config/app-settings", methods=["GET"])(api_admin_config_app_settings)
    bp.route("/api/admin/config/app-settings", methods=["PUT"])(api_admin_config_save_app_settings)
    bp.route("/api/admin/config/mcp-tools", methods=["GET"])(api_admin_config_mcp_tools)
    bp.route("/api/admin/config/mcp-tools", methods=["POST"])(api_admin_config_save_mcp_tool)
    bp.route("/api/admin/marketing-automation/config", methods=["GET"])(api_admin_marketing_automation_config)
    bp.route("/api/admin/marketing-automation/config", methods=["PUT"])(api_admin_marketing_automation_save_config)
    bp.route("/api/admin/marketing-automation/config/preview", methods=["POST"])(api_admin_marketing_automation_preview)
    bp.route("/api/admin/marketing-automation/dispatch-history", methods=["GET"])(api_admin_marketing_automation_dispatch_history)
    bp.route("/api/admin/marketing-automation/recompute", methods=["POST"])(api_admin_marketing_automation_recompute)
    bp.route("/api/admin/config/marketing-automation/signup-conversion", methods=["GET"])(api_admin_config_signup_conversion)
    bp.route("/api/admin/config/marketing-automation/signup-conversion", methods=["PUT"])(api_admin_config_save_signup_conversion)
