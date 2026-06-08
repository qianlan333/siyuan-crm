from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from aicrm_next.commerce.domain import safe_completion_redirect_url

from ...db import get_db
from ...infra.json_utils import safe_json_loads
from ...infra.settings import get_setting
from ...infra.text_encoding import repair_utf8_mojibake
from . import repo
from .client import WeChatPayClient, WeChatPayClientConfig, WeChatPayClientError
from .exceptions import WeChatPayConfigError, WeChatPayOrderError
from .product_service import get_completion_redirect_for_product_code, get_lead_qr_for_product_code, get_product, list_products


logger = logging.getLogger(__name__)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _mask_mobile(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) <= 5:
        return "*" * len(digits)
    return f"{digits[:3]}****{digits[-4:]}"


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


def _is_order_fully_refunded(order: dict[str, Any]) -> bool:
    amount_total = int(order.get("amount_total") or 0)
    refunded_amount_total = int(order.get("refunded_amount_total") or 0)
    return _normalized_text(order.get("refund_status")) == "full_refunded" or (
        amount_total > 0 and refunded_amount_total >= amount_total
    )


def _is_order_effectively_paid(order: dict[str, Any]) -> bool:
    if _is_order_fully_refunded(order):
        return False
    return _normalized_text(order.get("status")) == "paid" or _normalized_text(order.get("trade_state")) == "SUCCESS"


