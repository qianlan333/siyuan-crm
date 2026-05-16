"""用户激活漏斗看板 — admin 后台路由

页面: ``/admin/hxc-dashboard``  (HTML, Jinja 模板嵌入 JSON + Tabulator)
即时刷新: ``POST /api/admin/hxc-dashboard/refresh``
发送人白名单 CRUD: ``/api/admin/hxc-dashboard/send-config``
一键群发: ``POST /api/admin/hxc-dashboard/broadcast``
"""
from __future__ import annotations

from typing import Any

from flask import jsonify, request, url_for

from ..domains.user_ops.hxc_dashboard_snapshot_service import refresh_hxc_dashboard_snapshot
from ..domains.user_ops.hxc_dashboard_view_service import (
    get_dashboard_summary,
    list_hxc_dashboard_rows,
)
from ..domains.user_ops.hxc_send_config_service import (
    broadcast_to_filtered_users,
    build_send_config_page_data,
    delete_send_config,
    list_send_configs,
    upsert_send_config,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from .common import _coerce_request_bool


def _json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True) or {}
    return payload if isinstance(payload, dict) else {}


def _string_field(payload: dict[str, Any], field: str) -> str:
    return str(payload.get(field) or "").strip()


def _int_field(payload: dict[str, Any], field: str, *, default: int) -> int:
    try:
        return int(payload.get(field, default))
    except (TypeError, ValueError):
        return default


def _optional_int_field(payload: dict[str, Any], field: str) -> int | None:
    value = payload.get(field)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list_field(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if value is None:
        return []
    values = value if isinstance(value, list | tuple | set) else [value]
    return [item for item in (str(raw or "").strip() for raw in values) if item]


def _int_list_field(payload: dict[str, Any], field: str, *, limit: int) -> list[int]:
    values = payload.get(field) or []
    if not isinstance(values, list | tuple | set):
        values = [values]
    result: list[int] = []
    for raw in list(values)[:limit]:
        try:
            result.append(int(raw))
        except (TypeError, ValueError):
            pass
    return result


def admin_hxc_dashboard_workspace():
    rows = list_hxc_dashboard_rows()
    summary = get_dashboard_summary()
    send_configs = list_send_configs()
    return _render_admin_template(
        "hxc_dashboard.html",
        active_nav="user_ops_funnel",
        page_title="用户激活漏斗看板",
        page_summary=(
            "CRM 三表 (lead_pool / people / 激活问卷) 手机号并集 × 黄小璨用户/会员/会话/消息 "
            "聚合, 每 30 分钟自动刷新. 列头可筛选, 表格右上角可导出 CSV / Excel."
        ),
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("用户激活漏斗看板", None),
        ),
        dashboard_rows=rows,
        dashboard_summary=summary,
        send_configs=send_configs,
    )


def admin_hxc_send_config_page():
    page_data = build_send_config_page_data()
    return _render_admin_template(
        "hxc_send_config.html",
        active_nav="user_ops_funnel",
        page_title="群发发送人管理",
        page_summary="从企微通讯录选择群发发送人，设置优先级和启用状态。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("激活漏斗看板", url_for("api.admin_hxc_dashboard_workspace")),
            ("群发发送人管理", None),
        ),
        **page_data,
    )


def admin_hxc_refresh_directory():
    from ..domains.admin_auth.service import sync_admin_wecom_directory_members
    result = sync_admin_wecom_directory_members(operator="hxc_send_config")
    return jsonify(result)


def admin_hxc_dashboard_refresh():
    trigger_source = _string_field(_json_body(), "trigger_source") or "admin"
    result = refresh_hxc_dashboard_snapshot(trigger_source=str(trigger_source))
    status_code = 200 if result.get("ok") else 500
    return jsonify(result), status_code


# ── 发送人白名单 CRUD ──

def admin_hxc_send_config_list():
    return jsonify(list_send_configs())


def admin_hxc_send_config_upsert():
    body = _json_body()
    sender_userid = _string_field(body, "sender_userid")
    if not sender_userid:
        return jsonify({"ok": False, "error": "sender_userid required"}), 400
    result = upsert_send_config(
        sender_userid=sender_userid,
        display_name=_string_field(body, "display_name"),
        priority=_int_field(body, "priority", default=100),
        is_active=_coerce_request_bool(body.get("is_active", True), default=True),
    )
    return jsonify(result)


def admin_hxc_send_config_delete(sender_userid):
    result = delete_send_config(sender_userid)
    return jsonify(result)


# ── 一键群发 ──

def admin_hxc_dashboard_broadcast():
    body = _json_body()
    external_userids = _string_list_field(body, "external_userids")
    content = _string_field(body, "content")
    image_library_ids = _int_list_field(body, "image_library_ids", limit=3)
    miniprogram_library_id = _optional_int_field(body, "miniprogram_library_id")

    if not external_userids:
        return jsonify({"ok": False, "error": "no targets"}), 400
    if not content and not image_library_ids and not miniprogram_library_id:
        return jsonify({"ok": False, "error": "empty content"}), 400

    result = broadcast_to_filtered_users(
        external_userids=external_userids,
        content=content,
        image_library_ids=image_library_ids or None,
        miniprogram_library_id=miniprogram_library_id,
        operator_id="admin",
    )
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


def register_routes(bp):
    bp.route("/admin/hxc-dashboard", methods=["GET"])(admin_hxc_dashboard_workspace)
    bp.route("/admin/hxc-send-config", methods=["GET"])(admin_hxc_send_config_page)
    bp.route("/api/admin/hxc-dashboard/refresh", methods=["POST"])(admin_hxc_dashboard_refresh)
    bp.route("/api/admin/hxc-dashboard/refresh-directory", methods=["POST"])(admin_hxc_refresh_directory)
    bp.route("/api/admin/hxc-dashboard/send-config", methods=["GET"])(admin_hxc_send_config_list)
    bp.route("/api/admin/hxc-dashboard/send-config", methods=["POST"])(admin_hxc_send_config_upsert)
    bp.route("/api/admin/hxc-dashboard/send-config/<sender_userid>", methods=["DELETE"])(admin_hxc_send_config_delete)
    bp.route("/api/admin/hxc-dashboard/broadcast", methods=["POST"])(admin_hxc_dashboard_broadcast)
