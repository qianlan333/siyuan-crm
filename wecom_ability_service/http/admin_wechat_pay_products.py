from __future__ import annotations

from typing import Any

from flask import jsonify, request, url_for

from ..domains.wechat_pay import (
    WeChatPayProductError,
    add_admin_product_slice,
    build_admin_product_share,
    copy_admin_product,
    create_admin_product,
    delete_admin_product,
    delete_admin_product_slice,
    get_admin_product,
    list_admin_products,
    list_lead_plan_options,
    reorder_admin_product_slices,
    set_admin_product_status,
    update_admin_product,
)
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import current_admin_operator, validate_admin_console_action_token


def _json_payload() -> dict[str, Any]:
    return dict(request.get_json(silent=True) or {})


def _mutation_error() -> tuple[Any, int] | None:
    token_error = validate_admin_console_action_token()
    if token_error:
        return jsonify({"ok": False, "error": token_error}), 400
    return None


def _error_response(exc: Exception, *, status_code: int = 400):
    return jsonify({"ok": False, "error": str(exc)}), status_code


def admin_wechat_pay_products_page():
    return _render_admin_template(
        "wechat_pay_products.html",
        active_nav="wechat_pay_products",
        page_title="商品管理",
        page_summary="长图介绍页、支付确认与支付后引流的商品配置。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("交易管理", None), ("商品管理", None)),
        page_actions=[{"label": "创建商品", "href": url_for("api.admin_wechat_pay_product_new_page"), "variant": "primary"}],
        page_mode="list",
    )


def admin_wechat_pay_product_new_page():
    return _render_admin_template(
        "wechat_pay_products.html",
        active_nav="wechat_pay_products",
        page_title="创建商品",
        page_summary="配置商品基础信息、引流计划和全景贴图切片。",
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
        page_summary="配置商品基础信息、引流计划和全景贴图切片。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("商品管理", url_for("api.admin_wechat_pay_products_page")),
            ("编辑商品", None),
        ),
        page_mode="edit",
        product_id=int(product_id),
    )


def api_admin_wechat_pay_products():
    if request.method == "GET":
        return jsonify({"ok": True, "items": list_admin_products()})
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        product = create_admin_product(_json_payload(), operator=current_admin_operator())
        return jsonify({"ok": True, "product": product})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product(product_id: int):
    if request.method == "GET":
        try:
            return jsonify({"ok": True, "product": get_admin_product(int(product_id))})
        except WeChatPayProductError as exc:
            return _error_response(exc, status_code=404)
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        if request.method == "PUT":
            product = update_admin_product(int(product_id), _json_payload(), operator=current_admin_operator())
            return jsonify({"ok": True, "product": product})
        delete_admin_product(int(product_id), operator=current_admin_operator())
        return jsonify({"ok": True})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_enable(product_id: int):
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        product = set_admin_product_status(int(product_id), "active", operator=current_admin_operator())
        return jsonify({"ok": True, "product": product})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_disable(product_id: int):
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        product = set_admin_product_status(int(product_id), "disabled", operator=current_admin_operator())
        return jsonify({"ok": True, "product": product})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_copy(product_id: int):
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        product = copy_admin_product(int(product_id), operator=current_admin_operator())
        return jsonify({"ok": True, "product": product})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_slices(product_id: int):
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        product = add_admin_product_slice(int(product_id), _json_payload())
        return jsonify({"ok": True, "product": product})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_slices_reorder(product_id: int):
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        product = reorder_admin_product_slices(int(product_id), _json_payload())
        return jsonify({"ok": True, "product": product})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_slice_delete(product_id: int, slice_id: int):
    token_response = _mutation_error()
    if token_response:
        return token_response
    try:
        product = delete_admin_product_slice(int(product_id), int(slice_id))
        return jsonify({"ok": True, "product": product})
    except WeChatPayProductError as exc:
        return _error_response(exc)


def api_admin_wechat_pay_product_lead_plans():
    return jsonify({"ok": True, "items": list_lead_plan_options()})


def api_admin_wechat_pay_product_share(product_id: int):
    try:
        product = get_admin_product(int(product_id))
        product_url = url_for(
            "api.h5_wechat_pay_product_page",
            product_code=product["product_code"],
            _external=True,
        )
        return jsonify(
            {
                "ok": True,
                "share": build_admin_product_share(int(product_id), product_url=product_url),
            }
        )
    except WeChatPayProductError as exc:
        return _error_response(exc, status_code=404)


def register_routes(bp) -> None:
    bp.route("/admin/wechat-pay/products", methods=["GET"])(admin_wechat_pay_products_page)
    bp.route("/admin/wechat-pay/products/new", methods=["GET"])(admin_wechat_pay_product_new_page)
    bp.route("/admin/wechat-pay/products/<int:product_id>/edit", methods=["GET"])(admin_wechat_pay_product_edit_page)
    bp.route("/api/admin/wechat-pay/products", methods=["GET", "POST"])(api_admin_wechat_pay_products)
    bp.route("/api/admin/wechat-pay/products/lead-plans", methods=["GET"])(api_admin_wechat_pay_product_lead_plans)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>", methods=["GET", "PUT", "DELETE"])(api_admin_wechat_pay_product)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/share", methods=["GET"])(api_admin_wechat_pay_product_share)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/enable", methods=["POST"])(api_admin_wechat_pay_product_enable)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/disable", methods=["POST"])(api_admin_wechat_pay_product_disable)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/copy", methods=["POST"])(api_admin_wechat_pay_product_copy)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/slices", methods=["POST"])(api_admin_wechat_pay_product_slices)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/slices/reorder", methods=["PUT"])(api_admin_wechat_pay_product_slices_reorder)
    bp.route("/api/admin/wechat-pay/products/<int:product_id>/slices/<int:slice_id>", methods=["DELETE"])(api_admin_wechat_pay_product_slice_delete)
