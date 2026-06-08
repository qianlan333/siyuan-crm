from __future__ import annotations

import json

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.admin_auth.auth_runtime import (
    ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY,
    ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY,
    ADMIN_SESSION_LOGIN_TYPE_KEY,
    ADMIN_SESSION_ROLE_LIST_KEY,
    ADMIN_SESSION_USER_ID_KEY,
)
from wecom_ability_service.domains.alipay_pay import repo as alipay_repo
from wecom_ability_service.domains.alipay_pay import service as alipay_service


def _configure_alipay(app, tmp_path, *, enabled: str = "true") -> None:
    private_key = tmp_path / "alipay_app_private_key.pem"
    public_key = tmp_path / "alipay_public_key.pem"
    private_key.write_text("fake-private-key", encoding="utf-8")
    public_key.write_text("fake-public-key", encoding="utf-8")
    app.config.update(
        ALIPAY_ENABLED=enabled,
        ALIPAY_APP_ID="2026000000000001",
        ALIPAY_APP_PRIVATE_KEY_PATH=str(private_key),
        ALIPAY_PUBLIC_KEY_PATH=str(public_key),
        ALIPAY_SERVER_URL="https://openapi-sandbox.dl.alipaydev.com/gateway.do",
        ALIPAY_SIGN_TYPE="RSA2",
        ALIPAY_NOTIFY_URL="https://crm.example.com/api/h5/alipay/notify",
        ALIPAY_RETURN_URL="https://crm.example.com/api/h5/alipay/return",
        ALIPAY_TIMEOUT_EXPRESS="30m",
        WECHAT_PAY_PRODUCT_CATALOG_JSON=json.dumps(
            {
                "products": [
                    {
                        "product_code": "assessment_report_v1",
                        "name": "AI 测评报告",
                        "description": "AI 测评报告",
                        "amount_total": 9900,
                        "success_url": "/paid",
                        "require_mobile": True,
                        "cta_text": "立即报名",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )


def _login_admin(client, *, token: str = "test-admin-action-token") -> str:
    with client.session_transaction() as sess:
        sess[ADMIN_SESSION_USER_ID_KEY] = 0
        sess[ADMIN_SESSION_LOGIN_TYPE_KEY] = "break_glass"
        sess[ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY] = "tester"
        sess[ADMIN_SESSION_ROLE_LIST_KEY] = ["super_admin"]
        sess[ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY] = token
    return token


def _insert_order(*, out_trade_no: str, product_code: str = "assessment_report_v1", amount_total: int = 9900, status: str = "paying"):
    order = alipay_repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "product_code": product_code,
            "product_name": "AI 测评报告",
            "description": "AI 测评报告",
            "amount_total": amount_total,
            "status": status,
            "metadata": {},
            "request_meta": {},
            "mobile_snapshot": "13800138000",
        }
    )
    get_db().commit()
    return order


def _notify_payload(out_trade_no: str, *, trade_status: str = "TRADE_SUCCESS", total_amount: str = "99.00") -> dict[str, str]:
    return {
        "app_id": "2026000000000001",
        "sign_type": "RSA2",
        "sign": "signed",
        "out_trade_no": out_trade_no,
        "trade_no": "20260519" + out_trade_no[-12:],
        "trade_status": trade_status,
        "total_amount": total_amount,
        "buyer_id": "208800000000001",
        "buyer_logon_id": "buyer@example.com",
        "gmt_payment": "2026-05-19 12:00:00",
    }


def test_alipay_create_order_requires_complete_config(app, client, tmp_path):
    _configure_alipay(app, tmp_path)
    app.config["ALIPAY_APP_PRIVATE_KEY_PATH"] = ""

    response = client.post(
        "/api/h5/alipay/wap/orders",
        json={"product_code": "assessment_report_v1", "mobile": "13800138000"},
    )

    assert response.status_code == 503
    assert "ALIPAY_APP_PRIVATE_KEY_PATH" in response.get_json()["error"]


def test_alipay_create_order_rejects_unknown_product(app, client, tmp_path, monkeypatch):
    _configure_alipay(app, tmp_path)
    monkeypatch.setattr(alipay_service, "_create_alipay_pay_client", lambda: object())

    response = client.post("/api/h5/alipay/wap/orders", json={"product_code": "unknown"})

    assert response.status_code == 400
    assert response.get_json()["error"] == "product_not_configured"


def test_alipay_wap_order_uses_server_product_amount_and_inserts_order(app, client, tmp_path, monkeypatch):
    _configure_alipay(app, tmp_path)
    calls: dict[str, object] = {}

    class FakeClient:
        def create_wap_pay_url(self, *, biz_payload, notify_url, return_url):
            calls["biz_payload"] = biz_payload
            calls["notify_url"] = notify_url
            calls["return_url"] = return_url
            return "https://openapi.alipay.test/gateway.do?pay=1"

    monkeypatch.setattr(alipay_service, "_create_alipay_pay_client", lambda: FakeClient())

    response = client.post(
        "/api/h5/alipay/wap/orders",
        json={
            "product_code": "assessment_report_v1",
            "mobile": "13800138000",
            "amount_total": 1,
            "total_amount": "0.01",
            "client_order_ref": "client-ref-1",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["payment_url"].startswith("https://openapi.alipay.test/")
    assert payload["order"]["amount_total"] == 9900
    assert payload["order"]["out_trade_no"].startswith("ALP")
    assert calls["biz_payload"]["total_amount"] == "99.00"
    assert "amount_total" not in calls["biz_payload"]
    assert "product_code=assessment_report_v1" in calls["biz_payload"]["passback_params"]
    row = get_db().execute(
        "SELECT status, amount_total, mobile_snapshot FROM alipay_pay_orders WHERE out_trade_no = ?",
        (payload["order"]["out_trade_no"],),
    ).fetchone()
    assert dict(row) == {"status": "paying", "amount_total": 9900, "mobile_snapshot": "13800138000"}


def test_alipay_out_trade_no_is_unique_and_prefixed(app, client, tmp_path, monkeypatch):
    _configure_alipay(app, tmp_path)

    class FakeClient:
        def create_wap_pay_url(self, *, biz_payload, notify_url, return_url):
            return "https://openapi.alipay.test/gateway.do?out_trade_no=" + biz_payload["out_trade_no"]

    monkeypatch.setattr(alipay_service, "_create_alipay_pay_client", lambda: FakeClient())

    first = client.post("/api/h5/alipay/wap/orders", json={"product_code": "assessment_report_v1", "mobile": "13800138000"}).get_json()
    second = client.post("/api/h5/alipay/wap/orders", json={"product_code": "assessment_report_v1", "mobile": "13800138001"}).get_json()

    assert first["order"]["out_trade_no"].startswith("ALP")
    assert second["order"]["out_trade_no"].startswith("ALP")
    assert first["order"]["out_trade_no"] != second["order"]["out_trade_no"]


def test_alipay_notify_signature_failure_does_not_update_order(app, client, tmp_path, monkeypatch):
    _configure_alipay(app, tmp_path)
    _insert_order(out_trade_no="ALP_NOTIFY_BAD_SIGN")

    class FakeClient:
        def verify_notification(self, params):
            return False

    monkeypatch.setattr(alipay_service, "_create_alipay_pay_client", lambda: FakeClient())

    response = client.post("/api/h5/alipay/notify", data=_notify_payload("ALP_NOTIFY_BAD_SIGN"))

    assert response.status_code == 400
    row = get_db().execute(
        "SELECT status, trade_status, trade_no FROM alipay_pay_orders WHERE out_trade_no = ?",
        ("ALP_NOTIFY_BAD_SIGN",),
    ).fetchone()
    assert dict(row) == {"status": "paying", "trade_status": "", "trade_no": ""}


def test_alipay_notify_amount_mismatch_does_not_update_order(app, client, tmp_path, monkeypatch):
    _configure_alipay(app, tmp_path)
    _insert_order(out_trade_no="ALP_NOTIFY_BAD_AMOUNT")

    class FakeClient:
        def verify_notification(self, params):
            return True

    monkeypatch.setattr(alipay_service, "_create_alipay_pay_client", lambda: FakeClient())

    response = client.post(
        "/api/h5/alipay/notify",
        data=_notify_payload("ALP_NOTIFY_BAD_AMOUNT", total_amount="1.00"),
    )

    assert response.status_code == 400
    row = get_db().execute(
        "SELECT status, trade_status, trade_no FROM alipay_pay_orders WHERE out_trade_no = ?",
        ("ALP_NOTIFY_BAD_AMOUNT",),
    ).fetchone()
    assert dict(row) == {"status": "paying", "trade_status": "", "trade_no": ""}


def test_alipay_notify_success_and_finished_mark_paid(app, client, tmp_path, monkeypatch):
    _configure_alipay(app, tmp_path)
    _insert_order(out_trade_no="ALP_NOTIFY_SUCCESS")
    _insert_order(out_trade_no="ALP_NOTIFY_FINISHED")

    class FakeClient:
        def verify_notification(self, params):
            return True

    monkeypatch.setattr(alipay_service, "_create_alipay_pay_client", lambda: FakeClient())

    success = client.post("/api/h5/alipay/notify", data=_notify_payload("ALP_NOTIFY_SUCCESS", trade_status="TRADE_SUCCESS"))
    finished = client.post("/api/h5/alipay/notify", data=_notify_payload("ALP_NOTIFY_FINISHED", trade_status="TRADE_FINISHED"))

    assert success.status_code == 200
    assert finished.status_code == 200
    rows = get_db().execute(
        """
        SELECT out_trade_no, status, trade_status
        FROM alipay_pay_orders
        WHERE out_trade_no IN (?, ?)
        ORDER BY out_trade_no
        """,
        ("ALP_NOTIFY_FINISHED", "ALP_NOTIFY_SUCCESS"),
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {"out_trade_no": "ALP_NOTIFY_FINISHED", "status": "paid", "trade_status": "TRADE_FINISHED"},
        {"out_trade_no": "ALP_NOTIFY_SUCCESS", "status": "paid", "trade_status": "TRADE_SUCCESS"},
    ]


def test_alipay_return_does_not_mark_order_paid(app, client, tmp_path):
    _configure_alipay(app, tmp_path)
    _insert_order(out_trade_no="ALP_RETURN_ONLY")

    response = client.get(
        "/api/h5/alipay/return?out_trade_no=ALP_RETURN_ONLY&trade_no=20260519RETURN&trade_status=TRADE_SUCCESS"
    )

    assert response.status_code == 200
    row = get_db().execute(
        "SELECT status, trade_status, return_payload_json FROM alipay_pay_orders WHERE out_trade_no = ?",
        ("ALP_RETURN_ONLY",),
    ).fetchone()
    assert row["status"] == "paying"
    assert row["trade_status"] == ""
    assert row["return_payload_json"]["trade_status"] == "TRADE_SUCCESS"


def test_alipay_refresh_queries_trade_and_updates_status(app, client, tmp_path, monkeypatch):
    _configure_alipay(app, tmp_path)
    _insert_order(out_trade_no="ALP_REFRESH_PAID")
    calls: dict[str, object] = {}

    class FakeClient:
        def query_order(self, out_trade_no):
            calls["out_trade_no"] = out_trade_no
            return {
                "out_trade_no": out_trade_no,
                "trade_no": "20260519QUERY",
                "trade_status": "TRADE_SUCCESS",
                "total_amount": "99.00",
                "buyer_id": "208800000000001",
                "buyer_logon_id": "buyer@example.com",
                "send_pay_date": "2026-05-19 12:30:00",
            }

    monkeypatch.setattr(alipay_service, "_create_alipay_pay_client", lambda: FakeClient())

    payload = client.get("/api/h5/alipay/orders/ALP_REFRESH_PAID?refresh=1").get_json()

    assert payload["ok"] is True
    assert payload["order"]["status"] == "paid"
    assert payload["order"]["trade_status"] == "TRADE_SUCCESS"
    assert calls["out_trade_no"] == "ALP_REFRESH_PAID"


def test_alipay_paid_payload_returns_lead_qr(app, client, tmp_path):
    _configure_alipay(app, tmp_path)
    program = get_db().execute(
        """
        INSERT INTO automation_program (program_code, program_name, status, config_json)
        VALUES ('alipay_lead_plan_v1', '支付宝引流计划', 'active', '{}'::jsonb)
        RETURNING *
        """
    ).fetchone()
    channel = get_db().execute(
        """
        INSERT INTO automation_channel (
            program_id, channel_code, channel_name, qr_url, status
        )
        VALUES (?, 'program_alipay_lead_plan_v1', '默认渠道', 'https://example.com/alipay-qr.png', 'active')
        RETURNING *
        """,
        (program["id"],),
    ).fetchone()
    product = get_db().execute(
        """
        INSERT INTO wechat_pay_products (
            product_code, name, amount_total, status, enabled, cta_text, require_mobile, lead_program_id, lead_channel_id
        )
        VALUES ('alipay_course_v1', '支付宝小课', 9900, 'active', TRUE, '立即报名', FALSE, ?, ?)
        RETURNING *
        """,
        (program["id"], channel["id"]),
    ).fetchone()
    get_db().commit()
    order = _insert_order(out_trade_no="ALP_LEAD_QR", product_code=product["product_code"], status="paid")
    get_db().execute(
        "UPDATE alipay_pay_orders SET trade_status = 'TRADE_SUCCESS' WHERE out_trade_no = ?",
        (order["out_trade_no"],),
    )
    get_db().commit()

    payload = client.get(f"/api/h5/alipay/orders/{order['out_trade_no']}").get_json()

    assert payload["order"]["lead_qr"]["qr_url"] == "https://example.com/alipay-qr.png"


def test_alipay_pay_page_does_not_require_wechat_browser_or_openid(app, client, tmp_path):
    _configure_alipay(app, tmp_path)

    response = client.get("/alipay/pay/assessment_report_v1")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "WeixinJSBridge" not in html
    assert "openid_required" not in html
    assert "/api/h5/alipay/wap/orders" in html


def test_admin_alipay_transactions_filter_and_export(app, client, tmp_path):
    _configure_alipay(app, tmp_path)
    _login_admin(client)
    _insert_order(out_trade_no="ALP_ADMIN_A", product_code="assessment_report_v1")
    _insert_order(out_trade_no="ALP_ADMIN_B", product_code="other_product")

    response = client.get("/api/admin/alipay/orders?product_code=assessment_report_v1&limit=20")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert [item["out_trade_no"] for item in payload["items"]] == ["ALP_ADMIN_A"]

    exported = client.get("/api/admin/alipay/order-export.csv?product_code=assessment_report_v1")
    assert exported.status_code == 200
    csv_text = exported.get_data(as_text=True)
    assert "商户订单号" in csv_text
    assert "ALP_ADMIN_A" in csv_text
    assert "ALP_ADMIN_B" not in csv_text
