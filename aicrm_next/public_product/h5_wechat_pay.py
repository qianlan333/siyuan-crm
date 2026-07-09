from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from aicrm_next.commerce.domain import completion_redirect_projection, safe_completion_redirect_url
from aicrm_next.commerce.external_push_admin import plan_order_paid_external_push_effect
from aicrm_next.navigation_target import completion_action_for_target, completion_target_projection
from aicrm_next.commerce.external_push_outbox import enqueue_transaction_paid_outbox
from aicrm_next.commerce.order_expiration import close_expired_wechat_pay_orders, pending_order_expires_at_text
from aicrm_next.commerce.product_code_aliases import product_code_filter_values
from aicrm_next.integration_gateway.wechat_pay_client import WeChatPayClient, WeChatPayClientConfig, WeChatPayClientError
from aicrm_next.integration_gateway.wechat_oauth_client import WeChatOAuthClientError, build_wechat_oauth_client
from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.internal_events import InternalEventService, register_payment_succeeded_consumers
from aicrm_next.platform_foundation.internal_events.config import event_type_allowed, payment_internal_events_enabled
from aicrm_next.platform_foundation.internal_events.payment import PAYMENT_SUCCEEDED_EVENT_TYPE
from aicrm_next.questionnaire.oauth import questionnaire_h5_identity_from_cookies
from aicrm_next.shared.runtime import production_data_ready

from .repo import connect_h5_wechat_pay_db as _connect
from .signed_context import append_ctx_query, load_sidebar_product_context_token
from .sidebar_order_context import resolve_sidebar_order_context
from .service import format_price, get_public_product, product_not_found_payload, route_headers


COOKIE_NAME = "wechat_pay_h5_identity"
STATE_TTL_SECONDS = 600
LOGGER = logging.getLogger(__name__)
_OAUTH_CLIENT_FACTORY = build_wechat_oauth_client


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _env(name: str, default: str = "") -> str:
    return _normalized_text(os.getenv(name, default))


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except (TypeError, ValueError):
        return int(default)


def set_h5_wechat_pay_oauth_client_factory(factory):
    global _OAUTH_CLIENT_FACTORY
    _OAUTH_CLIENT_FACTORY = factory


def reset_h5_wechat_pay_oauth_client_factory():
    global _OAUTH_CLIENT_FACTORY
    _OAUTH_CLIENT_FACTORY = build_wechat_oauth_client


def _oauth_client():
    return _OAUTH_CLIENT_FACTORY()