def _order_public_payload(order: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(order.get("status"))
    if _is_order_fully_refunded(order):
        status = "full_refunded"
    payload = {
        "out_trade_no": _normalized_text(order.get("out_trade_no")),
        "product_code": _normalized_text(order.get("product_code")),
        "product_name": _normalized_text(order.get("product_name")),
        "amount_total": int(order.get("amount_total") or 0),
        "currency": _normalized_text(order.get("currency")) or "CNY",
        "status": status,
        "trade_state": _normalized_text(order.get("trade_state")),
        "refund_status": _normalized_text(order.get("refund_status")),
        "refunded_amount_total": int(order.get("refunded_amount_total") or 0),
        "success_url": _safe_success_url(order.get("success_url")),
        "paid_at": _normalized_text(order.get("paid_at")),
        "created_at": _normalized_text(order.get("created_at")),
    }
    completion_redirect = get_completion_redirect_for_product_code(payload["product_code"])
    payload["completion_redirect_enabled"] = bool(completion_redirect.get("completion_redirect_enabled"))
    payload["completion_redirect_url"] = safe_completion_redirect_url(completion_redirect.get("completion_redirect_url"))
    effective_completion_redirect = dict(completion_redirect.get("completion_redirect") or {})
    payload["completion_redirect"] = {
        "enabled": bool(effective_completion_redirect.get("enabled")),
        "url": safe_completion_redirect_url(effective_completion_redirect.get("url")),
    }
    payload["completion_action"] = (
        {"type": "redirect", "redirect_url": payload["completion_redirect"]["url"]}
        if payload["completion_redirect"]["enabled"] and payload["completion_redirect"]["url"]
        else {"type": "default", "redirect_url": ""}
    )
    if _is_order_effectively_paid(order):
        if payload["completion_redirect"]["enabled"] and payload["completion_redirect"]["url"]:
            payload["completion_redirect_url"] = payload["completion_redirect"]["url"]
        else:
            lead_qr = get_lead_qr_for_product_code(payload["product_code"])
            if lead_qr.get("qr_url"):
                payload["lead_qr"] = lead_qr
                payload["completion_action"] = {"type": "lead_qr", "redirect_url": ""}
    return payload


def _existing_paid_order_for_product(product: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any] | None:
    order = repo.get_paid_order_for_product_identity(
        product_code=_normalized_text(product.get("product_code")),
        payer_openid=_normalized_text(identity.get("openid")),
        unionid=_normalized_text(identity.get("unionid")),
        external_userid=_normalized_text(identity.get("external_userid")),
    )
    return _order_public_payload(order) if order else None


def _normalize_order_mobile(*, product: dict[str, Any], mobile: str) -> str:
    text = _normalized_text(mobile)
    if not text:
        if product.get("require_mobile"):
            raise WeChatPayOrderError("mobile_required")
        return ""
    from ..identity import service as identity_service

    try:
        return identity_service.normalize_mobile(text)
    except ValueError as exc:
        raise WeChatPayOrderError(str(exc)) from exc


def _mobile_binding_audit(
    *,
    mobile: str,
    openid: str,
    unionid: str,
    external_userid: str,
    owner_userid: str = "",
    bind_by_userid: str = "",
) -> dict[str, Any]:
    if not mobile:
        return {}
    try:
        from ...application.identity_contact.commands import BindExternalContactIdentityCommand
        from ...application.identity_contact.dto import (
            BindExternalContactIdentityCommandDTO,
            ResolveExternalContactIdentityQueryDTO,
        )
        from ...application.identity_contact.queries import ResolveExternalContactIdentityQuery

        resolved = ResolveExternalContactIdentityQuery()(
            ResolveExternalContactIdentityQueryDTO(
                openid=openid,
                unionid=unionid,
                external_userid=external_userid,
            )
        ) or {}
        resolved_external_userid = _normalized_text(resolved.get("external_userid")) or _normalized_text(external_userid)
        resolved_owner_userid = (
            _normalized_text(owner_userid)
            or _normalized_text(resolved.get("follow_user_userid"))
            or _normalized_text(resolved.get("owner_userid"))
            or _normalized_text(resolved.get("last_owner_userid"))
            or _normalized_text(resolved.get("first_owner_userid"))
        )
        if not resolved_external_userid:
            return {"status": "skipped", "reason": "external_userid_unresolved", "mobile_masked": _mask_mobile(mobile)}
        binding = BindExternalContactIdentityCommand()(
            BindExternalContactIdentityCommandDTO(
                external_userid=resolved_external_userid,
                owner_userid=resolved_owner_userid,
                bind_by_userid=_normalized_text(bind_by_userid) or resolved_owner_userid or "wechat_pay_h5",
                mobile=mobile,
                force_rebind=False,
            )
        )
        return {
            "status": "bound",
            "mobile_masked": _mask_mobile(mobile),
            "external_userid": resolved_external_userid,
            "owner_userid": resolved_owner_userid,
            "person_id": (binding or {}).get("person_id") if isinstance(binding, dict) else None,
        }
    except Exception as exc:  # Do not block payment if identity binding cannot be resolved.
        logger.warning("wechat pay mobile bind skipped mobile=%s reason=%s", _mask_mobile(mobile), exc)
        return {"status": "skipped", "reason": str(exc), "mobile_masked": _mask_mobile(mobile)}


def _transaction_amount_total(transaction: dict[str, Any]) -> int:
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    return int(amount.get("total") or amount.get("payer_total") or 0)


def _transaction_currency(transaction: dict[str, Any]) -> str:
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    return _normalized_text(amount.get("currency")) or "CNY"


def _transaction_payer_openid(transaction: dict[str, Any]) -> str:
    payer = transaction.get("payer") if isinstance(transaction.get("payer"), dict) else {}
    return _normalized_text(payer.get("openid"))


def _transaction_attach_payload(transaction: dict[str, Any]) -> dict[str, Any]:
    payload = safe_json_loads(_normalized_text(transaction.get("attach")), default={})
    return payload if isinstance(payload, dict) else {}


def _match_recovered_product(transaction: dict[str, Any]) -> dict[str, Any]:
    amount_total = _transaction_amount_total(transaction)
    description = _normalized_text(transaction.get("description"))
    attach = _transaction_attach_payload(transaction)
    product_code = _normalized_text(attach.get("product_code"))
    if product_code:
        product = get_product(product_code)
        if product:
            return product
    for product in list_products():
        if amount_total and int(product.get("amount_total") or 0) != amount_total:
            continue
        names = {
            _normalized_text(product.get("name")),
            _normalized_text(product.get("description")),
        }
        if description and description in names:
            return product
    amount_matches = [
        product
        for product in list_products()
        if amount_total and int(product.get("amount_total") or 0) == amount_total
    ]
    if len(amount_matches) == 1:
        return amount_matches[0]
    return {
        "product_code": product_code or "recovered_wechat_pay",
        "name": description or "微信支付恢复订单",
        "description": description or "微信支付恢复订单",
        "amount_total": amount_total,
        "currency": _transaction_currency(transaction),
        "success_url": "",
        "metadata": {},
    }


def _created_at_from_out_trade_no(out_trade_no: str) -> str:
    text = _normalized_text(out_trade_no)
    stamp = text[3:15] if text.startswith("WXP") and len(text) >= 15 else ""
    if len(stamp) != 12 or not stamp.isdigit():
        return ""
    try:
        created = datetime(
            year=2000 + int(stamp[0:2]),
            month=int(stamp[2:4]),
            day=int(stamp[4:6]),
            hour=int(stamp[6:8]),
            minute=int(stamp[8:10]),
            second=int(stamp[10:12]),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return ""
    return created.strftime("%Y-%m-%dT%H:%M:%SZ")


def _enrich_recovered_order_from_transaction(order: dict[str, Any], transaction: dict[str, Any]) -> dict[str, Any]:
    if not _normalized_text(order.get("order_source")).startswith("recovered_"):
        return order
    product = _match_recovered_product(transaction)
    product_code = _normalized_text(product.get("product_code"))
    if not product_code:
        return order
    product_name = _normalized_text(product.get("name") or product.get("description")) or product_code
    updated = repo.update_recovered_order_context(
        _normalized_text(order.get("out_trade_no") or transaction.get("out_trade_no")),
        product_code=product_code,
        product_name=product_name,
        description=_normalized_text(transaction.get("description")) or product_name,
        success_url=_normalized_text(product.get("success_url")),
        created_at=_created_at_from_out_trade_no(_normalized_text(order.get("out_trade_no") or transaction.get("out_trade_no"))),
    )
    return updated or order


def _should_refresh_recovered_order(order: dict[str, Any]) -> bool:
    if not _normalized_text(order.get("order_source")).startswith("recovered_"):
        return False
    return _normalized_text(order.get("product_code")) in {"", "recovered_wechat_pay"} or _normalized_text(
        order.get("product_name")
    ) in {"", "微信支付恢复订单", "recovered_wechat_pay"}


def _recover_missing_order_from_transaction(transaction: dict[str, Any], *, event_type: str) -> dict[str, Any]:
    out_trade_no = _normalized_text(transaction.get("out_trade_no"))
    if not out_trade_no:
        return {}
    existing = repo.get_order(out_trade_no)
    if existing:
        return existing
    amount_total = _transaction_amount_total(transaction)
    if amount_total <= 0:
        raise WeChatPayOrderError("order_not_found")
    attach = _transaction_attach_payload(transaction)
    product = _match_recovered_product(transaction)
    product_code = _normalized_text(product.get("product_code")) or "recovered_wechat_pay"
    product_name = _normalized_text(product.get("name") or product.get("description")) or product_code
    logger.warning(
        "recover missing WeChat Pay order out_trade_no=%s transaction_id=%s event_type=%s product_code=%s",
        out_trade_no,
        _normalized_text(transaction.get("transaction_id")),
        event_type,
        product_code,
    )
    return repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "order_source": f"recovered_{event_type}",
            "client_order_ref": _normalized_text(attach.get("client_order_ref")),
            "product_code": product_code,
            "product_name": product_name,
            "description": _normalized_text(transaction.get("description")) or product_name,
            "amount_total": amount_total,
            "currency": _transaction_currency(transaction),
            "payer_openid": _transaction_payer_openid(transaction),
            "status": "created",
            "success_url": _normalized_text(product.get("success_url")),
            "created_at": _created_at_from_out_trade_no(out_trade_no),
            "metadata": {
                "recovered": True,
                "recovered_event_type": event_type,
            },
            "request_meta": {
                "recovered_from_wechat_transaction": True,
                "transaction_id": _normalized_text(transaction.get("transaction_id")),
            },
        }
    )


