from __future__ import annotations

from datetime import datetime, timedelta

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


def test_wechat_pay_admin_product_filter(app, client):
    _login_admin(client)
    _insert_order(out_trade_no="WXP_PROD_A", product_code="assessment_report_v1", product_name="AI 测评报告")
    _insert_order(out_trade_no="WXP_PROD_B", product_code="vip_course", product_name="会员课程")

    response = client.get("/api/admin/wechat-pay/orders?product_code=vip_course&limit=20")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert [item["product_code"] for item in payload["items"]] == ["vip_course"]


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


def test_wechat_pay_admin_export_job_saves_filters_json(app, client):
    token = _login_admin(client)
    _insert_order(out_trade_no="WXP_EXPORT", product_code="vip_course", product_name="会员课程")

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
