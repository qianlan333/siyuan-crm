from __future__ import annotations

from typing import Any

from flask import jsonify, request, send_file, url_for

from ..domains.external_push import service as external_push_service
from ..domains.wechat_pay import admin_service, product_service
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import (
    current_admin_operator,
    validate_admin_console_action_token,
)


def _json_payload() -> dict[str, Any]:
    return dict(request.get_json(silent=True) or {})


def _error_response(exc: Exception, *, status_code: int = 400):
    return jsonify({"ok": False, "error": str(exc)}), status_code


def _mutation_token_error():
    token_error = validate_admin_console_action_token()
    if token_error:
        return jsonify({"ok": False, "error": token_error}), 400
    return None


def _product_public_url(product: dict[str, Any]) -> str:
    root = request.url_root.rstrip("/")
    return f"{root}/p/{product.get('product_code')}"


def admin_wechat_pay_products_page():
    return _render_admin_template(
        "wechat_pay_products.html",
        active_nav="wechat_pay_products",
        page_title="商品管理",
        page_summary="长图介绍页、支付确认与支付后引流的商品配置。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("交易管理", None),
            ("商品管理", None),
        ),
        page_mode="list",
        product_id=0,
    )


def admin_wechat_pay_product_new_page():
    return _render_admin_template(
        "wechat_pay_products.html",
        active_nav="wechat_pay_products",
        page_title="创建商品",
        page_summary="配置商品基础信息、引流渠道码和全景贴图切片。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("商品管理", url_for("api.admin_wechat_pay_products_page")),
            ("创建商品", None),
        ),
        page_mode="edit",
        product_id=0,
    )


def admin_wechat_pay_product_edit_page(product_id: int):
    return _render_admin_template(
        "wechat_pay_products.html",
        active_nav="wechat_pay_products",
        page_title="编辑商品",
        page_summary="维护商品基础信息、引流渠道码和全景贴图切片。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("商品管理", url_for("api.admin_wechat_pay_products_page")),
            ("编辑商品", None),
        ),
        page_mode="edit",
        product_id=int(product_id),
    )


def api_admin_wechat_pay_products():
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "items": product_service.list_admin_products()})
        token_response = _mutation_token_error()
        if token_response:
            return token_response
        product = product_service.create_admin_product(_json_payload(), operator=current_admin_operator())
        return jsonify({"ok": True, "product": product}), 201
    except product_service.WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_detail(product_id: int):
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "product": product_service.get_admin_product(product_id)})
        token_response = _mutation_token_error()
        if token_response:
            return token_response
        if request.method == "PUT":
            product = product_service.update_admin_product(product_id, _json_payload(), operator=current_admin_operator())
            return jsonify({"ok": True, "product": product})
        product_service.delete_admin_product(product_id, operator=current_admin_operator())
        return jsonify({"ok": True})
    except product_service.WeChatPayProductError as exc:
        return _error_response(exc, status_code=404 if request.method == "GET" else 400)


def api_admin_wechat_pay_product_enable(product_id: int):
    token_response = _mutation_token_error()
    if token_response:
        return token_response
    try:
        product = product_service.set_admin_product_status(product_id, "active", operator=current_admin_operator())
        return jsonify({"ok": True, "product": product})
    except product_service.WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_disable(product_id: int):
    token_response = _mutation_token_error()
    if token_response:
        return token_response
    try:
        product = product_service.set_admin_product_status(product_id, "disabled", operator=current_admin_operator())
        return jsonify({"ok": True, "product": product})
    except product_service.WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_copy(product_id: int):
    token_response = _mutation_token_error()
    if token_response:
        return token_response
    try:
        product = product_service.copy_admin_product(product_id, operator=current_admin_operator())
        return jsonify({"ok": True, "product": product}), 201
    except product_service.WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_share(product_id: int):
    try:
        product = product_service.get_admin_product(product_id)
        share = product_service.build_admin_product_share(product_id, product_url=_product_public_url(product))
        return jsonify({"ok": True, "share": share})
    except product_service.WeChatPayProductError as exc:
        return _error_response(exc, status_code=404)


def api_admin_wechat_pay_product_external_push(product_id: int):
    try:
        if request.method == "GET":
            return jsonify({"ok": True, "config": external_push_service.get_product_external_push_config(product_id)})
        token_response = _mutation_token_error()
        if token_response:
            return token_response
        config = external_push_service.save_product_external_push_config(
            product_id,
            _json_payload(),
            operator=current_admin_operator(),
        )
        return jsonify({"ok": True, "config": config})
    except external_push_service.ExternalPushError as exc:
        return _error_response(exc, status_code=404 if str(exc) == "商品不存在" else 400)