def create_jsapi_order(
    *,
    product_code: str,
    payer_openid: str,
    respondent_key: str = "",
    unionid: str = "",
    external_userid: str = "",
    payer_name: str = "",
    client_order_ref: str = "",
    order_source: str = "h5_checkout",
    notify_url: str,
    mobile: str = "",
    request_meta: dict[str, Any] | None = None,
    owner_userid: str = "",
    bind_by_userid: str = "",
    context_source: str = "",
    mobile_source: str = "",
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
    existing_paid_order = _existing_paid_order_for_product(
        product,
        {"openid": openid, "unionid": unionid, "external_userid": external_userid},
    )
    if existing_paid_order:
        raise WeChatPayOrderError("already_paid")
    normalized_mobile = _normalize_order_mobile(product=product, mobile=mobile)
    request_meta_payload = dict(request_meta or {})
    identity_external_userid = _normalized_text(external_userid)
    userid_snapshot = _normalized_text(owner_userid)
    if _normalized_text(context_source):
        request_meta_payload["sidebar_context"] = {
            "context_source": _normalized_text(context_source),
            "external_userid_present": bool(identity_external_userid),
            "owner_userid_present": bool(userid_snapshot),
            "mobile_source": _normalized_text(mobile_source) or ("payload" if normalized_mobile else "none"),
        }
    if normalized_mobile:
        mobile_binding = _mobile_binding_audit(
            mobile=normalized_mobile,
            openid=openid,
            unionid=unionid,
            external_userid=external_userid,
            owner_userid=owner_userid,
            bind_by_userid=bind_by_userid,
        )
        request_meta_payload["mobile_binding"] = mobile_binding
        if isinstance(mobile_binding, dict) and mobile_binding.get("status") == "bound":
            identity_external_userid = _normalized_text(mobile_binding.get("external_userid")) or identity_external_userid
            userid_snapshot = _normalized_text(mobile_binding.get("owner_userid"))
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
            "external_userid": identity_external_userid,
            "userid_snapshot": userid_snapshot,
            "mobile_snapshot": normalized_mobile,
            "payer_name_snapshot": repair_utf8_mojibake(payer_name),
            "status": "created",
            "success_url": success_url,
            "metadata": product.get("metadata") or {},
            "request_meta": request_meta_payload,
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
        "attach": json.dumps(
            {"product_code": product["product_code"], "client_order_ref": client_order_ref},
            ensure_ascii=False,
            separators=(",", ":"),
        )[:128],
    }
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
        get_db().commit()
    except Exception as exc:
        repo.mark_order_failed(out_trade_no, error_message=str(exc))
        get_db().commit()
        raise
    return {
        "order": _order_public_payload(order),
        "pay_params": pay_params,
    }


