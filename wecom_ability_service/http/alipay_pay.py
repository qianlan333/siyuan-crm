from __future__ import annotations

import logging
from typing import Any

from flask import abort, current_app, jsonify, render_template, request, url_for

from ..domains.alipay_pay import (
    AlipayPayConfigError,
    AlipayPayOrderError,
    build_checkout_page_state,
    create_wap_order,
    get_order_status,
    handle_alipay_notify,
    handle_alipay_return,
)
from ..infra.settings import get_setting
from .questionnaire_support import _external_base_url, _questionnaire_request_meta


logger = logging.getLogger("alipay_pay")


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _error_response(exc: Exception, *, status_code: int = 400):
    return jsonify({"ok": False, "error": str(exc)}), status_code


def _notify_url() -> str:
    configured = _normalized_text(get_setting("ALIPAY_NOTIFY_URL") or current_app.config.get("ALIPAY_NOTIFY_URL"))
    return configured or (_external_base_url() + url_for("api.api_h5_alipay_notify"))


def _return_url() -> str:
    configured = _normalized_text(get_setting("ALIPAY_RETURN_URL") or current_app.config.get("ALIPAY_RETURN_URL"))
    return configured or (_external_base_url() + url_for("api.api_h5_alipay_return"))


def h5_alipay_pay_checkout(product_code: str):
    try:
        page_state = build_checkout_page_state(product_code)
    except AlipayPayOrderError:
        abort(404)
    return render_template("alipay_pay_h5_checkout.html", page_state=page_state)


def api_h5_alipay_create_wap_order():
    payload = request.get_json(silent=True) or {}
    product_code = _normalized_text(payload.get("product_code"))
    try:
        result = create_wap_order(
            product_code=product_code,
            client_order_ref=_normalized_text(payload.get("client_order_ref")),
            order_source=_normalized_text(payload.get("order_source")) or "h5_alipay_wap",
            notify_url=_notify_url(),
            return_url=_return_url(),
            mobile=_normalized_text(payload.get("mobile")),
            identity=_normalized_text(payload.get("identity")),
            request_meta=_questionnaire_request_meta(),
        )
        return jsonify({"ok": True, **result})
    except AlipayPayConfigError as exc:
        return _error_response(exc, status_code=503)
    except AlipayPayOrderError as exc:
        return _error_response(exc, status_code=400)
    except Exception as exc:  # pragma: no cover - production envelope
        logger.exception("create Alipay WAP order failed")
        return _error_response(exc, status_code=502)


def api_h5_alipay_order_status(out_trade_no: str):
    refresh = _normalized_text(request.args.get("refresh")).lower() in {"1", "true", "yes", "on"}
    try:
        return jsonify({"ok": True, **get_order_status(out_trade_no=out_trade_no, refresh=refresh)})
    except AlipayPayOrderError as exc:
        return _error_response(exc, status_code=404)
    except Exception as exc:  # pragma: no cover - production envelope
        logger.exception("query Alipay order status failed out_trade_no=%s", out_trade_no)
        return _error_response(exc, status_code=502)


def api_h5_alipay_notify():
    params = request.form.to_dict(flat=True)
    if not params and request.is_json:
        params = dict(request.get_json(silent=True) or {})
    try:
        handle_alipay_notify(params=params, headers=dict(request.headers))
    except Exception as exc:
        logger.exception("Alipay notify failed")
        return "fail", 400, {"Content-Type": "text/plain; charset=utf-8"}
    return "success", 200, {"Content-Type": "text/plain; charset=utf-8"}


def api_h5_alipay_return():
    params = request.args.to_dict(flat=True)
    page_state = {"order": {}, "error": ""}
    if params.get("out_trade_no"):
        try:
            page_state = handle_alipay_return(params=params)
        except AlipayPayOrderError as exc:
            page_state = {"order": {}, "error": str(exc)}
    return render_template("alipay_pay_return.html", page_state=page_state)


def register_routes(bp) -> None:
    bp.route("/alipay/pay/<product_code>", methods=["GET"])(h5_alipay_pay_checkout)
    bp.route("/api/h5/alipay/wap/orders", methods=["POST"])(api_h5_alipay_create_wap_order)
    bp.route("/api/h5/alipay/notify", methods=["POST"])(api_h5_alipay_notify)
    bp.route("/api/h5/alipay/return", methods=["GET"])(api_h5_alipay_return)
    bp.route("/api/h5/alipay/orders/<out_trade_no>", methods=["GET"])(api_h5_alipay_order_status)
