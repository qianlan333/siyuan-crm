from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from aicrm_next.commerce import admin_transactions
from wecom_ability_service.db import get_db
from wecom_ability_service.domains.admin_auth.auth_runtime import (
    ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY,
    ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY,
    ADMIN_SESSION_LOGIN_TYPE_KEY,
    ADMIN_SESSION_ROLE_LIST_KEY,
    ADMIN_SESSION_USER_ID_KEY,
)
from wecom_ability_service.domains.wechat_pay import repo as wechat_pay_repo
from wecom_ability_service.domains.wechat_pay import admin_service as wechat_pay_admin_service


REPO_ROOT = Path(__file__).resolve().parents[1]


def _login_admin(client, *, token: str = "test-admin-action-token") -> str:
    with client.session_transaction() as sess:
        sess[ADMIN_SESSION_USER_ID_KEY] = 0
        sess[ADMIN_SESSION_LOGIN_TYPE_KEY] = "break_glass"
        sess[ADMIN_SESSION_BREAK_GLASS_USERNAME_KEY] = "tester"
        sess[ADMIN_SESSION_ROLE_LIST_KEY] = ["super_admin"]
        sess[ADMIN_CONSOLE_ACTION_TOKEN_SESSION_KEY] = token
    return token


def _insert_order(
    *,
    out_trade_no: str,
    product_code: str = "assessment_report_v1",
    product_name: str = "AI 测评报告",
    amount_total: int = 9900,
    status: str = "paying",
    trade_state: str = "",
    transaction_id: str = "",
    refunded_amount_total: int = 0,
    mobile_snapshot: str = "13800000000",
    unionid: str = "unionid_test",
    external_userid: str = "wm_test",
    userid_snapshot: str = "zhangsan",
    payer_name_snapshot: str = "张三",
    created_at: str | None = None,
):
    order = wechat_pay_repo.insert_order(
        {
            "out_trade_no": out_trade_no,
            "product_code": product_code,
            "product_name": product_name,
            "description": product_name or product_code,
            "amount_total": amount_total,
            "payer_openid": "op_test",
            "unionid": unionid,
            "external_userid": external_userid,
            "userid_snapshot": userid_snapshot,
            "mobile_snapshot": mobile_snapshot,
            "payer_name_snapshot": payer_name_snapshot,
            "status": status,
            "metadata": {},
            "request_meta": {},
        }
    )
    get_db().execute(
        """
        UPDATE wechat_pay_orders
        SET trade_state = ?,
            transaction_id = ?,
            refunded_amount_total = ?,
            refund_status = CASE
                WHEN ? >= amount_total AND amount_total > 0 THEN 'full_refunded'
                WHEN ? > 0 THEN 'partial_refunded'
                ELSE ''
            END,
            created_at = COALESCE(?::timestamptz, created_at)
        WHERE id = ?
        """,
        (
            trade_state,
            transaction_id,
            refunded_amount_total,
            refunded_amount_total,
            refunded_amount_total,
            created_at,
            order["id"],
        ),
    )
    return wechat_pay_repo.get_admin_order_by_id(order["id"])


def test_wechat_pay_admin_backfills_empty_product_name(app):
    order = _insert_order(out_trade_no="WXP_EMPTY_PRODUCT", product_code="vip_course", product_name="")

    assert order["product_name"] == "vip_course"
    payload = wechat_pay_admin_service.list_orders(filters={"product_code": "vip_course"}, limit=20)
    assert payload["items"][0]["product_name"] == "vip_course"
    assert payload["items"][0]["product_label"] == "vip_course"


def test_wechat_pay_admin_transaction_template_hides_internal_filter_copy():
    source = (REPO_ROOT / "wecom_ability_service/templates/admin_console/wechat_pay_transactions.html").read_text(
        encoding="utf-8"
    )

    assert "mobile_snapshot / mobile" not in source
    assert "userid / external_userid" not in source
    assert "placeholder=\"transaction_id\"" not in source
    assert "row.product_code" not in source
    assert "{{ product.product_name }} / {{ product.product_code }}" not in source
    assert "导出文件包含订单创建时间、微信单号、手机号、unionid、商品名称、商品编码、金额和状态。" in source


