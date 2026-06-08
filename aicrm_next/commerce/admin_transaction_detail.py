from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from aicrm_next.shared.errors import NotFoundError
from aicrm_next.shared.runtime import database_mode, raw_database_url

from .application import GetTransactionQuery, ListTransactionsQuery
from .product_code_aliases import canonical_product_code, product_code_filter_values

ADMIN_TZ = ZoneInfo("Asia/Shanghai")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        source = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return source.astimezone(ADMIN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return _text(value)


def _money_yuan(value: Any) -> str:
    return f"{_int(value) / 100:.2f}"


class PaymentProviderStatusMapper:
    LABELS = {
        "pending": "待支付",
        "paid": "已支付",
        "closed": "已关闭",
        "refund_processing": "退款处理中",
        "partial_refunded": "部分退款",
        "full_refunded": "全额退款",
        "failed": "支付失败",
    }

    def map(self, provider: str, row: dict[str, Any]) -> dict[str, str]:
        status = self._status(provider, row)
        return {"status": status, "status_label": self.LABELS[status]}

    def _status(self, provider: str, row: dict[str, Any]) -> str:
        amount_total = _int(row.get("amount_total") or row.get("amount_cents"))
        refunded = _int(row.get("refunded_amount_total"))
        active_refunding = _int(row.get("active_refund_amount_total"))
        refund_status = _text(row.get("refund_status")).lower()
        raw_status = _text(row.get("status") or row.get("payment_status")).lower()
        provider_state = _text(row.get("trade_state") or row.get("trade_status")).upper()
        if refund_status == "full_refunded" or (amount_total > 0 and refunded >= amount_total):
            return "full_refunded"
        if active_refunding > 0 or refund_status in {"requested", "processing", "refund_processing"}:
            return "refund_processing"
        if refund_status == "partial_refunded" or refunded > 0:
            return "partial_refunded"
        if provider == "alipay":
            if provider_state in {"TRADE_SUCCESS", "TRADE_FINISHED"} or raw_status in {"paid", "success"}:
                return "paid"
            if provider_state == "TRADE_CLOSED" or raw_status in {"closed", "cancelled", "canceled"}:
                return "closed"
            if raw_status in {"failed", "error"}:
                return "failed"
            return "pending"
        if provider_state == "SUCCESS" or raw_status == "paid":
            return "paid"
        if provider_state in {"CLOSED", "REVOKED", "PAYERROR"} or raw_status in {"closed", "cancelled", "canceled"}:
            return "closed"
        if raw_status == "failed":
            return "failed"
        return "pending"


class PaymentTimelineProjection:
    def project(self, *, provider: str, order: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
        timeline: list[dict[str, str]] = []
        if _text(order.get("created_at")):
            timeline.append({"time": _format_time(order.get("created_at")), "event": "订单创建", "status": _text(order.get("status") or order.get("payment_status"))})
        if _text(order.get("paid_at")):
            timeline.append({"time": _format_time(order.get("paid_at")), "event": "支付成功", "status": _text(order.get("trade_state") or order.get("trade_status") or "paid")})
        for event in events[:20]:
            event_type = _text(event.get("event_type")) or "payment_event"
            provider_state = _text(event.get("trade_state") or event.get("trade_status"))
            timeline.append({"time": _format_time(event.get("created_at")), "event": event_type, "status": provider_state})
        latest_event = events[0] if events else {}
        callback_payload = _json_dict(order.get("notify_payload_json"))
        if provider == "alipay" and not callback_payload:
            callback_payload = _json_dict(order.get("return_payload_json"))
        callback_summary = {
            "event_count": len(events),
            "latest_event_type": _text(latest_event.get("event_type")) or "-",
            "latest_provider_status": _text(latest_event.get("trade_state") or latest_event.get("trade_status")) or "-",
            "notify_payload_present": bool(_json_dict(order.get("notify_payload_json"))),
            "return_payload_present": bool(_json_dict(order.get("return_payload_json"))),
            "payload_keys": sorted(callback_payload.keys())[:12],
        }
        return {"timeline": timeline, "callback_summary": callback_summary}


@dataclass(frozen=True)
class _ProviderConfig:
    provider: str
    provider_label: str
    platform_no_label: str
    page_path: str
    api_path: str


PROVIDERS = {
    "wechat": _ProviderConfig("wechat", "微信支付", "微信单号", "/admin/wechat-pay/transactions", "/api/admin/wechat-pay/transactions"),
    "alipay": _ProviderConfig("alipay", "支付宝", "支付宝交易号", "/admin/alipay/transactions", "/api/admin/alipay/transactions"),
}


def provider_config(provider: str) -> _ProviderConfig:
    key = _text(provider) or "wechat"
    if key not in PROVIDERS:
        raise NotFoundError("payment provider not found")
    return PROVIDERS[key]


def _platform_transaction_no(provider: str, row: dict[str, Any]) -> str:
    if provider == "alipay":
        return _text(row.get("trade_no") or row.get("transaction_id")) or "待支付暂无支付宝交易号"
    return _text(row.get("transaction_id")) or "待支付暂无微信单号"


def _merchant_order_no(row: dict[str, Any]) -> str:
    return _text(row.get("out_trade_no") or row.get("order_no"))


def _product_name(row: dict[str, Any]) -> str:
    product_code = canonical_product_code(row.get("product_code"))
    return _text(row.get("product_name") or row.get("product_title") or product_code) or "-"


def _customer(row: dict[str, Any]) -> dict[str, str]:
    return {
        "name": _text(row.get("payer_name_snapshot") or row.get("payer_name") or row.get("buyer_logon_id")) or "未记录付款人",
        "mobile": _text(row.get("mobile_snapshot") or row.get("buyer_mobile")),
        "userid": _text(row.get("userid_snapshot") or row.get("buyer_id")),
        "external_userid": _text(row.get("external_userid") or row.get("identity_snapshot")),
        "unionid": _text(row.get("unionid")),
    }


def _present(provider: str, row: dict[str, Any], *, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    config = provider_config(provider)
    status = PaymentProviderStatusMapper().map(provider, row)
    amount_total = _int(row.get("amount_total") or row.get("amount_cents"))
    refunded = max(0, _int(row.get("refunded_amount_total")))
    active_refunding = max(0, _int(row.get("active_refund_amount_total")))
    refundable = max(0, amount_total - refunded - active_refunding)
    merchant_order_no = _merchant_order_no(row)
    platform_no = _platform_transaction_no(provider, row)
    order_id = _text(row.get("id") or row.get("order_no") or merchant_order_no)
    customer = _customer(row)
    product_code = canonical_product_code(row.get("product_code"))
    timeline = PaymentTimelineProjection().project(provider=provider, order=row, events=events or [])
    return {
        "id": order_id,
        "provider": provider,
        "provider_label": config.provider_label,
        "merchant_order_no": merchant_order_no,
        "out_trade_no": merchant_order_no,
        "platform_transaction_no": platform_no,
        "transaction_id": platform_no,
        "has_transaction_id": bool(_text(row.get("transaction_id") or row.get("trade_no"))),
        "created_at": _format_time(row.get("created_at")),
        "paid_at": _format_time(row.get("paid_at")),
        "customer": customer,
        "payer_name": customer["name"],
        "mobile": customer["mobile"],
        "userid": customer["userid"],
        "external_userid": customer["external_userid"],
        "unionid": customer["unionid"],
        "product_code": product_code,
        "product_name": _product_name(row),
        "amount_total": amount_total,
        "amount_yuan": _money_yuan(amount_total),
        "currency": _text(row.get("currency")) or "CNY",
        **status,
        "raw_status": _text(row.get("status") or row.get("payment_status")),
        "provider_status": _text(row.get("trade_state") or row.get("trade_status")),
        "refunded_amount_total": refunded,
        "refunded_amount_yuan": _money_yuan(refunded),
        "active_refund_amount_total": active_refunding,
        "active_refund_amount_yuan": _money_yuan(active_refunding),
        "refundable_amount_total": refundable,
        "refundable_amount_yuan": _money_yuan(refundable),
        "can_refund": provider == "wechat" and status["status"] in {"paid", "partial_refunded"} and refundable > 0,
        "callback_summary": timeline["callback_summary"],
        "timeline": timeline["timeline"],
        "detail_url": f"{config.page_path}/{order_id}",
    }


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(raw_database_url(), row_factory=dict_row)


def _postgres_filter_clause(provider: str, filters: dict[str, Any], params: list[Any]) -> str:
    table_alias = "o"
    where = ["1 = 1"]
    product_code = _text(filters.get("product_code"))
    if product_code:
        values = product_code_filter_values(product_code)
        where.append(f"{table_alias}.product_code IN ({', '.join(['%s'] * len(values))})")
        params.extend(values)
    mobile = _text(filters.get("mobile") or filters.get("mobile_snapshot"))
    if mobile:
        where.append(f"COALESCE({table_alias}.mobile_snapshot, '') ILIKE %s")
        params.append(f"%{mobile}%")
    identity = _text(filters.get("identity") or filters.get("external_userid"))
    if identity:
        if provider == "alipay":
            where.append("(COALESCE(o.identity_snapshot, '') ILIKE %s OR COALESCE(o.buyer_id, '') ILIKE %s OR COALESCE(o.buyer_logon_id, '') ILIKE %s)")
        else:
            where.append("(COALESCE(o.userid_snapshot, '') ILIKE %s OR COALESCE(o.external_userid, '') ILIKE %s OR COALESCE(o.respondent_key, '') ILIKE %s)")
        needle = f"%{identity}%"
        params.extend([needle, needle, needle])
    transaction = _text(filters.get("transaction_id") or filters.get("platform_transaction_no"))
    if transaction:
        column = "trade_no" if provider == "alipay" else "transaction_id"
        where.append(f"COALESCE(o.{column}, '') ILIKE %s")
        params.append(f"%{transaction}%")
    created_from = _text(filters.get("created_from") or filters.get("date_from"))
    if created_from:
        where.append("o.created_at >= %s")
        params.append(created_from.replace("T", " "))
    created_to = _text(filters.get("created_to") or filters.get("date_to"))
    if created_to:
        where.append("o.created_at <= %s")
        params.append(created_to.replace("T", " "))
    status = _text(filters.get("status") or filters.get("payment_status"))
    if status == "paid":
        state_column = "trade_status" if provider == "alipay" else "trade_state"
        success_values = ("TRADE_SUCCESS", "TRADE_FINISHED") if provider == "alipay" else ("SUCCESS",)
        where.append(f"(o.status = 'paid' OR o.{state_column} IN ({', '.join(['%s'] * len(success_values))}))")
        params.extend(success_values)
    elif status == "pending":
        where.append("COALESCE(o.status, '') NOT IN ('paid', 'failed', 'closed')")
    elif status == "closed":
        state_column = "trade_status" if provider == "alipay" else "trade_state"
        closed_values = ("TRADE_CLOSED",) if provider == "alipay" else ("CLOSED", "REVOKED", "PAYERROR")
        where.append(f"(o.status IN ('closed', 'cancelled', 'canceled') OR o.{state_column} IN ({', '.join(['%s'] * len(closed_values))}))")
        params.extend(closed_values)
    elif status == "failed":
        where.append("o.status = 'failed'")
    elif status == "partial_refunded":
        where.append("(o.refund_status = 'partial_refunded' OR COALESCE(o.refunded_amount_total, 0) > 0)")
    elif status == "full_refunded":
        where.append("(o.refund_status = 'full_refunded' OR COALESCE(o.refunded_amount_total, 0) >= COALESCE(o.amount_total, 0))")
    return " AND ".join(where)


def _postgres_order_select(provider: str) -> str:
    if provider == "alipay":
        return """
            o.id, o.out_trade_no, o.trade_no, o.product_name, o.product_code, o.amount_total, o.currency,
            o.buyer_id, o.buyer_logon_id, o.mobile_snapshot, o.identity_snapshot, o.status, o.trade_status,
            o.notify_payload_json, o.return_payload_json, o.refunded_amount_total, o.refund_status,
            o.paid_at, o.created_at, o.updated_at, 0 AS active_refund_amount_total
        """
    return """
        o.id, o.out_trade_no, o.transaction_id, o.payer_name_snapshot, o.mobile_snapshot, o.userid_snapshot,
        o.external_userid, o.unionid, o.respondent_key, o.product_name, o.product_code, o.amount_total, o.currency,
        o.status, o.trade_state, o.notify_payload_json, o.refunded_amount_total, o.refund_status, o.paid_at,
        o.created_at, o.updated_at,
        (
            SELECT COALESCE(SUM(r.refund_amount_total), 0)
            FROM wechat_pay_refunds r
            WHERE r.order_id = o.id
              AND r.status NOT IN ('failed', 'closed', 'CLOSED', 'ABNORMAL', 'SUCCESS')
        ) AS active_refund_amount_total
    """


def _postgres_table(provider: str) -> str:
    return "alipay_pay_orders" if provider == "alipay" else "wechat_pay_orders"


def _postgres_events(provider: str, out_trade_no: str) -> list[dict[str, Any]]:
    table = "alipay_pay_order_events" if provider == "alipay" else "wechat_pay_order_events"
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE out_trade_no = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (_text(out_trade_no),),
        ).fetchall()
    return [dict(row) for row in rows]


def _postgres_list(provider: str, filters: dict[str, Any], *, limit: int, offset: int) -> dict[str, Any]:
    limit = max(1, min(_int(limit) or 50, 100))
    offset = max(0, _int(offset))
    params: list[Any] = []
    clause = _postgres_filter_clause(provider, filters, params)
    table = _postgres_table(provider)
    select = _postgres_order_select(provider)
    with _connect() as conn:
        total = int((conn.execute(f"SELECT count(*) AS total FROM {table} o WHERE {clause}", tuple(params)).fetchone() or {}).get("total") or 0)
        rows = conn.execute(
            f"""
            SELECT {select}
            FROM {table} o
            WHERE {clause}
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT %s OFFSET %s
            """,
            tuple([*params, limit, offset]),
        ).fetchall()
    return {
        "items": [_present(provider, dict(row)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "next_offset": offset + limit if offset + limit < total else None,
    }


def _postgres_get(provider: str, identifier: str) -> dict[str, Any] | None:
    table = _postgres_table(provider)
    select = _postgres_order_select(provider)
    transaction_column = "trade_no" if provider == "alipay" else "transaction_id"
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT {select}
            FROM {table} o
            WHERE o.id::text = %s OR o.out_trade_no = %s OR o.{transaction_column} = %s
            LIMIT 1
            """,
            (_text(identifier), _text(identifier), _text(identifier)),
        ).fetchone()
    if not row:
        return None
    row_dict = dict(row)
    return _present(provider, row_dict, events=_postgres_events(provider, _text(row_dict.get("out_trade_no"))))


def _fixture_list(provider: str, filters: dict[str, Any], *, limit: int, offset: int) -> dict[str, Any]:
    payload = ListTransactionsQuery(provider)(filters, limit=limit, offset=offset)
    items = [_present(provider, row) for row in payload.get("items", [])]
    status_filter = _text(filters.get("status") or filters.get("payment_status"))
    if status_filter in PaymentProviderStatusMapper.LABELS:
        items = [item for item in items if item["status"] == status_filter]
    total = len(items) if status_filter in PaymentProviderStatusMapper.LABELS else _int(payload.get("total") or len(items))
    return {"items": items, "total": total, "limit": limit, "offset": offset, "has_more": offset + limit < total, "next_offset": offset + limit if offset + limit < total else None}


def _fixture_get(provider: str, identifier: str) -> dict[str, Any] | None:
    try:
        payload = GetTransactionQuery(provider)(_text(identifier))
    except Exception:
        return None
    return _present(provider, dict(payload.get("transaction") or {}))


class CommerceAdminTransactionListReadModel:
    def __init__(self, provider: str) -> None:
        self.provider = provider_config(provider).provider

    def execute(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        payload = (
            _postgres_list(self.provider, dict(filters or {}), limit=limit, offset=offset)
            if database_mode() == "postgres"
            else _fixture_list(self.provider, dict(filters or {}), limit=limit, offset=offset)
        )
        return {
            "ok": True,
            "provider": self.provider,
            "provider_label": provider_config(self.provider).provider_label,
            "filters": dict(filters or {}),
            **payload,
        }


class CommerceAdminTransactionDetailReadModel:
    def __init__(self, provider: str) -> None:
        self.provider = provider_config(provider).provider

    def execute(self, identifier: str) -> dict[str, Any]:
        order = _postgres_get(self.provider, identifier) if database_mode() == "postgres" else _fixture_get(self.provider, identifier)
        if not order:
            raise NotFoundError("transaction not found")
        return {
            "ok": True,
            "provider": self.provider,
            "provider_label": provider_config(self.provider).provider_label,
            "transaction": order,
        }
