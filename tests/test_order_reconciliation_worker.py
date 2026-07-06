from __future__ import annotations

from datetime import datetime, timezone

from aicrm_next.commerce import order_reconciliation
from aicrm_next.commerce.order_reconciliation import WeChatPayOrderReconciliationWorker
from aicrm_next.integration_gateway.wechat_pay_client import WeChatPayClient, WeChatPayClientConfig


class _Cursor:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.queries: list[tuple[str, tuple]] = []
        self.committed = False
        self.commit_count = 0
        self.closed = False

    def execute(self, query, params=()):
        self.queries.append((query, tuple(params)))
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT * FROM wechat_pay_orders"):
            return _Cursor(rows=self.rows)
        return _Cursor()

    def commit(self):
        self.committed = True
        self.commit_count += 1

    def rollback(self):
        raise AssertionError("rollback should not be called")

    def close(self):
        self.closed = True


class _FakeClient:
    def __init__(self, states, *, before_query=None):
        self.states = states
        self.before_query = before_query
        self.closed_orders: list[str] = []

    def query_order_by_out_trade_no(self, out_trade_no):
        if self.before_query:
            self.before_query(out_trade_no)
        return {
            "out_trade_no": out_trade_no,
            "trade_state": self.states[out_trade_no],
            "transaction_id": f"tx_{out_trade_no}",
            "amount": {"total": 990, "payer_total": 990},
        }

    def close_order_by_out_trade_no(self, out_trade_no):
        self.closed_orders.append(out_trade_no)
        return {}


def test_wechat_pay_reconciliation_repairs_success_and_closes_unpaid(monkeypatch) -> None:
    conn = _FakeConn(
        [
            {"id": 1, "out_trade_no": "WXP_SUCCESS"},
            {"id": 2, "out_trade_no": "WXP_NOTPAY"},
        ]
    )
    client = _FakeClient({"WXP_SUCCESS": "SUCCESS", "WXP_NOTPAY": "NOTPAY"})
    repaired: list[str] = []

    def fake_apply_transaction(active_conn, transaction, *, source_route):
        assert active_conn is conn
        assert source_route == "wechat_pay_order_reconciliation_worker"
        repaired.append(transaction["out_trade_no"])
        return {"out_trade_no": transaction["out_trade_no"], "status": "paid"}

    monkeypatch.setattr(order_reconciliation, "_apply_transaction", fake_apply_transaction)
    result = WeChatPayOrderReconciliationWorker(
        client_factory=lambda: client,
        connection_factory=lambda: conn,
    ).run_once(limit=10, ttl_hours=2, dry_run=False, now=datetime(2026, 7, 4, tzinfo=timezone.utc))

    assert result["ok"] is True
    assert result["repaired_count"] == 1
    assert result["closed_count"] == 1
    assert repaired == ["WXP_SUCCESS"]
    assert client.closed_orders == ["WXP_NOTPAY"]
    assert any("UPDATE wechat_pay_orders" in query and "status = 'closed'" in query for query, _ in conn.queries)
    assert conn.committed is True
    assert conn.commit_count >= 2
    assert conn.closed is True


def test_wechat_pay_reconciliation_dry_run_does_not_mutate() -> None:
    conn = _FakeConn([{"id": 1, "out_trade_no": "WXP_SUCCESS"}])
    client = _FakeClient({"WXP_SUCCESS": "SUCCESS"})

    result = WeChatPayOrderReconciliationWorker(
        client_factory=lambda: client,
        connection_factory=lambda: conn,
    ).run_once(limit=10, ttl_hours=2, dry_run=True, now=datetime(2026, 7, 4, tzinfo=timezone.utc))

    assert result["dry_run"] is True
    assert result["repaired_count"] == 0
    assert result["closed_count"] == 0
    assert client.closed_orders == []
    assert not any("UPDATE wechat_pay_orders" in query for query, _ in conn.queries)


def test_wechat_pay_reconciliation_releases_candidate_lock_before_http_query() -> None:
    conn = _FakeConn([{"id": 1, "out_trade_no": "WXP_SUCCESS"}])
    commit_counts_before_query: list[int] = []
    client = _FakeClient(
        {"WXP_SUCCESS": "SUCCESS"},
        before_query=lambda out_trade_no: commit_counts_before_query.append(conn.commit_count),
    )

    result = WeChatPayOrderReconciliationWorker(
        client_factory=lambda: client,
        connection_factory=lambda: conn,
    ).run_once(limit=10, ttl_hours=2, dry_run=True, now=datetime(2026, 7, 4, tzinfo=timezone.utc))

    assert result["dry_run"] is True
    assert commit_counts_before_query == [1]
    assert conn.commit_count >= 2


def test_wechat_pay_client_close_order_and_trade_bill_request_shapes() -> None:
    requests: list[dict] = []

    class Response:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    def fake_request(method, url, data, headers, timeout):
        requests.append({"method": method, "url": url, "data": data.decode("utf-8") if isinstance(data, bytes) else data})
        return Response()

    client = WeChatPayClient(
        WeChatPayClientConfig(
            app_id="app",
            mch_id="mch_123",
            api_v3_key="x" * 32,
            private_key_path="/tmp/missing.pem",
            merchant_serial_no="serial",
            api_base="https://pay.example.test",
        ),
        http_request=fake_request,
    )
    client._merchant_signature = lambda message: "signature"  # type: ignore[method-assign]

    client.close_order_by_out_trade_no("WXP_CLOSE")
    client.request_trade_bill(bill_date="2026-07-04")

    assert requests[0]["method"] == "POST"
    assert requests[0]["url"] == "https://pay.example.test/v3/pay/transactions/out-trade-no/WXP_CLOSE/close"
    assert requests[0]["data"] == '{"mchid":"mch_123"}'
    assert requests[1]["method"] == "GET"
    assert requests[1]["url"] == "https://pay.example.test/v3/bill/tradebill?bill_date=2026-07-04&bill_type=ALL"
