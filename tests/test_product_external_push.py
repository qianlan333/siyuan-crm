from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.admin_auth.auth_runtime import (
    ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY,
    ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY,
    ADMIN_SESSION_LOGIN_TYPE_KEY,
    ADMIN_SESSION_ROLE_LIST_KEY,
    ADMIN_SESSION_USER_ID_KEY,
)
from wecom_ability_service.domains.external_push import repo as external_push_repo
from wecom_ability_service.domains.external_push import security as external_push_security
from wecom_ability_service.domains.external_push import service as external_push_service
from wecom_ability_service.domains.wechat_pay import product_service
from wecom_ability_service.domains.wechat_pay import repo as wechat_pay_repo
from wecom_ability_service.domains.wechat_pay import service as wechat_pay_service


def _login_admin(client, *, token: str = "test-admin-action-token") -> str:
    with client.session_transaction() as sess:
        sess[ADMIN_SESSION_USER_ID_KEY] = 0
        sess[ADMIN_SESSION_LOGIN_TYPE_KEY] = "break_glass"
        sess[ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY] = "tester"
        sess[ADMIN_SESSION_ROLE_LIST_KEY] = ["super_admin"]
        sess[ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY] = token
    return token


def _public_dns(monkeypatch, ip: str = "93.184.216.34") -> None:
    monkeypatch.setattr(
        external_push_security.socket,
        "getaddrinfo",
        lambda host, port, type=None: [(external_push_security.socket.AF_INET, external_push_security.socket.SOCK_STREAM, 6, "", (ip, port))],
    )


def _create_product(**overrides) -> dict:
    payload = {
        "name": "外推测试商品",
        "amount_total": 9900,
        "status": "active",
        "require_mobile": False,
        "cta_text": "立即购买",
        "lead_program_id": None,
        "slices": [],
    }
    payload.update(overrides)
    return product_service.create_admin_product(payload, operator="pytest")


def _insert_order(
    product: dict,
    *,
    out_trade_no: str = "WXP_PUSH_TEST",
    status: str = "paying",
    unionid: str = "unionid_product_push",
) -> dict:
    return wechat_pay_repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "product_code": product["product_code"],
            "product_name": product["name"],
            "description": product["name"],
            "amount_total": product["amount_total"],
            "payer_openid": "openid_product_push",
            "unionid": unionid,
            "external_userid": "wm_product_push",
            "userid_snapshot": "tester",
            "mobile_snapshot": "13800000000",
            "payer_name_snapshot": "测试用户",
            "status": status,
            "metadata": {},
            "request_meta": {},
        }
    )


def _success_transaction(order: dict) -> dict:
    return {
        "out_trade_no": order["out_trade_no"],
        "transaction_id": "420000PRODUCTPUSH",
        "trade_state": "SUCCESS",
        "bank_type": "OTHERS",
        "success_time": "2026-05-30T10:00:00+08:00",
        "amount": {"total": order["amount_total"], "payer_total": order["amount_total"], "currency": "CNY"},
        "payer": {"openid": "openid_product_push"},
    }


def _response(status_code: int, text: str):
    return SimpleNamespace(status_code=status_code, text=text, is_redirect=False, headers={})


def test_external_push_payload_includes_empty_buyer_unionid_when_missing():
    payload = external_push_service.build_external_push_payload(
        "transaction.paid",
        {
            "id": 7,
            "out_trade_no": "WXP_NO_UNIONID",
            "amount_total": 9900,
            "payer_total": 9900,
            "paid_at": "2026-05-30T10:00:00+08:00",
            "payer_openid": "openid_product_push",
            "mobile_snapshot": "13800000000",
        },
        {"id": 3, "product_code": "prd_no_unionid", "name": "无 unionid 商品", "amount_total": 9900},
        {},
        delivery_id="deliv_no_unionid",
    )

    assert payload["buyer"]["unionid"] == ""


