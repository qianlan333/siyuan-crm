from __future__ import annotations

import json
import os
import secrets
import hashlib
import hmac
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from aicrm_next.shared.runtime import production_data_ready, raw_database_url

from .external_push_outbox import DEFAULT_TENANT_ID, EVENT_TRANSACTION_PAID


EVENT_EXTERNAL_PUSH_TEST = "external_push.test"
MAX_BODY_BYTES = 8192
QUESTIONNAIRE_TITLE_PAYMENT_OPEN_MEMBER = "微信支付开通黄小璨会员"
WEBHOOK_LOCAL_TIMEZONE = timezone(timedelta(hours=8))


class ExternalPushAdminError(ValueError):
    pass


class WebhookUrlValidationError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(_text(address).strip("[]"))
    except ValueError as exc:
        raise WebhookUrlValidationError("webhook_url DNS resolved to an invalid IP") from exc
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if str(ip) == "169.254.169.254":
        return True
    return False


def _validate_webhook_url(url: str) -> str:
    parsed = urlparse(_text(url))
    if parsed.scheme.lower() != "https":
        raise WebhookUrlValidationError("webhook_url must be an https URL")
    if not parsed.hostname:
        raise WebhookUrlValidationError("webhook_url host is required")
    hostname = parsed.hostname.strip().lower()
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or hostname.endswith(".localhost"):
        raise WebhookUrlValidationError("webhook_url host is not allowed")
    try:
        if _is_blocked_ip(hostname):
            raise WebhookUrlValidationError("webhook_url host must resolve to a public IP")
    except WebhookUrlValidationError as exc:
        if "invalid IP" not in str(exc):
            raise
    return parsed.geturl()


def _resolve_and_validate_public_https_url(url: str) -> str:
    normalized = _validate_webhook_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebhookUrlValidationError("webhook_url DNS resolution failed") from exc
    resolved_ips = {item[4][0] for item in addr_infos if item and item[4]}
    if not resolved_ips:
        raise WebhookUrlValidationError("webhook_url DNS resolution returned no IP")
    for address in resolved_ips:
        if _is_blocked_ip(address):
            raise WebhookUrlValidationError("webhook_url resolved to a non-public IP")
    return normalized


resolve_and_validate_public_https_url = _resolve_and_validate_public_https_url


def _iso(value: Any = None) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        text = _text(value)
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


def _mask_openid(value: Any) -> str:
    text = _text(value)
    if len(text) <= 8:
        return text[:2] + "***" if text else ""
    return f"{text[:4]}***{text[-4:]}"


def _mask_phone(value: Any) -> str:
    digits = _text(value)
    if len(digits) < 7:
        return "***" if digits else ""
    return f"{digits[:3]}****{digits[-4:]}"


def _redact_sensitive_fields(payload: Any) -> Any:
    if isinstance(payload, list):
        return [_redact_sensitive_fields(item) for item in payload]
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
            redacted[key] = _redact_sensitive_fields(value)
    return redacted


