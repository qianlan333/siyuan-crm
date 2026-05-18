from __future__ import annotations

from flask import redirect, render_template, request, url_for

from ..domains.admin_console.service import (
    build_questionnaire_detail_payload,
    build_questionnaire_index_payload,
    save_questionnaire_editor,
    toggle_questionnaire_disabled,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_console_questionnaires():
    payload = build_questionnaire_index_payload()
    return _render_admin_template(
        "questionnaires.html",
        active_nav="questionnaires",
        page_title="问卷管理",
        page_summary="在这里统一管理问卷列表、启停状态和分享入口。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("问卷", None)),
        questionnaire_payload=payload,
    )


def _questionnaire_not_found_response(questionnaire_id: int):
    return _render_admin_template(
        "placeholder.html",
        active_nav="questionnaires",
        page_title="问卷不存在",
        page_summary="当前没有找到这个问卷。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("问卷", url_for("api.admin_console_questionnaires")),
            (str(questionnaire_id), None),
        ),
        actions=[{"label": "返回问卷管理", "href": url_for("api.admin_console_questionnaires"), "variant": "secondary"}],
        state_title="问卷不存在",
        state_body="请确认问卷编号是否正确，或稍后重试。",
        state_items=["问卷可能已被删除", "当前环境也可能还没有初始化相关数据"],
        page_error="未找到问卷",
    ), 404


def _is_assessment_template_asset(questionnaire: dict | None) -> bool:
    if not questionnaire or not questionnaire.get("assessment_enabled"):
        return False
    config = questionnaire.get("assessment_config") if isinstance(questionnaire.get("assessment_config"), dict) else {}
    asset_kind = str(config.get("asset_kind") or "").strip()
    if asset_kind:
        return asset_kind == "assessment_template"
    # Backward compatibility for templates saved before asset_kind existed.
    return str(config.get("template_id") or "").strip() == "siyuan_ip_business"


def _render_questionnaire_editor_page(
    *,
    questionnaire_id: int | None = None,
):
    payload = build_questionnaire_detail_payload(questionnaire_id) if questionnaire_id is not None else None
    if questionnaire_id is not None and not payload:
        return _questionnaire_not_found_response(questionnaire_id)
    questionnaire = payload["questionnaire"] if payload else None
    default_assessment = (
        (questionnaire_id is None and str(request.args.get("mode") or "").strip() == "assessment")
        or _is_assessment_template_asset(questionnaire)
    )
    new_heading = "创建测评问卷模板" if default_assessment else "新建问卷"
    edit_heading = "编辑测评问卷模板" if default_assessment else "编辑问卷"
    new_subtitle = (
        "配置测评题目、维度分型和结果页规则，保存后可作为普通问卷的整组引用模板。"
        if default_assessment
        else "从空白模板开始搭建题目、标签和分数规则。"
    )
    edit_subtitle = (
        "维护这个测评模板的题目、维度分型和结果页规则。"
        if default_assessment
        else "维护当前问卷的题目、分数规则和发布设置。"
    )
    return render_template(
        "admin_questionnaires.html",
        editor_mode="edit" if questionnaire_id is not None else "new",
        editor_page_title=(questionnaire or {}).get("title")
        or (questionnaire or {}).get("name")
        or (edit_heading if questionnaire_id is not None else new_heading),
        editor_heading=edit_heading if questionnaire_id is not None else new_heading,
        editor_subtitle=(
            edit_subtitle
            if questionnaire_id is not None
            else new_subtitle
        ),
        editor_back_href=url_for("api.admin_console_questionnaires"),
        editor_default_assessment=default_assessment,
        initial_questionnaire=questionnaire,
        initial_questionnaire_id=questionnaire_id,
    )


def admin_console_questionnaire_new():
    return _render_questionnaire_editor_page()


def admin_console_questionnaire_detail(questionnaire_id: int):
    return _render_questionnaire_editor_page(questionnaire_id=questionnaire_id)


def admin_console_questionnaire_save(questionnaire_id: int):
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        save_questionnaire_editor(questionnaire_id, form=request.form, operator=operator)
    except Exception:
        pass
    return redirect(url_for("api.admin_console_questionnaire_detail", questionnaire_id=questionnaire_id))


def admin_console_questionnaire_toggle(questionnaire_id: int):
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        is_disabled = str(request.form.get("toggle_action") or "").strip() == "disable"
        toggle_questionnaire_disabled(questionnaire_id, is_disabled=is_disabled, operator=operator)
    except Exception:
        pass
    return redirect(url_for("api.admin_console_questionnaire_detail", questionnaire_id=questionnaire_id))


def register_routes(bp):
    bp.route("/admin/questionnaires", methods=["GET"])(admin_console_questionnaires)
    bp.route("/admin/questionnaires/new", methods=["GET"])(admin_console_questionnaire_new)
    bp.route("/admin/questionnaires/<int:questionnaire_id>", methods=["GET"])(admin_console_questionnaire_detail)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/save", methods=["POST"])(admin_console_questionnaire_save)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/toggle", methods=["POST"])(admin_console_questionnaire_toggle)
