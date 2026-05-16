from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from ...infra.json_utils import safe_json_loads
from ...infra.settings import get_setting
from . import repo
from .client import WeChatPayClient, WeChatPayClientConfig, WeChatPayClientError


class WeChatPayConfigError(ValueError):
    pass


class WeChatPayOrderError(ValueError):
    pass


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


def _client_config() -> WeChatPayClientConfig:
    app_id = _setting("WECHAT_PAY_APP_ID") or _setting("WECHAT_MP_APP_ID")
    return WeChatPayClientConfig(
        app_id=app_id,
        mch_id=_setting("WECHAT_PAY_MCH_ID"),
        api_v3_key=_setting("WECHAT_PAY_API_V3_KEY"),
        private_key_path=_setting("WECHAT_PAY_PRIVATE_KEY_PATH"),
        merchant_serial_no=_setting("WECHAT_PAY_CERT_SERIAL_NO"),
        platform_public_key_path=_setting("WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH"),
        platform_serial_no=_setting("WECHAT_PAY_PLATFORM_CERT_SERIAL_NO"),
        api_base=_setting("WECHAT_PAY_API_BASE", "https://api.mch.weixin.qq.com") or "https://api.mch.weixin.qq.com",
        timeout_seconds=_setting_int("WECHAT_PAY_TIMEOUT_SECONDS", 10),
    )


def _create_wechat_pay_client() -> WeChatPayClient:
    config = _client_config()
    return WeChatPayClient(config)


def _require_ready_for_order() -> WeChatPayClientConfig:
    if not _setting_bool("WECHAT_PAY_ENABLED", False):
        raise WeChatPayConfigError("wechat_pay_disabled")
    config = _client_config()
    missing = []
    for key, value in {
        "WECHAT_PAY_APP_ID/WECHAT_MP_APP_ID": config.app_id,
        "WECHAT_PAY_MCH_ID": config.mch_id,
        "WECHAT_PAY_PRIVATE_KEY_PATH": config.private_key_path,
        "WECHAT_PAY_CERT_SERIAL_NO": config.merchant_serial_no,
    }.items():
        if not _normalized_text(value):
            missing.append(key)
    if missing:
        raise WeChatPayConfigError("missing WeChat Pay config: " + ", ".join(missing))
    return config


def _product_catalog() -> dict[str, dict[str, Any]]:
    raw = _setting("WECHAT_PAY_PRODUCT_CATALOG_JSON")
    payload = safe_json_loads(raw, default={}) if raw else {}
    catalog: dict[str, dict[str, Any]] = {}
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("products"), list):
            items = payload.get("products") or []
        else:
            items = [
                {"product_code": key, **(value if isinstance(value, dict) else {})}
                for key, value in payload.items()
            ]
    else:
        items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = _normalized_text(item.get("product_code") or item.get("code") or item.get("id"))
        if not code:
            continue
        amount_total = item.get("amount_total", item.get("amount_fen", item.get("price_fen", 0)))
        try:
            amount = int(amount_total)
        except (TypeError, ValueError):
            amount = 0
        catalog[code] = {
            "product_code": code,
            "name": _normalized_text(item.get("name") or item.get("title") or item.get("description") or code),
            "description": _normalized_text(item.get("description") or item.get("name") or item.get("title") or code),
            "amount_total": amount,
            "currency": _normalized_text(item.get("currency")) or "CNY",
            "success_url": _normalized_text(item.get("success_url")),
            "enabled": str(item.get("enabled", "true")).lower() not in {"0", "false", "no", "off"},
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        }
    return catalog


def list_products() -> list[dict[str, Any]]:
    return [product for product in _product_catalog().values() if product.get("enabled")]


def get_product(product_code: str) -> dict[str, Any] | None:
    product = _product_catalog().get(_normalized_text(product_code))
    if not product or not product.get("enabled"):
        return None
    return dict(product)


def _generate_out_trade_no() -> str:
    # WeChat Pay out_trade_no max length is 32. Keep this compact and sortable.
    return "WXP" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + secrets.token_hex(6).upper()


def _safe_success_url(value: str) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return ""
    if normalized.startswith(("https://", "http://", "/")) and not normalized.startswith("//"):
        return normalized
    return ""