def test_product_external_push_config_api_validates_and_saves(app, client, monkeypatch):
    token = _login_admin(client)
    product = _create_product()
    _public_dns(monkeypatch)

    missing = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}/external-push",
        json={"admin_action_token": token, "enabled": True, "webhook_url": ""},
    )
    assert missing.status_code == 400
    assert "required" in missing.json["error"]

    non_https = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}/external-push",
        json={"admin_action_token": token, "enabled": True, "webhook_url": "http://example.com/hook"},
    )
    assert non_https.status_code == 400
    assert "https" in non_https.json["error"]

    private_host = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}/external-push",
        json={"admin_action_token": token, "enabled": True, "webhook_url": "https://127.0.0.1/hook"},
    )
    assert private_host.status_code == 400

    saved = client.put(
        f"/api/admin/wechat-pay/products/{product['id']}/external-push",
        json={
            "admin_action_token": token,
            "enabled": True,
            "webhook_url": "https://example.com/hook",
            "push_type": "paid_notify",
            "expires_at_ts": 1893456000,
            "day": 7,
            "frequency": 1,
            "remark": "用户购买后通知外部系统",
            "custom_params": {"source": "ai-crm"},
            "secret": "webhook-secret",
        },
    )
    assert saved.status_code == 200
    assert saved.json["config"]["enabled"] is True
    assert saved.json["config"]["webhook_url"] == "https://example.com/hook"
    assert "secret" not in saved.json["config"]
    assert saved.json["config"]["has_secret"] is True

    fetched = client.get(f"/api/admin/wechat-pay/products/{product['id']}/external-push")
    assert fetched.status_code == 200
    assert fetched.json["config"]["custom_params"] == {"source": "ai-crm"}

    missing_product = client.put(
        "/api/admin/wechat-pay/products/999999/external-push",
        json={"admin_action_token": token, "enabled": False},
    )
    assert missing_product.status_code == 404


def test_webhook_url_security_rejects_private_and_dns_private(monkeypatch):
    _public_dns(monkeypatch)
    assert external_push_security.resolve_and_validate_public_https_url("https://example.com/foo") == "https://example.com/foo"

    for url in [
        "http://example.com/foo",
        "https://localhost/foo",
        "https://127.0.0.1/foo",
        "https://192.168.1.1/foo",
    ]:
        with pytest.raises(external_push_security.WebhookUrlValidationError):
            external_push_security.resolve_and_validate_public_https_url(url)

    _public_dns(monkeypatch, ip="10.0.0.8")
    with pytest.raises(external_push_security.WebhookUrlValidationError):
        external_push_security.resolve_and_validate_public_https_url("https://example.com/foo")


def test_paid_transition_writes_outbox_once(app):
    product = _create_product()
    order = _insert_order(product)

    wechat_pay_service._apply_transaction(_success_transaction(order), event_type="notify")
    wechat_pay_service._apply_transaction(_success_transaction(order), event_type="notify")

    rows = get_db().execute("SELECT * FROM domain_event_outbox WHERE event_type = 'transaction.paid'").fetchall()
    assert len(rows) == 1
    assert rows[0]["aggregate_type"] == "wechat_pay_order"
    assert rows[0]["payload"]["order_id"] == str(order["id"])


