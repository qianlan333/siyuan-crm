from __future__ import annotations

from flask import jsonify, request, url_for

from ..domains.admin_console.customer_profile_service import (
    build_customer_detail_payload,
    build_customer_list_payload,
    get_customer_messages_payload,
    get_customer_profile_payload,
    get_customer_profile_tags_payload,
    get_customer_questionnaire_answers_payload,
)
from ..domains.admin_console.service import (
    execute_customer_tag_action,
    execute_customer_task_action,
    preview_customer_tag_action,
    preview_customer_task_action,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token


def _lookup_params(source) -> dict[str, str]:
    getter = getattr(source, "get", lambda *_: "")
    return {
        "external_userid": str(getter("external_userid") or "").strip(),
        "mobile": str(getter("mobile") or "").strip(),
        "user_id": str(getter("user_id") or "").strip(),
    }


def admin_console_customers():
    payload = build_customer_list_payload(request.args)
    return _render_admin_template(
        "customers.html",
        active_nav="customers",
        page_title="客户中心",
        page_summary="按关键词、负责人、手机号或标签快速找到客户。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("客户", None)),
        customer_payload=payload,
    )


def _render_customer_detail_page(
    external_userid: str,
    *,
    legacy_tab: str = "",
    page_notice: str = "",
    page_error: str = "",
    action_result: dict | None = None,
):
    payload = build_customer_detail_payload(external_userid, legacy_tab=legacy_tab)
    if not payload:
        return _render_admin_template(
            "placeholder.html",
            active_nav="customers",
            page_title="客户不存在",
            page_summary="当前客户编号没有查到对应客户。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("客户", url_for("api.admin_console_customers")),
                (external_userid, None),
            ),
            actions=[{"label": "返回客户列表", "href": url_for("api.admin_console_customers"), "variant": "secondary"}],
            state_title="客户不存在",
            state_body="请确认客户编号是否正确，或稍后重试。",
            state_items=["检查客户编号是否输入正确", "确认当前环境已经同步到该客户数据"],
            page_error=page_error or "未找到客户",
        ), 404

    return _render_admin_template(
        "customer_detail.html",
        active_nav="customers",
        page_title=payload["customer"].get("customer_name") or external_userid,
        page_summary="查看客户基础资料、实时标签、问卷问答和聊天记录。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("客户", url_for("api.admin_console_customers")),
            (payload["customer"].get("customer_name") or external_userid, None),
        ),
        customer_payload=payload,
        page_notice=page_notice,
        page_error=page_error,
        show_shell_meta=False,
        admin_action_token=ensure_admin_console_action_token(),
        action_result=action_result or {},
        customer_profile_urls={
            "profile": url_for("api.admin_customer_profile_api", external_userid=external_userid),
            "tags": url_for("api.admin_customer_profile_tags_api", external_userid=external_userid),
            "questionnaire_answers": url_for(
                "api.admin_customer_profile_questionnaire_answers_api",
                external_userid=external_userid,
            ),
            "messages": url_for("api.admin_customer_profile_messages_api", external_userid=external_userid),
            "automation_member": url_for("api.api_admin_automation_conversion_member", external_contact_id=external_userid),
            "automation_put_in_pool": url_for("api.api_admin_automation_conversion_put_in_pool"),
            "automation_remove_from_pool": url_for("api.api_admin_automation_conversion_remove_from_pool"),
            "automation_set_focus": url_for("api.api_admin_automation_conversion_set_focus"),
            "automation_set_normal": url_for("api.api_admin_automation_conversion_set_normal"),
            "automation_mark_won": url_for("api.api_admin_automation_conversion_mark_won"),
            "automation_unmark_won": url_for("api.api_admin_automation_conversion_unmark_won"),
            "automation_push_openclaw": url_for("api.api_admin_automation_conversion_push_openclaw"),
        },
    )


def admin_console_customer_detail(external_userid: str):
    legacy_tab = str(request.args.get("tab") or "").strip()
    return _render_customer_detail_page(external_userid, legacy_tab=legacy_tab)


