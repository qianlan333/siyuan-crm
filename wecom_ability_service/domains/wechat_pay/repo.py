from __future__ import annotations

import base64
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
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def insert_order(payload: dict[str, Any]) -> dict[str, Any]:
    product_code = _normalized_text(payload.get("product_code"))
    product_name = _normalized_text(payload.get("product_name")) or product_code
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_orders (
            out_trade_no,
            order_source,
            client_order_ref,
            product_code,
            product_name,
            description,
            amount_total,
            currency,
            payer_openid,
            respondent_key,
            unionid,
            external_userid,
            userid_snapshot,
            mobile_snapshot,
            payer_name_snapshot,
            status,
            success_url,
            metadata_json,
            request_meta_json,
            expires_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS jsonb), ?::timestamptz, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("out_trade_no")),
            _normalized_text(payload.get("order_source")) or "h5_checkout",
            _normalized_text(payload.get("client_order_ref")),
            product_code,
            product_name,
            _normalized_text(payload.get("description")),
            int(payload.get("amount_total") or 0),
            _normalized_text(payload.get("currency")) or "CNY",
            _normalized_text(payload.get("payer_openid")),
            _normalized_text(payload.get("respondent_key")),
            _normalized_text(payload.get("unionid")),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("userid_snapshot") or payload.get("userid")),
            _normalized_text(payload.get("mobile_snapshot") or payload.get("mobile")),
            _normalized_text(payload.get("payer_name_snapshot") or payload.get("payer_name")),
            _normalized_text(payload.get("status")) or "created",
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
    prepay_id: str,
    status: str = "paying",
    request_payload: dict[str, Any] | None = None,
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET prepay_id = ?,
            status = ?,
            request_payload_json = CAST(? AS jsonb),
            response_payload_json = CAST(? AS jsonb),
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (
            _normalized_text(prepay_id),
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
        UPDATE wechat_pay_orders
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
        FROM wechat_pay_orders
        WHERE out_trade_no = ?
        LIMIT 1
        """,
        (_normalized_text(out_trade_no),),
    )


def update_order_from_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    out_trade_no = _normalized_text(transaction.get("out_trade_no"))
    trade_state = _normalized_text(transaction.get("trade_state"))
    status = "paid" if trade_state == "SUCCESS" else ("closed" if trade_state in {"CLOSED", "REVOKED"} else "paying")
    amount = transaction.get("amount") if isinstance(transaction.get("amount"), dict) else {}
    payer = transaction.get("payer") if isinstance(transaction.get("payer"), dict) else {}
    row = get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET status = ?,
            trade_state = ?,
            transaction_id = ?,
            bank_type = ?,
            payer_openid = COALESCE(NULLIF(?, ''), payer_openid),
            payer_total = ?,
            paid_at = CASE WHEN ? = 'SUCCESS' THEN NULLIF(?, '')::timestamptz ELSE paid_at END,
            notify_payload_json = CAST(? AS jsonb),
            last_error = '',
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = ?
        RETURNING *
        """,
        (
            status,
            trade_state,
            _normalized_text(transaction.get("transaction_id")),
            _normalized_text(transaction.get("bank_type")),
            _normalized_text(payer.get("openid")),
            int(amount.get("payer_total") or amount.get("total") or 0),
            trade_state,
            _normalized_text(transaction.get("success_time")),
            _json(transaction),
            out_trade_no,
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_event(
    *,
    out_trade_no: str,
    event_type: str,
    transaction_id: str = "",
    trade_state: str = "",
    payload: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_order_events (
            out_trade_no,
            event_type,
            transaction_id,
            trade_state,
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
            _normalized_text(transaction_id),
            _normalized_text(trade_state),
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
        FROM wechat_pay_orders
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
    transaction_id = _normalized_text(filters.get("transaction_id"))

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
        clauses.append("(external_userid = ? OR userid_snapshot = ? OR respondent_key = ?)")
        params.extend([identity, identity, identity])
    if transaction_id:
        clauses.append("transaction_id = ?")
        params.append(transaction_id)

    if status == "pending":
        clauses.append(
            "COALESCE(refunded_amount_total, 0) = 0 "
            "AND COALESCE(status, '') NOT IN ('paid') "
            "AND COALESCE(trade_state, '') <> 'SUCCESS'"
        )
    elif status == "paid":
        clauses.append(
            "COALESCE(refunded_amount_total, 0) = 0 "
            "AND (COALESCE(status, '') = 'paid' OR COALESCE(trade_state, '') = 'SUCCESS')"
        )
    elif status == "partial_refunded":
        clauses.append("COALESCE(refunded_amount_total, 0) > 0 AND COALESCE(refunded_amount_total, 0) < amount_total")
    elif status == "full_refunded":
        clauses.append("COALESCE(refunded_amount_total, 0) >= amount_total AND amount_total > 0")
    return clauses


def list_admin_orders(*, filters: dict[str, Any], limit: int, cursor: str = "") -> list[dict[str, Any]]:
    params: list[Any] = []
    clauses = _order_query_where(filters, params)
    cursor_payload = _decode_cursor(cursor)
    cursor_created_at = _normalized_text(cursor_payload.get("created_at"))
    cursor_id = int(cursor_payload.get("id") or 0)
    if cursor_created_at and cursor_id > 0:
        clauses.append("(created_at < ?::timestamptz OR (created_at = ?::timestamptz AND id < ?))")
        params.extend([cursor_created_at, cursor_created_at, cursor_id])
    params.append(max(1, int(limit)))
    return _fetchall_dicts(
        f"""
        SELECT
            id,
            created_at,
            transaction_id,
            payer_name_snapshot,
            mobile_snapshot,
            userid_snapshot,
            external_userid,
            respondent_key,
            product_code,
            COALESCE(NULLIF(product_name, ''), product_code) AS product_name,
            amount_total,
            currency,
            status,
            trade_state,
            refunded_amount_total,
            refund_status
        FROM wechat_pay_orders
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
        FROM wechat_pay_orders
        WHERE id = ?
        LIMIT 1
        """,
        (int(order_id),),
    )


def list_order_events(out_trade_no: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, event_type, transaction_id, trade_state, created_at
        FROM wechat_pay_order_events
        WHERE out_trade_no = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 50
        """,
        (_normalized_text(out_trade_no),),
    )


def insert_refund_request(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_refunds (
            order_id,
            out_trade_no,
            transaction_id,
            out_refund_no,
            reason,
            refund_amount_total,
            order_amount_total,
            currency,
            status,
            requested_by,
            request_payload_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'requested', ?, CAST(? AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("order_id") or 0),
            _normalized_text(payload.get("out_trade_no")),
            _normalized_text(payload.get("transaction_id")),
            _normalized_text(payload.get("out_refund_no")),
            _normalized_text(payload.get("reason")),
            int(payload.get("refund_amount_total") or 0),
            int(payload.get("order_amount_total") or 0),
            _normalized_text(payload.get("currency")) or "CNY",
            _normalized_text(payload.get("requested_by")),
            _json(payload.get("request_payload") or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_refund_response(
    out_refund_no: str,
    *,
    refund_id: str = "",
    status: str,
    response_payload: dict[str, Any] | None = None,
    error_message: str = "",
) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE wechat_pay_refunds
        SET refund_id = COALESCE(NULLIF(?, ''), refund_id),
            status = ?,
            response_payload_json = CAST(? AS jsonb),
            error_message = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE out_refund_no = ?
        RETURNING *
        """,
        (
            _normalized_text(refund_id),
            _normalized_text(status) or "processing",
            _json(response_payload or {}),
            _normalized_text(error_message)[:500],
            _normalized_text(out_refund_no),
        ),
    ).fetchone()
    return dict(row) if row else {}


def sum_active_refund_amount(order_id: int) -> int:
    row = get_db().execute(
        """
        SELECT COALESCE(SUM(refund_amount_total), 0) AS total
        FROM wechat_pay_refunds
        WHERE order_id = ?
          AND status NOT IN ('failed', 'closed', 'CLOSED', 'ABNORMAL', 'SUCCESS')
        """,
        (int(order_id),),
    ).fetchone()
    return int((row or {}).get("total") or 0)


def apply_successful_refund(*, order_id: int, amount_total: int) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET refunded_amount_total = LEAST(amount_total, COALESCE(refunded_amount_total, 0) + ?),
            refund_status = CASE
                WHEN LEAST(amount_total, COALESCE(refunded_amount_total, 0) + ?) >= amount_total THEN 'full_refunded'
                ELSE 'partial_refunded'
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (int(amount_total), int(amount_total), int(order_id)),
    ).fetchone()
    return dict(row) if row else {}


def insert_export_job(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO wechat_pay_order_export_jobs (
            job_id,
            requested_by,
            filters_json,
            scope,
            file_format,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, CAST(? AS jsonb), ?, ?, 'queued', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("job_id")),
            _normalized_text(payload.get("requested_by")),
            _json(payload.get("filters") or {}),
            _normalized_text(payload.get("scope")) or "filtered",
            _normalized_text(payload.get("file_format")) or "xlsx",
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_export_job(job_id: str, **fields: Any) -> dict[str, Any]:
    allowed = {"status", "exported_count", "file_name", "file_path", "error_message", "finished_at"}
    assignments = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        assignments.append(f"{key} = ?")
        params.append(value)
    if not assignments:
        return get_export_job(job_id) or {}
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.append(_normalized_text(job_id))
    row = get_db().execute(
        f"""
        UPDATE wechat_pay_order_export_jobs
        SET {", ".join(assignments)}
        WHERE job_id = ?
        RETURNING *
        """,
        tuple(params),
    ).fetchone()
    return dict(row) if row else {}


def get_export_job(job_id: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM wechat_pay_order_export_jobs
        WHERE job_id = ?
        LIMIT 1
        """,
        (_normalized_text(job_id),),
    )
