from __future__ import annotations

from typing import Any

from flask import jsonify, request, send_file, url_for

from ..domains.wechat_pay import admin_service
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import (
    current_admin_operator,
    validate_admin_console_action_token,
)


def _json_payload() -> dict[str, Any]:
    return dict(request.get_json(silent=True) or {})


def _error_response(exc: Exception, *, status_code: int = 400):
    return jsonify({"ok": False, "error": str(exc)}), status_code


def admin_wechat_pay_transactions_page():
    return _render_admin_template(
        "wechat_pay_transactions.html",
        active_nav="wechat_pay_transactions",
        page_title="微信支付交易管理",
        page_summary="按订单创建时间检索微信支付订单、导出筛选结果，并进入独立详情页查看订单状态。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("交易管理", None)),
        product_options=admin_service.list_product_options(),
        default_filters=admin_service.default_filters(),
        page_mode="list",
    )


def admin_wechat_pay_transaction_detail_page(order_id: int):
    try:
        detail = admin_service.get_order_detail(order_id)
    except admin_service.WeChatPayAdminError as exc:
        return _render_admin_template(
            "wechat_pay_transactions.html",
            active_nav="wechat_pay_transactions",
            page_title="微信支付订单详情",
            page_summary="订单不存在或已不可访问。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("交易管理", url_for("api.admin_wechat_pay_transactions_page")),
                ("订单详情", None),
            ),
            product_options=admin_service.list_product_options(),
            default_filters=admin_service.default_filters(),
            page_mode="detail",
            detail_error=str(exc),
        ), 404
    return _render_admin_template(
        "wechat_pay_transactions.html",
        active_nav="wechat_pay_transactions",
        page_title="微信支付订单详情",
        page_summary="退款只能在详情页申请，提交前需要二次确认微信单号和核对信息。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("交易管理", url_for("api.admin_wechat_pay_transactions_page")),
            ("订单详情", None),
        ),
        product_options=admin_service.list_product_options(),
        default_filters=admin_service.default_filters(),
        page_mode="detail",
        detail=detail,
    )


def api_admin_wechat_pay_orders():
    try:
        payload = admin_service.list_orders(
            filters=request.args,
            limit=request.args.get("limit"),
            cursor=request.args.get("cursor", ""),
        )
        return jsonify({"ok": True, **payload})
    except admin_service.WeChatPayAdminError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_order_exports():
    token_error = validate_admin_console_action_token()
    if token_error:
        return jsonify({"ok": False, "error": token_error}), 400
    payload = _json_payload()
    try:
        job = admin_service.create_export_job(
            filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else {},
            scope=payload.get("scope", "filtered"),
            file_format=payload.get("format", "xlsx"),
            cursor=payload.get("cursor", ""),
            limit=payload.get("limit", 20),
            requested_by=current_admin_operator(),
        )
        return jsonify({"ok": True, "job": job})
    except admin_service.WeChatPayAdminError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_order_export(job_id: str):
    try:
        return jsonify({"ok": True, "job": admin_service.get_export_job(job_id)})
    except admin_service.WeChatPayAdminError as exc:
        return _error_response(exc, status_code=404)


def api_admin_wechat_pay_order_export_download(job_id: str):
    try:
        path, file_name = admin_service.export_download_path(job_id)
    except admin_service.WeChatPayAdminError as exc:
        return _error_response(exc, status_code=404)
    mimetype = (
        "text/csv"
        if file_name.endswith(".csv")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return send_file(path, mimetype=mimetype, as_attachment=True, download_name=file_name)


def api_admin_wechat_pay_order_refund(order_id: int):
    token_error = validate_admin_console_action_token()
    if token_error:
        return jsonify({"ok": False, "error": token_error}), 400
    payload = _json_payload()
    try:
        result = admin_service.create_refund_request(
            order_id=order_id,
            refund_amount_total=payload.get("refund_amount_total"),
            reason=payload.get("reason"),
            transaction_id_confirmation=payload.get("transaction_id_confirmation"),
            checked=payload.get("checked"),
            operator=current_admin_operator(),
        )
        return jsonify({"ok": True, **result})
    except admin_service.WeChatPayAdminError as exc:
        return _error_response(exc)


def register_routes(bp) -> None:
    bp.route("/admin/wechat-pay/transactions", methods=["GET"])(admin_wechat_pay_transactions_page)
    bp.route("/admin/wechat-pay/transactions/<int:order_id>", methods=["GET"])(admin_wechat_pay_transaction_detail_page)
    bp.route("/api/admin/wechat-pay/orders", methods=["GET"])(api_admin_wechat_pay_orders)
    bp.route("/api/admin/wechat-pay/orders/<int:order_id>/refunds", methods=["POST"])(api_admin_wechat_pay_order_refund)
    bp.route("/api/admin/wechat-pay/order-exports", methods=["POST"])(api_admin_wechat_pay_order_exports)
    bp.route("/api/admin/wechat-pay/order-exports/<job_id>", methods=["GET"])(api_admin_wechat_pay_order_export)
    bp.route("/api/admin/wechat-pay/order-exports/<job_id>/download", methods=["GET"])(api_admin_wechat_pay_order_export_download)
