from __future__ import annotations

from flask import redirect, render_template, request, url_for

from ..application.questionnaire.commands import RetryQuestionnaireExternalPushCommand
from ..application.questionnaire.dto import RetryQuestionnaireExternalPushCommandDTO
from ..application.questionnaire.queries import (
    GetGlobalQuestionnaireExternalPushLogsQuery,
    GetQuestionnaireExternalPushLogsQuery,
)
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


def _render_questionnaire_editor_page(
    *,
    questionnaire_id: int | None = None,
):
    payload = build_questionnaire_detail_payload(questionnaire_id) if questionnaire_id is not None else None
    if questionnaire_id is not None and not payload:
        return _questionnaire_not_found_response(questionnaire_id)
    questionnaire = payload["questionnaire"] if payload else None
    return render_template(
        "admin_questionnaires.html",
        editor_mode="edit" if questionnaire_id is not None else "new",
        editor_page_title=(questionnaire or {}).get("title")
        or (questionnaire or {}).get("name")
        or ("编辑问卷" if questionnaire_id is not None else "新建问卷"),
        editor_heading="编辑问卷" if questionnaire_id is not None else "新建问卷",
        editor_subtitle=(
            "维护当前问卷的题目、分数规则和发布设置。"
            if questionnaire_id is not None
            else "从空白模板开始搭建题目、标签和分数规则。"
        ),
        editor_back_href=url_for("api.admin_console_questionnaires"),
        editor_default_assessment=questionnaire_id is None
        and str(request.args.get("mode") or "").strip() == "assessment",
        initial_questionnaire=questionnaire,
        initial_questionnaire_id=questionnaire_id,
    )


def admin_console_questionnaire_new():
    return _render_questionnaire_editor_page()


def admin_console_questionnaire_detail(questionnaire_id: int):
    return _render_questionnaire_editor_page(questionnaire_id=questionnaire_id)


def admin_console_questionnaire_external_push_logs(questionnaire_id: int):
    status = str(request.args.get("status") or "").strip()
    limit = request.args.get("limit", 50)
    page_notice = str(request.args.get("notice") or "").strip()
    page_error = str(request.args.get("error") or "").strip()
    payload = GetQuestionnaireExternalPushLogsQuery()(
        questionnaire_id=int(questionnaire_id),
        status=status,
        limit=limit,
    )
    if not payload:
        return _questionnaire_not_found_response(questionnaire_id)
    questionnaire = payload["questionnaire"]
    return _render_admin_template(
        "questionnaire_external_push_logs.html",
        active_nav="questionnaires",
        page_title="问卷外部推送记录",
        page_summary="查看问卷提交成功后的外部推送结果，重点排查失败记录和返回信息。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("问卷", url_for("api.admin_console_questionnaires")),
            ((questionnaire.get("title") or questionnaire.get("name") or str(questionnaire_id)), url_for("api.admin_console_questionnaire_detail", questionnaire_id=questionnaire_id)),
            ("外部推送记录", None),
        ),
        logs_payload=payload,
        page_notice=page_notice,
        page_error=page_error,
    )


def admin_console_global_questionnaire_external_push_logs():
    payload = GetGlobalQuestionnaireExternalPushLogsQuery()(
        questionnaire_id=request.args.get("questionnaire_id", ""),
        questionnaire_title=request.args.get("questionnaire_title", ""),
        status=request.args.get("status", ""),
        user_id=request.args.get("user_id", ""),
        target_url=request.args.get("target_url", ""),
        limit=request.args.get("limit", 50),
    )
    return _render_admin_template(
        "questionnaire_external_push_logs.html",
        active_nav="questionnaires",
        page_title="问卷外部推送总览",
        page_summary="跨问卷查看当前外推状态，集中排查待补发失败项并直接处理。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("问卷", url_for("api.admin_console_questionnaires")),
            ("外部推送总览", None),
        ),
        logs_payload=payload,
        page_notice=str(request.args.get("notice") or "").strip(),
        page_error=str(request.args.get("error") or "").strip(),
    )


def admin_console_questionnaire_external_push_logs_retry(questionnaire_id: int, push_log_id: int):
    status = str(request.form.get("status") or "").strip()
    limit = request.form.get("limit", 50)
    try:
        result = RetryQuestionnaireExternalPushCommand()(
            RetryQuestionnaireExternalPushCommandDTO(push_log_id=int(push_log_id))
        )
        notice = "补发已执行，请查看最近结果。"
        error = ""
        if result.get("ok"):
            status = ""
    except Exception as exc:
        notice = ""
        error = str(exc).strip() or "补发失败"
    return redirect(
        url_for(
            "api.admin_console_questionnaire_external_push_logs",
            questionnaire_id=questionnaire_id,
            status=status,
            limit=limit,
            notice=notice,
            error=error,
        )
    )


