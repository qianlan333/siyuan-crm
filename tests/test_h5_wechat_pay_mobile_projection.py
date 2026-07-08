from __future__ import annotations

import json
from pathlib import Path

from aicrm_next.public_product import h5_wechat_pay

ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _ProjectionConn:
    def __init__(self, row):
        self.row = row
        self.calls: list[dict] = []

    def execute(self, query, params):
        self.calls.append({"query": query, "params": params})
        return _Cursor(self.row)


def test_project_order_mobile_to_identity_uses_order_metadata(monkeypatch) -> None:
    monkeypatch.setattr(h5_wechat_pay, "_jsonb", lambda value: json.dumps(value, ensure_ascii=False))
    conn = _ProjectionConn({"unionid": "union_order_001", "mobile": "15812345678"})

    result = h5_wechat_pay._project_order_mobile_to_identity(
        conn,
        {
            "out_trade_no": "WXP_MOBILE_PROJECT",
            "unionid": "union_order_001",
            "payer_name_snapshot": "付款人",
            "metadata_json": {
                "payer_identity": {
                    "mobile": "158 1234 5678",
                    "external_userid": "wm_order_001",
                    "owner_userid": "HuangYouCan",
                }
            },
        },
        source_route="/api/h5/wechat-pay/notify",
    )

    assert result == {"ok": True, "projected": True, "unionid": "union_order_001", "mobile": "15812345678"}
    call = conn.calls[0]
    assert "UPDATE crm_user_identity" in call["query"]
    assert "COALESCE(mobile, '') = '' OR mobile = %s OR mobile_normalized = %s" in call["query"]
    assert call["params"][0:5] == ("15812345678", "15812345678", "wm_order_001", "HuangYouCan", "付款人")
    assert call["params"][6:] == ("union_order_001", "15812345678", "15812345678")


def test_project_order_mobile_to_identity_skips_invalid_or_missing_identity(monkeypatch) -> None:
    monkeypatch.setattr(h5_wechat_pay, "_jsonb", lambda value: json.dumps(value, ensure_ascii=False))
    conn = _ProjectionConn({"unionid": "union_order_001"})

    missing_unionid = h5_wechat_pay._project_order_mobile_to_identity(
        conn,
        {"metadata_json": {"payer_identity": {"mobile": "15812345678"}}},
        source_route="/api/h5/wechat-pay/notify",
    )
    invalid_mobile = h5_wechat_pay._project_order_mobile_to_identity(
        conn,
        {"unionid": "union_order_001", "metadata_json": {"payer_identity": {"mobile": "12345"}}},
        source_route="/api/h5/wechat-pay/notify",
    )

    assert missing_unionid["reason"] == "missing_unionid"
    assert invalid_mobile["reason"] == "invalid_mobile"
    assert conn.calls == []


def test_project_order_mobile_to_identity_does_not_overwrite_conflicting_mobile(monkeypatch) -> None:
    monkeypatch.setattr(h5_wechat_pay, "_jsonb", lambda value: json.dumps(value, ensure_ascii=False))
    conn = _ProjectionConn(None)

    result = h5_wechat_pay._project_order_mobile_to_identity(
        conn,
        {
            "unionid": "union_order_001",
            "metadata_json": {"payer_identity": {"mobile": "15812345678"}},
        },
        source_route="/api/h5/wechat-pay/notify",
    )

    assert result == {
        "ok": True,
        "projected": False,
        "reason": "identity_missing_or_mobile_conflict",
        "unionid": "union_order_001",
    }


def test_apply_transaction_runs_mobile_projection_before_order_side_effects(monkeypatch) -> None:
    calls: list[str] = []

    class Conn:
        def execute(self, query, params):
            if query.startswith("SELECT * FROM wechat_pay_orders"):
                return _Cursor({"status": "paying"})
            if query.strip().startswith("UPDATE wechat_pay_orders"):
                return _Cursor(
                    {
                        "id": 1,
                        "out_trade_no": "WXP_APPLY_MOBILE",
                        "status": "paid",
                        "trade_state": "SUCCESS",
                        "unionid": "union_apply_001",
                        "metadata_json": {"payer_identity": {"mobile": "15812345678"}},
                    }
                )
            raise AssertionError(query)

    monkeypatch.setattr(
        h5_wechat_pay,
        "_safe_project_order_mobile_to_identity",
        lambda conn, order, *, source_route: calls.append("project") or {"ok": True, "projected": True},
    )
    monkeypatch.setattr(
        h5_wechat_pay,
        "enqueue_transaction_paid_outbox",
        lambda conn, order: calls.append("outbox") or {"id": 1},
    )
    monkeypatch.setattr(
        h5_wechat_pay,
        "_emit_payment_succeeded_internal_event",
        lambda **kwargs: calls.append("event"),
    )
    monkeypatch.setattr(
        h5_wechat_pay,
        "_plan_order_paid_external_effect_job",
        lambda conn, *, order, transaction, outbox: calls.append("external_effect"),
    )

    order = h5_wechat_pay._apply_transaction(
        Conn(),
        {
            "out_trade_no": "WXP_APPLY_MOBILE",
            "trade_state": "SUCCESS",
            "amount": {"total": 990},
            "success_time": "2026-07-07T07:33:14Z",
        },
    )

    assert order["status"] == "paid"
    assert calls == ["project", "outbox", "event", "external_effect"]


def test_order_read_models_fallback_to_metadata_mobile_for_historical_orders() -> None:
    sidebar_source = (ROOT / "aicrm_next/customer_read_model/sidebar_v2.py").read_text(encoding="utf-8")
    transactions_source = (ROOT / "aicrm_next/commerce/admin_transactions.py").read_text(encoding="utf-8")
    detail_source = (ROOT / "aicrm_next/commerce/admin_transaction_detail.py").read_text(encoding="utf-8")

    assert "o.metadata_json #>> '{payer_identity,mobile}'" in sidebar_source
    assert "o.metadata_json #>> '{buyer_identity,mobile}'" in sidebar_source
    assert "metadata_json #>> '{{payer_identity,mobile}}'" in transactions_source
    assert "metadata_json #>> '{{buyer_identity,mobile}}'" in transactions_source
    assert "o.metadata_json #>> '{{payer_identity,mobile}}'" in detail_source
    assert "o.metadata_json #>> '{{buyer_identity,mobile}}'" in detail_source
