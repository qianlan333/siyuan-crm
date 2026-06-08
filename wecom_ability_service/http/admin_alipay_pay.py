from __future__ import annotations

from typing import Any

from flask import Response, jsonify, request, url_for

from ..domains.alipay_pay import admin_service
from .admin_console import _breadcrumb_items, _render_admin_template


def _error_response(exc: Exception, *, status_code: int = 400):
    return jsonify({"ok": False, "error": str(exc)}), status_code


def admin_alipay_pay_transactions_page():
    try:
        payload = admin_service.list_orders(
            filters=request.args,
            limit=request.args.get("limit"),
            cursor=request.args.get("cursor", ""),
        )
    except admin_service.AlipayPayAdminError:
        payload = {"items": [], "next_cursor": "", "has_more": False, "limit": 20}
    return _render_admin_template(
        "alipay_pay_transactions.html",
        active_nav="wechat_pay_transactions",
        page_title="支付宝支付交易管理",
        page_summary="按订单创建时间检索支付宝订单，并导出当前筛选结果。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("支付宝交易管理", None)),
        product_options=admin_service.list_product_options(),
        default_filters={**admin_service.default_filters(), **{key: value for key, value in request.args.items()}},
        order_payload=payload,
        status_options=admin_service.ADMIN_ORDER_STATUSES,
    )


def api_admin_alipay_pay_orders():
    try:
        payload = admin_service.list_orders(
            filters=request.args,
            limit=request.args.get("limit"),
            cursor=request.args.get("cursor", ""),
        )
        return jsonify({"ok": True, **payload})
    except admin_service.AlipayPayAdminError as exc:
        return _error_response(exc)


def api_admin_alipay_pay_order_export():
    try:
        csv_text, file_name = admin_service.export_orders_csv(filters=request.args)
    except admin_service.AlipayPayAdminError as exc:
        return _error_response(exc)
    return Response(
        "\ufeff" + csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


def register_routes(bp) -> None:
    bp.route("/admin/alipay/transactions", methods=["GET"])(admin_alipay_pay_transactions_page)
    bp.route("/api/admin/alipay/orders", methods=["GET"])(api_admin_alipay_pay_orders)
    bp.route("/api/admin/alipay/order-export.csv", methods=["GET"])(api_admin_alipay_pay_order_export)
