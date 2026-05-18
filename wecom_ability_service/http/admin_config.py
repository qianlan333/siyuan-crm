from __future__ import annotations

from flask import redirect, request, url_for

from ..domains.admin_config import (
    build_config_home_payload,
    config_tabs,
    list_admin_app_settings,
    save_admin_app_settings,
)
from .internal_auth import (
    current_admin_operator,
    validate_admin_console_action_token,
)
from .admin_console import _breadcrumb_items, _render_admin_template


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
    **extra,
):
    return _render_admin_template(
        template_name,
        active_nav="config",
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
        page_summary="在这里维护渠道与分配规则、标签班期规则、系统设置，以及登录与权限。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("配置中心", None)),
        overview_cards=payload["cards"],
    )


def _routing_page(*, page_error: str = ""):
    query = _query_text("q")
    active_only = _query_bool("active_only")
    payload = list_owner_routing_settings(query=query, active_only=active_only)
    edit_owner = _query_text("edit_owner")
    edit_rule = _query_text("edit_rule")
    owner_form = next((row for row in payload["owner_rows"] if row["userid"] == edit_owner), {"active": True, "role": "sales"})
    routing_form = next(
        (row for row in payload["routing_rows"] if row["rule_key"] == edit_rule),
        {"active": True, "routing_target": "manual_review"},
    )
    return _render_config_template(
        "config_routing.html",
        active_tab="routing",
        page_title="负责人 / 分配规则",
        page_summary="在这里维护负责人角色和客户分配规则。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("负责人 / 分配规则", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "active_only": active_only},
        owner_rows=payload["owner_rows"],
        routing_rows=payload["routing_rows"],
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
        role_options=payload["role_options"],
        routing_target_options=payload["routing_target_options"],
        owner_form=owner_form,
        routing_form=routing_form,
    )


def admin_config_routing():
    return _routing_page()


def admin_config_save_owner_role():
    token_error = validate_admin_console_action_token()
    if token_error:
        return _routing_page(page_error=token_error)
    payload = dict(request.form)
    try:
        saved = save_owner_role_setting(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _routing_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_routing", saved=1, edit_owner=saved.get("userid", "")), code=302)


def admin_config_save_routing_rule():
    token_error = validate_admin_console_action_token()
    if token_error:
        return _routing_page(page_error=token_error)
    payload = dict(request.form)
    try:
        saved = save_routing_rule_setting(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _routing_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_routing", saved=1, edit_rule=saved.get("rule_key", "")), code=302)


def _signup_tags_page(*, page_error: str = ""):
    query = _query_text("q")
    active_only = _query_bool("active_only")
    payload = list_signup_tag_settings(query=query, active_only=active_only)
    edit_tag = _query_text("edit_tag")
    form_row = next((row for row in payload["rows"] if row["tag_id"] == edit_tag), {"active": True})
    return _render_config_template(
        "config_signup_tags.html",
        active_tab="signup_tags",
        page_title="报名标签规则",
        page_summary="在这里维护报名标签和业务状态之间的对应关系。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("报名标签规则", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "active_only": active_only},
        rows=payload["rows"],
        definitions=payload["definitions"],
        tag_group_name=payload["tag_group_name"],
        missing_statuses=payload["missing_statuses"],
        bootstrap_initialized=payload["bootstrap_initialized"],
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
        form_row=form_row,
    )


def admin_config_signup_tags():
    return _signup_tags_page()


def admin_config_wecom_tags():
    return redirect(url_for("api.admin_wecom_tags_page"), code=302)


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


def admin_config_save_signup_tag():
    token_error = validate_admin_console_action_token()
    if token_error:
        return _signup_tags_page(page_error=token_error)
    payload = dict(request.form)
    try:
        saved = save_signup_tag_setting(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _signup_tags_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_signup_tags", saved=1, edit_tag=saved.get("tag_id", "")), code=302)


def _class_term_tags_page(*, page_error: str = ""):
    query = _query_text("q")
    active_only = _query_bool("active_only")
    payload = list_class_term_tag_mappings(query=query, active_only=active_only)
    edit_mapping = _query_text("edit_mapping")
    form_row = next(
        (row for row in payload["rows"] if str(row["id"]) == edit_mapping),
        {"is_active": True, "tag_group_name": payload["bootstrap_group_name"]},
    )
    return _render_config_template(
        "config_class_term_tags.html",
        active_tab="class_term_tags",
        page_title="班期标签规则",
        page_summary="在这里维护班期和标签之间的对应关系。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("班期标签规则", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "active_only": active_only},
        rows=payload["rows"],
        bootstrap_group_name=payload["bootstrap_group_name"],
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
        form_row=form_row,
    )


def admin_config_class_term_tags():
    return _class_term_tags_page()


def admin_config_save_class_term_tag():
    token_error = validate_admin_console_action_token()
    if token_error:
        return _class_term_tags_page(page_error=token_error)
    payload = dict(request.form)
    try:
        saved = save_class_term_tag_mapping(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _class_term_tags_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_class_term_tags", saved=1, edit_mapping=saved.get("id", "")), code=302)


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


def admin_config_mcp_tools():
    return redirect(url_for("api.admin_console_api_docs"), code=302)


def admin_config_save_mcp_tool():
    return redirect(url_for("api.admin_console_api_docs"), code=302)


def register_routes(bp):
    bp.route("/admin/config", methods=["GET"])(admin_config_home)
    bp.route("/admin/wecom-tags", methods=["GET"])(admin_wecom_tags_page)
    bp.route("/admin/config/wecom-tags", methods=["GET"])(admin_config_wecom_tags)
    bp.route("/admin/config/app-settings", methods=["GET"])(admin_config_app_settings)
    bp.route("/admin/config/app-settings/save", methods=["POST"])(admin_config_save_app_settings)
    bp.route("/admin/config/mcp-tools", methods=["GET"])(admin_config_mcp_tools)
    bp.route("/admin/config/mcp-tools/save", methods=["POST"])(admin_config_save_mcp_tool)