def test_wechat_pay_admin_present_order_uses_operator_product_label():
    row = {
        "id": 1,
        "created_at": "2026-05-18 12:00:00",
        "transaction_id": "420000DISPLAY",
        "payer_name_snapshot": "张三",
        "mobile_snapshot": "13800000000",
        "userid_snapshot": "zhangsan",
        "external_userid": "wm_test",
        "product_code": "assessment_report_v1",
        "product_name": "AI 测评报告",
        "amount_total": 9900,
        "status": "paid",
        "trade_state": "SUCCESS",
    }

    presented = wechat_pay_admin_service._present_order(row)

    assert presented["product_label"] == "AI 测评报告"
    assert presented["product_code"] == "assessment_report_v1"


def test_wechat_pay_admin_repairs_utf8_mojibake_payer_name_snapshot():
    row = {
        "id": 1,
        "created_at": "2026-05-20 09:27:39",
        "transaction_id": "4200003131202605208651604176",
        "payer_name_snapshot": "æ›¾å¾·é’§",
        "mobile_snapshot": "18675597381",
        "userid_snapshot": "HuangYouCan",
        "external_userid": "",
        "product_code": "first_month_trial",
        "product_name": "黄小璨首月体验",
        "amount_total": 990,
        "status": "paid",
        "trade_state": "SUCCESS",
    }

    presented = wechat_pay_admin_service._present_order(row)

    assert presented["payer_name"] == "曾德钧"
    assert presented["identity"] == "曾德钧 / 18675597381 / HuangYouCan"


def test_wechat_pay_admin_product_filter(app, client):
    _login_admin(client)
    _insert_order(out_trade_no="WXP_PROD_A", product_code="assessment_report_v1", product_name="AI 测评报告")
    _insert_order(out_trade_no="WXP_PROD_B", product_code="vip_course", product_name="会员课程")

    response = client.get("/api/admin/wechat-pay/orders?product_code=vip_course&limit=20")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert [item["product_code"] for item in payload["items"]] == ["vip_course"]


def test_wechat_pay_admin_product_filter_accepts_current_code_for_aliased_orders(app, client):
    _login_admin(client)
    _insert_order(
        out_trade_no="WXP_ALIAS_PRODUCT",
        product_code="prd_20260518095708_9f77db",
        product_name="黄小璨首月体验",
        transaction_id="420000ALIASPRODUCT",
    )

    response = client.get("/api/admin/wechat-pay/orders?product_code=subscription_trial_month&limit=20")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert [item["product_code"] for item in payload["items"]] == ["subscription_trial_month"]


def test_wechat_pay_admin_status_mapping(app):
    _insert_order(out_trade_no="WXP_PENDING", status="paying")
    _insert_order(out_trade_no="WXP_PAID", status="paid", trade_state="SUCCESS", transaction_id="4200000001")
    _insert_order(out_trade_no="WXP_PARTIAL", status="paid", trade_state="SUCCESS", transaction_id="4200000002", refunded_amount_total=1000)
    _insert_order(out_trade_no="WXP_FULL", status="paid", trade_state="SUCCESS", transaction_id="4200000003", refunded_amount_total=9900)

    payload = wechat_pay_admin_service.list_orders(filters={}, limit=20)
    status_by_tx = {item["transaction_id"]: item["status_label"] for item in payload["items"]}

    assert "待支付" in [item["status_label"] for item in payload["items"]]
    assert status_by_tx["4200000001"] == "已支付"
    assert status_by_tx["4200000002"] == "部分退款"
    assert status_by_tx["4200000003"] == "全额退款"


def test_wechat_pay_admin_status_mapping_shows_refund_processing(app):
    order = _insert_order(
        out_trade_no="WXP_REFUNDING_STATUS",
        amount_total=990,
        status="paid",
        trade_state="SUCCESS",
        transaction_id="420000REFUNDINGSTATUS",
    )
    wechat_pay_repo.insert_refund_request(
        {
            "order_id": order["id"],
            "out_trade_no": "WXP_REFUNDING_STATUS",
            "transaction_id": "420000REFUNDINGSTATUS",
            "out_refund_no": "WXR_REFUNDING_STATUS",
            "reason": "客户主动申请退款",
            "refund_amount_total": 990,
            "order_amount_total": 990,
            "currency": "CNY",
            "requested_by": "tester",
            "request_payload": {},
        }
    )

    payload = wechat_pay_admin_service.list_orders(filters={"status": "refund_processing"}, limit=20)

    assert len(payload["items"]) == 1
    assert payload["items"][0]["status"] == "refund_processing"
    assert payload["items"][0]["status_label"] == "退款处理中"


