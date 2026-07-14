from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from psycopg.types.json import Jsonb

from aicrm_next.integration_gateway.wechat_pay_client import (
    WeChatPayClient,
    WeChatPayClientConfig,
    wechat_pay_client_config_from_env,
)
from .order_expiration import pending_order_ttl_hours
from .repo import connect_commerce_db


UNPAID_TRADE_STATES = {"", "NOTPAY", "USERPAYING", "ACCEPT", "PAYERROR"}
TERMINAL_UNPAID_STATES = {"CLOSED", "REVOKED"}
_apply_transaction: Callable[..., dict[str, Any]] | None = None


class WeChatPayOrderReconciliationWorker:
    def __init__(
        self,
        *,
        client_factory: Callable[[], WeChatPayClient] | None = None,
        connection_factory: Callable[[], Any] | None = None,
        transaction_applier: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.client_factory = client_factory or (lambda: WeChatPayClient(wechat_pay_client_config_from_env()))
        self.connection_factory = connection_factory or connect_commerce_db
        self.transaction_applier = transaction_applier

    def run_once(
        self,
        *,
        limit: int = 100,
        ttl_hours: int | None = None,
        window_hours: int = 24,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        source_now = _utc(now)
        conn = self.connection_factory()
        client = self.client_factory()
        scanned = 0
        repaired = 0
        closed = 0
        skipped = 0
        failed = 0
        details: list[dict[str, Any]] = []
        try:
            candidates = _select_candidates(
                conn,
                now=source_now,
                ttl_hours=ttl_hours or pending_order_ttl_hours(),
                window_hours=window_hours,
                limit=limit,
            )
            conn.commit()
            for order in candidates:
                scanned += 1
                out_trade_no = str(order.get("out_trade_no") or "").strip()
                if not out_trade_no:
                    skipped += 1
                    continue
                try:
                    transaction = client.query_order_by_out_trade_no(out_trade_no)
                    trade_state = str(transaction.get("trade_state") or "").strip().upper()
                    if dry_run:
                        details.append({"out_trade_no": out_trade_no, "trade_state": trade_state, "action": "preview"})
                        continue
                    if trade_state == "SUCCESS":
                        transaction_applier = self.transaction_applier or _apply_transaction
                        if transaction_applier is None:
                            raise RuntimeError("payment transaction applier composition unavailable")
                        transaction_applier(conn, transaction, source_route="wechat_pay_order_reconciliation_worker")
                        _insert_order_event(
                            conn,
                            out_trade_no=out_trade_no,
                            event_type="reconciliation_payment_repaired",
                            transaction=transaction,
                        )
                        repaired += 1
                        details.append({"out_trade_no": out_trade_no, "trade_state": trade_state, "action": "repaired"})
                    elif trade_state in UNPAID_TRADE_STATES:
                        client.close_order_by_out_trade_no(out_trade_no)
                        _mark_order_closed(conn, out_trade_no=out_trade_no, reason="wechat_pay_reconciliation_closed_unpaid")
                        _insert_order_event(
                            conn,
                            out_trade_no=out_trade_no,
                            event_type="reconciliation_order_closed",
                            transaction=transaction,
                        )
                        closed += 1
                        details.append({"out_trade_no": out_trade_no, "trade_state": trade_state, "action": "closed"})
                    elif trade_state in TERMINAL_UNPAID_STATES:
                        _mark_order_closed(conn, out_trade_no=out_trade_no, reason="wechat_pay_reconciliation_terminal_unpaid")
                        closed += 1
                        details.append({"out_trade_no": out_trade_no, "trade_state": trade_state, "action": "marked_closed"})
                    else:
                        skipped += 1
                        details.append({"out_trade_no": out_trade_no, "trade_state": trade_state, "action": "skipped"})
                except Exception as exc:  # pragma: no cover - defensive per-order isolation
                    failed += 1
                    if not dry_run:
                        _mark_order_reconciliation_error(conn, out_trade_no=out_trade_no, error=str(exc))
                    details.append({"out_trade_no": out_trade_no, "action": "failed", "error": type(exc).__name__})
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return {
            "ok": failed == 0,
            "dry_run": dry_run,
            "scanned_count": scanned,
            "repaired_count": repaired,
            "closed_count": closed,
            "skipped_count": skipped,
            "failed_count": failed,
            "details": details,
            "source_status": "wechat_pay_order_reconciliation_worker",
            "real_external_call_executed": not dry_run and scanned > 0,
        }


def request_wechat_pay_trade_bill(
    *,
    bill_date: str,
    bill_type: str = "ALL",
    client: WeChatPayClient | None = None,
    config: WeChatPayClientConfig | None = None,
) -> dict[str, Any]:
    active_client = client or WeChatPayClient(config or wechat_pay_client_config_from_env())
    return active_client.request_trade_bill(bill_date=bill_date, bill_type=bill_type)


def _select_candidates(
    conn: Any,
    *,
    now: datetime,
    ttl_hours: int,
    window_hours: int,
    limit: int,
) -> list[dict[str, Any]]:
    cutoff = now - timedelta(hours=max(1, ttl_hours))
    oldest = now - timedelta(hours=max(1, ttl_hours) + max(1, window_hours))
    rows = conn.execute(
        """
        SELECT *
        FROM wechat_pay_orders
        WHERE COALESCE(status, '') IN ('created', 'paying', 'pending', '')
          AND COALESCE(trade_state, '') <> 'SUCCESS'
          AND paid_at IS NULL
          AND created_at <= %s::timestamptz
          AND created_at >= %s::timestamptz
        ORDER BY created_at ASC, id ASC
        LIMIT %s
        FOR UPDATE SKIP LOCKED
        """,
        (cutoff, oldest, max(1, min(int(limit or 100), 500))),
    ).fetchall()
    return [dict(row) for row in rows or []]


def _mark_order_closed(conn: Any, *, out_trade_no: str, reason: str) -> None:
    conn.execute(
        """
        UPDATE wechat_pay_orders
        SET status = 'closed',
            trade_state = 'CLOSED',
            last_error = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = %s
        """,
        (reason, out_trade_no),
    )


def _mark_order_reconciliation_error(conn: Any, *, out_trade_no: str, error: str) -> None:
    conn.execute(
        """
        UPDATE wechat_pay_orders
        SET last_error = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE out_trade_no = %s
        """,
        (f"wechat_pay_reconciliation_error: {error}"[:500], out_trade_no),
    )


def _insert_order_event(conn: Any, *, out_trade_no: str, event_type: str, transaction: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO wechat_pay_order_events (
            out_trade_no, event_type, transaction_id, trade_state, payload_json, headers_json, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (
            out_trade_no,
            event_type,
            str(transaction.get("transaction_id") or ""),
            str(transaction.get("trade_state") or ""),
            Jsonb(transaction),
            Jsonb({}),
        ),
    )


def _utc(value: datetime | None) -> datetime:
    source = value or datetime.now(timezone.utc)
    if source.tzinfo is None:
        source = source.replace(tzinfo=timezone.utc)
    return source.astimezone(timezone.utc)
