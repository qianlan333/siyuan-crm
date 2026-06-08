from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from aicrm_next.commerce import external_push_admin
from aicrm_next.main import create_app
from aicrm_next.public_product import h5_wechat_pay
from wecom_ability_service.db import get_db
from wecom_ability_service.domains.wechat_pay import product_service
from wecom_ability_service.domains.wechat_pay import repo as wechat_pay_repo


def _next_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "next-h5-external-push-outbox")
    monkeypatch.setenv("WECHAT_PAY_APP_ID", "wx-pay-app")
    monkeypatch.setenv("WECHAT_PAY_MCH_ID", "1900000001")
    monkeypatch.setenv("WECHAT_PAY_API_V3_KEY", "12345678901234567890123456789012")
    monkeypatch.setenv("WECHAT_PAY_PRIVATE_KEY_PATH", "/tmp/fake-wechat-pay-key.pem")
    monkeypatch.setenv("WECHAT_PAY_CERT_SERIAL_NO", "merchant-serial")
    return TestClient(create_app(), raise_server_exceptions=False)


def _create_product(**overrides) -> dict:
    payload = {
        "name": "Next H5 外推商品",
        "amount_total": 990,
        "status": "active",
        "require_mobile": False,
        "cta_text": "立即购买",
        "lead_program_id": None,
        "slices": [],
    }
    payload.update(overrides)
    return product_service.create_admin_product(payload, operator="pytest")


def _insert_order(product: dict, *, out_trade_no: str, status: str = "paying", trade_state: str = "") -> dict:
    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["name"],
            "amount_total": product["amount_total"],
            "payer_openid": "op_next_h5",
            "unionid": "unionid_next_h5",
            "external_userid": "wm_next_h5",
            "userid_snapshot": "tester",
            "mobile_snapshot": "13800000000",
            "payer_name_snapshot": "测试用户",
            "status": status,
            "metadata": {},
            "request_meta": {},
        }
    )
    if trade_state:
        get_db().execute("UPDATE wechat_pay_orders SET trade_state = ? WHERE id = ?", (trade_state, order["id"]))
    get_db().commit()
    return wechat_pay_repo.get_admin_order_by_id(order["id"])


def _success_transaction(out_trade_no: str, amount_total: int = 990) -> dict:
    return {
        "out_trade_no": out_trade_no,
        "transaction_id": "420000NEXTEXTERNALPUSH",
        "trade_state": "SUCCESS",
        "bank_type": "OTHERS",
        "success_time": "2026-06-05T02:54:47+08:00",
        "amount": {"total": amount_total, "payer_total": amount_total, "currency": "CNY"},
        "payer": {"openid": "op_next_h5"},
    }


