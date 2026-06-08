from __future__ import annotations

import base64
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any

from ..wechat_pay.product_service import list_products
from . import repo


ADMIN_ORDER_STATUSES = {
    "created": "已创建",
    "paying": "待支付",
    "paid": "已支付",
    "closed": "已关闭",
    "failed": "下单失败",
}
ALLOWED_LIMITS = {20, 50, 100}
EXPORT_HEADERS = [
    "订单创建时间",
    "支付宝交易号",
    "商户订单号",
    "付款人身份",
    "手机号",
    "商品名称",
    "商品编码",
    "金额",
    "状态",
]
EXPORT_MAX_DAYS = 90
EXPORT_MAX_ROWS = 5000


class AlipayPayAdminError(ValueError):
    pass


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dt_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return _normalized_text(value)


def _iso_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _normalized_text(value)


def _money_text(amount_total: Any) -> str:
    cents = _normalized_int(amount_total)
    return f"{cents / 100:.2f}"


def _encode_cursor(row: dict[str, Any]) -> str:
    payload = {"created_at": _iso_text(row.get("created_at")), "id": int(row.get("id") or 0)}
    return base64.urlsafe_b64encode(__import__("json").dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


def _identity_text(order: dict[str, Any]) -> str:
    return (
        _normalized_text(order.get("buyer_logon_id"))
        or _normalized_text(order.get("buyer_id"))
        or _normalized_text(order.get("identity_snapshot"))
        or _normalized_text(order.get("client_order_ref"))
        or "-"
    )


def _present_order(order: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(order.get("status")) or "created"
    product_code = _normalized_text(order.get("product_code"))
    product_name = _normalized_text(order.get("product_name")) or product_code
    return {
        "id": int(order.get("id") or 0),
        "created_at": _dt_text(order.get("created_at")),
        "out_trade_no": _normalized_text(order.get("out_trade_no")),
        "trade_no": _normalized_text(order.get("trade_no")) or "待支付暂无支付宝交易号",
        "buyer_id": _normalized_text(order.get("buyer_id")),
        "buyer_logon_id": _normalized_text(order.get("buyer_logon_id")),
        "mobile": _normalized_text(order.get("mobile_snapshot")),
        "identity": _identity_text(order),
        "product_code": product_code,
        "product_name": product_name,
        "amount_total": _normalized_int(order.get("amount_total")),
        "amount_yuan": _money_text(order.get("amount_total")),
        "currency": _normalized_text(order.get("currency")) or "CNY",
        "status": status,
        "status_label": ADMIN_ORDER_STATUSES.get(status, status or "-"),
        "trade_status": _normalized_text(order.get("trade_status")),
    }


def default_filters() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    return {
        "created_from": start.strftime("%Y-%m-%dT00:00"),
        "created_to": now.strftime("%Y-%m-%dT23:59"),
        "product_code": "",
        "status": "",
        "mobile": "",
        "identity": "",
        "trade_id": "",
    }


def normalize_filters(payload: dict[str, Any] | None) -> dict[str, str]:
    source = dict(payload or {})
    filters = {
        "created_from": _normalized_text(source.get("created_from")),
        "created_to": _normalized_text(source.get("created_to")),
        "product_code": _normalized_text(source.get("product_code")),
        "status": _normalized_text(source.get("status")),
        "mobile": _normalized_text(source.get("mobile") or source.get("mobile_snapshot")),
        "identity": _normalized_text(source.get("identity")),
        "trade_id": _normalized_text(source.get("trade_id") or source.get("trade_no") or source.get("out_trade_no")),
    }
    if filters["status"] and filters["status"] not in ADMIN_ORDER_STATUSES:
        raise AlipayPayAdminError("订单状态筛选不合法")
    return filters


def normalize_limit(value: Any) -> int:
    limit = _normalized_int(value, default=20)
    return limit if limit in ALLOWED_LIMITS else 20


def list_product_options() -> list[dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for product in list_products():
        code = _normalized_text(product.get("product_code"))
        if code:
            options[code] = {"product_code": code, "product_name": _normalized_text(product.get("name")) or code}
    for product in repo.list_products_from_orders():
        code = _normalized_text(product.get("product_code"))
        if code and code not in options:
            options[code] = {"product_code": code, "product_name": _normalized_text(product.get("product_name")) or code}
    return list(options.values())


def list_orders(*, filters: dict[str, Any] | None, limit: Any = 20, cursor: str = "") -> dict[str, Any]:
    normalized_filters = normalize_filters(filters)
    page_size = normalize_limit(limit)
    rows = repo.list_admin_orders(filters=normalized_filters, limit=page_size + 1, cursor=_normalized_text(cursor))
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    next_cursor = _encode_cursor(page_rows[-1]) if has_more and page_rows else ""
    return {
        "items": [_present_order(row) for row in page_rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "limit": page_size,
    }


def _parse_date(value: str) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _validate_export_filters(filters: dict[str, str]) -> None:
    created_from = _parse_date(filters.get("created_from", ""))
    created_to = _parse_date(filters.get("created_to", ""))
    if created_from and created_to and created_to - created_from > timedelta(days=EXPORT_MAX_DAYS):
        raise AlipayPayAdminError(f"导出时间范围最多 {EXPORT_MAX_DAYS} 天")


def export_orders_csv(*, filters: dict[str, Any] | None) -> tuple[str, str]:
    normalized_filters = normalize_filters(filters)
    export_defaults = default_filters()
    normalized_filters["created_from"] = normalized_filters["created_from"] or export_defaults["created_from"]
    normalized_filters["created_to"] = normalized_filters["created_to"] or export_defaults["created_to"]
    _validate_export_filters(normalized_filters)
    rows = repo.list_admin_orders(filters=normalized_filters, limit=EXPORT_MAX_ROWS + 1, cursor="")
    if len(rows) > EXPORT_MAX_ROWS:
        rows = rows[:EXPORT_MAX_ROWS]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(EXPORT_HEADERS)
    for row in [_present_order(item) for item in rows]:
        writer.writerow(
            [
                row["created_at"],
                row["trade_no"],
                row["out_trade_no"],
                row["identity"],
                row["mobile"],
                row["product_name"],
                row["product_code"],
                row["amount_yuan"],
                row["status_label"],
            ]
        )
    file_name = "alipay_pay_orders_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + ".csv"
    return output.getvalue(), file_name