def admin_console_customer_tag_action(external_userid: str):
    legacy_tab = str(request.form.get("return_tab") or "tags").strip() or "tags"
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        if request.form.get("confirm"):
            action_result = execute_customer_tag_action(
                external_userid=external_userid,
                userid=str(request.form.get("userid") or "").strip(),
                action=str(request.form.get("tag_action") or "").strip(),
                tag_ids=str(request.form.get("tag_ids") or "").strip().split(","),
                operator=operator,
            )
            return _render_customer_detail_page(
                external_userid,
                legacy_tab=legacy_tab,
                page_notice="标签操作已执行，并已记录操作人和时间。",
                action_result=action_result,
            )
        action_result = preview_customer_tag_action(
            external_userid=external_userid,
            userid=str(request.form.get("userid") or "").strip(),
            action=str(request.form.get("tag_action") or "").strip(),
            tag_ids=str(request.form.get("tag_ids") or "").strip().split(","),
        )
        return _render_customer_detail_page(
            external_userid,
            legacy_tab=legacy_tab,
            page_notice="这里会先展示操作预览，确认后才会真正执行。",
            action_result=action_result,
        )
    except Exception as exc:
        return _render_customer_detail_page(
            external_userid,
            legacy_tab=legacy_tab,
            page_error=str(exc),
        )


def admin_console_customer_task_action(external_userid: str):
    legacy_tab = str(request.form.get("return_tab") or "tasks").strip() or "tasks"
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        if request.form.get("confirm"):
            action_result = execute_customer_task_action(
                external_userid=external_userid,
                task_type=str(request.form.get("task_type") or "").strip(),
                userid=str(request.form.get("userid") or "").strip(),
                content=str(request.form.get("content") or "").strip(),
                operator=operator,
            )
            return _render_customer_detail_page(
                external_userid,
                legacy_tab=legacy_tab,
                page_notice="触达任务已执行，并已记录操作人和时间。",
                action_result=action_result,
            )
        action_result = preview_customer_task_action(
            external_userid=external_userid,
            task_type=str(request.form.get("task_type") or "").strip(),
            userid=str(request.form.get("userid") or "").strip(),
            content=str(request.form.get("content") or "").strip(),
        )
        return _render_customer_detail_page(
            external_userid,
            legacy_tab=legacy_tab,
            page_notice="这里会先展示操作预览，确认后才会真正执行。",
            action_result=action_result,
        )
    except Exception as exc:
        return _render_customer_detail_page(
            external_userid,
            legacy_tab=legacy_tab,
            page_error=str(exc),
        )


def admin_customer_profile_api():
    try:
        payload = get_customer_profile_payload(**_lookup_params(request.args))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not payload:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, **payload})


def admin_customer_profile_tags_api():
    external_userid = str(request.args.get("external_userid") or "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required", "tags": []}), 400
    try:
        payload = get_customer_profile_tags_payload(external_userid=external_userid)
        return jsonify({"ok": True, **payload})
    except Exception:
        return jsonify({"ok": False, "error": "当前无法加载实时标签", "external_userid": external_userid, "tags": []})


def admin_customer_profile_questionnaire_answers_api():
    try:
        payload = get_customer_questionnaire_answers_payload(**_lookup_params(request.args))
        return jsonify({"ok": True, **payload})
    except LookupError:
        return jsonify({"ok": False, "error": "customer not found", "answers": []}), 404
    except Exception:
        return jsonify({"ok": False, "error": "当前无法加载问卷记录", "answers": []})


def admin_customer_profile_messages_api():
    try:
        payload = get_customer_messages_payload(
            **_lookup_params(request.args),
            limit=request.args.get("limit"),
            fetch_all=request.args.get("fetch_all"),
        )
        return jsonify({"ok": True, **payload})
    except LookupError:
        return jsonify({"ok": False, "error": "customer not found", "messages": []}), 404
    except Exception:
        return jsonify({"ok": False, "error": "当前无法加载聊天记录", "messages": []})


def register_routes(bp):
    bp.route("/admin/customers", methods=["GET"])(admin_console_customers)
    bp.route("/admin/customers/<external_userid>", methods=["GET"])(admin_console_customer_detail)
    bp.route("/admin/customers/<external_userid>/tags", methods=["POST"])(admin_console_customer_tag_action)
    bp.route("/admin/customers/<external_userid>/tasks", methods=["POST"])(admin_console_customer_task_action)
    bp.route("/api/admin/customers/profile", methods=["GET"])(admin_customer_profile_api)
    bp.route("/api/admin/customers/profile/tags", methods=["GET"])(admin_customer_profile_tags_api)
    bp.route("/api/admin/customers/profile/questionnaire-answers", methods=["GET"])(
        admin_customer_profile_questionnaire_answers_api
    )
    bp.route("/api/admin/customers/profile/messages", methods=["GET"])(admin_customer_profile_messages_api)
