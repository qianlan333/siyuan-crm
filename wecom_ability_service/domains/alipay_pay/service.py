from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

from flask import current_app

from ...infra.settings import get_setting
from . import repo
from .client import AlipayPayClient, AlipayPayClientConfig, AlipayPayClientError
from ..wechat_pay.product_service import get_lead_qr_for_product_code, get_product


logger = logging.getLogger(__name__)


class AlipayPayConfigError(RuntimeError):
    pass


class AlipayPayOrderError(RuntimeError):
    pass


PAID_TRADE_STATUSES = {"TRADE_SUCCESS", "TRADE_FINISHED"}
TRADE_STATUS_TO_ORDER_STATUS = {
    "WAIT_BUYER_PAY": "paying",
    "TRADE_SUCCESS": "paid",
    "TRADE_FINISHED": "paid",
    "TRADE_CLOSED": "closed",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _setting(key: str, default: str = "") -> str:
    stored = get_setting(key)
    if stored is not None:
        return _normalized_text(stored)
    return _normalized_text(current_app.config.get(key, default))


def _setting_bool(key: str, default: bool = False) -> bool:
    value = _setting(key)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _setting_int(key: str, default: int) -> int:
    try:
        return int(_setting(key) or default)
    except (TypeError, ValueError):
        return int(default)


def _client_config() -> AlipayPayClientConfig:
    return AlipayPayClientConfig(
        app_id=_setting("ALIPAY_APP_ID"),
        app_private_key_path=_setting("ALIPAY_APP_PRIVATE_KEY_PATH"),
        alipay_public_key_path=_setting("ALIPAY_PUBLIC_KEY_PATH"),
        server_url=_setting("ALIPAY_SERVER_URL", "https://openapi.alipay.com/gateway.do")
        or "https://openapi.alipay.com/gateway.do",
        sign_type=_setting("ALIPAY_SIGN_TYPE", "RSA2") or "RSA2",
        timeout_seconds=_setting_int("ALIPAY_TIMEOUT_SECONDS", 10),
    )


def _create_alipay_pay_client() -> AlipayPayClient:
    return AlipayPayClient(_client_config())


def _seller_id_config() -> str:
    return _setting("ALIPAY_SELLER_ID") or _setting("ALIPAY_PID") or _setting("ALIPAY_MERCHANT_ID")


def _require_ready_for_order() -> AlipayPayClientConfig:
    if not _setting_bool("ALIPAY_ENABLED", False):
        raise AlipayPayConfigError("alipay_pay_disabled")
    config = _client_config()
    missing = []
    for key, value in {
        "ALIPAY_APP_ID": config.app_id,
        "ALIPAY_APP_PRIVATE_KEY_PATH": config.app_private_key_path,
        "ALIPAY_PUBLIC_KEY_PATH": config.alipay_public_key_path,
    }.items():
        if not _normalized_text(value):
            missing.append(key)
    if missing:
        raise AlipayPayConfigError("missing Alipay config: " + ", ".join(missing))
    return config


def _generate_out_trade_no() -> str:
    return "ALP" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + secrets.token_hex(6).upper()


def _safe_success_url(value: str) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return ""
    if normalized.startswith(("https://", "http://", "/")) and not normalized.startswith("//"):
        return normalized
    return ""


def _timeout_express() -> str:
    return _setting("ALIPAY_TIMEOUT_EXPRESS", "30m") or "30m"


def _expires_at_text(timeout_express: str) -> str:
    text = _normalized_text(timeout_express).lower()
    amount = 30
    unit = "m"
    if len(text) >= 2:
        try:
            amount = int(text[:-1])
            unit = text[-1]
        except (TypeError, ValueError):
            amount = 30
            unit = "m"
    minutes = amount
    if unit == "h":
        minutes = amount * 60
    elif unit == "d":
        minutes = amount * 24 * 60
    return (datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes))).strftime("%Y-%m-%dT%H:%M:%SZ")


def _amount_yuan_text(amount_total: int) -> str:
    return f"{Decimal(int(amount_total)) / Decimal(100):.2f}"


def _amount_total_from_yuan(value: Any) -> int | None:
    text = _normalized_text(value)
    if not text:
        return None
    try:
        amount = Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise AlipayPayOrderError("alipay_amount_invalid") from exc
    return int(amount * 100)


def _normalize_order_mobile(*, product: dict[str, Any], mobile: str) -> str:
    text = _normalized_text(mobile)
    if not text:
        if product.get("require_mobile"):
            raise AlipayPayOrderError("mobile_required")
        return ""
    from ..identity import service as identity_service

    try:
        return identity_service.normalize_mobile(text)
    except ValueError as exc:
        raise AlipayPayOrderError(str(exc)) from exc