def test_external_push_worker_success_failure_skip_and_dedupe(app, monkeypatch):
    product = _create_product()
    get_db().execute("UPDATE wechat_pay_products SET product_code = ? WHERE id = ?", ("subscription_trial_month", product["id"]))
    get_db().commit()
    product["product_code"] = "subscription_trial_month"
    order = _insert_order(product)
    _public_dns(monkeypatch)

    outbox = external_push_service.enqueue_transaction_paid_event(order)
    result = external_push_service.process_transaction_paid_outbox(outbox)
    assert result["skipped"] is True
    assert result["reason"] == "config_not_found"
    skipped_outbox = get_db().execute("SELECT status FROM domain_event_outbox WHERE id = ?", (outbox["id"],)).fetchone()
    assert skipped_outbox["status"] == "skipped"

    external_push_service.save_product_external_push_config(
        product["id"],
        {
            "enabled": True,
            "webhook_url": "https://example.com/hook",
            "push_type": "premium",
            "day": 31,
            "frequency": 3,
            "remark": "69元1个月续费",
            "custom_params": {"source": "ai-crm"},
            "secret": "secret",
        },
        operator="pytest",
    )
    outbox = external_push_repo.insert_outbox_event(
        tenant_id="aicrm",
        event_type="transaction.paid",
        aggregate_type="wechat_pay_order",
        aggregate_id=str(order["id"]),
        payload={"order_id": str(order["id"])},
    )
    assert outbox is None
    outbox_row = get_db().execute("SELECT * FROM domain_event_outbox WHERE aggregate_id = ?", (str(order["id"]),)).fetchone()
    get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET status = 'paid', trade_state = 'SUCCESS', paid_at = ?
        WHERE id = ?
        """,
        ("2026-06-01T07:30:10+00:00", order["id"]),
    )
    get_db().execute("UPDATE domain_event_outbox SET status = 'pending' WHERE id = ?", (outbox_row["id"],))
    get_db().commit()

    sent_payloads = []

    def capture_success_post(*args, **kwargs):
        sent_payloads.append(json.loads(kwargs["data"].decode("utf-8")))
        return _response(200, '{"ok":true}')

    monkeypatch.setattr(external_push_service.requests, "post", capture_success_post)
    result = external_push_service.process_transaction_paid_outbox(dict(outbox_row))
    assert result["ok"] is True
    delivery = get_db().execute("SELECT * FROM external_push_delivery WHERE order_id = ?", (order["id"],)).fetchone()
    assert delivery["status"] == "success"
    assert delivery["attempt_count"] == 1
    assert sent_payloads[0] == {
        "phone_number": "13800000000",
        "type": "premium",
        "day": 31,
        "frequency": 3,
        "remark": "69元1个月续费",
        "submitted_at": "2026-06-01T15:30:10+08:00",
        "questionnaire_title": "微信支付开通黄小璨会员",
        "delivery_id": delivery["delivery_id"],
        "event": "transaction.paid",
        "order": {
            "id": str(order["id"]),
            "status": "paid",
            "paid_at": "2026-06-01T07:30:10Z",
            "order_no": "WXP_PUSH_TEST",
            "paid_amount": 9900,
            "pay_channel": "wechat",
            "out_trade_no": "WXP_PUSH_TEST",
        },
        "product": {
            "id": str(product["id"]),
            "code": product["product_code"],
            "name": "外推测试商品",
            "price": 9900,
        },
        "buyer": {
            "id": "wm_product_push",
            "openid": "open***push",
            "unionid": "unionid_product_push",
            "phone": "13800000000",
        },
    }
    assert delivery["request_body"]["event"] == "transaction.paid"
    assert delivery["request_body"]["phone_number"] == "138****0000"
    assert delivery["request_body"]["submitted_at"] == "2026-06-01T15:30:10+08:00"
    assert delivery["request_body"]["buyer"]["unionid"] == "unio***push"
    assert delivery["request_body"]["buyer"]["phone"] == "138****0000"
    assert "config" not in delivery["request_body"]
    assert "tenant" not in delivery["request_body"]
    assert delivery["request_headers"]["X-AICRM-Signature"].startswith("sha256=")

    deduped = external_push_service.process_transaction_paid_outbox(dict(outbox_row))
    assert deduped["deduped"] is True
    assert get_db().execute("SELECT COUNT(*) AS count FROM external_push_delivery WHERE order_id = ?", (order["id"],)).fetchone()["count"] == 1

    alias_order = _insert_order(product, out_trade_no="WXP_PUSH_ALIAS")
    get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET status = 'paid',
            trade_state = 'SUCCESS',
            product_code = 'prd_20260518095708_9f77db',
            paid_at = ?
        WHERE id = ?
        """,
        ("2026-06-01T08:30:10+00:00", alias_order["id"]),
    )
    get_db().commit()
    alias_outbox = external_push_service.enqueue_transaction_paid_event(
        dict(get_db().execute("SELECT * FROM wechat_pay_orders WHERE id = ?", (alias_order["id"],)).fetchone())
    )
    monkeypatch.setattr(external_push_service.requests, "post", capture_success_post)
    alias_result = external_push_service.process_transaction_paid_outbox(alias_outbox)
    alias_delivery = get_db().execute("SELECT * FROM external_push_delivery WHERE order_id = ?", (alias_order["id"],)).fetchone()
    assert alias_result["ok"] is True
    assert alias_delivery["status"] == "success"
    assert alias_delivery["product_id"] == product["id"]

    product_failed = _create_product(name="失败外推商品")
    order_failed = _insert_order(product_failed, out_trade_no="WXP_PUSH_FAILED")
    external_push_service.save_product_external_push_config(
        product_failed["id"],
        {"enabled": True, "webhook_url": "https://example.com/fail"},
        operator="pytest",
    )
    failed_outbox = external_push_service.enqueue_transaction_paid_event(order_failed)
    monkeypatch.setattr(external_push_service.requests, "post", lambda *args, **kwargs: _response(500, "x" * 9000))
    failed = external_push_service.process_transaction_paid_outbox(failed_outbox)
    failed_delivery = failed["delivery"]
    assert failed_delivery["status"] == "retrying"
    assert failed_delivery["response_status"] == 500
    assert len(failed_delivery["response_body"].encode("utf-8")) <= external_push_service.MAX_BODY_BYTES
    assert failed_delivery["next_retry_at"]
    assert failed_delivery["request_body"]["phone_number"] == "138****0000"
    assert failed_delivery["request_body"]["buyer"]["phone"] == "138****0000"
    assert failed_delivery["request_body"]["buyer"]["unionid"] == "unio***push"

    retried_payloads = []

    def capture_retry_success_post(*args, **kwargs):
        retried_payloads.append(json.loads(kwargs["data"].decode("utf-8")))
        return _response(200, '{"ok":true}')

    monkeypatch.setattr(external_push_service.requests, "post", capture_retry_success_post)
    retried = external_push_service.send_webhook_delivery(failed_delivery["delivery_id"])
    assert retried["ok"] is True
    assert retried_payloads[0]["phone_number"] == "13800000000"
    assert retried_payloads[0]["buyer"]["phone"] == "13800000000"
    assert retried_payloads[0]["buyer"]["unionid"] == "unionid_product_push"

    product_disabled = _create_product(name="停用外推商品")
    order_disabled = _insert_order(product_disabled, out_trade_no="WXP_PUSH_DISABLED")
    external_push_service.save_product_external_push_config(
        product_disabled["id"],
        {"enabled": False, "webhook_url": "https://example.com/disabled"},
        operator="pytest",
    )
    skipped = external_push_service.process_transaction_paid_outbox(external_push_service.enqueue_transaction_paid_event(order_disabled))
    assert skipped["reason"] == "config_disabled"

    product_expired = _create_product(name="过期外推商品")
    order_expired = _insert_order(product_expired, out_trade_no="WXP_PUSH_EXPIRED")
    external_push_service.save_product_external_push_config(
        product_expired["id"],
        {"enabled": True, "webhook_url": "https://example.com/expired", "expires_at_ts": 1},
        operator="pytest",
    )
    expired = external_push_service.process_transaction_paid_outbox(external_push_service.enqueue_transaction_paid_event(order_expired))
    assert expired["reason"] == "config_expired"

    product_invalid_url = _create_product(name="非法 URL 外推商品")
    order_invalid_url = _insert_order(product_invalid_url, out_trade_no="WXP_PUSH_INVALID_URL")
    invalid_config = get_db().execute(
        """
        INSERT INTO external_push_config (
            tenant_id, target_type, target_id, event_type, enabled, webhook_url,
            created_at, updated_at
        )
        VALUES ('aicrm', 'product', ?, 'transaction.paid', TRUE, 'http://127.0.0.1/hook', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (str(product_invalid_url["id"]),),
    ).fetchone()
    get_db().commit()
    external_push_service.enqueue_transaction_paid_event(order_invalid_url)
    invalid_result = external_push_service.run_due_external_push_events(limit=10)
    invalid_delivery = get_db().execute(
        "SELECT * FROM external_push_delivery WHERE config_id = ? AND order_id = ?",
        (invalid_config["id"], order_invalid_url["id"]),
    ).fetchone()
    assert invalid_result["ok"] is True
    assert invalid_delivery is not None
    assert invalid_delivery["status"] == "retrying"
    assert "https" in invalid_delivery["error_message"]


def test_signature_and_retry_api(app, client, monkeypatch):
    token = _login_admin(client)
    product = _create_product()
    order = _insert_order(product)
    _public_dns(monkeypatch)

    external_push_service.save_product_external_push_config(
        product["id"],
        {"enabled": True, "webhook_url": "https://example.com/retry", "secret": "retry-secret"},
        operator="pytest",
    )
    stored_config = external_push_repo.get_product_config(product["id"]) or {}
    first_sig = external_push_service.sign_webhook_payload("retry-secret", "1778888888", '{"a":1}')
    assert first_sig == external_push_service.sign_webhook_payload("retry-secret", "1778888888", '{"a":1}')
    assert first_sig != external_push_service.sign_webhook_payload("retry-secret", "1778888888", '{"a":2}')

    delivery = external_push_repo.create_delivery_once(
        {
            "tenant_id": "aicrm",
            "config_id": stored_config["id"],
            "event_type": "transaction.paid",
            "delivery_id": external_push_repo.generate_delivery_id(),
            "target_type": "product",
            "target_id": str(product["id"]),
            "order_id": order["id"],
            "product_id": product["id"],
            "request_url": "https://example.com/retry",
        }
    )
    next_retry_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    external_push_repo.update_delivery_result(
        delivery["delivery_id"],
        status="retrying",
        attempt_count=1,
        request_url="https://example.com/retry",
        request_headers={},
        request_body={},
        response_status=500,
        response_body="failed",
        error_message="HTTP 500",
        next_retry_at=next_retry_at,
    )

    listed = client.get(f"/api/admin/wechat-pay/orders/{order['id']}/external-push-deliveries")
    assert listed.status_code == 200
    assert listed.json["items"][0]["delivery_id"] == delivery["delivery_id"]

    monkeypatch.setattr(external_push_service.requests, "post", lambda *args, **kwargs: _response(200, "ok"))
    retry = client.post(
        f"/api/admin/wechat-pay/orders/{order['id']}/external-push-deliveries/{delivery['delivery_id']}/retry",
        json={"admin_action_token": token},
    )
    assert retry.status_code == 200
    assert retry.json["result"]["delivery"]["status"] == "success"

    repeat = client.post(
        f"/api/admin/wechat-pay/orders/{order['id']}/external-push-deliveries/{delivery['delivery_id']}/retry",
        json={"admin_action_token": token},
    )
    assert repeat.status_code == 400
