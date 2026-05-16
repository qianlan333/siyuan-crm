from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for

from ..domains.wechat_pay import (
    WeChatPayConfigError,
    WeChatPayOrderError,
    build_checkout_page_state,
    create_jsapi_order,
    get_order_status,
    get_product,
    handle_wechat_pay_notification,
)
from ..infra.wechat_oauth import WeChatOAuthRequestError, exchange_wechat_oauth_code, fetch_wechat_userinfo
from ..infra.settings import get_setting
from .questionnaire_support import (
    _decode_oauth_state,
    _encode_oauth_state,
    _external_base_url,
    _is_wechat_browser,
    _mask_identity_value,
    _questionnaire_request_meta,
    _require_wechat_browser_api,
    _require_wechat_browser_page,
    _wechat_oauth_authorize_url,
    _wechat_oauth_is_configured,
    _wechat_oauth_scope,
)


logger = logging.getLogger("wechat_pay")


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_return_url(value: str) -> str:
    normalized = _normalized_text(value)
    if not normalized or not normalized.startswith("/") or normalized.startswith("//"):
        return "/"
    return normalized


def _payment_oauth_callback_url() -> str:
    return _external_base_url() + url_for("api.h5_wechat_pay_oauth_callback")


def _payment_oauth_start_url(return_url: str) -> str:
    query = urlencode({"return_url": _safe_return_url(return_url)})
    return f"{url_for('api.h5_wechat_pay_oauth_start')}?{query}"


def _wechat_h5_identity() -> dict[str, str]:
    for session_key in ("wechat_pay_h5_identity", "questionnaire_h5_identity"):
        identity = session.get(session_key) or {}
        if not isinstance(identity, dict):
            continue
        openid = _normalized_text(identity.get("openid"))
        if openid:
            return {
                "openid": openid,
                "unionid": _normalized_text(identity.get("unionid")),
                "respondent_key": _normalized_text(identity.get("respondent_key")),
                "external_userid": _normalized_text(identity.get("external_userid")),
            }
    return {}


def _error_response(exc: Exception, *, status_code: int = 400):
    return jsonify({"ok": False, "error": str(exc)}), status_code


def h5_wechat_pay_checkout(product_code: str):
    product = get_product(product_code)
    if not product:
        abort(404)
    wechat_gate = _require_wechat_browser_page()
    if wechat_gate is not None:
        return wechat_gate
    identity = _wechat_h5_identity()
    page_state = build_checkout_page_state(
        product_code=product_code,
        identity=identity,
        oauth_start_url=_payment_oauth_start_url(f"/pay/{product_code}"),
    )
    return render_template("wechat_pay_h5_checkout.html", page_state=page_state)


def h5_wechat_pay_oauth_start():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    return_url = _safe_return_url(request.args.get("return_url", "/"))
    authorize_url = _wechat_oauth_authorize_url(
        app_id=current_app.config["WECHAT_MP_APP_ID"],
        redirect_uri=_payment_oauth_callback_url(),
        scope=_wechat_oauth_scope(),
        state=_encode_oauth_state({"return_url": return_url}),
    )
    return redirect(authorize_url)


def h5_wechat_pay_oauth_callback():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    code = _normalized_text(request.args.get("code"))
    state_payload = _decode_oauth_state(_normalized_text(request.args.get("state")))
    return_url = _safe_return_url(_normalized_text(state_payload.get("return_url")) or "/")
    if not code:
        return jsonify({"ok": False, "error": "code is required"}), 400
    try:
        oauth_payload = exchange_wechat_oauth_code(
            app_id=current_app.config["WECHAT_MP_APP_ID"],
            app_secret=current_app.config["WECHAT_MP_APP_SECRET"],
            code=code,
        )
    except WeChatOAuthRequestError as exc:
        logger.exception("wechat pay oauth exchange failed return_url=%s", return_url)
        return jsonify({"ok": False, "error": f"wechat_oauth_exchange_failed: {exc}"}), 502
    if oauth_payload.get("errcode") not in (None, 0):
        logger.warning("wechat pay oauth exchange returned error payload=%s", oauth_payload)
        return jsonify({"ok": False, "error": "wechat_oauth_exchange_failed", "wechat_payload": oauth_payload}), 502
    openid = _normalized_text(oauth_payload.get("openid"))
    unionid = _normalized_text(oauth_payload.get("unionid"))
    access_token = _normalized_text(oauth_payload.get("access_token"))
    if not unionid and _wechat_oauth_scope() == "snsapi_userinfo" and access_token and openid:
        try:
            userinfo = fetch_wechat_userinfo(access_token=access_token, openid=openid)
            if userinfo.get("errcode") in (None, 0):
                unionid = _normalized_text(userinfo.get("unionid"))
        except WeChatOAuthRequestError:
            unionid = ""
    session["wechat_pay_h5_identity"] = {"openid": openid, "unionid": unionid}
    session.modified = True
    logger.info(
        "wechat pay oauth success openid=%s unionid=%s return_url=%s",
        _mask_identity_value(openid),
        _mask_identity_value(unionid),
        return_url,
    )
    return redirect(return_url, code=302)


