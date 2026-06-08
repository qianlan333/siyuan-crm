from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from wecom_ability_service.db import close_db, get_db
from wecom_ability_service.domains.wechat_pay.client import WeChatPayClient, WeChatPayClientConfig
from wecom_ability_service.domains.wechat_pay import repo as wechat_pay_repo
from wecom_ability_service.domains.wechat_pay import service as wechat_pay_service
from wecom_ability_service.http import wechat_pay as wechat_pay_http
from wecom_ability_service.infra.settings import mask_value


def _wechat_headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 MicroMessenger/8.0.50"}


def _configure_pay(app, tmp_path) -> None:
    private_key = tmp_path / "wechat_pay_apiclient_key.pem"
    platform_key = tmp_path / "wechat_pay_platform_public_key.pem"
    private_key.write_text("fake-private-key", encoding="utf-8")
    platform_key.write_text("fake-public-key", encoding="utf-8")
    app.config.update(
        WECHAT_MP_APP_ID="wx-mp-app",
        WECHAT_MP_APP_SECRET="mp-secret",
        WECHAT_PAY_ENABLED="true",
        WECHAT_PAY_APP_ID="wx-pay-app",
        WECHAT_PAY_MCH_ID="1900000001",
        WECHAT_PAY_API_V3_KEY="12345678901234567890123456789012",
        WECHAT_PAY_PRIVATE_KEY_PATH=str(private_key),
        WECHAT_PAY_CERT_SERIAL_NO="merchant-serial",
        WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH=str(platform_key),
        WECHAT_PAY_PRODUCT_CATALOG_JSON=json.dumps(
            {
                "products": [
                    {
                        "product_code": "assessment_report_v1",
                        "name": "AI 测评报告",
                        "description": "AI 测评报告",
                        "amount_total": 9900,
                        "success_url": "/paid",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )


def test_wechat_pay_sensitive_settings_are_masked():
    assert mask_value("WECHAT_PAY_API_V3_KEY", "12345678901234567890123456789012") == "123***12"
    assert mask_value("WECHAT_PAY_CERT_SERIAL_NO", "serial123456") == "ser***56"


def test_wechat_pay_client_sends_platform_public_key_id_header():
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    class FakeHttpClient:
        def request(self, method, url, *, data, headers):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

    pay_client = WeChatPayClient(
        WeChatPayClientConfig(
            app_id="wx-app",
            mch_id="1900000001",
            api_v3_key="12345678901234567890123456789012",
            private_key_path="",
            merchant_serial_no="merchant-serial",
            platform_serial_no="PUB_KEY_ID_0116571234562024052000123400000000",
        ),
        http_client=FakeHttpClient(),
    )
    pay_client._merchant_signature = lambda message: "signed"  # type: ignore[method-assign]

    pay_client.query_order_by_out_trade_no("WXPTEST0001")

    headers = captured["headers"]
    assert headers["Wechatpay-Serial"] == "PUB_KEY_ID_0116571234562024052000123400000000"


def test_wechat_pay_client_does_not_send_platform_certificate_serial_header():
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    class FakeHttpClient:
        def request(self, method, url, *, data, headers):
            captured["headers"] = headers
            return FakeResponse()

    pay_client = WeChatPayClient(
        WeChatPayClientConfig(
            app_id="wx-app",
            mch_id="1900000001",
            api_v3_key="12345678901234567890123456789012",
            private_key_path="",
            merchant_serial_no="merchant-serial",
            platform_serial_no="19FBBF2A24A3F3C97F5925FA855A850D6E4624AF",
        ),
        http_client=FakeHttpClient(),
    )
    pay_client._merchant_signature = lambda message: "signed"  # type: ignore[method-assign]

    pay_client.query_order_by_out_trade_no("WXPTEST0001")

    assert "Wechatpay-Serial" not in captured["headers"]


def test_wechat_pay_client_creates_refund_request():
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = '{"status":"SUCCESS","refund_id":"503000000020260516"}'

        def json(self):
            return {"status": "SUCCESS", "refund_id": "503000000020260516"}

    class FakeHttpClient:
        def request(self, method, url, *, data, headers):
            captured["method"] = method
            captured["url"] = url
            captured["data"] = data.decode("utf-8")
            captured["headers"] = headers
            return FakeResponse()

    pay_client = WeChatPayClient(
        WeChatPayClientConfig(
            app_id="wx-app",
            mch_id="1900000001",
            api_v3_key="12345678901234567890123456789012",
            private_key_path="",
            merchant_serial_no="merchant-serial",
        ),
        http_client=FakeHttpClient(),
    )
    pay_client._merchant_signature = lambda message: "signed"  # type: ignore[method-assign]

    result = pay_client.create_refund(
        {
            "transaction_id": "420000REALREFUND",
            "out_refund_no": "WXRTEST0001",
            "reason": "客户主动申请退款",
            "amount": {"refund": 1000, "total": 9900, "currency": "CNY"},
        }
    )

    assert result["status"] == "SUCCESS"
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v3/refund/domestic/refunds")
    assert json.loads(captured["data"])["out_refund_no"] == "WXRTEST0001"


def test_wechat_pay_client_verifies_notify_signature_with_platform_certificate(tmp_path):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "WeChat Pay Test"),
            x509.NameAttribute(NameOID.COMMON_NAME, "wechatpay.test"),
        ]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(1234567890)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(private_key, hashes.SHA256())
    )
    certificate_path = tmp_path / "wechatpay_platform_cert.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))

    body = '{"id":"notify-id"}'
    timestamp = "1778888888"
    nonce = "notify-nonce"
    message = f"{timestamp}\n{nonce}\n{body}\n".encode("utf-8")
    signature = base64.b64encode(
        private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    ).decode("ascii")

    pay_client = WeChatPayClient(
        WeChatPayClientConfig(
            app_id="wx-app",
            mch_id="1900000001",
            api_v3_key="12345678901234567890123456789012",
            private_key_path="",
            merchant_serial_no="merchant-serial",
            platform_public_key_path=str(certificate_path),
            platform_serial_no="1234567890",
        )
    )

    pay_client.verify_notification_signature(
        body=body,
        headers={
            "Wechatpay-Timestamp": timestamp,
            "Wechatpay-Nonce": nonce,
            "Wechatpay-Signature": signature,
            "Wechatpay-Serial": "1234567890",
        },
    )


def test_wechat_pay_oauth_requests_userinfo_by_default(app, client, tmp_path):
    _configure_pay(app, tmp_path)

    response = client.get(
        "/api/h5/wechat-pay/oauth/start?return_url=/pay/assessment_report_v1",
        headers=_wechat_headers(),
    )

    assert response.status_code == 302
    assert "scope=snsapi_userinfo" in response.headers["Location"]


def test_wechat_pay_oauth_start_unconfigured_returns_readable_html(app, client):
    app.config.update(WECHAT_MP_APP_ID="", WECHAT_MP_APP_SECRET="", SECRET_KEY="")

    response = client.get(
        "/api/h5/wechat-pay/oauth/start?return_url=/pay/assessment_report_v1",
        headers=_wechat_headers(),
    )

    assert response.status_code == 501
    assert response.content_type.startswith("text/html")
    assert "当前微信授权配置未完成，请联系管理员" in response.get_data(as_text=True)
    assert '{"ok":' not in response.get_data(as_text=True)


def test_wechat_pay_oauth_callback_missing_code_returns_readable_html(app, client, tmp_path):
    _configure_pay(app, tmp_path)

    response = client.get(
        "/api/h5/wechat-pay/oauth/callback",
        headers=_wechat_headers(),
    )

    assert response.status_code == 400
    assert response.content_type.startswith("text/html")
    assert "授权未完成，请重新进入商品页" in response.get_data(as_text=True)
    assert '{"ok":' not in response.get_data(as_text=True)


def test_wechat_pay_oauth_callback_stores_payer_name(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)

    monkeypatch.setattr(
        wechat_pay_http,
        "exchange_wechat_oauth_code",
        lambda **kwargs: {"openid": "op_test", "access_token": "token"},
    )
    monkeypatch.setattr(
        wechat_pay_http,
        "fetch_wechat_userinfo",
        lambda **kwargs: {"openid": "op_test", "unionid": "un_test", "nickname": "微信昵称"},
    )

    response = client.get("/api/h5/wechat-pay/oauth/callback?code=code", headers=_wechat_headers())

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["wechat_pay_h5_identity"] == {
            "openid": "op_test",
            "unionid": "un_test",
            "payer_name": "微信昵称",
        }


def test_create_jsapi_order_uses_session_openid_and_server_catalog(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    calls: dict[str, object] = {}

    class FakeClient:
        def create_jsapi_transaction(self, payload):
            calls["transaction_payload"] = payload
            return {"prepay_id": "wx-prepay-id"}

        def build_jsapi_pay_params(self, prepay_id):
            calls["prepay_id"] = prepay_id
            return {
                "appId": "wx-pay-app",
                "timeStamp": "1710000000",
                "nonceStr": "nonce",
                "package": f"prepay_id={prepay_id}",
                "signType": "RSA",
                "paySign": "signed",
            }

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_test", "unionid": "un_test", "payer_name": "微信昵称"}

    response = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={"product_code": "assessment_report_v1"},
        headers=_wechat_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["order"]["amount_total"] == 9900
    assert payload["order"]["status"] == "paying"
    assert payload["pay_params"]["package"] == "prepay_id=wx-prepay-id"
    assert calls["transaction_payload"]["payer"]["openid"] == "op_test"
    assert calls["transaction_payload"]["amount"]["total"] == 9900
    assert json.loads(calls["transaction_payload"]["attach"])["product_code"] == "assessment_report_v1"

    close_db()
    row = get_db().execute(
        "SELECT * FROM wechat_pay_orders WHERE out_trade_no = ?",
        (payload["order"]["out_trade_no"],),
    ).fetchone()
    assert row["status"] == "paying"
    assert row["prepay_id"] == "wx-prepay-id"
    assert row["payer_openid"] == "op_test"
    assert row["payer_name_snapshot"] == "微信昵称"

    status_response = client.get(
        f"/api/h5/wechat-pay/orders/{payload['order']['out_trade_no']}",
        headers=_wechat_headers(),
    )
    assert status_response.status_code == 200
    assert status_response.get_json()["order"]["out_trade_no"] == payload["order"]["out_trade_no"]


def test_create_jsapi_order_repairs_stale_mojibake_payer_name(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)

    class FakeClient:
        def create_jsapi_transaction(self, payload):
            return {"prepay_id": "wx-prepay-id"}

        def build_jsapi_pay_params(self, prepay_id):
            return {
                "appId": "wx-pay-app",
                "timeStamp": "1710000000",
                "nonceStr": "nonce",
                "package": f"prepay_id={prepay_id}",
                "signType": "RSA",
                "paySign": "signed",
            }

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_test", "payer_name": "æ›¾å¾·é’§"}

    response = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={"product_code": "assessment_report_v1"},
        headers=_wechat_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    close_db()
    row = get_db().execute(
        "SELECT payer_name_snapshot FROM wechat_pay_orders WHERE out_trade_no = ?",
        (payload["order"]["out_trade_no"],),
    ).fetchone()
    assert row["payer_name_snapshot"] == "曾德钧"


def test_create_jsapi_order_rejects_unknown_product(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: object())
    with client.session_transaction() as sess:
        sess["wechat_pay_h5_identity"] = {"openid": "op_test", "payer_name": "微信昵称"}

    response = client.post(
        "/api/h5/wechat-pay/jsapi/orders",
        json={"product_code": "unknown"},
        headers=_wechat_headers(),
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "product_not_configured"


def test_wechat_pay_notify_marks_order_paid_and_records_event(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": "WXPTEST0001",
            "product_code": "assessment_report_v1",
            "product_name": "AI 测评报告",
            "description": "AI 测评报告",
            "amount_total": 9900,
            "payer_openid": "op_test",
            "status": "paying",
            "success_url": "/paid",
            "metadata": {},
            "request_meta": {},
        }
    )
    assert order["out_trade_no"] == "WXPTEST0001"

    class FakeClient:
        def verify_and_decrypt_notification(self, *, body, headers):
            assert body == '{"id":"notify-id"}'
            return {
                "out_trade_no": "WXPTEST0001",
                "transaction_id": "420000000020260516",
                "trade_state": "SUCCESS",
                "bank_type": "OTHERS",
                "success_time": "2026-05-16T12:00:00+08:00",
                "amount": {"total": 9900, "payer_total": 9900},
                "payer": {"openid": "op_test"},
            }

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())

    response = client.post(
        "/api/h5/wechat-pay/notify",
        data='{"id":"notify-id"}',
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.get_json()["code"] == "SUCCESS"
    row = get_db().execute(
        "SELECT status, trade_state, transaction_id FROM wechat_pay_orders WHERE out_trade_no = ?",
        ("WXPTEST0001",),
    ).fetchone()
    assert dict(row) == {
        "status": "paid",
        "trade_state": "SUCCESS",
        "transaction_id": "420000000020260516",
    }
    event_count = get_db().execute(
        "SELECT COUNT(*) AS total FROM wechat_pay_order_events WHERE out_trade_no = ? AND event_type = 'notify'",
        ("WXPTEST0001",),
    ).fetchone()["total"]
    assert event_count == 1


def test_wechat_pay_notify_recovers_missing_paid_order(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)

    class FakeClient:
        def verify_and_decrypt_notification(self, *, body, headers):
            assert body == '{"id":"notify-id"}'
            return {
                "out_trade_no": "WXP_MISSING_NOTIFY",
                "transaction_id": "420000MISSINGNOTIFY",
                "trade_state": "SUCCESS",
                "bank_type": "OTHERS",
                "description": "AI 测评报告",
                "success_time": "2026-05-18T19:06:14+08:00",
                "amount": {"total": 9900, "payer_total": 9900, "currency": "CNY"},
                "payer": {"openid": "op_missing"},
            }

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())

    response = client.post(
        "/api/h5/wechat-pay/notify",
        data='{"id":"notify-id"}',
        content_type="application/json",
    )

    assert response.status_code == 200
    row = get_db().execute(
        """
        SELECT status, trade_state, transaction_id, product_code, product_name, amount_total
        FROM wechat_pay_orders
        WHERE out_trade_no = ?
        """,
        ("WXP_MISSING_NOTIFY",),
    ).fetchone()
    assert dict(row) == {
        "status": "paid",
        "trade_state": "SUCCESS",
        "transaction_id": "420000MISSINGNOTIFY",
        "product_code": "assessment_report_v1",
        "product_name": "AI 测评报告",
        "amount_total": 9900,
    }


def test_wechat_pay_status_refresh_recovers_missing_paid_order(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)

    class FakeClient:
        def query_order_by_out_trade_no(self, out_trade_no):
            assert out_trade_no == "WXP_MISSING_QUERY"
            return {
                "out_trade_no": "WXP_MISSING_QUERY",
                "transaction_id": "420000MISSINGQUERY",
                "trade_state": "SUCCESS",
                "bank_type": "OTHERS",
                "description": "AI 测评报告",
                "success_time": "2026-05-18T19:06:14+08:00",
                "amount": {"total": 9900, "payer_total": 9900, "currency": "CNY"},
                "payer": {"openid": "op_missing"},
            }

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())

    response = client.get(
        "/api/h5/wechat-pay/orders/WXP_MISSING_QUERY?refresh=1",
        headers=_wechat_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["order"]["out_trade_no"] == "WXP_MISSING_QUERY"
    assert payload["order"]["status"] == "paid"
    row = get_db().execute(
        "SELECT transaction_id, product_name FROM wechat_pay_orders WHERE out_trade_no = ?",
        ("WXP_MISSING_QUERY",),
    ).fetchone()
    assert dict(row) == {"transaction_id": "420000MISSINGQUERY", "product_name": "AI 测评报告"}


def test_wechat_pay_status_refresh_enriches_existing_recovered_order(app, client, tmp_path, monkeypatch):
    _configure_pay(app, tmp_path)
    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": "WXP260518110609ABCDEF",
            "order_source": "recovered_query",
            "product_code": "recovered_wechat_pay",
            "product_name": "微信支付恢复订单",
            "description": "微信支付恢复订单",
            "amount_total": 9900,
            "payer_openid": "op_missing",
            "status": "paid",
            "metadata": {"recovered": True},
            "request_meta": {},
        }
    )

    class FakeClient:
        def query_order_by_out_trade_no(self, out_trade_no):
            assert out_trade_no == order["out_trade_no"]
            return {
                "out_trade_no": order["out_trade_no"],
                "transaction_id": "420000RECOVEREDENRICH",
                "trade_state": "SUCCESS",
                "bank_type": "OTHERS",
                "success_time": "2026-05-18T19:06:14+08:00",
                "amount": {"total": 9900, "payer_total": 9900, "currency": "CNY"},
                "payer": {"openid": "op_missing"},
            }

    monkeypatch.setattr(wechat_pay_service, "_create_wechat_pay_client", lambda: FakeClient())

    response = client.get(
        f"/api/h5/wechat-pay/orders/{order['out_trade_no']}?refresh=1",
        headers=_wechat_headers(),
    )

    assert response.status_code == 200
    row = get_db().execute(
        """
        SELECT product_code, product_name, transaction_id, created_at
        FROM wechat_pay_orders
        WHERE out_trade_no = ?
        """,
        (order["out_trade_no"],),
    ).fetchone()
    assert row["product_code"] == "assessment_report_v1"
    assert row["product_name"] == "AI 测评报告"
    assert row["transaction_id"] == "420000RECOVEREDENRICH"
    assert row["created_at"].strftime("%Y-%m-%d %H:%M:%S") == "2026-05-18 11:06:09"