def api_admin_wechat_pay_product_external_push_test(product_id: int):
    token_response = _mutation_token_error()
    if token_response:
        return token_response
    try:
        result = external_push_service.send_product_external_push_test(product_id)
        return jsonify({"ok": True, "result": result})
    except external_push_service.ExternalPushError as exc:
        return _error_response(exc, status_code=404 if str(exc) == "商品不存在" else 400)


def api_admin_wechat_pay_product_lead_plans():
    return jsonify({"ok": True, "items": product_service.list_lead_plan_options()})


def api_admin_wechat_pay_product_lead_channels():
    return jsonify({"ok": True, "items": product_service.list_lead_channel_options()})


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


def api_admin_wechat_pay_order_external_push_deliveries(order_id: int):
    try:
        return jsonify({"ok": True, "items": external_push_service.list_order_deliveries(order_id)})
    except external_push_service.ExternalPushError as exc:
        return _error_response(exc, status_code=404)


def api_admin_wechat_pay_order_external_push_delivery_retry(order_id: int, delivery_id: str):
    token_response = _mutation_token_error()
    if token_response:
        return token_response
    try:
        result = external_push_service.retry_order_delivery(order_id, delivery_id)
        return jsonify({"ok": True, "result": result})
    except external_push_service.ExternalPushError as exc:
        return _error_response(exc, status_code=404 if "不存在" in str(exc) else 400)


def register_routes(bp) -> None:
    bp.route("/admin/wechat-pay/products", methods=["GET"])(admin_wechat_pay_products_page)
    bp.route("/admin/wechat-pay/products/new", methods=["GET"])(admin_wechat_pay_product_new_page)
    bp.route("/admin/wechat-pay/products/<int:product_id>/edit", methods=["GET"])(admin_wechat_pay_product_edit_page)
    bp.route("/admin/wechat-pay/transactions", methods=["GET"])(admin_wechat_pay_transactions_page)
    bp.route("/admin/wechat-pay/transactions/<int:order_id>", methods=["GET"])(admin_wechat_pay_transaction_detail_page)
    bp.route("/api/admin/wechat-pay/products", methods=["GET", "POST"])(api_admin_wechat_pay_products)
    bp.route("/api/admin/wechat-pay/products/lead-plans", methods=["GET"])(api_admin_wechat_pay_product_lead_plans)
    bp.route("/api/admin/wechat-pay/products/lead-channels", methods=["GET"])(api_admin_wechat_pay_product_lead_channels)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>", methods=["GET", "PUT", "DELETE"])(api_admin_wechat_pay_product_detail)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/enable", methods=["POST"])(api_admin_wechat_pay_product_enable)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/disable", methods=["POST"])(api_admin_wechat_pay_product_disable)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/copy", methods=["POST"])(api_admin_wechat_pay_product_copy)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/share", methods=["GET"])(api_admin_wechat_pay_product_share)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/external-push", methods=["GET", "PUT"])(api_admin_wechat_pay_product_external_push)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/external-push/test", methods=["POST"])(api_admin_wechat_pay_product_external_push_test)
    bp.route("/api/admin/wechat-pay/orders", methods=["GET"])(api_admin_wechat_pay_orders)
    bp.route("/api/admin/wechat-pay/orders/<int:order_id>/refunds", methods=["POST"])(api_admin_wechat_pay_order_refund)
    bp.route("/api/admin/wechat-pay/orders/<int:order_id>/external-push-deliveries", methods=["GET"])(api_admin_wechat_pay_order_external_push_deliveries)
    bp.route("/api/admin/wechat-pay/orders/<int:order_id>/external-push-deliveries/<delivery_id>/retry", methods=["POST"])(api_admin_wechat_pay_order_external_push_delivery_retry)
    bp.route("/api/admin/wechat-pay/order-exports", methods=["POST"])(api_admin_wechat_pay_order_exports)
    bp.route("/api/admin/wechat-pay/order-exports/<job_id>", methods=["GET"])(api_admin_wechat_pay_order_export)
    bp.route("/api/admin/wechat-pay/order-exports/<job_id>/download", methods=["GET"])(api_admin_wechat_pay_order_export_download)