def _sign_webhook_payload(secret: str, timestamp: int | str, raw_body: str) -> str:
    digest = hmac.new(
        _text(secret).encode("utf-8"),
        f"{_text(timestamp)}.{raw_body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _truncate_body(body: Any, max_bytes: int = MAX_BODY_BYTES) -> str:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _build_external_push_payload(
    event: str,
    order: dict[str, Any],
    product: dict[str, Any],
    config: dict[str, Any],
    *,
    delivery_id: str,
) -> dict[str, Any]:
    event_type = _text(event)
    if event_type == EVENT_EXTERNAL_PUSH_TEST:
        return {
            "event": EVENT_EXTERNAL_PUSH_TEST,
            "delivery_id": delivery_id,
            "occurred_at": _iso(),
            "tenant": {"id": _text(config.get("tenant_id")) or DEFAULT_TENANT_ID},
            "product": {
                "id": str(product.get("id") or config.get("target_id") or ""),
                "name": _text(product.get("name")),
            },
            "custom_params": config.get("custom_params") if isinstance(config.get("custom_params"), dict) else {},
        }
    order_payload = {
        "id": str(order.get("id") or ""),
        "order_no": _text(order.get("out_trade_no")),
        "out_trade_no": _text(order.get("out_trade_no")),
        "status": "paid",
        "paid_amount": int(order.get("payer_total") or order.get("amount_total") or 0),
        "paid_at": _iso(order.get("paid_at")),
        "pay_channel": "wechat",
    }
    product_payload = {
        "id": str(product.get("id") or ""),
        "code": _text(product.get("product_code")),
        "name": _text(product.get("name") or order.get("product_name")),
        "price": int(product.get("amount_total") or order.get("amount_total") or 0),
    }
    return {
        "phone_number": _text(order.get("mobile_snapshot")),
        "type": _text(config.get("push_type")),
        "day": config.get("day"),
        "frequency": config.get("frequency"),
        "remark": _text(config.get("remark")),
        "submitted_at": _iso_local(order.get("paid_at")),
        "questionnaire_title": QUESTIONNAIRE_TITLE_PAYMENT_OPEN_MEMBER,
        "delivery_id": delivery_id,
        "event": EVENT_TRANSACTION_PAID,
        "order": order_payload,
        "product": product_payload,
        "buyer": {
            "id": _text(order.get("external_userid") or order.get("userid_snapshot") or order.get("respondent_key")),
            "openid": _mask_openid(order.get("payer_openid")),
            "unionid": _text(order.get("unionid")),
            "phone": _text(order.get("mobile_snapshot")),
        },
    }


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=lambda data: json.dumps(data, ensure_ascii=False, default=str))


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    if not production_data_ready():
        raise ExternalPushAdminError("production_database_required")
    return psycopg.connect(raw_database_url(), row_factory=dict_row)