def _outbox_rows(order_id: int) -> list[dict]:
    rows = get_db().execute(
        """
        SELECT *
        FROM domain_event_outbox
        WHERE tenant_id = 'aicrm'
          AND event_type = 'transaction.paid'
          AND aggregate_type = 'wechat_pay_order'
          AND aggregate_id = ?
        ORDER BY id ASC
        """,
        (str(order_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def test_next_h5_notify_marks_paid_and_writes_transaction_paid_outbox_once(app, monkeypatch):
    product = _create_product()
    order = _insert_order(product, out_trade_no="WXP_NEXT_NOTIFY_OUTBOX")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def verify_and_decrypt_notification(self, *, body, headers):
            assert body == '{"id":"notify-id"}'
            return _success_transaction("WXP_NEXT_NOTIFY_OUTBOX", product["amount_total"])

    monkeypatch.setattr(h5_wechat_pay, "WeChatPayClient", FakeClient)
    client = _next_client(monkeypatch)

    first = client.post("/api/h5/wechat-pay/notify", data='{"id":"notify-id"}', headers={"Content-Type": "application/json"})
    second = client.post("/api/h5/wechat-pay/notify", data='{"id":"notify-id"}', headers={"Content-Type": "application/json"})

    assert first.status_code == 200
    assert second.status_code == 200
    row = get_db().execute(
        "SELECT status, trade_state, transaction_id FROM wechat_pay_orders WHERE id = ?",
        (order["id"],),
    ).fetchone()
    assert dict(row) == {
        "status": "paid",
        "trade_state": "SUCCESS",
        "transaction_id": "420000NEXTEXTERNALPUSH",
    }
    rows = _outbox_rows(order["id"])
    assert len(rows) == 1
    assert rows[0]["payload"]["order_id"] == str(order["id"])
    assert rows[0]["payload"]["product_id"] == str(product["id"])
    assert rows[0]["payload"]["product_code"] == product["product_code"]
    assert rows[0]["payload"]["tenant_id"] == "aicrm"
    assert rows[0]["payload"]["buyer_id"] == "wm_next_h5"
    assert rows[0]["payload"]["paid_amount"] == 990
    assert rows[0]["payload"]["pay_channel"] == "wechat"


def test_next_h5_refresh_backfills_missing_outbox_for_already_paid_success_order(app, monkeypatch):
    product = _create_product()
    order = _insert_order(product, out_trade_no="WXP_NEXT_REFRESH_OUTBOX", status="paid", trade_state="SUCCESS")
    assert _outbox_rows(order["id"]) == []

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def query_order_by_out_trade_no(self, out_trade_no):
            assert out_trade_no == "WXP_NEXT_REFRESH_OUTBOX"
            return _success_transaction("WXP_NEXT_REFRESH_OUTBOX", product["amount_total"])

    monkeypatch.setattr(h5_wechat_pay, "WeChatPayClient", FakeClient)
    client = _next_client(monkeypatch)

    first = client.get("/api/h5/wechat-pay/orders/WXP_NEXT_REFRESH_OUTBOX?refresh=1")
    second = client.get("/api/h5/wechat-pay/orders/WXP_NEXT_REFRESH_OUTBOX?refresh=1")

    assert first.status_code == 200
    assert first.json()["order"]["status"] == "paid"
    assert second.status_code == 200
    rows = _outbox_rows(order["id"])
    assert len(rows) == 1
    assert rows[0]["payload"]["order_id"] == str(order["id"])


def test_next_product_external_push_api_get_and_real_test_push(app, monkeypatch):
    product = _create_product()
    client = _next_client(monkeypatch)

    empty = client.get(f"/api/admin/wechat-pay/products/{product['id']}/external-push")
    assert empty.status_code == 200
    assert empty.json()["config"]["enabled"] is False

    saved = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}/external-push",
        json={
            "enabled": True,
            "webhook_url": "https://example.com/test-hook",
            "push_type": "trial",
            "custom_params": {"source": "next-api-test"},
            "secret": "test-secret",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["config"]["enabled"] is True
    assert saved.json()["config"]["has_secret"] is True

    sent_payloads: list[dict] = []
    monkeypatch.setattr(external_push_admin, "resolve_and_validate_public_https_url", lambda url: url)

    def capture_post(*args, **kwargs):
        sent_payloads.append(json.loads(kwargs["data"].decode("utf-8")))
        return SimpleNamespace(status_code=200, text='{"ok":true}', is_redirect=False, headers={})

    monkeypatch.setattr(external_push_admin.requests, "post", capture_post)
    pushed = client.post(f"/api/admin/wechat-pay/products/{product['id']}/external-push/test")

    assert pushed.status_code == 200
    payload = pushed.json()
    assert payload["real_external_call_executed"] is True
    assert payload["result"]["delivery"]["status"] == "success"
    assert payload["result"]["delivery"]["event_type"] == "external_push.test"
    assert sent_payloads[0]["event"] == "external_push.test"
    delivery_count = get_db().execute(
        "SELECT COUNT(*) AS total FROM external_push_delivery WHERE product_id = ? AND event_type = 'external_push.test'",
        (product["id"],),
    ).fetchone()["total"]
    assert delivery_count == 1


def test_next_order_external_push_delivery_list_and_retry(app, monkeypatch):
    product = _create_product()
    order = _insert_order(product, out_trade_no="WXP_NEXT_DELIVERY_RETRY", status="paid", trade_state="SUCCESS")
    client = _next_client(monkeypatch)
    saved = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}/external-push",
        json={"enabled": True, "webhook_url": "https://example.com/retry-hook", "secret": "retry-secret"},
    )
    assert saved.status_code == 200
    config = get_db().execute(
        "SELECT * FROM external_push_config WHERE target_id = ? AND event_type = 'transaction.paid'",
        (str(product["id"]),),
    ).fetchone()
    delivery = get_db().execute(
        """
        INSERT INTO external_push_delivery (
            tenant_id, config_id, event_type, delivery_id, target_type, target_id,
            order_id, product_id, status, attempt_count, request_url, request_headers,
            request_body, response_status, response_body, error_message, next_retry_at,
            created_at, updated_at
        )
        VALUES ('aicrm', ?, 'transaction.paid', 'deliv_next_retry', 'product', ?, ?, ?, 'retrying', 1, ?, '{}'::jsonb, '{}'::jsonb, 500, 'failed', 'HTTP 500', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (config["id"], str(product["id"]), order["id"], product["id"], "https://example.com/retry-hook"),
    ).fetchone()
    get_db().commit()

    listed = client.get(f"/api/admin/wechat-pay/orders/{order['id']}/external-push-deliveries")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["delivery_id"] == delivery["delivery_id"]
    assert listed.json()["outbox"] == []

    monkeypatch.setattr(external_push_admin, "resolve_and_validate_public_https_url", lambda url: url)
    monkeypatch.setattr(
        external_push_admin.requests,
        "post",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, text="ok", is_redirect=False, headers={}),
    )
    retried = client.post(f"/api/admin/wechat-pay/orders/{order['id']}/external-push-deliveries/deliv_next_retry/retry")

    assert retried.status_code == 200
    assert retried.json()["real_external_call_executed"] is True
    assert retried.json()["result"]["delivery"]["status"] == "success"
    row = get_db().execute(
        "SELECT status, attempt_count, error_message FROM external_push_delivery WHERE delivery_id = 'deliv_next_retry'"
    ).fetchone()
    assert dict(row) == {"status": "success", "attempt_count": 2, "error_message": ""}