def test_wechat_pay_admin_status_filters_align_with_presented_refund_status():
    cases = {
        "pending": [
            "COALESCE(refund_status, '') NOT IN ('partial_refunded', 'full_refunded')",
        ],
        "paid": [
            "COALESCE(refund_status, '') NOT IN ('partial_refunded', 'full_refunded')",
            "NOT EXISTS",
        ],
        "refund_processing": [
            "COALESCE(refund_status, '') <> 'full_refunded'",
            "NOT (COALESCE(refunded_amount_total, 0) >= amount_total AND amount_total > 0)",
        ],
        "partial_refunded": [
            "COALESCE(refund_status, '') = 'partial_refunded'",
            "NOT EXISTS",
        ],
        "full_refunded": [
            "COALESCE(refund_status, '') = 'full_refunded'",
        ],
    }

    for status, expected_fragments in cases.items():
        clauses = wechat_pay_repo._order_query_where({"status": status}, [])
        sql = " AND ".join(clauses)
        for fragment in expected_fragments:
            assert fragment in sql


def test_wechat_pay_admin_cursor_pagination(app, client):
    _login_admin(client)
    base = datetime(2026, 5, 16, 12, 0, 0)
    for index in range(21):
        _insert_order(
            out_trade_no=f"WXP_PAGE_{index:02d}",
            transaction_id=f"420000PAGE{index:02d}",
            created_at=(base - timedelta(minutes=index)).isoformat(),
        )

    first = client.get("/api/admin/wechat-pay/orders?limit=20").get_json()
    second = client.get(f"/api/admin/wechat-pay/orders?limit=20&cursor={first['next_cursor']}").get_json()

    assert first["ok"] is True
    assert len(first["items"]) == 20
    assert first["has_more"] is True
    assert second["ok"] is True
    assert len(second["items"]) == 1
    assert second["has_more"] is False


def test_wechat_pay_admin_displays_created_at_in_beijing_time(app):
    _insert_order(
        out_trade_no="WXP_TZ_DISPLAY",
        transaction_id="420000TZDISPLAY",
        created_at="2026-05-18T11:27:51+00:00",
    )

    payload = wechat_pay_admin_service.list_orders(filters={"transaction_id": "420000TZDISPLAY"}, limit=20)

    assert payload["items"][0]["created_at"] == "2026-05-18 19:27:51"