def _apply_transaction(transaction: dict[str, Any], *, event_type: str, headers: dict[str, Any] | None = None) -> dict[str, Any]:
    out_trade_no = _normalized_text(transaction.get("out_trade_no"))
    if not out_trade_no:
        raise WeChatPayOrderError("out_trade_no_missing")
    previous_order = repo.get_order(out_trade_no)
    was_paid = _normalized_text((previous_order or {}).get("status")) == "paid" or _normalized_text(
        (previous_order or {}).get("trade_state")
    ) == "SUCCESS"
    order = repo.update_order_from_transaction(transaction)
    if not order:
        _recover_missing_order_from_transaction(transaction, event_type=event_type)
        order = repo.update_order_from_transaction(transaction)
    if not order:
        raise WeChatPayOrderError("order_not_found")
    order = _enrich_recovered_order_from_transaction(order, transaction)
    is_now_paid = _normalized_text(order.get("status")) == "paid" or _normalized_text(order.get("trade_state")) == "SUCCESS"
    if is_now_paid and not was_paid:
        from ..external_push import service as external_push_service

        external_push_service.enqueue_transaction_paid_event(order)
    repo.insert_event(
        out_trade_no=out_trade_no,
        event_type=event_type,
        transaction_id=_normalized_text(transaction.get("transaction_id")),
        trade_state=_normalized_text(transaction.get("trade_state")),
        payload=transaction,
        headers=headers or {},
    )
    get_db().commit()
    return order


def handle_wechat_pay_notification(*, body: str, headers: dict[str, Any]) -> dict[str, Any]:
    client = _create_wechat_pay_client()
    transaction = client.verify_and_decrypt_notification(body=body, headers=headers)
    order = _apply_transaction(transaction, event_type="notify", headers=headers)
    return {"order": _order_public_payload(order), "transaction": transaction}


def get_order_status(*, out_trade_no: str, refresh: bool = False) -> dict[str, Any]:
    order = repo.get_order(out_trade_no)
    if not order and refresh:
        client = _create_wechat_pay_client()
        transaction = client.query_order_by_out_trade_no(out_trade_no)
        order = _apply_transaction(transaction, event_type="query")
    if not order:
        raise WeChatPayOrderError("order_not_found")
    if refresh and (_normalized_text(order.get("status")) not in {"paid", "closed"} or _should_refresh_recovered_order(order)):
        client = _create_wechat_pay_client()
        transaction = client.query_order_by_out_trade_no(out_trade_no)
        order = _apply_transaction(transaction, event_type="query")
    return {"order": _order_public_payload(order)}


def build_checkout_page_state(
    *,
    product_code: str,
    identity: dict[str, str] | None,
    oauth_start_url: str,
    context_token: str = "",
    context_status: str = "",
) -> dict[str, Any]:
    product = get_product(product_code)
    if not product:
        raise WeChatPayOrderError("product_not_configured")
    identity_payload = dict(identity or {})
    paid_order = _existing_paid_order_for_product(product, identity_payload) if identity_payload else None
    completion_redirect = get_completion_redirect_for_product_code(product["product_code"])
    return {
        "product": product,
        "identity_ready": bool(_normalized_text(identity_payload.get("openid"))),
        "oauth_start_url": oauth_start_url,
        "create_order_url": "/api/h5/wechat-pay/jsapi/orders",
        "status_url_template": "/api/h5/wechat-pay/orders/{out_trade_no}",
        "enabled": _setting_bool("WECHAT_PAY_ENABLED", False),
        "require_mobile": bool(product.get("require_mobile")),
        "cta_text": _normalized_text(product.get("cta_text")) or "确认支付",
        "lead_plan_configured": bool(product.get("lead_plan_configured")),
        "completion_redirect": completion_redirect,
        "completion_action": completion_redirect.get("completion_action") or {"type": "default", "redirect_url": ""},
        "paid_order": paid_order,
        "context_token": _normalized_text(context_token),
        "context_status": _normalized_text(context_status) or ("valid" if _normalized_text(context_token) else "missing"),
    }
