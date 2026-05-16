from __future__ import annotations

from flask import current_app, jsonify, request, url_for

from ..domains.automation_conversion.customer_acquisition_service import (
    build_customer_acquisition_preflight_payload,
    create_customer_acquisition_link,
    list_customer_acquisition_links,
    set_customer_acquisition_link_enabled,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_wecom_customer_acquisition_links_ui():
    return _render_admin_template(
        "wecom_customer_acquisition_links.html",
        active_nav="operations",
        page_title="获客助手链接",
        page_summary="绑定人工已创建的企业微信获客助手链接，并生成可投放的 customer_channel 链接。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("获客助手链接", None),
        ),
        preflight=build_customer_acquisition_preflight_payload(current_app.config),
    )


def api_list_wecom_customer_acquisition_links():
    status = str(request.args.get("status") or "").strip()
    return jsonify({"ok": True, "links": list_customer_acquisition_links(status=status)})


def api_create_wecom_customer_acquisition_link():
    payload = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    try:
        result = create_customer_acquisition_link(dict(payload or {}))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, **result}), 201


def api_disable_wecom_customer_acquisition_link(link_id: int):
    try:
        link = set_customer_acquisition_link_enabled(int(link_id), enabled=False)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "link": link})


def api_enable_wecom_customer_acquisition_link(link_id: int):
    try:
        link = set_customer_acquisition_link_enabled(int(link_id), enabled=True)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "link": link})


def api_wecom_customer_acquisition_preflight():
    return jsonify({"ok": True, "preflight": build_customer_acquisition_preflight_payload(current_app.config)})


def register_routes(bp):
    bp.route("/admin/wecom-customer-acquisition-links/ui", methods=["GET"])(
        admin_wecom_customer_acquisition_links_ui
    )
    bp.route("/api/admin/wecom-customer-acquisition-links", methods=["GET"])(
        api_list_wecom_customer_acquisition_links
    )
    bp.route("/api/admin/wecom-customer-acquisition-links", methods=["POST"])(
        api_create_wecom_customer_acquisition_link
    )
    bp.route("/api/admin/wecom-customer-acquisition-links/<int:link_id>/disable", methods=["POST"])(
        api_disable_wecom_customer_acquisition_link
    )
    bp.route("/api/admin/wecom-customer-acquisition-links/<int:link_id>/enable", methods=["POST"])(
        api_enable_wecom_customer_acquisition_link
    )
    bp.route("/api/admin/wecom-customer-acquisition-links/preflight", methods=["GET"])(
        api_wecom_customer_acquisition_preflight
    )
