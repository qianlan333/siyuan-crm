from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from ...db import get_db
from ...infra.json_utils import json_dumps


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any) -> str:
    return json_dumps(value, none_as_empty_object=True)


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def _decode_cursor(cursor: str) -> dict[str, Any]:
    text = _normalized_text(cursor)
    if not text:
        return {}
    try:
        payload = json.loads(base64.urlsafe_b64decode(text.encode("ascii")).decode("utf-8"))
    except (binascii.Error, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def insert_order(payload: dict[str, Any]) -> dict[str, Any]:
    product_code = _normalized_text(payload.get("product_code"))
    product_name = _normalized_text(payload.get("product_name")) or product_code
    row = get_db().execute(
        """
        INSERT INTO alipay_pay_orders (
            out_trade_no,
            order_source,
            client_order_ref,
            product_code,
            product_name,
            description,
            amount_total,
            currency,
            buyer_id,
            buyer_logon_id,
            mobile_snapshot,
            identity_snapshot,
            status,
            trade_status,
            success_url,
            metadata_json,
            request_meta_json,
            expires_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), ?::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("out_trade_no")),
            _normalized_text(payload.get("order_source")) or "h5_alipay_wap",
            _normalized_text(payload.get("client_order_ref")),
            product_code,
            product_name,
            _normalized_text(payload.get("description")),
            int(payload.get("amount_total") or 0),
            _normalized_text(payload.get("currency")) or "CNY",
            _normalized_text(payload.get("buyer_id")),
            _normalized_text(payload.get("buyer_logon_id")),
            _normalized_text(payload.get("mobile_snapshot") or payload.get("mobile")),
            _normalized_text(payload.get("identity_snapshot") or payload.get("identity")),
            _normalized_text(payload.get("status")) or "created",
            _normalized_text(payload.get("trade_status")),
            _normalized_text(payload.get("success_url")),
            _json(payload.get("metadata") or {}),
            _json(payload.get("request_meta") or {}),
            _normalized_text(payload.get("expires_at")) or None,
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_order_payment_request(
    out_trade_no: str,
    *,
    status: str = "paying",
    request_payload: dict[str, Any] | None = None,
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE alipay_pay_orders
        SET status = ?,
            request_payload_json = CAST(? AS jsonb),
            response_payload_json = CAST(? AS jsonb),
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (
            _normalized_text(status) or "paying",
            _json(request_payload or {}),
            _json(response_payload or {}),
            _normalized_text(out_trade_no),
        ),
    ).fetchone()
    return dict(row) if row else {}


def mark_order_failed(out_trade_no: str, *, error_message: str) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE alipay_pay_orders
        SET status = 'failed',
            last_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (_normalized_text(error_message)[:500], _normalized_text(out_trade_no)),
    ).fetchone()
    return dict(row) if row else {}


def get_order(out_trade_no: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM alipay_pay_orders
        WHERE out_trade_no = ?
        LIMIT 1
        """,
        (_normalized_text(out_trade_no),),
    )


def update_order_return_payload(out_trade_no: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE alipay_pay_orders
        SET return_payload_json = CAST(? AS jsonb),
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (_json(payload or {}), _normalized_text(out_trade_no)),
    ).fetchone()
    return dict(row) if row else {}


def _status_from_trade_status(trade_status: str) -> str:
    if trade_status in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
        return "paid"
    if trade_status == "TRADE_CLOSED":
        return "closed"
    if trade_status == "WAIT_BUYER_PAY":
        return "paying"
    return "paying"


def update_order_from_trade(
    trade: dict[str, Any],
    *,
    payload_kind: str,
) -> dict[str, Any]:
    out_trade_no = _normalized_text(trade.get("out_trade_no"))
    trade_status = _normalized_text(trade.get("trade_status"))
    status = _status_from_trade_status(trade_status)
    trade_no = _normalized_text(trade.get("trade_no"))
    paid_time = (
        _normalized_text(trade.get("gmt_payment"))
        or _normalized_text(trade.get("send_pay_date"))
        or _normalized_text(trade.get("gmt_close") if status == "paid" else "")
    )
    payload_column = "notify_payload_json" if payload_kind == "notify" else "response_payload_json"
    row = get_db().execute(
        f"""
        UPDATE alipay_pay_orders
        SET status = ?,
            trade_status = ?,
            trade_no = COALESCE(NULLIF(?, ''), trade_no),
            buyer_id = COALESCE(NULLIF(?, ''), buyer_id),
            buyer_logon_id = COALESCE(NULLIF(?, ''), buyer_logon_id),
            {payload_column} = CAST(? AS jsonb),
            paid_at = CASE WHEN ? = 'paid' THEN COALESCE(NULLIF(?, '')::timestamptz, paid_at, CURRENT_TIMESTAMP) ELSE paid_at END,
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (
            status,
            trade_status,
            trade_no,
            _normalized_text(trade.get("buyer_id")),
            _normalized_text(trade.get("buyer_logon_id")),
            _json(trade),
            status,
            paid_time,
            out_trade_no,
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_event(
    *,
    out_trade_no: str,
    event_type: str,
    trade_no: str = "",
    trade_status: str = "",
    payload: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO alipay_pay_order_events (
            out_trade_no,
            event_type,
            trade_no,
            trade_status,
            payload_json,
            headers_json,
            created_at
        )
        VALUES (?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(out_trade_no),
            _normalized_text(event_type),
            _normalized_text(trade_no),
            _normalized_text(trade_status),
            _json(payload or {}),
            _json(headers or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_products_from_orders() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT
            product_code,
            MAX(NULLIF(product_name, '')) AS product_name,
            COUNT(*) AS order_count
        FROM alipay_pay_orders
        WHERE product_code <> ''
        GROUP BY product_code
        ORDER BY product_code ASC
        """
    )


def _order_query_where(filters: dict[str, Any], params: list[Any]) -> list[str]:
    clauses = ["1 = 1"]
    created_from = _normalized_text(filters.get("created_from"))
    created_to = _normalized_text(filters.get("created_to"))
    product_code = _normalized_text(filters.get("product_code"))
    status = _normalized_text(filters.get("status"))
    mobile = _normalized_text(filters.get("mobile"))
    identity = _normalized_text(filters.get("identity"))
    trade_id = _normalized_text(filters.get("trade_id") or filters.get("trade_no") or filters.get("out_trade_no"))

    if created_from:
        clauses.append("created_at >= ?::timestamptz")
        params.append(created_from)
    if created_to:
        clauses.append("created_at <= ?::timestamptz")
        params.append(created_to)
    if product_code:
        clauses.append("product_code = ?")
        params.append(product_code)
    if mobile:
        clauses.append("mobile_snapshot ILIKE ?")
        params.append(f"%{mobile}%")
    if identity:
        clauses.append(
            "(buyer_id = ? OR buyer_logon_id ILIKE ? OR identity_snapshot = ? OR client_order_ref = ?)"
        )
        params.extend([identity, f"%{identity}%", identity, identity])
    if trade_id:
        clauses.append("(trade_no = ? OR out_trade_no = ?)")
        params.extend([trade_id, trade_id])
    if status:
        clauses.append("status = ?")
        params.append(status)
    return clauses


def list_admin_orders(*, filters: dict[str, Any], limit: int, cursor: str = "") -> list[dict[str, Any]]:
    params: list[Any] = []
    clauses = _order_query_where(filters, params)
    cursor_payload = _decode_cursor(cursor)
    cursor_created_at = _normalized_text(cursor_payload.get("created_at"))
    cursor_id = int(cursor_payload.get("id") or 0)
    if cursor_created_at and cursor_id > 0:
        clauses.append(
            "((created_at AT TIME ZONE 'UTC') < ?::timestamp "
            "OR ((created_at AT TIME ZONE 'UTC') = ?::timestamp AND id < ?))"
        )
        params.extend([cursor_created_at, cursor_created_at, cursor_id])
    params.append(max(1, int(limit)))
    return _fetchall_dicts(
        f"""
        SELECT
            id,
            created_at,
            out_trade_no,
            trade_no,
            buyer_id,
            buyer_logon_id,
            mobile_snapshot,
            identity_snapshot,
            client_order_ref,
            product_code,
            COALESCE(NULLIF(product_name, ''), product_code) AS product_name,
            amount_total,
            currency,
            status,
            trade_status
        FROM alipay_pay_orders
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    )


def get_admin_order_by_id(order_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM alipay_pay_orders
        WHERE id = ?
        LIMIT 1
        """,
        (int(order_id),),
    )


def list_order_events(out_trade_no: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, event_type, trade_no, trade_status, created_at
        FROM alipay_pay_order_events
        WHERE out_trade_no = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 50
        """,
        (_normalized_text(out_trade_no),),
    )