def _secret() -> str:
    return _env("AICRM_NEXT_ACTION_TOKEN_SECRET") or _env("SECRET_KEY") or "aicrm-next-h5-wechat-pay-dev-secret"


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(message: str) -> str:
    return hmac.new(_secret().encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_blob(payload: dict[str, Any]) -> str:
    encoded = _b64encode(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_sign(encoded)}"


def _load_signed_blob(value: str) -> dict[str, Any]:
    try:
        encoded, signature = value.split(".", 1)
    except ValueError:
        return {}
    if not hmac.compare_digest(_sign(encoded), signature):
        return {}
    try:
        payload = json.loads(_b64decode(encoded).decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_return_url(value: Any) -> str:
    normalized = _normalized_text(value)
    if not normalized or not normalized.startswith("/") or normalized.startswith("//") or "\\" in normalized:
        return "/"
    return normalized


def sidebar_product_context_status(context_token: str) -> str:
    result = load_sidebar_product_context_token(_normalized_text(context_token))
    return _normalized_text(result.get("status")) or "missing"


def _external_base_url(request: Request) -> str:
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    scheme = forwarded_proto or request.url.scheme or "http"
    host = forwarded_host or request.headers.get("Host") or request.url.netloc
    return f"{scheme}://{host}".rstrip("/")


def _oauth_configured() -> bool:
    return bool(_env("WECHAT_MP_APP_ID") and _env("WECHAT_MP_APP_SECRET") and _secret())


def _wechat_oauth_scope() -> str:
    return _env("WECHAT_PAY_OAUTH_SCOPE") or "snsapi_userinfo"


def _wechat_oauth_authorize_url(*, app_id: str, redirect_uri: str, scope: str, state: str) -> str:
    query = urlencode(
        {
            "appid": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope or "snsapi_base",
            "state": state,
        }
    )
    return f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect"


def _is_wechat_browser(request: Request) -> bool:
    return "micromessenger" in (request.headers.get("User-Agent") or "").lower()


def _identity_from_request(request: Request) -> dict[str, str]:
    for cookie_name in (COOKIE_NAME,):
        payload = _load_signed_blob(_normalized_text(request.cookies.get(cookie_name)))
        openid = _normalized_text(payload.get("openid"))
        if openid:
            return {
                "openid": openid,
                "unionid": _normalized_text(payload.get("unionid")),
                "respondent_key": _normalized_text(payload.get("respondent_key")),
                "external_userid": _normalized_text(payload.get("external_userid")),
                "payer_name": _normalized_text(payload.get("payer_name")),
            }
    questionnaire_identity = questionnaire_h5_identity_from_cookies(request.cookies)
    openid = _normalized_text(questionnaire_identity.get("openid"))
    if openid:
        return {
            "openid": openid,
            "unionid": _normalized_text(questionnaire_identity.get("unionid")),
            "respondent_key": _normalized_text(questionnaire_identity.get("respondent_key")),
            "external_userid": _normalized_text(questionnaire_identity.get("external_userid")),
            "payer_name": "",
        }
    return {}


def h5_payment_identity_from_request(request: Request) -> dict[str, str]:
    return _identity_from_request(request)


def payment_oauth_start_url(return_url: str) -> str:
    return f"/api/h5/wechat-pay/oauth/start?{urlencode({'return_url': _safe_return_url(return_url)})}"


def payment_oauth_start(request: Request) -> RedirectResponse | JSONResponse:
    return_url = _safe_return_url(request.query_params.get("return_url") or "/")
    if _identity_from_request(request).get("openid"):
        return RedirectResponse(return_url, status_code=302, headers=route_headers())
    if not _oauth_configured():
        return JSONResponse({"ok": False, "error": "wechat_pay_oauth_not_configured"}, status_code=501, headers=route_headers())
    now = int(datetime.now(timezone.utc).timestamp())
    state = _signed_blob({"return_url": return_url, "nonce": secrets.token_urlsafe(16), "iat": now, "exp": now + STATE_TTL_SECONDS})
    authorize_url = _wechat_oauth_authorize_url(
        app_id=_env("WECHAT_MP_APP_ID"),
        redirect_uri=f"{_external_base_url(request)}/api/h5/wechat-pay/oauth/callback",
        scope=_wechat_oauth_scope(),
        state=state,
    )
    return RedirectResponse(authorize_url, status_code=302, headers=route_headers())


def payment_oauth_callback(request: Request) -> RedirectResponse | JSONResponse:
    state_payload = _load_signed_blob(_normalized_text(request.query_params.get("state")))
    if not state_payload:
        return JSONResponse({"ok": False, "error": "state_invalid"}, status_code=400, headers=route_headers())
    if int(state_payload.get("exp") or 0) < int(datetime.now(timezone.utc).timestamp()):
        return JSONResponse({"ok": False, "error": "state_expired"}, status_code=400, headers=route_headers())
    code = _normalized_text(request.query_params.get("code"))
    if not code:
        return JSONResponse({"ok": False, "error": "code_required"}, status_code=400, headers=route_headers())
    try:
        client = _oauth_client()
        oauth_payload = client.exchange_code(app_id=_env("WECHAT_MP_APP_ID"), app_secret=_env("WECHAT_MP_APP_SECRET"), code=code)
    except (WeChatOAuthClientError, Exception):
        return JSONResponse({"ok": False, "error": "wechat_oauth_failed"}, status_code=502, headers=route_headers())
    if oauth_payload.get("errcode") not in (None, 0):
        return JSONResponse({"ok": False, "error": oauth_payload.get("errmsg") or "wechat_oauth_failed"}, status_code=502, headers=route_headers())
    openid = _normalized_text(oauth_payload.get("openid"))
    if not openid:
        return JSONResponse({"ok": False, "error": "wechat_oauth_openid_missing"}, status_code=502, headers=route_headers())
    unionid = _normalized_text(oauth_payload.get("unionid"))
    payer_name = ""
    access_token = _normalized_text(oauth_payload.get("access_token"))
    if _wechat_oauth_scope() == "snsapi_userinfo" and access_token and openid:
        try:
            userinfo = client.fetch_userinfo(access_token=access_token, openid=openid)
            if userinfo.get("errcode") in (None, 0):
                unionid = unionid or _normalized_text(userinfo.get("unionid"))
                payer_name = _normalized_text(userinfo.get("nickname"))
        except (WeChatOAuthClientError, Exception):
            payer_name = ""
    response = RedirectResponse(_safe_return_url(state_payload.get("return_url")), status_code=302, headers=route_headers())
    response.set_cookie(
        COOKIE_NAME,
        _signed_blob({"openid": openid, "unionid": unionid, "payer_name": payer_name, "iat": int(datetime.now(timezone.utc).timestamp())}),
        max_age=86400 * 30,
        httponly=True,
        secure=_external_base_url(request).startswith("https://"),
        samesite="lax",
        path="/",
    )
    return response


def checkout_page_state(product: dict[str, Any], request: Request) -> dict[str, Any]:
    identity = _identity_from_request(request)
    code = _normalized_text(product.get("product_code"))
    paid_order = _existing_paid_order_for_checkout(product, identity) if identity.get("openid") else None
    context_token = _normalized_text(request.query_params.get("ctx"))
    context_result = load_sidebar_product_context_token(context_token)
    pay_path = append_ctx_query(f"/pay/{code}", context_token) if context_token else f"/pay/{code}"
    return {
        "product": {
            "product_code": code,
            "name": _normalized_text(product.get("title") or product.get("name")),
            "amount_total": int(product.get("price_cents") or product.get("amount_total") or 0),
            "currency": _normalized_text(product.get("currency")) or "CNY",
        },
        "identity_ready": bool(identity.get("openid")),
        "oauth_start_url": payment_oauth_start_url(pay_path),
        "create_order_url": "/api/h5/wechat-pay/jsapi/orders",
        "status_url_template": "/api/h5/wechat-pay/orders/{out_trade_no}",
        "enabled": _env_bool("WECHAT_PAY_ENABLED", False),
        "require_mobile": bool(product.get("require_mobile")),
        "cta_text": _normalized_text(product.get("buy_button_text")) or "确认支付",
        "completion_target": product.get("completion_target") or {},
        "completion_action": product.get("completion_action") or {"type": "default", "redirect_url": ""},
        "paid_order": paid_order,
        "price_display": format_price(product),
        "context_token": context_token,
        "context_status": _normalized_text(context_result.get("status")) or "missing",
    }


def _client_config() -> WeChatPayClientConfig:
    app_id = _env("WECHAT_PAY_APP_ID") or _env("WECHAT_MP_APP_ID")
    return WeChatPayClientConfig(
        app_id=app_id,
        mch_id=_env("WECHAT_PAY_MCH_ID"),
        api_v3_key=_env("WECHAT_PAY_API_V3_KEY"),
        private_key_path=_env("WECHAT_PAY_PRIVATE_KEY_PATH"),
        merchant_serial_no=_env("WECHAT_PAY_CERT_SERIAL_NO"),
        platform_public_key_path=_env("WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH"),
        platform_serial_no=_env("WECHAT_PAY_PLATFORM_CERT_SERIAL_NO"),
        api_base=_env("WECHAT_PAY_API_BASE") or "https://api.mch.weixin.qq.com",
        timeout_seconds=_env_int("WECHAT_PAY_TIMEOUT_SECONDS", 10),
    )


def _require_payment_ready() -> WeChatPayClientConfig:
    if not _env_bool("WECHAT_PAY_ENABLED", False):
        raise RuntimeError("wechat_pay_disabled")
    config = _client_config()
    missing = [
        key
        for key, value in {
            "WECHAT_PAY_APP_ID/WECHAT_MP_APP_ID": config.app_id,
            "WECHAT_PAY_MCH_ID": config.mch_id,
            "WECHAT_PAY_PRIVATE_KEY_PATH": config.private_key_path,
            "WECHAT_PAY_CERT_SERIAL_NO": config.merchant_serial_no,
        }.items()
        if not _normalized_text(value)
    ]
    if missing:
        raise RuntimeError("missing WeChat Pay config: " + ", ".join(missing))
    if not production_data_ready():
        raise RuntimeError("production_database_required")
    return config


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=lambda data: json.dumps(data, ensure_ascii=False, default=str))


def _out_trade_no() -> str:
    return "WXP" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + secrets.token_hex(6).upper()


def _expires_at() -> str:
    return pending_order_expires_at_text()


def _safe_success_url(value: Any) -> str:
    normalized = _normalized_text(value)
    if normalized.startswith("/") and not normalized.startswith("//"):
        return normalized
    if normalized.startswith(("https://", "http://")):
        return normalized
    return ""


def _is_order_fully_refunded(row: dict[str, Any]) -> bool:
    amount_total = int(row.get("amount_total") or 0)
    refunded_amount_total = int(row.get("refunded_amount_total") or 0)
    return _normalized_text(row.get("refund_status")) == "full_refunded" or (
        amount_total > 0 and refunded_amount_total >= amount_total
    )


def _is_order_effectively_paid(row: dict[str, Any]) -> bool:
    if _is_order_fully_refunded(row):
        return False
    return _normalized_text(row.get("status")) == "paid" or _normalized_text(row.get("trade_state")) == "SUCCESS"


def _masked_mobile(value: Any) -> str:
    text = _normalized_text(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    return ""


def _payment_subject_id(order: dict[str, Any]) -> str:
    return (
        _normalized_text(order.get("external_userid"))
        or _normalized_text(order.get("userid_snapshot"))
        or _normalized_text(order.get("respondent_key"))
    )


def _emit_payment_succeeded_internal_event(
    *,
    order: dict[str, Any],
    transaction: dict[str, Any],
    outbox: dict[str, Any] | None,
    source_route: str,
) -> dict[str, Any] | None:
    if not payment_internal_events_enabled() or not event_type_allowed(PAYMENT_SUCCEEDED_EVENT_TYPE):
        return None
    out_trade_no = _normalized_text(order.get("out_trade_no") or transaction.get("out_trade_no"))
    aggregate_id = _normalized_text(order.get("id") or out_trade_no)
    if not out_trade_no or not aggregate_id:
        return None
    subject_id = _payment_subject_id(order)
    try:
        register_payment_succeeded_consumers()
        result = InternalEventService().emit_event(
            event_type=PAYMENT_SUCCEEDED_EVENT_TYPE,
            event_version=1,
            aggregate_type="wechat_pay_order",
            aggregate_id=aggregate_id,
            subject_type="customer",
            subject_id=subject_id,
            idempotency_key=f"payment.succeeded:{out_trade_no}",
            source_module="public_product.h5_wechat_pay",
            source_command_id=out_trade_no,
            correlation_id=out_trade_no,
            context=CommandContext(
                actor_id="wechat_pay_notify",
                actor_type="system",
                trace_id=out_trade_no,
                request_id=_normalized_text(transaction.get("transaction_id")),
                source_route=source_route or "/api/h5/wechat-pay/notify",
            ),
            payload={
                "order": dict(order),
                "transaction": dict(transaction or {}),
                "domain_event_outbox_id": (outbox or {}).get("id"),
                "legacy_event_aliases": ["transaction.paid", "payment_succeeded"],
            },
            payload_summary={
                "out_trade_no": out_trade_no,
                "order_id": order.get("id"),
                "aggregate_id": aggregate_id,
                "subject_type": "customer",
                "subject_id": subject_id,
                "product_code": order.get("product_code"),
                "amount_total": int(order.get("amount_total") or order.get("payer_total") or 0),
                "status": order.get("status"),
                "trade_state": order.get("trade_state"),
                "paid_at": str(order.get("paid_at") or ""),
                "mobile_masked": _masked_mobile(order.get("mobile_snapshot")),
                "domain_event_outbox_id": (outbox or {}).get("id"),
            },
        )
        LOGGER.info(
            "payment_succeeded_internal_event_ensured",
            extra={"out_trade_no": out_trade_no, "event_id": (result.get("event") or {}).get("event_id")},
        )
        return result
    except Exception:
        LOGGER.exception("payment_succeeded_internal_event_failed", extra={"out_trade_no": out_trade_no})
        return None


def _completion_redirect_from_product(product: dict[str, Any]) -> dict[str, Any]:
    completion_redirect = completion_redirect_projection(
        product.get("completion_redirect_enabled"),
        product.get("completion_redirect_url"),
    )
    completion_target = completion_target_projection(
        product.get("completion_target_json") if product.get("completion_target_json") is not None else product.get("completion_target"),
        legacy_h5_url=completion_redirect.get("completion_redirect_url"),
        legacy_enabled=completion_redirect.get("completion_redirect_enabled"),
    )
    return {
        **completion_redirect,
        **completion_target,
        "completion_action": completion_action_for_target(
            completion_target["completion_target"],
            legacy_redirect_url=completion_redirect.get("completion_redirect_url"),
            legacy_enabled=completion_redirect.get("completion_redirect_enabled"),
        ),
    }


def _completion_redirect_for_product_code(conn: Any, product_code: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT completion_redirect_enabled, completion_redirect_url, completion_target_json
        FROM wechat_pay_products
        WHERE product_code = %s
        LIMIT 1
        """,
        (_normalized_text(product_code),),
    ).fetchone()
    if not row:
        return completion_redirect_projection(False, "")
    return _completion_redirect_from_product(dict(row))


def _lead_qr_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    row = dict(row or {})
    qr_url = _normalized_text(row.get("qr_url"))
    if not qr_url:
        return {}
    return {
        "channel_id": int(row.get("channel_id") or 0),
        "channel_name": _normalized_text(row.get("channel_name")),
        "qr_url": qr_url,
        "status": _normalized_text(row.get("status")),
    }


def _resolve_lead_channel_qr(conn: Any, *, channel_id: int | None = None) -> dict[str, Any]:
    if channel_id:
        row = conn.execute(
            """
            SELECT
                c.id AS channel_id,
                c.channel_name,
                COALESCE(NULLIF(active_asset.qr_url, ''), NULLIF(c.qr_url, ''), '') AS qr_url,
                c.status
            FROM automation_channel c
            LEFT JOIN LATERAL (
                SELECT qa.qr_url
                FROM automation_channel_qrcode_asset qa
                WHERE qa.channel_id = c.id
                  AND qa.status = 'active'
                  AND NULLIF(qa.qr_url, '') IS NOT NULL
                ORDER BY qa.generated_at DESC, qa.id DESC
                LIMIT 1
            ) active_asset ON TRUE
            WHERE c.id = %s
            LIMIT 1
            """,
            (int(channel_id),),
        ).fetchone()
        return _lead_qr_payload(row)
    return {}


def _lead_qr_for_product_code(conn: Any, product_code: str) -> dict[str, Any]:
    product = conn.execute(
        """
        SELECT lead_channel_id
        FROM wechat_pay_products
        WHERE product_code = %s
        LIMIT 1
        """,
        (_normalized_text(product_code),),
    ).fetchone()
    if not product:
        return {}
    channel_id = int(product.get("lead_channel_id") or 0) or None
    return _resolve_lead_channel_qr(conn, channel_id=channel_id)


def _resolve_unionid_for_payment_identity(conn: Any, identity: dict[str, str]) -> str:
    unionid = _normalized_text(identity.get("unionid"))
    if unionid:
        return unionid
    clauses: list[str] = []
    params: list[Any] = []
    openid = _normalized_text(identity.get("openid"))
    if openid:
        clauses.append("(primary_openid = %s OR jsonb_exists(openids_json, %s))")
        params.extend([openid, openid])
    external_userid = _normalized_text(identity.get("external_userid"))
    if external_userid:
        clauses.append("(primary_external_userid = %s OR jsonb_exists(external_userids_json, %s))")
        params.extend([external_userid, external_userid])
    if not clauses:
        return ""
    row = conn.execute(
        f"""
        SELECT unionid
        FROM crm_user_identity
        WHERE {" OR ".join(clauses)}
        ORDER BY
            CASE
                WHEN primary_external_userid = %s THEN 0
                WHEN primary_openid = %s THEN 1
                ELSE 2
            END,
            last_seen_at DESC NULLS LAST,
            updated_at DESC NULLS LAST
        LIMIT 1
        """,
        tuple([*params, external_userid, openid]),
    ).fetchone()
    return _normalized_text((row or {}).get("unionid"))


def _paid_order_for_product_identity(conn: Any, *, product: dict[str, Any], identity: dict[str, str]) -> dict[str, Any] | None:
    product_codes = product_code_filter_values(product.get("product_code"))
    unionid = _normalized_text(identity.get("unionid"))
    if not unionid:
        unionid = _resolve_unionid_for_payment_identity(conn, identity)
    if not product_codes or not unionid:
        return None
    params: list[Any] = [*product_codes, unionid]
    product_placeholders = ", ".join(["%s"] * len(product_codes))
    row = conn.execute(
        f"""
        SELECT *
        FROM wechat_pay_orders
        WHERE product_code IN ({product_placeholders})
          AND (status = 'paid' OR trade_state = 'SUCCESS')
          AND NOT (
            COALESCE(refund_status, '') = 'full_refunded'
            OR (amount_total > 0 AND COALESCE(refunded_amount_total, 0) >= amount_total)
          )
          AND unionid = %s
        ORDER BY paid_at DESC NULLS LAST, updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return dict(row) if row else None


def _paid_order_payload_for_product_identity(conn: Any, *, product: dict[str, Any], identity: dict[str, str]) -> dict[str, Any] | None:
    order = _paid_order_for_product_identity(conn, product=product, identity=identity)
    if not order:
        return None
    completion_redirect = _completion_redirect_from_product(product)
    lead_qr = {} if completion_redirect.get("completion_redirect", {}).get("enabled") else _lead_qr_for_product_code(conn, _normalized_text(product.get("product_code")))
    return _order_payload(order, completion_redirect=completion_redirect, lead_qr=lead_qr)


def _existing_paid_order_for_checkout(product: dict[str, Any], identity: dict[str, str]) -> dict[str, Any] | None:
    if not production_data_ready():
        return None
    try:
        with _connect() as conn:
            return _paid_order_payload_for_product_identity(conn, product=product, identity=identity)
    except Exception:
        return None


def _order_payload(
    row: dict[str, Any],
    *,
    completion_redirect: dict[str, Any] | None = None,
    lead_qr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_completion = completion_redirect or completion_redirect_projection(
        row.get("completion_redirect_enabled"),
        row.get("completion_redirect_url"),
    )
    completion = dict(effective_completion.get("completion_redirect") or {})
    completion_url = safe_completion_redirect_url(completion.get("url") or effective_completion.get("completion_redirect_url"))
    completion_enabled = bool(completion.get("enabled")) and bool(completion_url)
    completion_target = (effective_completion.get("completion_target") or effective_completion.get("completion_target_json") or {}) if isinstance(effective_completion, dict) else {}
    target_enabled = bool(completion_target.get("enabled")) if isinstance(completion_target, dict) else False
    completion_action = (
        completion_action_for_target(
            completion_target,
            legacy_redirect_url=completion_url,
            legacy_enabled=completion_enabled,
        )
        if isinstance(completion_target, dict) and completion_target
        else ({"type": "redirect", "redirect_url": completion_url} if completion_enabled else {"type": "default", "redirect_url": ""})
    )
    status = _normalized_text(row.get("status"))
    if _is_order_fully_refunded(row):
        status = "full_refunded"
    payload = {
        "out_trade_no": _normalized_text(row.get("out_trade_no")),
        "product_code": _normalized_text(row.get("product_code")),
        "product_name": _normalized_text(row.get("product_name")),
        "amount_total": int(row.get("amount_total") or 0),
        "currency": _normalized_text(row.get("currency")) or "CNY",
        "status": status,
        "trade_state": _normalized_text(row.get("trade_state")),
        "refund_status": _normalized_text(row.get("refund_status")),
        "refunded_amount_total": int(row.get("refunded_amount_total") or 0),
        "success_url": _safe_success_url(row.get("success_url")),
        "paid_at": _normalized_text(row.get("paid_at")),
        "created_at": _normalized_text(row.get("created_at")),
        "completion_redirect_enabled": bool(effective_completion.get("completion_redirect_enabled")),
        "completion_redirect_url": completion_url,
        "completion_redirect": {"enabled": completion_enabled, "url": completion_url if completion_enabled else ""},
        "completion_target": completion_target if isinstance(completion_target, dict) else {},
        "completion_action": completion_action,
    }
    if _is_order_effectively_paid(row) and not completion_enabled and not target_enabled and lead_qr and lead_qr.get("qr_url"):
        payload["lead_qr"] = lead_qr
        payload["completion_action"] = {"type": "lead_qr", "redirect_url": ""}
    return payload


def _insert_order(
    conn: Any,
    *,
    product: dict[str, Any],
    identity: dict[str, str],
    mobile: str,
    out_trade_no: str,
    request_meta: dict[str, Any] | None = None,
    order_source: str = "h5_checkout",
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO wechat_pay_orders (
            out_trade_no, order_source, client_order_ref, product_code, product_name, description,
            amount_total, currency, unionid, payer_name_snapshot, status, success_url, metadata_json,
            request_meta_json, expires_at, created_at, updated_at
        )
        VALUES (
            %s, %s, '', %s, %s, %s, %s, %s, %s, %s,
            'created', %s, %s::jsonb, %s::jsonb, %s::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        RETURNING *
        """,
        (
            out_trade_no,
            _normalized_text(order_source) or "h5_checkout",
            product["product_code"],
            product["title"],
            product.get("description") or product["title"],
            int(product.get("price_cents") or 0),
            product.get("currency") or "CNY",
            identity.get("unionid") or "",
            identity.get("payer_name") or "",
            _safe_success_url(product.get("completion_redirect_url")),
            _jsonb(
                {
                    "completion_redirect": product.get("completion_redirect") or {},
                    "payer_identity": {
                        "openid": identity.get("openid") or "",
                        "respondent_key": identity.get("respondent_key") or "",
                        "external_userid": identity.get("external_userid") or "",
                        "owner_userid": identity.get("owner_userid") or "",
                        "mobile": mobile,
                    },
                }
            ),
            _jsonb(request_meta or {}),
            _expires_at(),
        ),
    ).fetchone()
    return dict(row or {})


def _update_payment_request(conn: Any, out_trade_no: str, *, prepay_id: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute(
        """
        UPDATE wechat_pay_orders
        SET prepay_id = %s,
            status = 'paying',
            request_payload_json = %s::jsonb,
            response_payload_json = %s::jsonb,
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = %s
        RETURNING *
        """,
        (prepay_id, _jsonb(request_payload), _jsonb(response_payload), out_trade_no),
    ).fetchone()
    return dict(row or {})


def _mark_order_failed(conn: Any, out_trade_no: str, error_message: str) -> None:
    conn.execute(
        "UPDATE wechat_pay_orders SET status = 'failed', last_error = %s, updated_at = CURRENT_TIMESTAMP WHERE out_trade_no = %s",
        (error_message[:500], out_trade_no),
    )


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _order_metadata_identity(order: dict[str, Any]) -> dict[str, Any]:
    metadata = _json_object(order.get("metadata_json"))
    for key in ("payer_identity", "buyer_identity"):
        identity = metadata.get(key)
        if isinstance(identity, dict):
            return identity
    return {}


def _project_order_mobile_to_identity(conn: Any, order: dict[str, Any], *, source_route: str) -> dict[str, Any]:
    identity = _order_metadata_identity(order)
    mobile = "".join(ch for ch in _normalized_text(identity.get("mobile")) if ch.isdigit())
    unionid = _normalized_text(order.get("unionid") or identity.get("unionid"))
    if not unionid:
        return {"ok": True, "projected": False, "reason": "missing_unionid"}
    if not mobile:
        return {"ok": True, "projected": False, "reason": "missing_mobile"}
    if not (len(mobile) == 11 and mobile.startswith("1")):
        return {"ok": True, "projected": False, "reason": "invalid_mobile"}

    external_userid = _normalized_text(identity.get("external_userid"))
    owner_userid = _normalized_text(identity.get("owner_userid"))
    customer_name = _normalized_text(order.get("payer_name_snapshot") or identity.get("payer_name"))
    row = conn.execute(
        """
        UPDATE crm_user_identity
        SET mobile = %s,
            mobile_normalized = %s,
            mobile_verified = TRUE,
            mobile_source = CASE
                WHEN COALESCE(NULLIF(mobile_source, ''), '') = '' THEN 'wechat_pay_order'
                ELSE mobile_source
            END,
            primary_external_userid = COALESCE(NULLIF(primary_external_userid, ''), NULLIF(%s, ''), primary_external_userid),
            primary_owner_userid = COALESCE(NULLIF(primary_owner_userid, ''), NULLIF(%s, ''), primary_owner_userid),
            customer_name = COALESCE(NULLIF(customer_name, ''), NULLIF(%s, ''), customer_name),
            profile_json = COALESCE(profile_json, '{}'::jsonb) || %s::jsonb,
            last_seen_at = NOW(),
            updated_at = NOW()
        WHERE unionid = %s
          AND (COALESCE(mobile, '') = '' OR mobile = %s OR mobile_normalized = %s)
        RETURNING unionid, mobile, primary_external_userid, primary_owner_userid
        """,
        (
            mobile,
            mobile,
            external_userid,
            owner_userid,
            customer_name,
            _jsonb(
                {
                    "wechat_pay_mobile_projection": {
                        "out_trade_no": _normalized_text(order.get("out_trade_no")),
                        "source_route": source_route,
                    }
                }
            ),
            unionid,
            mobile,
            mobile,
        ),
    ).fetchone()
    if not row:
        return {"ok": True, "projected": False, "reason": "identity_missing_or_mobile_conflict", "unionid": unionid}
    return {"ok": True, "projected": True, "unionid": unionid, "mobile": mobile}


def _safe_project_order_mobile_to_identity(conn: Any, order: dict[str, Any], *, source_route: str) -> dict[str, Any]:
    try:
        return _project_order_mobile_to_identity(conn, order, source_route=source_route)
    except Exception:
        LOGGER.exception(
            "wechat_pay_order_mobile_projection_failed",
            extra={"out_trade_no": _normalized_text(order.get("out_trade_no")), "source_route": source_route},
        )
        return {"ok": False, "projected": False, "reason": "projection_error"}


def _apply_transaction(conn: Any, transaction: dict[str, Any], *, source_route: str = "/api/h5/wechat-pay/notify") -> dict[str, Any]:
    trade_no = _normalized_text(transaction.get("out_trade_no"))
    trade_state = _normalized_text(transaction.get("trade_state"))
    status = "paid" if trade_state == "SUCCESS" else ("closed" if trade_state in {"CLOSED", "REVOKED"} else "paying")
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    previous = conn.execute("SELECT * FROM wechat_pay_orders WHERE out_trade_no = %s LIMIT 1", (trade_no,)).fetchone()
    was_paid = _normalized_text((previous or {}).get("status")) == "paid" or _normalized_text((previous or {}).get("trade_state")) == "SUCCESS"
    order = conn.execute(
        """
        UPDATE wechat_pay_orders
        SET status = %s,
            trade_state = %s,
            transaction_id = %s,
            bank_type = %s,
            payer_total = %s,
            paid_at = CASE WHEN %s = 'SUCCESS' THEN NULLIF(%s, '')::timestamptz ELSE paid_at END,
            notify_payload_json = %s::jsonb,
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = %s
        RETURNING *
        """,
        (
            status,
            trade_state,
            _normalized_text(transaction.get("transaction_id")),
            _normalized_text(transaction.get("bank_type")),
            int(amount.get("payer_total") or amount.get("total") or 0),
            trade_state,
            _normalized_text(transaction.get("success_time")),
            _jsonb(transaction),
            trade_no,
        ),
    ).fetchone()
    order_payload = dict(order or {})
    is_paid = _normalized_text(order_payload.get("status")) == "paid" or _normalized_text(order_payload.get("trade_state")) == "SUCCESS"
    if is_paid:
        mobile_projection = _safe_project_order_mobile_to_identity(conn, order_payload, source_route=source_route)
        outbox = enqueue_transaction_paid_outbox(conn, order_payload)
        _emit_payment_succeeded_internal_event(
            order=order_payload,
            transaction=transaction,
            outbox=outbox,
            source_route=source_route,
        )
        _plan_order_paid_external_effect_job(conn, order=order_payload, transaction=transaction, outbox=outbox)
        LOGGER.info(
            "wechat_pay_transaction_paid_outbox_ensured",
            extra={
                "order_id": order_payload.get("id"),
                "out_trade_no": _normalized_text(order_payload.get("out_trade_no")),
                "event_type": "transaction.paid",
                "outbox_created": bool(outbox),
                "was_paid": was_paid,
                "mobile_projected": bool(mobile_projection.get("projected")),
                "mobile_projection_reason": _normalized_text(mobile_projection.get("reason")),
            },
        )
    return order_payload


def _plan_order_paid_external_effect_job(conn: Any, *, order: dict[str, Any], transaction: dict[str, Any], outbox: dict[str, Any] | None) -> None:
    out_trade_no = _normalized_text(order.get("out_trade_no"))
    try:
        result = plan_order_paid_external_push_effect(
            conn,
            order=order,
            transaction=transaction,
            outbox=outbox,
            source_module="public_product.h5_wechat_pay",
            source_route="/api/h5/wechat-pay/notify",
        )
        if result.get("skipped"):
            LOGGER.info(
                "wechat_pay_order_external_push_skipped",
                extra={"out_trade_no": out_trade_no, "reason": result.get("reason")},
            )
    except Exception:
        LOGGER.exception("wechat_pay_external_effect_job_failed", extra={"out_trade_no": out_trade_no})


def create_jsapi_order_response(
    request: Request,
    payload: dict[str, Any],
    *,
    product_override: dict[str, Any] | None = None,
    checkout_return_path: str = "",
    allow_paid_reuse: bool = True,
    order_source: str = "h5_checkout",
    request_meta_extra: dict[str, Any] | None = None,
) -> JSONResponse:
    if not _is_wechat_browser(request):
        return JSONResponse({"ok": False, "error": "please_open_in_wechat"}, status_code=403, headers=route_headers())
    product_code = _normalized_text(payload.get("product_code"))
    if product_override is None:
        try:
            product = get_public_product(product_code)
        except Exception:
            return JSONResponse(product_not_found_payload(product_code), status_code=404, headers=route_headers())
    else:
        product = dict(product_override)
        product_code = _normalized_text(product.get("product_code") or product_code)
    identity = _identity_from_request(request)
    if not identity.get("openid"):
        return JSONResponse(
            {"ok": False, "error": "openid_required", "oauth_start_url": payment_oauth_start_url(checkout_return_path or f"/pay/{product_code}")},
            status_code=401,
            headers=route_headers(),
        )
    try:
        config = _require_payment_ready()
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=503, headers=route_headers())
    mobile = _normalized_text(payload.get("mobile"))
    context_token = _normalized_text(payload.get("ctx") or payload.get("context_token"))
    resolved_context = resolve_sidebar_order_context(
        context_token=context_token,
        payment_identity=identity,
        product=product,
        payload_mobile=mobile,
    )
    if product.get("require_mobile") and not _normalized_text(resolved_context.get("mobile")):
        return JSONResponse({"ok": False, "error": "mobile_required"}, status_code=400, headers=route_headers())
    order_identity = {
        **identity,
        "external_userid": _normalized_text(resolved_context.get("external_userid")),
        "owner_userid": _normalized_text(resolved_context.get("owner_userid")),
    }
    request_meta = {
        "sidebar_product_context": {
            "context_status": resolved_context.get("context_status"),
            "context_source": resolved_context.get("context_source"),
            "external_userid_present": bool(resolved_context.get("external_userid")),
            "owner_userid_present": bool(resolved_context.get("owner_userid")),
            "mobile_source": resolved_context.get("mobile_source"),
        }
    }
    if request_meta_extra:
        request_meta.update(request_meta_extra)
    out_trade_no = _out_trade_no()
    notify_url = _env("WECHAT_PAY_NOTIFY_URL") or f"{_external_base_url(request)}/api/h5/wechat-pay/notify"
    transaction_payload = {
        "appid": config.app_id,
        "mchid": config.mch_id,
        "description": _normalized_text(product.get("title"))[:127],
        "out_trade_no": out_trade_no,
        "notify_url": notify_url,
        "amount": {"total": int(product.get("price_cents") or 0), "currency": product.get("currency") or "CNY"},
        "payer": {"openid": identity["openid"]},
        "attach": json.dumps({"product_code": product["product_code"], "client_order_ref": _normalized_text(payload.get("client_order_ref"))}, ensure_ascii=False, separators=(",", ":"))[:128],
    }
    try:
        with _connect() as conn:
            existing_paid_order = _paid_order_payload_for_product_identity(conn, product=product, identity=order_identity) if allow_paid_reuse else None
            if existing_paid_order is not None:
                return JSONResponse({"ok": True, "already_paid": True, "order": existing_paid_order}, headers=route_headers())
            client = WeChatPayClient(config)
            _insert_order(
                conn,
                product=product,
                identity=order_identity,
                mobile=_normalized_text(resolved_context.get("mobile")),
                out_trade_no=out_trade_no,
                request_meta=request_meta,
                order_source=order_source,
            )
            response_payload = client.create_jsapi_transaction(transaction_payload)
            prepay_id = _normalized_text(response_payload.get("prepay_id"))
            if not prepay_id:
                raise WeChatPayClientError("missing prepay_id from WeChat Pay")
            order = _update_payment_request(conn, out_trade_no, prepay_id=prepay_id, request_payload=transaction_payload, response_payload=response_payload)
            pay_params = client.build_jsapi_pay_params(prepay_id)
            completion_redirect = _completion_redirect_from_product(product)
            conn.commit()
        return JSONResponse(
            {"ok": True, "order": _order_payload(order, completion_redirect=completion_redirect), "pay_params": pay_params},
            headers=route_headers(),
        )
    except Exception as exc:
        try:
            with _connect() as conn:
                _mark_order_failed(conn, out_trade_no, str(exc))
                conn.commit()
        except Exception:
            pass
        return JSONResponse({"ok": False, "error": str(exc) or "create_wechat_pay_order_failed"}, status_code=502, headers=route_headers())


def order_status_response(out_trade_no: str, request: Request) -> JSONResponse:
    if not production_data_ready():
        return JSONResponse({"ok": False, "error": "production_database_required"}, status_code=503, headers=route_headers())
    trade_no = _normalized_text(out_trade_no)
    with _connect() as conn:
        close_expired_wechat_pay_orders(conn=conn, out_trade_no=trade_no, limit=1)
        order = conn.execute("SELECT * FROM wechat_pay_orders WHERE out_trade_no = %s LIMIT 1", (trade_no,)).fetchone()
        if not order:
            return JSONResponse({"ok": False, "error": "order_not_found"}, status_code=404, headers=route_headers())
        conn.commit()
        if _normalized_text(request.query_params.get("refresh")).lower() in {"1", "true", "yes", "on"}:
            try:
                transaction = WeChatPayClient(_client_config()).query_order_by_out_trade_no(trade_no)
                order = _apply_transaction(conn, transaction, source_route=f"/api/h5/wechat-pay/orders/{trade_no}")
                conn.commit()
            except Exception as exc:
                conn.rollback()
                LOGGER.exception(
                    "wechat_pay_order_status_refresh_failed",
                    extra={"out_trade_no": trade_no, "event_type": "transaction.paid"},
                )
                return JSONResponse({"ok": False, "error": str(exc) or "wechat_pay_order_refresh_failed"}, status_code=502, headers=route_headers())
        order_payload = dict(order)
        product_code = _normalized_text(order_payload.get("product_code"))
        completion_redirect = _completion_redirect_for_product_code(conn, product_code)
        lead_qr = {} if completion_redirect.get("completion_redirect", {}).get("enabled") else _lead_qr_for_product_code(conn, product_code)
    return JSONResponse(
        {"ok": True, "order": _order_payload(order_payload, completion_redirect=completion_redirect, lead_qr=lead_qr)},
        headers=route_headers(),
    )


def notify_response(request: Request, body: bytes) -> JSONResponse:
    body_text = body.decode("utf-8")
    try:
        transaction = WeChatPayClient(_client_config()).verify_and_decrypt_notification(body=body_text, headers=dict(request.headers))
        if not production_data_ready():
            raise RuntimeError("production_database_required")
        with _connect() as conn:
            _apply_transaction(conn, transaction, source_route="/api/h5/wechat-pay/notify")
            conn.commit()
        return JSONResponse({"code": "SUCCESS", "message": "成功"})
    except Exception as exc:
        LOGGER.exception("wechat_pay_notify_failed", extra={"event_type": "transaction.paid"})
        return JSONResponse({"code": "FAIL", "message": str(exc)}, status_code=401)