def _expires_at_text(minutes: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _order_public_payload(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "out_trade_no": _normalized_text(order.get("out_trade_no")),
        "product_code": _normalized_text(order.get("product_code")),
        "product_name": _normalized_text(order.get("product_name")),
        "amount_total": int(order.get("amount_total") or 0),
        "currency": _normalized_text(order.get("currency")) or "CNY",
        "status": _normalized_text(order.get("status")),
        "trade_state": _normalized_text(order.get("trade_state")),
        "success_url": _safe_success_url(order.get("success_url")),
        "paid_at": _normalized_text(order.get("paid_at")),
        "created_at": _normalized_text(order.get("created_at")),
    }


def create_jsapi_order(
    *,
    product_code: str,
    payer_openid: str,
    respondent_key: str = "",
    unionid: str = "",
    external_userid: str = "",
    client_order_ref: str = "",
    order_source: str = "h5_checkout",
    notify_url: str,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _require_ready_for_order()
    product = get_product(product_code)
    if not product:
        raise WeChatPayOrderError("product_not_configured")
    openid = _normalized_text(payer_openid)
    if not openid:
        raise WeChatPayOrderError("openid_required")
    amount_total = int(product.get("amount_total") or 0)
    if amount_total <= 0:
        raise WeChatPayOrderError("product_amount_invalid")
    out_trade_no = _generate_out_trade_no()
    success_url = _safe_success_url(product.get("success_url"))
    order = repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "order_source": order_source,
            "client_order_ref": client_order_ref,
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["description"],
            "amount_total": amount_total,
            "currency": product.get("currency") or "CNY",
            "payer_openid": openid,
            "respondent_key": respondent_key,
            "unionid": unionid,
            "external_userid": external_userid,
            "status": "created",
            "success_url": success_url,
            "metadata": product.get("metadata") or {},
            "request_meta": request_meta or {},
            "expires_at": _expires_at_text(),
        }
    )
    transaction_payload = {
        "appid": config.app_id,
        "mchid": config.mch_id,
        "description": product["description"][:127],
        "out_trade_no": out_trade_no,
        "notify_url": _normalized_text(notify_url),
        "amount": {"total": amount_total, "currency": product.get("currency") or "CNY"},
        "payer": {"openid": openid},
    }
    if client_order_ref:
        transaction_payload["attach"] = json.dumps(
            {"product_code": product["product_code"], "client_order_ref": client_order_ref},
            ensure_ascii=False,
            separators=(",", ":"),
        )[:128]
    try:
        client = _create_wechat_pay_client()
        response_payload = client.create_jsapi_transaction(transaction_payload)
        prepay_id = _normalized_text(response_payload.get("prepay_id"))
        if not prepay_id:
            raise WeChatPayClientError("missing prepay_id from WeChat Pay")
        order = repo.update_order_payment_request(
            out_trade_no,
            prepay_id=prepay_id,
            request_payload=transaction_payload,
            response_payload=response_payload,
        )
        pay_params = client.build_jsapi_pay_params(prepay_id)
    except Exception as exc:
        repo.mark_order_failed(out_trade_no, error_message=str(exc))
        raise
    return {
        "order": _order_public_payload(order),
        "pay_params": pay_params,
    }


def _apply_transaction(transaction: dict[str, Any], *, event_type: str, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    out_trade_no = _normalized_text(transaction.get("out_trade_no"))
    if not out_trade_no:
        raise WeChatPayOrderError("out_trade_no_missing")
    order = repo.update_order_from_transaction(transaction)
    if not order:
        raise WeChatPayOrderError("order_not_found")
    repo.insert_event(
        out_trade_no=out_trade_no,
        event_type=event_type,
        transaction_id=_normalized_text(transaction.get("transaction_id")),
        trade_state=_normalized_text(transaction.get("trade_state")),
        payload=transaction,
        headers=headers or {},
    )
    return order


def handle_wechat_pay_notification(*, body: str, headers: dict[str, Any]) -> dict[str, Any]:
    client = _create_wechat_pay_client()
    transaction = client.verify_and_decrypt_notification(body=body, headers=headers)
    order = _apply_transaction(transaction, event_type="notify", headers=headers)
    return {"order": _order_public_payload(order), "transaction": transaction}


def get_order_status(*, out_trade_no: str, refresh: bool = False) -> dict[str, Any]:
    order = repo.get_order(out_trade_no)
    if not order:
        raise WeChatPayOrderError("order_not_found")
    if refresh and _normalized_text(order.get("status")) not in {"paid", "closed"}:
        client = _create_wechat_pay_client()
        transaction = client.query_order_by_out_trade_no(out_trade_no)
        order = _apply_transaction(transaction, event_type="query")
    return {"order": _order_public_payload(order)}


def build_checkout_page_state(
    *,
    product_code: str,
    identity: dict[str, str] | None,
    oauth_start_url: str,
) -> dict[str, Any]:
    product = get_product(product_code)
    if not product:
        raise WeChatPayOrderError("product_not_configured")
    identity_payload = dict(identity or {})
    return {
        "product": product,
        "identity_ready": bool(_normalized_text(identity_payload.get("openid"))),
        "oauth_start_url": oauth_start_url,
        "create_order_url": "/api/h5/wechat-pay/jsapi/orders",
        "status_url_template": "/api/h5/wechat-pay/orders/{out_trade_no}",
        "enabled": _setting_bool("WECHAT_PAY_ENABLED", False),
    }
