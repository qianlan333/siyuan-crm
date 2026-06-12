from __future__ import annotations

import csv
import io
import os
import secrets
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from aicrm_next.shared.runtime import database_mode
from aicrm_next.shared.text_encoding import repair_utf8_mojibake

from .repo import build_commerce_repository
from .application import GetTransactionQuery, ListProductsQuery, ListTransactionsQuery
from .product_code_aliases import canonical_product_code, product_code_filter_values
from .wechat_pay_client import WeChatPayClient, WeChatPayClientConfig

ADMIN_TZ = ZoneInfo("Asia/Shanghai")
ALLOWED_LIMITS = {20, 50, 100}
STATUS_LABELS = {
    "pending": "待支付",
    "paid": "已支付",
    "refund_processing": "退款处理中",
    "partial_refunded": "部分退款",
    "full_refunded": "全额退款",
    "failed": "支付失败",
}


def default_filters() -> dict[str, str]:
    now = datetime.now(ADMIN_TZ)
    start = now - timedelta(days=30)
    return {
        "created_from": start.strftime("%Y-%m-%dT00:00"),
        "created_to": now.strftime("%Y-%m-%dT23:59"),
        "product_code": "",
        "status": "",
        "mobile": "",
        "identity": "",
        "transaction_id": "",
    }


def normalize_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return 20
    return limit if limit in ALLOWED_LIMITS else 20