def _public_delivery(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["config_id"] = int(payload.get("config_id") or 0)
    payload["order_id"] = int(payload.get("order_id") or 0)
    payload["product_id"] = int(payload.get("product_id") or 0)
    payload["attempt_count"] = int(payload.get("attempt_count") or 0)
    payload["request_headers"] = _json_obj(payload.get("request_headers"))
    payload["request_body"] = _json_obj(payload.get("request_body"))
    payload["response_body"] = _text(payload.get("response_body"))
    return payload


def _public_outbox(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["retry_count"] = int(payload.get("retry_count") or 0)
    payload["payload"] = _json_obj(payload.get("payload"))
    return payload


def _public_config(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = dict(row)
    payload["id"] = int(payload.get("id") or 0)
    payload["enabled"] = bool(payload.get("enabled"))
    payload["custom_params"] = _json_obj(payload.get("custom_params"))
    payload["has_secret"] = bool(_text(payload.get("secret")))
    payload.pop("secret", None)
    return payload


def _delivery_id() -> str:
    return "deliv_" + secrets.token_urlsafe(18).replace("-", "").replace("_", "")[:24]


def _retry_at(attempt_count: int) -> str | None:
    delays = {1: 0, 2: 60, 3: 300, 4: 1800, 5: 7200}
    if int(attempt_count) >= 5:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=delays.get(int(attempt_count) + 1, 7200))).isoformat()


def _get_order(conn: Any, order_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM wechat_pay_orders WHERE id = %s LIMIT 1", (int(order_id),)).fetchone()
    return dict(row) if row else None


def _get_product(conn: Any, product_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM wechat_pay_products WHERE id = %s LIMIT 1", (int(product_id),)).fetchone()
    return dict(row) if row else None


def _get_product_for_order(conn: Any, order: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM wechat_pay_products
        WHERE product_code = %s
        LIMIT 1
        """,
        (_text(order.get("product_code")),),
    ).fetchone()
    if row:
        return dict(row)
    return {
        "id": 0,
        "product_code": _text(order.get("product_code")),
        "name": _text(order.get("product_name") or order.get("product_code")),
        "amount_total": int(order.get("amount_total") or 0),
    }


def _get_config(conn: Any, config_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM external_push_config WHERE id = %s LIMIT 1", (int(config_id),)).fetchone()
    return dict(row) if row else None


def _get_product_config(conn: Any, product_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM external_push_config
        WHERE tenant_id = %s
          AND target_type = 'product'
          AND target_id = %s
          AND event_type = %s
        LIMIT 1
        """,
        (DEFAULT_TENANT_ID, str(int(product_id)), EVENT_TRANSACTION_PAID),
    ).fetchone()
    return dict(row) if row else None


def _get_delivery(conn: Any, delivery_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM external_push_delivery WHERE delivery_id = %s LIMIT 1", (_text(delivery_id),)).fetchone()
    return dict(row) if row else None


def _update_delivery_result(
    conn: Any,
    delivery_id: str,
    *,
    status: str,
    attempt_count: int,
    request_url: str,
    request_headers: dict[str, Any],
    request_body: dict[str, Any],
    response_status: int | None,
    response_body: str,
    error_message: str,
    next_retry_at: str | None,
) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE external_push_delivery
        SET status = %s,
            attempt_count = %s,
            request_url = %s,
            request_headers = %s::jsonb,
            request_body = %s::jsonb,
            response_status = %s,
            response_body = %s,
            error_message = %s,
            next_retry_at = NULLIF(%s, '')::timestamptz,
            updated_at = CURRENT_TIMESTAMP
        WHERE delivery_id = %s
        RETURNING *
        """,
        (
            _text(status),
            int(attempt_count),
            _text(request_url),
            _jsonb(request_headers or {}),
            _jsonb(request_body or {}),
            response_status,
            _text(response_body),
            _text(error_message),
            _text(next_retry_at),
            _text(delivery_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def _create_test_delivery(conn: Any, *, config: dict[str, Any], product_id: int, request_url: str) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO external_push_delivery (
            tenant_id, config_id, event_type, delivery_id, target_type, target_id,
            order_id, product_id, status, attempt_count, request_url, request_headers,
            request_body, response_status, response_body, error_message, next_retry_at,
            created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, 'product', %s, 0, %s, 'pending', 0, %s, '{}'::jsonb, '{}'::jsonb, NULL, '', '', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            DEFAULT_TENANT_ID,
            int(config.get("id") or 0),
            EVENT_EXTERNAL_PUSH_TEST,
            _delivery_id(),
            str(int(product_id)),
            int(product_id),
            request_url,
        ),
    ).fetchone()
    return dict(row) if row else {}


def _send_http_post(url: str, *, raw_body: str, headers: dict[str, str], timeout: float) -> tuple[int, str, str]:
    resolved = resolve_and_validate_public_https_url(url)
    response = requests.post(resolved, data=raw_body.encode("utf-8"), headers=headers, timeout=timeout, allow_redirects=False)
    if response.is_redirect and response.headers.get("Location"):
        redirect_url = urljoin(resolved, response.headers["Location"])
        redirect_url = resolve_and_validate_public_https_url(redirect_url)
        response = requests.post(redirect_url, data=raw_body.encode("utf-8"), headers=headers, timeout=timeout, allow_redirects=False)
        resolved = redirect_url
    return int(response.status_code), _truncate_body(response.text or "", MAX_BODY_BYTES), resolved


def _attempt_delivery(conn: Any, delivery: dict[str, Any], *, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    delivery_id = _text(delivery.get("delivery_id"))
    event_type = _text(delivery.get("event_type")) or EVENT_TRANSACTION_PAID
    raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    headers = {
        "Content-Type": "application/json",
        "X-AICRM-Event": event_type,
        "X-AICRM-Delivery-Id": delivery_id,
        "X-AICRM-Timestamp": timestamp,
    }
    secret = _text(config.get("secret"))
    headers["X-AICRM-Signature"] = _sign_webhook_payload(secret, timestamp, raw_body) if secret else ""
    next_attempt = int(delivery.get("attempt_count") or 0) + 1
    request_url = _text(config.get("webhook_url") or delivery.get("request_url"))
    try:
        status_code, response_body, final_url = _send_http_post(
            request_url,
            raw_body=raw_body,
            headers=headers,
            timeout=float(os.getenv("EXTERNAL_PUSH_WEBHOOK_TIMEOUT_SECONDS") or 5),
        )
        ok = 200 <= status_code < 300
        next_retry = "" if ok else (_retry_at(next_attempt) or "")
        status = "success" if ok else ("retrying" if next_retry else "gave_up")
        updated = _update_delivery_result(
            conn,
            delivery_id,
            status=status,
            attempt_count=next_attempt,
            request_url=final_url,
            request_headers=_redact_sensitive_fields(headers),
            request_body=_redact_sensitive_fields(payload),
            response_status=status_code,
            response_body=response_body,
            error_message="" if ok else f"HTTP {status_code}",
            next_retry_at=next_retry,
        )
        return {"ok": ok, "delivery": _public_delivery(updated), "status_code": status_code, "reason": "" if ok else f"HTTP {status_code}"}
    except Exception as exc:
        next_retry = _retry_at(next_attempt) or ""
        status = "retrying" if next_retry else "gave_up"
        updated = _update_delivery_result(
            conn,
            delivery_id,
            status=status,
            attempt_count=next_attempt,
            request_url=request_url,
            request_headers=_redact_sensitive_fields(headers),
            request_body=_redact_sensitive_fields(payload),
            response_status=None,
            response_body="",
            error_message=_truncate_body(str(exc), 1000),
            next_retry_at=next_retry,
        )
        return {"ok": False, "delivery": _public_delivery(updated), "reason": str(exc)}


def list_order_external_push_state(order_id: int) -> dict[str, Any]:
    with _connect() as conn:
        order = _get_order(conn, int(order_id))
        if not order:
            raise ExternalPushAdminError("订单不存在")
        delivery_rows = conn.execute(
            """
            SELECT *
            FROM external_push_delivery
            WHERE tenant_id = %s
              AND order_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (DEFAULT_TENANT_ID, int(order_id)),
        ).fetchall()
        outbox_rows = conn.execute(
            """
            SELECT *
            FROM domain_event_outbox
            WHERE tenant_id = %s
              AND event_type = %s
              AND aggregate_type = 'wechat_pay_order'
              AND aggregate_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (DEFAULT_TENANT_ID, EVENT_TRANSACTION_PAID, str(int(order_id))),
        ).fetchall()
    return {
        "ok": True,
        "order_id": int(order_id),
        "outbox": [_public_outbox(dict(row)) for row in outbox_rows],
        "items": [_public_delivery(dict(row)) for row in delivery_rows],
    }


def send_product_external_push_test(product_id: int) -> dict[str, Any]:
    with _connect() as conn:
        product = _get_product(conn, int(product_id))
        if not product:
            raise ExternalPushAdminError("商品不存在")
        config = _get_product_config(conn, int(product_id))
        if not config:
            raise ExternalPushAdminError("请先保存外部推送配置")
        config_public = _public_config(config)
        if not config_public.get("enabled"):
            raise ExternalPushAdminError("外部推送未启用")
        webhook_url = _text(config.get("webhook_url"))
        if not webhook_url:
            raise ExternalPushAdminError("webhook_url is required")
        delivery = _create_test_delivery(conn, config=config, product_id=int(product_id), request_url=webhook_url)
        payload = _build_external_push_payload(EVENT_EXTERNAL_PUSH_TEST, {}, product, config_public, delivery_id=delivery["delivery_id"])
        result = _attempt_delivery(conn, delivery, config=config, payload=payload)
        conn.commit()
        return result


def retry_order_delivery(order_id: int, delivery_id: str) -> dict[str, Any]:
    with _connect() as conn:
        order = _get_order(conn, int(order_id))
        if not order:
            raise ExternalPushAdminError("订单不存在")
        delivery = _get_delivery(conn, delivery_id)
        if not delivery or int(delivery.get("order_id") or 0) != int(order_id):
            raise ExternalPushAdminError("外推记录不存在")
        if _text(delivery.get("status")) not in {"failed", "retrying", "gave_up"}:
            raise ExternalPushAdminError("只能重试 failed / retrying / gave_up 状态")
        config = _get_config(conn, int(delivery.get("config_id") or 0)) or {}
        product = _get_product(conn, int(delivery.get("product_id") or 0)) or _get_product_for_order(conn, order)
        payload = _build_external_push_payload(EVENT_TRANSACTION_PAID, order, product, _public_config(config), delivery_id=delivery["delivery_id"])
        result = _attempt_delivery(conn, delivery, config=config, payload=payload)
        conn.commit()
        return result