def admin_console_global_questionnaire_external_push_logs_retry(push_log_id: int):
    params = {
        "questionnaire_id": str(request.form.get("questionnaire_id") or "").strip(),
        "questionnaire_title": str(request.form.get("questionnaire_title") or "").strip(),
        "status": str(request.form.get("status") or "").strip(),
        "user_id": str(request.form.get("user_id") or "").strip(),
        "target_url": str(request.form.get("target_url") or "").strip(),
        "limit": request.form.get("limit", 50),
    }
    try:
        result = RetryQuestionnaireExternalPushCommand()(
            RetryQuestionnaireExternalPushCommandDTO(push_log_id=int(push_log_id))
        )
        params["notice"] = "补发已执行，请查看最近结果。"
        params["error"] = ""
        if result.get("ok"):
            params["status"] = ""
    except Exception as exc:
        params["notice"] = ""
        params["error"] = str(exc).strip() or "补发失败"
    return redirect(url_for("api.admin_console_global_questionnaire_external_push_logs", **params))


def admin_console_questionnaire_external_push_logs_retry_batch(questionnaire_id: int):
    status = str(request.form.get("status") or "").strip()
    limit = request.form.get("limit", 50)
    push_log_ids = request.form.getlist("push_log_ids")
    if not push_log_ids:
        return redirect(
            url_for(
                "api.admin_console_questionnaire_external_push_logs",
                questionnaire_id=questionnaire_id,
                status=status,
                limit=limit,
                error="请先勾选至少一条待补发记录。",
            )
        )
    result = RetryQuestionnaireExternalPushCommand()(
        RetryQuestionnaireExternalPushCommandDTO(
            push_log_ids=[int(item) for item in push_log_ids],
        )
    )
    notice = (
        "批量补发已执行："
        f"选中 {int(result.get('selected_count') or 0)} 条，"
        f"实际补发 {int(result.get('retried_count') or 0)} 条，"
        f"成功 {int(result.get('success_count') or 0)} 条，"
        f"失败 {int(result.get('failed_count') or 0)} 条"
    )
    skipped_count = int(result.get("skipped_count") or 0)
    if skipped_count:
        notice += f"，跳过 {skipped_count} 条"
    notice += "。"
    return redirect(
        url_for(
            "api.admin_console_questionnaire_external_push_logs",
            questionnaire_id=questionnaire_id,
            status="",
            limit=limit,
            notice=notice,
        )
    )


def admin_console_global_questionnaire_external_push_logs_retry_batch():
    push_log_ids = request.form.getlist("push_log_ids")
    params = {
        "questionnaire_id": str(request.form.get("questionnaire_id") or "").strip(),
        "questionnaire_title": str(request.form.get("questionnaire_title") or "").strip(),
        "status": str(request.form.get("status") or "").strip(),
        "user_id": str(request.form.get("user_id") or "").strip(),
        "target_url": str(request.form.get("target_url") or "").strip(),
        "limit": request.form.get("limit", 50),
    }
    if not push_log_ids:
        params["error"] = "请先勾选至少一条待补发记录。"
        return redirect(url_for("api.admin_console_global_questionnaire_external_push_logs", **params))
    result = RetryQuestionnaireExternalPushCommand()(
        RetryQuestionnaireExternalPushCommandDTO(
            push_log_ids=[int(item) for item in push_log_ids],
        )
    )
    notice = (
        "批量补发已执行："
        f"选中 {int(result.get('selected_count') or 0)} 条，"
        f"实际补发 {int(result.get('retried_count') or 0)} 条，"
        f"成功 {int(result.get('success_count') or 0)} 条，"
        f"失败 {int(result.get('failed_count') or 0)} 条"
    )
    skipped_count = int(result.get("skipped_count") or 0)
    if skipped_count:
        notice += f"，跳过 {skipped_count} 条"
    notice += "。"
    params["status"] = ""
    params["notice"] = notice
    return redirect(url_for("api.admin_console_global_questionnaire_external_push_logs", **params))


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
    bp.route("/admin/questionnaires/external-push-logs", methods=["GET"])(admin_console_global_questionnaire_external_push_logs)
    bp.route("/admin/questionnaires/external-push-logs/retry-batch", methods=["POST"])(admin_console_global_questionnaire_external_push_logs_retry_batch)
    bp.route("/admin/questionnaires/external-push-logs/<int:push_log_id>/retry", methods=["POST"])(admin_console_global_questionnaire_external_push_logs_retry)
    bp.route("/admin/questionnaires/<int:questionnaire_id>", methods=["GET"])(admin_console_questionnaire_detail)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/external-push-logs", methods=["GET"])(admin_console_questionnaire_external_push_logs)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/external-push-logs/<int:push_log_id>/retry", methods=["POST"])(admin_console_questionnaire_external_push_logs_retry)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/external-push-logs/retry-batch", methods=["POST"])(admin_console_questionnaire_external_push_logs_retry_batch)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/save", methods=["POST"])(admin_console_questionnaire_save)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/toggle", methods=["POST"])(admin_console_questionnaire_toggle)
