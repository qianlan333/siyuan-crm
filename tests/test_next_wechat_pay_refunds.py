from __future__ import annotations

import sys
import types

import pytest

from aicrm_next.commerce import admin_transactions


def _paid_order(**overrides):
    order = {
        "id": 19,
        "out_trade_no": "WXP_REAL_REFUND",
        "transaction_id": "420000REALNEXT",
        "amount_total": 6900,
        "currency": "CNY",
        "trade_state": "SUCCESS",
        "can_refund": True,
        "refundable_amount_total": 6900,
    }
    order.update(overrides)
    return order


def _install_fake_psycopg(monkeypatch):
    executed: list[tuple[str, tuple]] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=()):
            executed.append((sql, tuple(params)))

    class FakeConnection:
        def __init__(self):
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            self.commits += 1

    connections: list[FakeConnection] = []

    def connect(*args, **kwargs):
        conn = FakeConnection()
        connections.append(conn)
        return conn

    psycopg = types.ModuleType("psycopg")
    psycopg.connect = connect
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    psycopg_types = types.ModuleType("psycopg.types")
    json_module = types.ModuleType("psycopg.types.json")
    json_module.Jsonb = lambda value: value
    monkeypatch.setitem(sys.modules, "psycopg", psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)
    monkeypatch.setitem(sys.modules, "psycopg.types", psycopg_types)
    monkeypatch.setitem(sys.modules, "psycopg.types.json", json_module)
    return executed, connections


def test_next_postgres_refund_calls_wechat_pay_and_updates_success(monkeypatch):
    executed, connections = _install_fake_psycopg(monkeypatch)
    order = _paid_order()
    final_order = {**order, "refunded_amount_total": 6900, "refund_status": "full_refunded"}
    calls: list[dict] = []

    class FakeClient:
        def create_refund(self, payload):
            calls.append(payload)
            return {
                "status": "SUCCESS",
                "refund_id": "503000000020260604",
                "out_refund_no": payload["out_refund_no"],
            }

    orders = iter([order, final_order])
    monkeypatch.setattr(admin_transactions, "database_mode", lambda: "postgres")
    monkeypatch.setattr(admin_transactions, "_database_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(admin_transactions, "get_wechat_admin_order", lambda order_id: next(orders))
    monkeypatch.setattr(admin_transactions, "_create_wechat_pay_refund_client", lambda: FakeClient())

    result = admin_transactions.create_wechat_refund_request(
        "19",
        {
            "refund_amount_total": 6900,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "420000REALNEXT",
            "checked": True,
            "operator": "tester",
        },
    )

    assert result["ok"] is True
    assert result["refund"]["status"] == "SUCCESS"
    assert result["refund"]["provider_refund_executed"] is True
    assert result["refund"]["refund_id"] == "503000000020260604"
    assert result["order"] == final_order
    assert calls == [
        {
            "transaction_id": "420000REALNEXT",
            "out_refund_no": result["refund"]["out_refund_no"],
            "reason": "客户主动申请退款",
            "amount": {"refund": 6900, "total": 6900, "currency": "CNY"},
        }
    ]
    sql_text = "\n".join(sql for sql, _params in executed)
    assert "INSERT INTO wechat_pay_refunds" in sql_text
    assert "UPDATE wechat_pay_refunds" in sql_text
    assert "UPDATE wechat_pay_orders" in sql_text
    assert "INSERT INTO wechat_pay_order_events" in sql_text
    assert connections[0].commits == 2


def test_next_postgres_refund_marks_failed_when_wechat_pay_rejects(monkeypatch):
    executed, connections = _install_fake_psycopg(monkeypatch)
    order = _paid_order(amount_total=9900, refundable_amount_total=9900)

    class FakeClient:
        def create_refund(self, payload):
            raise RuntimeError("wechat unavailable")

    monkeypatch.setattr(admin_transactions, "database_mode", lambda: "postgres")
    monkeypatch.setattr(admin_transactions, "_database_url", lambda: "postgresql://test/test")
    monkeypatch.setattr(admin_transactions, "get_wechat_admin_order", lambda order_id: order)
    monkeypatch.setattr(admin_transactions, "_create_wechat_pay_refund_client", lambda: FakeClient())

    with pytest.raises(ValueError, match="微信支付退款申请失败：wechat unavailable"):
        admin_transactions.create_wechat_refund_request(
            "19",
            {
                "refund_amount_total": 9900,
                "reason": "客户主动申请退款",
                "transaction_id_confirmation": "420000REALNEXT",
                "checked": True,
            },
        )

    sql_text = "\n".join(sql for sql, _params in executed)
    assert "INSERT INTO wechat_pay_refunds" in sql_text
    assert "status = 'failed'" in sql_text
    assert "'refund_failed'" in sql_text
    assert connections[0].commits == 2