def test_wechat_pay_admin_export_job_saves_filters_json_and_exports_required_fields(app, client):
    token = _login_admin(client)
    _insert_order(
        out_trade_no="WXP_EXPORT",
        product_code="vip_course",
        product_name="会员课程",
        transaction_id="420000EXPORT",
        mobile_snapshot="13800138000",
        unionid="unionid_export",
        created_at="2026-05-18T12:00:00+08:00",
    )

    response = client.post(
        "/api/admin/wechat-pay/order-exports",
        json={
            "admin_action_token": token,
            "filters": {"product_code": "vip_course", "created_from": "2026-05-01T00:00", "created_to": "2026-05-31T23:59"},
            "scope": "filtered",
            "format": "csv",
            "limit": 20,
        },
    )

    assert response.status_code == 200
    job_id = response.get_json()["job"]["job_id"]
    row = get_db().execute(
        "SELECT job_id, filters_json, status FROM wechat_pay_order_export_jobs WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    assert row["filters_json"]["product_code"] == "vip_course"
    assert row["status"] == "succeeded"

    download = client.get(f"/api/admin/wechat-pay/order-exports/{job_id}/download")
    csv_text = download.data.decode("utf-8-sig")
    assert "客户身份" not in csv_text
    assert csv_text.splitlines()[0] == "订单创建时间,微信单号,手机号,unionid,商品名称,商品编码,金额,状态"
    assert "420000EXPORT,13800138000,unionid_export,会员课程,vip_course,99.00,待支付" in csv_text


def test_wechat_pay_admin_export_uses_current_code_for_aliased_product(app, client):
    token = _login_admin(client)
    _insert_order(
        out_trade_no="WXP_ALIAS_EXPORT",
        product_code="prd_20260601055439_3c4f56",
        product_name="黄小璨月度会员私教版",
        transaction_id="420000ALIASEXPORT",
        mobile_snapshot="13681984146",
        unionid="unionid_alias_export",
        amount_total=6900,
        created_at="2026-06-03T16:55:42+08:00",
    )

    response = client.post(
        "/api/admin/wechat-pay/order-exports",
        json={
            "admin_action_token": token,
            "filters": {
                "product_code": "premium_monthly_trial",
                "created_from": "2026-06-01T00:00",
                "created_to": "2026-06-30T23:59",
            },
            "scope": "filtered",
            "format": "csv",
            "limit": 20,
        },
    )

    assert response.status_code == 200
    job_id = response.get_json()["job"]["job_id"]
    download = client.get(f"/api/admin/wechat-pay/order-exports/{job_id}/download")
    csv_text = download.data.decode("utf-8-sig")
    assert "prd_20260601055439_3c4f56" not in csv_text
    assert "420000ALIASEXPORT,13681984146,unionid_alias_export,黄小璨月度会员私教版,premium_monthly_trial,69.00,待支付" in csv_text


def test_next_wechat_pay_export_csv_uses_required_fields(monkeypatch):
    def fake_list_orders(filters, *, limit, offset):
        return {
            "items": [
                {
                    "created_at": "2026-05-18 19:27:51",
                    "transaction_id": "420000NEXTEXPORT",
                    "mobile": "13800138001",
                    "unionid": "unionid_next_export",
                    "userid": "zhangsan",
                    "external_userid": "wm_next",
                    "product_name": "会员课程",
                    "product_code": "vip_course",
                    "amount_yuan": "99.00",
                    "status_label": "已支付",
                }
            ]
        }

    monkeypatch.setattr(admin_transactions, "list_wechat_admin_orders", fake_list_orders)

    csv_text = admin_transactions.export_orders_csv({"product_code": "vip_course"})

    assert "客户身份" not in csv_text
    assert csv_text.splitlines()[0] == "订单创建时间,微信单号,手机号,unionid,商品名称,商品编码,金额,状态"
    assert "420000NEXTEXPORT,13800138001,unionid_next_export,会员课程,vip_course,99.00,已支付" in csv_text


def test_next_wechat_pay_present_order_uses_current_code_for_alias():
    presented = admin_transactions._present_order(
        {
            "id": 1,
            "created_at": "2026-06-03 19:17:21",
            "transaction_id": "420000NEXTALIAS",
            "mobile_snapshot": "18108191098",
            "unionid": "unionid_next_alias",
            "product_name": "黄小璨首月体验",
            "product_code": "prd_20260518095708_9f77db",
            "amount_total": 990,
            "status": "paid",
            "trade_state": "SUCCESS",
        }
    )

    assert presented["product_code"] == "subscription_trial_month"


def test_wechat_pay_admin_list_does_not_return_refund_action(app, client):
    _login_admin(client)
    _insert_order(out_trade_no="WXP_NO_REFUND_ACTION", status="paid", trade_state="SUCCESS", transaction_id="420000REFUNDLESS")

    payload = client.get("/api/admin/wechat-pay/orders?limit=20").get_json()

    assert payload["ok"] is True
    assert "refund" not in payload["items"][0]
    assert "refund_url" not in payload["items"][0]


def test_wechat_pay_admin_refund_requires_transaction_id_confirmation(app, client):
    token = _login_admin(client)
    order = _insert_order(
        out_trade_no="WXP_REFUND_CONFIRM",
        status="paid",
        trade_state="SUCCESS",
        transaction_id="420000CONFIRM",
    )

    response = client.post(
        f"/api/admin/wechat-pay/orders/{order['id']}/refunds",
        json={
            "admin_action_token": token,
            "refund_amount_total": 1000,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "420000WRONG",
            "checked": True,
        },
    )

    assert response.status_code == 400
    assert "微信单号二次确认不匹配" in response.get_json()["error"]


def test_wechat_pay_admin_refund_calls_wechat_pay_and_updates_success(app, client, monkeypatch):
    token = _login_admin(client)
    order = _insert_order(
        out_trade_no="WXP_REFUND_REAL",
        status="paid",
        trade_state="SUCCESS",
        transaction_id="420000REALREFUND",
    )
    calls: dict[str, object] = {}

    class FakeClient:
        def create_refund(self, payload):
            calls["payload"] = payload
            return {
                "refund_id": "503000000020260516",
                "out_refund_no": payload["out_refund_no"],
                "transaction_id": payload["transaction_id"],
                "status": "SUCCESS",
                "amount": {"refund": payload["amount"]["refund"], "total": payload["amount"]["total"], "currency": "CNY"},
            }

    monkeypatch.setattr(wechat_pay_admin_service, "_create_wechat_pay_client", lambda: FakeClient())

    response = client.post(
        f"/api/admin/wechat-pay/orders/{order['id']}/refunds",
        json={
            "admin_action_token": token,
            "refund_amount_total": 1000,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "420000REALREFUND",
            "checked": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["refund"]["status"] == "SUCCESS"
    assert payload["order"]["refunded_amount_total"] == 1000
    assert calls["payload"]["transaction_id"] == "420000REALREFUND"
    assert calls["payload"]["amount"] == {"refund": 1000, "total": 9900, "currency": "CNY"}
    refund_row = get_db().execute(
        "SELECT status, refund_id, refund_amount_total FROM wechat_pay_refunds WHERE order_id = ?",
        (order["id"],),
    ).fetchone()
    assert dict(refund_row) == {
        "status": "SUCCESS",
        "refund_id": "503000000020260516",
        "refund_amount_total": 1000,
    }


def test_wechat_pay_admin_refund_processing_counts_as_in_flight_amount(app, client, monkeypatch):
    token = _login_admin(client)
    order = _insert_order(
        out_trade_no="WXP_REFUND_PROCESSING",
        status="paid",
        trade_state="SUCCESS",
        transaction_id="420000PROCESSING",
        amount_total=990,
    )

    class FakeClient:
        def create_refund(self, payload):
            return {
                "refund_id": "503000000020260518",
                "out_refund_no": payload["out_refund_no"],
                "transaction_id": payload["transaction_id"],
                "status": "PROCESSING",
                "amount": {"refund": payload["amount"]["refund"], "total": payload["amount"]["total"], "currency": "CNY"},
            }

    monkeypatch.setattr(wechat_pay_admin_service, "_create_wechat_pay_client", lambda: FakeClient())

    response = client.post(
        f"/api/admin/wechat-pay/orders/{order['id']}/refunds",
        json={
            "admin_action_token": token,
            "refund_amount_total": 990,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "420000PROCESSING",
            "checked": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["refund"]["status"] == "PROCESSING"
    assert payload["order"]["refunded_amount_total"] == 0
    assert payload["order"]["active_refund_amount_total"] == 990
    assert payload["order"]["refundable_amount_total"] == 0
    assert payload["order"]["can_refund"] is False


def test_wechat_pay_admin_refund_rejects_amount_over_order_total(app, client, monkeypatch):
    token = _login_admin(client)
    order = _insert_order(
        out_trade_no="WXP_REFUND_OVER_TOTAL",
        status="paid",
        trade_state="SUCCESS",
        transaction_id="420000OVERTOTAL",
        amount_total=990,
    )
    called = False

    class FakeClient:
        def create_refund(self, payload):
            nonlocal called
            called = True
            return {"status": "SUCCESS"}

    monkeypatch.setattr(wechat_pay_admin_service, "_create_wechat_pay_client", lambda: FakeClient())

    response = client.post(
        f"/api/admin/wechat-pay/orders/{order['id']}/refunds",
        json={
            "admin_action_token": token,
            "refund_amount_total": 9900,
            "reason": "客户主动申请退款",
            "transaction_id_confirmation": "420000OVERTOTAL",
            "checked": True,
        },
    )

    assert response.status_code == 400
    assert "累计退款金额不能超过订单金额" in response.get_json()["error"]
    assert called is False