def _paid_not_full_refunded(order: dict[str, Any]) -> bool:
    status = _normalized_text(order.get("status"))
    trade_status = _normalized_text(order.get("trade_status"))
    amount_total = int(order.get("amount_total") or 0)
    refunded = int(order.get("refunded_amount_total") or 0)
    return (status == "paid" or trade_status in PAID_TRADE_STATUSES) and not (amount_total > 0 and refunded >= amount_total)


def _order_public_payload(order: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "out_trade_no": _normalized_text(order.get("out_trade_no")),
        "trade_no": _normalized_text(order.get("trade_no")),
        "product_code": _normalized_text(order.get("product_code")),
        "product_name": _normalized_text(order.get("product_name")),
        "amount_total": int(order.get("amount_total") or 0),
        "currency": _normalized_text(order.get("currency")) or "CNY",
        "status": _normalized_text(order.get("status")),
        "trade_status": _normalized_text(order.get("trade_status")),
        "success_url": _safe_success_url(order.get("success_url")),
        "paid_at": _normalized_text(order.get("paid_at")),
        "created_at": _normalized_text(order.get("created_at")),
    }
    if _paid_not_full_refunded(order):
        lead_qr = get_lead_qr_for_product_code(payload["product_code"])
        if lead_qr.get("qr_url"):
            payload["lead_qr"] = lead_qr
    return payload


def _passback_params(*, product_code: str, client_order_ref: str, order_source: str) -> str:
    return urlencode(
        {
            "product_code": _normalized_text(product_code),
            "client_order_ref": _normalized_text(client_order_ref),
            "order_source": _normalized_text(order_source) or "h5_alipay_wap",
        }
    )


def build_checkout_page_state(product_code: str) -> dict[str, Any]:
    product = get_product(product_code)
    if not product:
        raise AlipayPayOrderError("product_not_configured")
    return {
        "product": product,
        "create_order_url": "/api/h5/alipay/wap/orders",
        "status_url_template": "/api/h5/alipay/orders/{out_trade_no}",
        "enabled": _setting_bool("ALIPAY_ENABLED", False),
        "require_mobile": bool(product.get("require_mobile")),
        "cta_text": _normalized_text(product.get("cta_text")) or "确认支付",
        "lead_plan_configured": bool(product.get("lead_plan_configured")),
    }


def create_wap_order(
    *,
    product_code: str,
    client_order_ref: str = "",
    order_source: str = "h5_alipay_wap",
    notify_url: str,
    return_url: str,
    mobile: str = "",
    identity: str = "",
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_ready_for_order()
    product = get_product(product_code)
    if not product:
        raise AlipayPayOrderError("product_not_configured")
    amount_total = int(product.get("amount_total") or 0)
    if amount_total <= 0:
        raise AlipayPayOrderError("product_amount_invalid")
    normalized_mobile = _normalize_order_mobile(product=product, mobile=mobile)
    out_trade_no = _generate_out_trade_no()
    timeout_express = _timeout_express()
    success_url = _safe_success_url(product.get("success_url"))
    order = repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "order_source": _normalized_text(order_source) or "h5_alipay_wap",
            "client_order_ref": client_order_ref,
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["description"],
            "amount_total": amount_total,
            "currency": product.get("currency") or "CNY",
            "mobile_snapshot": normalized_mobile,
            "identity_snapshot": identity,
            "status": "created",
            "success_url": success_url,
            "metadata": product.get("metadata") or {},
            "request_meta": request_meta or {},
            "expires_at": _expires_at_text(timeout_express),
        }
    )
    biz_payload = {
        "out_trade_no": out_trade_no,
        "total_amount": _amount_yuan_text(amount_total),
        "subject": product["name"][:256],
        "body": (product.get("description") or product["name"])[:400],
        "product_code": "QUICK_WAP_WAY",
        "timeout_express": timeout_express,
        "passback_params": _passback_params(
            product_code=product["product_code"],
            client_order_ref=client_order_ref,
            order_source=order_source,
        ),
    }
    seller_id = _seller_id_config()
    if seller_id:
        biz_payload["seller_id"] = seller_id
    try:
        payment_url = _create_alipay_pay_client().create_wap_pay_url(
            biz_payload=biz_payload,
            notify_url=_normalized_text(notify_url),
            return_url=_normalized_text(return_url),
        )
        order = repo.update_order_payment_request(
            out_trade_no,
            status="paying",
            request_payload=biz_payload,
            response_payload={"payment_url": payment_url, "method": "GET"},
        )
    except Exception as exc:
        repo.mark_order_failed(out_trade_no, error_message=str(exc))
        raise
    return {
        "order": _order_public_payload(order),
        "payment_url": payment_url,
    }