def api_h5_wechat_pay_product(product_code: str):
    product = get_product(product_code)
    if not product:
        return jsonify({"ok": False, "error": "product_not_configured"}), 404
    return jsonify({"ok": True, "product": product})


def api_h5_wechat_pay_create_jsapi_order():
    wechat_gate = _require_wechat_browser_api()
    if wechat_gate is not None:
        return wechat_gate
    payload = request.get_json(silent=True) or {}
    product_code = _normalized_text(payload.get("product_code"))
    identity = _wechat_h5_identity()
    if not identity.get("openid"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "openid_required",
                    "oauth_start_url": _payment_oauth_start_url(f"/pay/{product_code}" if product_code else "/"),
                }
            ),
            401,
        )
    notify_url = _normalized_text(get_setting("WECHAT_PAY_NOTIFY_URL") or current_app.config.get("WECHAT_PAY_NOTIFY_URL")) or (
        _external_base_url() + url_for("api.api_h5_wechat_pay_notify")
    )
    try:
        result = create_jsapi_order(
            product_code=product_code,
            payer_openid=identity.get("openid", ""),
            respondent_key=identity.get("respondent_key", ""),
            unionid=identity.get("unionid", ""),
            external_userid=identity.get("external_userid", ""),
            client_order_ref=_normalized_text(payload.get("client_order_ref")),
            order_source=_normalized_text(payload.get("order_source")) or "h5_checkout",
            notify_url=notify_url,
            request_meta=_questionnaire_request_meta(),
        )
        return jsonify({"ok": True, **result})
    except WeChatPayConfigError as exc:
        return _error_response(exc, status_code=503)
    except WeChatPayOrderError as exc:
        return _error_response(exc, status_code=400)
    except Exception as exc:  # pragma: no cover - production envelope
        logger.exception("create WeChat Pay JSAPI order failed")
        return _error_response(exc, status_code=502)


def api_h5_wechat_pay_order_status(out_trade_no: str):
    refresh = _normalized_text(request.args.get("refresh")).lower() in {"1", "true", "yes", "on"}
    try:
        return jsonify({"ok": True, **get_order_status(out_trade_no=out_trade_no, refresh=refresh)})
    except WeChatPayOrderError as exc:
        return _error_response(exc, status_code=404)
    except Exception as exc:  # pragma: no cover - production envelope
        logger.exception("query WeChat Pay order status failed out_trade_no=%s", out_trade_no)
        return _error_response(exc, status_code=502)


def api_h5_wechat_pay_notify():
    body = request.get_data(as_text=True) or ""
    try:
        handle_wechat_pay_notification(body=body, headers=dict(request.headers))
    except Exception as exc:
        logger.exception("WeChat Pay notify failed")
        return jsonify({"code": "FAIL", "message": str(exc)}), 401
    return jsonify({"code": "SUCCESS", "message": "成功"})


def register_routes(bp) -> None:
    bp.route("/pay/<product_code>", methods=["GET"])(h5_wechat_pay_checkout)
    bp.route("/api/h5/wechat-pay/oauth/start", methods=["GET"])(h5_wechat_pay_oauth_start)
    bp.route("/api/h5/wechat-pay/oauth/callback", methods=["GET"])(h5_wechat_pay_oauth_callback)
    bp.route("/api/h5/wechat-pay/products/<product_code>", methods=["GET"])(api_h5_wechat_pay_product)
    bp.route("/api/h5/wechat-pay/jsapi/orders", methods=["POST"])(api_h5_wechat_pay_create_jsapi_order)
    bp.route("/api/h5/wechat-pay/orders/<out_trade_no>", methods=["GET"])(api_h5_wechat_pay_order_status)
    bp.route("/api/h5/wechat-pay/notify", methods=["POST"])(api_h5_wechat_pay_notify)
