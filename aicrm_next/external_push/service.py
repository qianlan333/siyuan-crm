from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import requests

from . import repo
from .security import WebhookUrlValidationError, resolve_and_validate_public_https_url, validate_webhook_url


EVENT_TRANSACTION_PAID = repo.EVENT_TRANSACTION_PAID
EVENT_EXTERNAL_PUSH_TEST = "external_push.test"
TARGET_PRODUCT = "product"
DEFAULT_TENANT_ID = repo.DEFAULT_TENANT_ID
MAX_ATTEMPTS = 5
MAX_BODY_BYTES = 8192
QUESTIONNAIRE_TITLE_PAYMENT_OPEN_MEMBER = "微信支付开通黄小璨会员"
WEBHOOK_LOCAL_TIMEZONE = timezone(timedelta(hours=8))


class ExternalPushError(ValueError):
    pass


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _iso(value: Any = None) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text = _normalized_text(value)
        if text:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return text
        else:
            dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_local(value: Any = None) -> str:
    text = _iso(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return dt.astimezone(WEBHOOK_LOCAL_TIMEZONE).isoformat()


def _int_or_none(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ExternalPushError(f"{field_name} must be a number") from exc


def _normalize_custom_params(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            source = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ExternalPushError("custom_params must be valid JSON") from exc
    else:
        source = value
    if isinstance(source, dict):
        items = [{"key": key, "value": val} for key, val in source.items()]
    elif isinstance(source, list):
        items = source
    else:
        raise ExternalPushError("custom_params must be an object or key-value list")
    result: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _normalized_text(item.get("key") or item.get("name"))
        if not key:
            raise ExternalPushError("custom_params key cannot be empty")
        if key in result:
            raise ExternalPushError("custom_params key cannot be duplicated")
        result[key] = item.get("value", "")
    return result


def normalize_config_payload(payload: dict[str, Any], *, validate_dns: bool = True) -> dict[str, Any]:
    enabled = bool(payload.get("enabled"))
    webhook_url = _normalized_text(payload.get("webhook_url") or payload.get("external_push_url"))
    if enabled and not webhook_url:
        raise ExternalPushError("webhook_url is required when external push is enabled")
    if webhook_url:
        try:
            webhook_url = resolve_and_validate_public_https_url(webhook_url) if validate_dns else validate_webhook_url(webhook_url)
        except WebhookUrlValidationError as exc:
            raise ExternalPushError(str(exc)) from exc
    return {
        "enabled": enabled,
        "webhook_url": webhook_url,
        "push_type": _normalized_text(payload.get("push_type") or payload.get("type") or payload.get("external_push_type")),
        "expires_at_ts": _int_or_none(payload.get("expires_at_ts"), "expires_at_ts"),
        "day": _int_or_none(payload.get("day"), "day"),
        "frequency": _int_or_none(payload.get("frequency"), "frequency"),
        "remark": _normalized_text(payload.get("remark")),
        "custom_params": _normalize_custom_params(payload.get("custom_params")),
        "secret": _normalized_text(payload.get("secret")) if "secret" in payload else None,
    }


def sign_webhook_payload(secret: str, timestamp: int | str, raw_body: str) -> str:
    digest = hmac.new(
        _normalized_text(secret).encode("utf-8"),
        f"{_normalized_text(timestamp)}.{raw_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def truncate_body(body: Any, max_bytes: int = MAX_BODY_BYTES) -> str:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _mask_openid(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) <= 8:
        return text[:2] + "***" if text else ""
    return f"{text[:4]}***{text[-4:]}"


def _mask_phone(value: Any) -> str:
    digits = _normalized_text(value)
    if len(digits) < 7:
        return "***" if digits else ""
    return f"{digits[:3]}****{digits[-4:]}"


def redact_sensitive_fields(payload: Any) -> Any:
    if isinstance(payload, list):
        return [redact_sensitive_fields(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if lowered in {"secret", "webhook_secret", "pay_sign", "paysign", "api_v3_key", "private_key"}:
            redacted[key] = "[REDACTED]"
        elif lowered in {"phone", "mobile", "mobile_snapshot", "phone_number"}:
            redacted[key] = _mask_phone(value)
        elif lowered in {"openid", "payer_openid", "unionid"}:
            redacted[key] = _mask_openid(value)
        else:
            redacted[key] = redact_sensitive_fields(value)
    return redacted


def _product_for_order(repository: Any, order: dict[str, Any]) -> dict[str, Any]:
    product = repository.get_product_for_order(order)
    if product:
        return product
    return {
        "id": 0,
        "product_code": _normalized_text(order.get("product_code")),
        "name": _normalized_text(order.get("product_name") or order.get("product_code")),
        "amount_total": int(order.get("amount_total") or 0),
        "currency": _normalized_text(order.get("currency")) or "CNY",
    }


def build_external_push_payload(
    event: str,
    order: dict[str, Any],
    product: dict[str, Any],
    config: dict[str, Any],
    *,
    delivery_id: str,
) -> dict[str, Any]:
    event_type = _normalized_text(event)
    if event_type == EVENT_EXTERNAL_PUSH_TEST:
        return {
            "event": EVENT_EXTERNAL_PUSH_TEST,
            "delivery_id": delivery_id,
            "occurred_at": _iso(),
            "tenant": {"id": _normalized_text(config.get("tenant_id")) or DEFAULT_TENANT_ID},
            "product": {
                "id": str(product.get("id") or config.get("target_id") or ""),
                "name": _normalized_text(product.get("name")),
            },
            "custom_params": config.get("custom_params") if isinstance(config.get("custom_params"), dict) else {},
        }
    order_payload = {
        "id": str(order.get("id") or ""),
        "order_no": _normalized_text(order.get("out_trade_no")),
        "out_trade_no": _normalized_text(order.get("out_trade_no")),
        "status": "paid",
        "paid_amount": int(order.get("payer_total") or order.get("amount_total") or 0),
        "paid_at": _iso(order.get("paid_at")),
        "pay_channel": "wechat",
    }
    product_payload = {
        "id": str(product.get("id") or ""),
        "code": _normalized_text(product.get("product_code")),
        "name": _normalized_text(product.get("name") or order.get("product_name")),
        "price": int(product.get("amount_total") or order.get("amount_total") or 0),
    }
    return {
        "phone_number": _normalized_text(order.get("mobile_snapshot")),
        "type": _normalized_text(config.get("push_type")),
        "day": config.get("day"),
        "frequency": config.get("frequency"),
        "remark": _normalized_text(config.get("remark")),
        "submitted_at": _iso_local(order.get("paid_at")),
        "questionnaire_title": QUESTIONNAIRE_TITLE_PAYMENT_OPEN_MEMBER,
        "delivery_id": delivery_id,
        "event": EVENT_TRANSACTION_PAID,
        "order": order_payload,
        "product": product_payload,
        "buyer": {
            "id": _normalized_text(order.get("external_userid") or order.get("userid_snapshot") or order.get("respondent_key")),
            "openid": _mask_openid(order.get("payer_openid")),
            "unionid": _normalized_text(order.get("unionid")),
            "phone": _normalized_text(order.get("mobile_snapshot")),
        },
    }


def schedule_next_retry(attempt_count: int) -> str | None:
    delays = {1: 0, 2: 60, 3: 300, 4: 1800, 5: 7200}
    if int(attempt_count) >= MAX_ATTEMPTS:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=delays.get(int(attempt_count) + 1, 7200))).isoformat()


def _webhook_timeout_seconds() -> float:
    return float(os.getenv("EXTERNAL_PUSH_WEBHOOK_TIMEOUT_SECONDS") or 5)


def _send_http_post(url: str, *, raw_body: str, headers: dict[str, str], timeout: float) -> tuple[int, str, str]:
    resolved = resolve_and_validate_public_https_url(url)
    response = requests.post(resolved, data=raw_body.encode("utf-8"), headers=headers, timeout=timeout, allow_redirects=False)
    if response.is_redirect and response.headers.get("Location"):
        redirect_url = urljoin(resolved, response.headers["Location"])
        redirect_url = resolve_and_validate_public_https_url(redirect_url)
        response = requests.post(redirect_url, data=raw_body.encode("utf-8"), headers=headers, timeout=timeout, allow_redirects=False)
        resolved = redirect_url
    return int(response.status_code), truncate_body(response.text or "", MAX_BODY_BYTES), resolved


def _attempt_delivery(
    delivery: dict[str, Any],
    *,
    config: dict[str, Any],
    payload: dict[str, Any] | None = None,
    repository: Any | None = None,
) -> dict[str, Any]:
    repository = repository or repo.build_external_push_repository()
    delivery_id = _normalized_text(delivery.get("delivery_id"))
    event_type = _normalized_text(delivery.get("event_type")) or EVENT_TRANSACTION_PAID
    request_payload = payload
    if request_payload is None and event_type == EVENT_TRANSACTION_PAID:
        order = repository.get_order_by_id(int(delivery.get("order_id") or 0)) or {}
        product = repository.get_product_by_id(int(delivery.get("product_id") or 0)) or _product_for_order(repository, order)
        request_payload = build_external_push_payload(
            event_type,
            order,
            product,
            config,
            delivery_id=delivery_id,
        )
    if request_payload is None:
        request_payload = delivery.get("request_body")
    if not isinstance(request_payload, dict) or not request_payload:
        order = repository.get_order_by_id(int(delivery.get("order_id") or 0)) or {}
        product = repository.get_product_by_id(int(delivery.get("product_id") or 0)) or _product_for_order(repository, order)
        request_payload = build_external_push_payload(
            event_type,
            order,
            product,
            config,
            delivery_id=delivery_id,
        )
    raw_body = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    headers = {
        "Content-Type": "application/json",
        "X-AICRM-Event": event_type,
        "X-AICRM-Delivery-Id": delivery_id,
        "X-AICRM-Timestamp": timestamp,
    }
    secret = _normalized_text(config.get("secret"))
    headers["X-AICRM-Signature"] = sign_webhook_payload(secret, timestamp, raw_body) if secret else ""
    next_attempt = int(delivery.get("attempt_count") or 0) + 1
    request_url = _normalized_text(config.get("webhook_url") or delivery.get("request_url"))
    try:
        status_code, response_body, final_url = _send_http_post(
            request_url,
            raw_body=raw_body,
            headers=headers,
            timeout=_webhook_timeout_seconds(),
        )
        ok = 200 <= status_code < 300
        next_retry = "" if ok else (schedule_next_retry(next_attempt) or "")
        status = "success" if ok else ("retrying" if next_retry else "gave_up")
        updated = repository.update_delivery_result(
            delivery_id,
            status=status,
            attempt_count=next_attempt,
            request_url=final_url,
            request_headers=redact_sensitive_fields(headers),
            request_body=redact_sensitive_fields(request_payload),
            response_status=status_code,
            response_body=response_body,
            error_message="" if ok else f"HTTP {status_code}",
            next_retry_at=next_retry,
        )
        return {"ok": ok, "delivery": updated, "status_code": status_code, "reason": "" if ok else f"HTTP {status_code}"}
    except Exception as exc:
        next_retry = schedule_next_retry(next_attempt) or ""
        status = "retrying" if next_retry else "gave_up"
        updated = repository.update_delivery_result(
            delivery_id,
            status=status,
            attempt_count=next_attempt,
            request_url=request_url,
            request_headers=redact_sensitive_fields(headers),
            request_body=redact_sensitive_fields(request_payload),
            response_status=None,
            response_body="",
            error_message=truncate_body(str(exc), 1000),
            next_retry_at=next_retry,
        )
        return {"ok": False, "delivery": updated, "reason": str(exc)}


def enqueue_transaction_paid_event(order: dict[str, Any], *, repository: Any | None = None) -> dict[str, Any] | None:
    repository = repository or repo.build_external_push_repository()
    product = _product_for_order(repository, order)
    payload = {
        "order_id": str(order.get("id") or ""),
        "product_id": str(product.get("id") or ""),
        "product_code": _normalized_text(order.get("product_code")),
        "tenant_id": DEFAULT_TENANT_ID,
        "buyer_id": _normalized_text(order.get("external_userid") or order.get("userid_snapshot") or order.get("respondent_key")),
        "paid_amount": int(order.get("payer_total") or order.get("amount_total") or 0),
        "paid_at": _iso(order.get("paid_at")),
        "pay_channel": "wechat",
    }
    return repository.insert_outbox_event(
        tenant_id=DEFAULT_TENANT_ID,
        event_type=EVENT_TRANSACTION_PAID,
        aggregate_type="wechat_pay_order",
        aggregate_id=str(order.get("id") or order.get("out_trade_no") or ""),
        payload=payload,
    )


def _is_config_expired(config: dict[str, Any]) -> bool:
    value = config.get("expires_at_ts")
    if value in (None, ""):
        return False
    return int(value) <= int(datetime.now(timezone.utc).timestamp())


def process_transaction_paid_outbox(outbox: dict[str, Any], *, repository: Any | None = None) -> dict[str, Any]:
    repository = repository or repo.build_external_push_repository()
    payload = outbox.get("payload") if isinstance(outbox.get("payload"), dict) else {}
    order_id = int(payload.get("order_id") or outbox.get("aggregate_id") or 0)
    order = repository.get_order_by_id(order_id)
    if not order:
        repository.mark_outbox_status(int(outbox["id"]), status="skipped")
        return {"ok": True, "skipped": True, "reason": "order_not_found"}
    product = _product_for_order(repository, order)
    product_id = int(product.get("id") or 0)
    config = repository.get_product_config(product_id)
    if not config:
        repository.mark_outbox_status(int(outbox["id"]), status="skipped")
        return {"ok": True, "skipped": True, "reason": "config_not_found"}
    config_with_secret = repository.get_config_with_secret(int(config["id"])) or config
    if not bool(config.get("enabled")):
        repository.mark_outbox_status(int(outbox["id"]), status="skipped")
        return {"ok": True, "skipped": True, "reason": "config_disabled"}
    if _is_config_expired(config):
        repository.mark_outbox_status(int(outbox["id"]), status="skipped")
        return {"ok": True, "skipped": True, "reason": "config_expired"}
    delivery = repository.create_delivery_once(
        {
            "tenant_id": DEFAULT_TENANT_ID,
            "config_id": int(config["id"]),
            "event_type": EVENT_TRANSACTION_PAID,
            "delivery_id": repo.generate_delivery_id(),
            "target_type": TARGET_PRODUCT,
            "target_id": str(product_id),
            "order_id": int(order.get("id") or 0),
            "product_id": product_id,
            "request_url": config.get("webhook_url"),
        }
    )
    if _normalized_text(delivery.get("status")) == "success":
        repository.mark_outbox_status(int(outbox["id"]), status="success")
        return {"ok": True, "delivery": delivery, "deduped": True}
    push_payload = build_external_push_payload(EVENT_TRANSACTION_PAID, order, product, config, delivery_id=delivery["delivery_id"])
    result = _attempt_delivery(delivery, config=config_with_secret, payload=push_payload, repository=repository)
    repository.mark_outbox_status(int(outbox["id"]), status="success")
    return result


def run_due_external_push_events(*, limit: int = 20, repository: Any | None = None) -> dict[str, Any]:
    repository = repository or repo.build_external_push_repository()
    events = repository.list_due_outbox_events(limit=limit)
    results = [process_transaction_paid_outbox(event, repository=repository) for event in events]
    return {
        "ok": True,
        "scanned_count": len(events),
        "success_count": sum(1 for item in results if item.get("ok") and not item.get("skipped")),
        "skipped_count": sum(1 for item in results if item.get("skipped")),
        "failed_count": sum(1 for item in results if not item.get("ok")),
        "items": results,
    }


def run_due_external_push_retries(*, limit: int = 20, repository: Any | None = None) -> dict[str, Any]:
    repository = repository or repo.build_external_push_repository()
    deliveries = repository.list_due_deliveries(limit=limit)
    results = []
    for delivery in deliveries:
        config = repository.get_config_with_secret(int(delivery.get("config_id") or 0)) or {}
        results.append(_attempt_delivery(delivery, config=config, repository=repository))
    return {"ok": True, "retried_count": len(results), "items": results}


def send_webhook_delivery(delivery_id: str, *, repository: Any | None = None) -> dict[str, Any]:
    repository = repository or repo.build_external_push_repository()
    delivery = repository.get_delivery_by_delivery_id(delivery_id)
    if not delivery:
        raise ExternalPushError("外推记录不存在")
    config = repository.get_config_with_secret(int(delivery.get("config_id") or 0)) or {}
    return _attempt_delivery(delivery, config=config, repository=repository)

def send_product_external_push_test(product_id: int, *, repository: Any | None = None) -> dict[str, Any]:
    repository = repository or repo.build_external_push_repository()
    product = repository.get_product_by_id(int(product_id))
    if not product:
        raise ExternalPushError("商品不存在")
    config = repository.get_product_config(int(product_id))
    if not config:
        raise ExternalPushError("请先保存外部推送配置")
    config_with_secret = repository.get_config_with_secret(int(config["id"])) or config
    webhook_url = _normalized_text(config_with_secret.get("webhook_url"))
    if not webhook_url:
        raise ExternalPushError("webhook_url is required")
    try:
        resolve_and_validate_public_https_url(webhook_url)
    except WebhookUrlValidationError as exc:
        raise ExternalPushError(str(exc)) from exc
    delivery = repository.create_test_delivery(
        {
            "tenant_id": DEFAULT_TENANT_ID,
            "config_id": int(config["id"]),
            "delivery_id": repo.generate_delivery_id(),
            "target_id": str(product_id),
            "product_id": int(product_id),
            "request_url": webhook_url,
        }
    )
    payload = build_external_push_payload(EVENT_EXTERNAL_PUSH_TEST, {}, product, config, delivery_id=delivery["delivery_id"])
    return _attempt_delivery(delivery, config=config_with_secret, payload=payload, repository=repository)


def list_order_deliveries(order_id: int, *, repository: Any | None = None) -> list[dict[str, Any]]:
    repository = repository or repo.build_external_push_repository()
    if not repository.get_order_by_id(int(order_id)):
        raise ExternalPushError("订单不存在")
    return repository.list_deliveries_for_order(int(order_id))


def retry_order_delivery(order_id: int, delivery_id: str, *, repository: Any | None = None) -> dict[str, Any]:
    repository = repository or repo.build_external_push_repository()
    order = repository.get_order_by_id(int(order_id))
    if not order:
        raise ExternalPushError("订单不存在")
    delivery = repository.get_delivery_by_delivery_id(delivery_id)
    if not delivery or int(delivery.get("order_id") or 0) != int(order_id):
        raise ExternalPushError("外推记录不存在")
    if _normalized_text(delivery.get("status")) not in {"failed", "retrying", "gave_up"}:
        raise ExternalPushError("只能重试 failed / retrying / gave_up 状态")
    config = repository.get_config_with_secret(int(delivery.get("config_id") or 0)) or {}
    return _attempt_delivery(delivery, config=config, repository=repository)