def _validate_trade_amount(order: dict[str, Any], trade: dict[str, Any]) -> None:
    expected = int(order.get("amount_total") or 0)
    actual = _amount_total_from_yuan(trade.get("total_amount"))
    if actual is None:
        raise AlipayPayOrderError("alipay_total_amount_missing")
    if actual != expected:
        raise AlipayPayOrderError("alipay_total_amount_mismatch")


def _validate_notify_identity(params: dict[str, Any], order: dict[str, Any]) -> None:
    config = _client_config()
    if _normalized_text(params.get("app_id")) != _normalized_text(config.app_id):
        raise AlipayPayOrderError("alipay_app_id_mismatch")
    sign_type = _normalized_text(params.get("sign_type"))
    if sign_type and sign_type != _normalized_text(config.sign_type):
        raise AlipayPayOrderError("alipay_sign_type_mismatch")
    seller_id = _seller_id_config()
    if seller_id and _normalized_text(params.get("seller_id")) != seller_id:
        raise AlipayPayOrderError("alipay_seller_id_mismatch")
    if _normalized_text(params.get("out_trade_no")) != _normalized_text(order.get("out_trade_no")):
        raise AlipayPayOrderError("alipay_out_trade_no_mismatch")
    _validate_trade_amount(order, params)


def _apply_trade(
    trade: dict[str, Any],
    *,
    event_type: str,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_trade_no = _normalized_text(trade.get("out_trade_no"))
    if not out_trade_no:
        raise AlipayPayOrderError("out_trade_no_missing")
    order = repo.get_order(out_trade_no)
    if not order:
        raise AlipayPayOrderError("order_not_found")
    _validate_trade_amount(order, trade)
    updated = repo.update_order_from_trade(trade, payload_kind="notify" if event_type == "notify" else "query")
    if not updated:
        raise AlipayPayOrderError("order_not_found")
    repo.insert_event(
        out_trade_no=out_trade_no,
        event_type=event_type,
        trade_no=_normalized_text(trade.get("trade_no")),
        trade_status=_normalized_text(trade.get("trade_status")),
        payload=trade,
        headers=headers or {},
    )
    return updated


def handle_alipay_notify(*, params: dict[str, Any], headers: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {key: value for key, value in dict(params or {}).items()}
    client = _create_alipay_pay_client()
    if not client.verify_notification(payload):
        raise AlipayPayOrderError("invalid_alipay_notify_signature")
    out_trade_no = _normalized_text(payload.get("out_trade_no"))
    order = repo.get_order(out_trade_no)
    if not order:
        raise AlipayPayOrderError("order_not_found")
    _validate_notify_identity(payload, order)
    updated = repo.update_order_from_trade(payload, payload_kind="notify")
    repo.insert_event(
        out_trade_no=out_trade_no,
        event_type="notify",
        trade_no=_normalized_text(payload.get("trade_no")),
        trade_status=_normalized_text(payload.get("trade_status")),
        payload=payload,
        headers=headers or {},
    )
    return {"order": _order_public_payload(updated), "transaction": payload}


def handle_alipay_return(*, params: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in dict(params or {}).items()}
    out_trade_no = _normalized_text(payload.get("out_trade_no"))
    if not out_trade_no:
        raise AlipayPayOrderError("out_trade_no_missing")
    order = repo.update_order_return_payload(out_trade_no, payload)
    if not order:
        raise AlipayPayOrderError("order_not_found")
    repo.insert_event(
        out_trade_no=out_trade_no,
        event_type="return",
        trade_no=_normalized_text(payload.get("trade_no")),
        trade_status=_normalized_text(payload.get("trade_status")),
        payload=payload,
        headers={},
    )
    return {"order": _order_public_payload(order), "return_payload": payload}


def get_order_status(*, out_trade_no: str, refresh: bool = False) -> dict[str, Any]:
    order = repo.get_order(out_trade_no)
    if not order:
        raise AlipayPayOrderError("order_not_found")
    if refresh:
        trade = _create_alipay_pay_client().query_order(out_trade_no)
        order = _apply_trade(trade, event_type="query")
    return {"order": _order_public_payload(order)}