def normalize_offset(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def normalize_filters(source: dict[str, Any] | None) -> dict[str, str]:
    payload = dict(source or {})
    status = str(payload.get("status") or payload.get("payment_status") or "").strip()
    if status and status not in STATUS_LABELS:
        status = ""
    return {
        "created_from": str(payload.get("created_from") or payload.get("date_from") or "").strip(),
        "created_to": str(payload.get("created_to") or payload.get("date_to") or "").strip(),
        "product_code": str(payload.get("product_code") or "").strip(),
        "status": status,
        "mobile": str(payload.get("mobile") or payload.get("mobile_snapshot") or "").strip(),
        "identity": str(payload.get("identity") or payload.get("external_userid") or "").strip(),
        "transaction_id": str(payload.get("transaction_id") or "").strip(),
    }


def _database_url() -> str:
    return str(os.getenv("DATABASE_URL", "") or "").strip()


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        source = value
        if source.tzinfo is None:
            source = source.replace(tzinfo=ADMIN_TZ)
        return source.astimezone(ADMIN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def _money_yuan(value: Any) -> str:
    try:
        cents = int(value or 0)
    except (TypeError, ValueError):
        cents = 0
    return f"{cents / 100:.2f}"


def _normalized_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _refund_status_label(status: str) -> str:
    mapping = {
        "requested": "退款申请已提交",
        "PROCESSING": "退款处理中",
        "SUCCESS": "退款成功",
        "CLOSED": "退款关闭",
        "ABNORMAL": "退款异常",
        "failed": "退款申请失败",
    }
    return mapping.get(str(status or "").strip(), str(status or "").strip() or "退款申请已提交")


def _out_refund_no() -> str:
    return "WXR" + datetime.now(ADMIN_TZ).strftime("%y%m%d%H%M%S") + secrets.token_hex(4).upper()


def _wechat_pay_client_config() -> WeChatPayClientConfig:
    app_id = str(os.getenv("WECHAT_PAY_APP_ID") or os.getenv("WECHAT_MP_APP_ID") or "").strip()
    return WeChatPayClientConfig(
        app_id=app_id,
        mch_id=str(os.getenv("WECHAT_PAY_MCH_ID") or "").strip(),
        api_v3_key=str(os.getenv("WECHAT_PAY_API_V3_KEY") or "").strip(),
        private_key_path=str(os.getenv("WECHAT_PAY_PRIVATE_KEY_PATH") or "").strip(),
        merchant_serial_no=str(os.getenv("WECHAT_PAY_CERT_SERIAL_NO") or "").strip(),
        platform_public_key_path=str(os.getenv("WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH") or "").strip(),
        platform_serial_no=str(os.getenv("WECHAT_PAY_PLATFORM_CERT_SERIAL_NO") or "").strip(),
        api_base=str(os.getenv("WECHAT_PAY_API_BASE") or "https://api.mch.weixin.qq.com").strip()
        or "https://api.mch.weixin.qq.com",
        timeout_seconds=_int_value(os.getenv("WECHAT_PAY_TIMEOUT_SECONDS") or 10),
    )


def _create_wechat_pay_refund_client() -> WeChatPayClient:
    return WeChatPayClient(_wechat_pay_client_config())


def _merged_status(row: dict[str, Any]) -> str:
    try:
        amount_total = int(row.get("amount_total") or row.get("amount_cents") or 0)
        refunded = int(row.get("refunded_amount_total") or 0)
        active_refunding = int(row.get("active_refund_amount_total") or 0)
    except (TypeError, ValueError):
        amount_total = 0
        refunded = 0
        active_refunding = 0
    refund_status = str(row.get("refund_status") or "").strip()
    raw = str(row.get("status") or row.get("payment_status") or "").strip()
    trade_state = str(row.get("trade_state") or "").strip()
    if refund_status == "full_refunded" or (amount_total > 0 and refunded >= amount_total):
        return "full_refunded"
    if active_refunding > 0:
        return "refund_processing"
    if refund_status == "partial_refunded" or refunded > 0:
        return "partial_refunded"
    if raw == "paid" or trade_state == "SUCCESS":
        return "paid"
    if raw == "failed":
        return "failed"
    return "pending"


def _present_order(row: dict[str, Any]) -> dict[str, Any]:
    status = _merged_status(row)
    order_id = row.get("id") or row.get("order_no") or ""
    amount_total = _int_value(row.get("amount_total") or row.get("amount_cents"))
    refunded = max(0, _int_value(row.get("refunded_amount_total")))
    active_refunding = max(0, _int_value(row.get("active_refund_amount_total")))
    refundable = max(0, amount_total - refunded - active_refunding)
    payer_name = repair_utf8_mojibake(row.get("payer_name_snapshot") or row.get("payer_name")) or "未记录付款人"
    mobile = str(row.get("mobile_snapshot") or row.get("buyer_mobile") or "").strip()
    userid = str(row.get("userid_snapshot") or "").strip()
    external_userid = str(row.get("external_userid") or "").strip()
    unionid = str(row.get("unionid") or "").strip()
    product_code = canonical_product_code(row.get("product_code"))
    product_name = str(row.get("product_name") or row.get("product_title") or product_code).strip()
    transaction_id = str(row.get("transaction_id") or "").strip()
    return {
        "id": order_id,
        "out_trade_no": str(row.get("out_trade_no") or row.get("order_no") or ""),
        "created_at": _format_time(row.get("created_at")),
        "transaction_id": transaction_id or "待支付暂无微信单号",
        "has_transaction_id": bool(transaction_id),
        "payer_name": payer_name or "未记录付款人",
        "mobile": mobile,
        "unionid": unionid,
        "userid": userid,
        "external_userid": external_userid,
        "product_code": product_code,
        "product_name": product_name or "-",
        "amount_total": amount_total,
        "amount_yuan": _money_yuan(amount_total),
        "currency": str(row.get("currency") or "CNY"),
        "status": status,
        "status_label": STATUS_LABELS[status],
        "refunded_amount_total": refunded,
        "refunded_amount_yuan": _money_yuan(refunded),
        "active_refund_amount_total": active_refunding,
        "active_refund_amount_yuan": _money_yuan(active_refunding),
        "refundable_amount_total": refundable,
        "refundable_amount_yuan": _money_yuan(refundable),
        "can_refund": status in {"paid", "partial_refunded"} and refundable > 0,
        "detail_url": f"/admin/wechat-pay/transactions/{order_id}",
    }


def _fixture_orders(filters: dict[str, str], *, limit: int, offset: int) -> dict[str, Any]:
    status_filter = filters.get("status")
    payload = ListTransactionsQuery("wechat")(
        {
            "payment_status": status_filter if status_filter in {"pending", "paid", "failed"} else "",
            "product_code": "",
            "mobile": filters.get("mobile"),
            "external_userid": filters.get("identity"),
            "date_from": filters.get("created_from"),
            "date_to": filters.get("created_to"),
        },
        limit=limit,
        offset=offset,
    )
    rows = payload.get("items", [])
    product_codes = set(product_code_filter_values(filters.get("product_code")))
    if product_codes:
        rows = [row for row in rows if str(row.get("product_code") or "").strip() in product_codes]
    if filters.get("transaction_id"):
        rows = [row for row in rows if filters["transaction_id"] in str(row.get("transaction_id") or "")]
    items = [_present_order(row) for row in rows]
    if status_filter and status_filter not in {"pending", "paid", "failed"}:
        items = [item for item in items if item["status"] == status_filter]
    total = len(items) if status_filter and status_filter not in {"pending", "paid", "failed"} else int(payload.get("total") or len(rows))
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "next_offset": offset + limit if offset + limit < total else None,
    }


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _postgres_order_select() -> str:
    return """
        id, out_trade_no, transaction_id, payer_name_snapshot, mobile_snapshot, userid_snapshot,
        external_userid, unionid, respondent_key, product_name, product_code, amount_total, currency,
        status, trade_state, refund_status, refunded_amount_total, created_at,
        (
            SELECT COALESCE(SUM(r.refund_amount_total), 0)
            FROM wechat_pay_refunds r
            WHERE r.order_id = wechat_pay_orders.id
              AND r.status NOT IN ('failed', 'closed', 'CLOSED', 'ABNORMAL', 'SUCCESS')
        ) AS active_refund_amount_total
    """


def _postgres_orders(filters: dict[str, str], *, limit: int, offset: int) -> dict[str, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required for production transaction admin") from exc

    where = ["1 = 1"]
    params: list[Any] = []
    if filters.get("product_code"):
        filter_values = product_code_filter_values(filters["product_code"])
        where.append(f"product_code IN ({', '.join(['%s'] * len(filter_values))})")
        params.extend(filter_values)
    if filters.get("mobile"):
        where.append("COALESCE(mobile_snapshot, '') ILIKE %s")
        params.append(f"%{filters['mobile']}%")
    if filters.get("identity"):
        where.append(
            "(COALESCE(userid_snapshot, '') ILIKE %s OR COALESCE(external_userid, '') ILIKE %s OR COALESCE(respondent_key, '') ILIKE %s)"
        )
        needle = f"%{filters['identity']}%"
        params.extend([needle, needle, needle])
    if filters.get("transaction_id"):
        where.append("COALESCE(transaction_id, '') ILIKE %s")
        params.append(f"%{filters['transaction_id']}%")
    if filters.get("created_from"):
        where.append("created_at >= %s")
        params.append(filters["created_from"].replace("T", " "))
    if filters.get("created_to"):
        where.append("created_at <= %s")
        params.append(filters["created_to"].replace("T", " "))
    if filters.get("status") == "paid":
        where.append("(status = 'paid' OR trade_state = 'SUCCESS')")
    elif filters.get("status") == "pending":
        where.append("COALESCE(status, '') NOT IN ('paid', 'failed') AND COALESCE(trade_state, '') <> 'SUCCESS'")
    elif filters.get("status") == "refund_processing":
        where.append(
            """
            EXISTS (
                SELECT 1 FROM wechat_pay_refunds r
                WHERE r.order_id = wechat_pay_orders.id
                  AND r.status NOT IN ('failed', 'closed', 'CLOSED', 'ABNORMAL', 'SUCCESS')
            )
            """
        )
    elif filters.get("status") == "failed":
        where.append("status = 'failed'")
    elif filters.get("status") == "partial_refunded":
        where.append("(refund_status = 'partial_refunded' OR COALESCE(refunded_amount_total, 0) > 0)")
    elif filters.get("status") == "full_refunded":
        where.append("(refund_status = 'full_refunded' OR COALESCE(refunded_amount_total, 0) >= COALESCE(amount_total, 0))")

    clause = " AND ".join(where)
    query = f"""
        SELECT {_postgres_order_select()}
        FROM wechat_pay_orders
        WHERE {clause}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
    """
    count_query = f"SELECT count(*) AS total FROM wechat_pay_orders WHERE {clause}"
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(count_query, tuple(params))
            total = int((cur.fetchone() or {}).get("total") or 0)
            cur.execute(query, tuple([*params, limit, offset]))
            rows = [dict(row) for row in cur.fetchall()]
    return {
        "items": [_present_order(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "next_offset": offset + limit if offset + limit < total else None,
    }


def list_wechat_admin_orders(filters: dict[str, Any] | None, *, limit: Any = 20, offset: Any = 0) -> dict[str, Any]:
    normalized = normalize_filters(filters)
    page_size = normalize_limit(limit)
    page_offset = normalize_offset(offset)
    payload = (
        _postgres_orders(normalized, limit=page_size, offset=page_offset)
        if database_mode() == "postgres"
        else _fixture_orders(normalized, limit=page_size, offset=page_offset)
    )
    return {"ok": True, "filters": normalized, **payload}


def get_wechat_admin_order(order_id: str) -> dict[str, Any] | None:
    identifier = str(order_id or "").strip()
    if not identifier:
        return None
    if database_mode() == "postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required for production transaction admin") from exc
        with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {_postgres_order_select()}
                    FROM wechat_pay_orders
                    WHERE id::text = %s OR out_trade_no = %s OR transaction_id = %s
                    LIMIT 1
                    """,
                    (identifier, identifier, identifier),
                )
                row = cur.fetchone()
                return _present_order(dict(row)) if row else None
    try:
        payload = GetTransactionQuery("wechat")(identifier)
    except Exception:
        return None
    return _present_order(payload.get("transaction", {}))


def _validate_refund_request(order: dict[str, Any], payload: dict[str, Any]) -> int:
    if not order:
        raise ValueError("订单不存在")
    if not order.get("can_refund"):
        raise ValueError("只有已支付或部分退款且仍有可退金额的订单可以申请退款")
    transaction_id = str(order.get("transaction_id") or "").strip()
    if not transaction_id or str(payload.get("transaction_id_confirmation") or "").strip() != transaction_id:
        raise ValueError("微信单号二次确认不匹配")
    if not _normalized_bool(payload.get("checked")):
        raise ValueError("请先勾选已核对付款人、商品、金额和微信单号")
    amount_total = _int_value(payload.get("refund_amount_total"))
    if amount_total <= 0:
        raise ValueError("退款金额必须大于 0")
    if amount_total > _int_value(order.get("refundable_amount_total")):
        raise ValueError("累计退款金额不能超过订单金额")
    if not str(payload.get("reason") or "").strip():
        raise ValueError("请选择退款原因")
    return amount_total


def create_wechat_refund_request(order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    order = get_wechat_admin_order(order_id)
    amount_total = _validate_refund_request(order or {}, payload)
    reason = str(payload.get("reason") or "").strip()
    out_refund_no = _out_refund_no()
    currency = str(order.get("currency") or "CNY").strip() or "CNY"
    request_payload = {
        "transaction_id": order["transaction_id"],
        "out_refund_no": out_refund_no,
        "reason": reason[:80],
        "amount": {
            "refund": amount_total,
            "total": order["amount_total"],
            "currency": currency,
        },
    }
    if database_mode() == "postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
        except ModuleNotFoundError as exc:
            raise RuntimeError("psycopg is required for production transaction admin") from exc
        with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO wechat_pay_refunds (
                        order_id, out_trade_no, transaction_id, out_refund_no, reason,
                        refund_amount_total, order_amount_total, currency, status,
                        requested_by, request_payload_json, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'requested', %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        int(order["id"]),
                        order.get("out_trade_no") or "",
                        order["transaction_id"],
                        out_refund_no,
                        reason,
                        amount_total,
                        order["amount_total"],
                        currency,
                        str(payload.get("operator") or "aicrm_next"),
                        Jsonb(request_payload),
                    ),
                )
            conn.commit()
            try:
                response_payload = _create_wechat_pay_refund_client().create_refund(request_payload)
            except Exception as exc:
                error_text = str(exc)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE wechat_pay_refunds
                        SET status = 'failed',
                            response_payload_json = %s,
                            error_message = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE out_refund_no = %s
                        """,
                        (Jsonb({}), error_text[:500], out_refund_no),
                    )
                    cur.execute(
                        """
                        INSERT INTO wechat_pay_order_events (
                            out_trade_no, event_type, transaction_id, trade_state,
                            payload_json, headers_json, created_at
                        )
                        VALUES (%s, 'refund_failed', %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        """,
                        (
                            order.get("out_trade_no") or "",
                            order["transaction_id"],
                            str(order.get("trade_state") or ""),
                            Jsonb({"out_refund_no": out_refund_no, "amount_total": amount_total, "error": error_text}),
                            Jsonb({}),
                        ),
                    )
                conn.commit()
                raise ValueError(f"微信支付退款申请失败：{error_text}") from exc

            refund_status = str(response_payload.get("status") or "PROCESSING").strip() or "PROCESSING"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE wechat_pay_refunds
                    SET refund_id = COALESCE(NULLIF(%s, ''), refund_id),
                        status = %s,
                        response_payload_json = %s,
                        error_message = '',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE out_refund_no = %s
                    """,
                    (
                        str(response_payload.get("refund_id") or "").strip(),
                        refund_status,
                        Jsonb(response_payload),
                        out_refund_no,
                    ),
                )
                if refund_status == "SUCCESS":
                    cur.execute(
                        """
                        UPDATE wechat_pay_orders
                        SET refunded_amount_total = LEAST(amount_total, COALESCE(refunded_amount_total, 0) + %s),
                            refund_status = CASE
                                WHEN LEAST(amount_total, COALESCE(refunded_amount_total, 0) + %s) >= amount_total THEN 'full_refunded'
                                ELSE 'partial_refunded'
                            END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (amount_total, amount_total, int(order["id"])),
                    )
                cur.execute(
                    """
                    INSERT INTO wechat_pay_order_events (
                        out_trade_no, event_type, transaction_id, trade_state,
                        payload_json, headers_json, created_at
                    )
                    VALUES (%s, 'refund_requested', %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        order.get("out_trade_no") or "",
                        order["transaction_id"],
                        str(order.get("trade_state") or ""),
                        Jsonb(
                            {
                                "out_refund_no": out_refund_no,
                                "refund_id": str(response_payload.get("refund_id") or "").strip(),
                                "wechat_refund_status": refund_status,
                                "amount_total": amount_total,
                            }
                        ),
                        Jsonb({}),
                    ),
                )
            conn.commit()
        updated_order = get_wechat_admin_order(order_id) or order
        return {
            "ok": True,
            "order": updated_order,
            "refund": {
                "status": refund_status,
                "status_label": _refund_status_label(refund_status),
                "out_refund_no": out_refund_no,
                "refund_id": str(response_payload.get("refund_id") or "").strip(),
                "provider_refund_executed": True,
            },
        }
    else:
        result = build_commerce_repository().request_refund("wechat", str(order_id), request_payload)
        updated_order = _present_order(result["order"])
    return {
        "ok": True,
        "order": updated_order,
        "refund": {
            "status": "requested",
            "status_label": _refund_status_label("requested"),
            "out_refund_no": out_refund_no,
            "provider_refund_executed": False,
        },
    }


def list_wechat_product_options() -> list[dict[str, str]]:
    if database_mode() == "postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ModuleNotFoundError:
            return []
        with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT product_code, COALESCE(NULLIF(name, ''), product_code) AS product_name
                    FROM wechat_pay_products
                    WHERE COALESCE(enabled, TRUE) = TRUE
                    ORDER BY updated_at DESC NULLS LAST, id DESC
                    LIMIT 100
                    """
                )
                return [
                    {"product_code": str(row["product_code"]), "product_name": str(row["product_name"])}
                    for row in cur.fetchall()
                    if row.get("product_code")
                ]
    payload = ListProductsQuery()(limit=100, offset=0)
    return [
        {"product_code": str(item["product_code"]), "product_name": str(item.get("title") or item["product_code"])}
        for item in payload.get("items", [])
        if item.get("product_code")
    ]


def export_orders_csv(filters: dict[str, Any] | None) -> str:
    payload = list_wechat_admin_orders(filters, limit=100, offset=0)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["订单创建时间", "微信单号", "手机号", "unionid", "商品名称", "商品编码", "金额", "状态"])
    for item in payload["items"]:
        writer.writerow(
            [
                item.get("created_at", ""),
                item.get("transaction_id", ""),
                item.get("mobile", ""),
                item.get("unionid", ""),
                item.get("product_name", ""),
                item.get("product_code", ""),
                item.get("amount_yuan", ""),
                item.get("status_label", ""),
            ]
        )
    return output.getvalue()
