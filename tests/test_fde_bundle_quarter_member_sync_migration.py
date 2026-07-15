from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
import os

import psycopg
from psycopg.rows import dict_row


MIGRATION = import_module("migrations.versions.0112_sync_fde_bundle_quarter_members")


def _insert_product(conn, *, code: str, name: str, amount_total: int) -> int:
    return conn.execute(
        """
        INSERT INTO wechat_pay_products (
            product_code, name, amount_total, status, enabled
        ) VALUES (%s, %s, %s, 'active', TRUE)
        RETURNING id
        """,
        (code, name, amount_total),
    ).fetchone()["id"]


def _insert_paid_order(
    conn,
    *,
    out_trade_no: str,
    unionid: str,
    external_userid: str,
    paid_at: str,
    payer_name: str,
    refunded_amount_total: int = 0,
) -> int:
    conn.execute(
        """
        INSERT INTO crm_user_identity (unionid, primary_external_userid, customer_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (unionid) DO UPDATE SET
            primary_external_userid = EXCLUDED.primary_external_userid,
            customer_name = EXCLUDED.customer_name
        """,
        (unionid, external_userid, payer_name),
    )
    return conn.execute(
        """
        INSERT INTO wechat_pay_orders (
            out_trade_no, transaction_id, product_code, product_name,
            amount_total, currency, unionid, payer_name_snapshot,
            status, trade_state, paid_at, refunded_amount_total
        ) VALUES (
            %s, %s, %s, '浸泡+实战 打包·第一期',
            199900, 'CNY', %s, %s,
            'paid', 'SUCCESS', %s::timestamptz, %s
        )
        RETURNING id
        """,
        (
            out_trade_no,
            f"wx-{out_trade_no}",
            MIGRATION.SOURCE_PRODUCT_CODE,
            unionid,
            payer_name,
            paid_at,
            refunded_amount_total,
        ),
    ).fetchone()["id"]


def test_sync_uses_first_paid_at_for_exact_90_day_entitlements_and_is_idempotent(next_pg_schema) -> None:
    del next_pg_schema
    database_url = os.environ.get("DATABASE_URL", "")
    assert database_url
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        target_trade_product_id = _insert_product(
            conn,
            code=MIGRATION.TARGET_PRODUCT_CODE,
            name=MIGRATION.TARGET_PRODUCT_NAME,
            amount_total=99900,
        )
        _insert_product(
            conn,
            code=MIGRATION.SOURCE_PRODUCT_CODE,
            name="浸泡+实战 打包·第一期",
            amount_total=199900,
        )
        service_product_id = conn.execute(
            """
            INSERT INTO service_period_products (
                trade_product_id, link_slug, membership_config_id,
                membership_config_name, duration_days
            ) VALUES (%s, 'ces', 'default_service_period_membership', '默认会员设置', 90)
            RETURNING id
            """,
            (target_trade_product_id,),
        ).fetchone()["id"]

        existing_order_id = _insert_paid_order(
            conn,
            out_trade_no="WXP_FDE_EXISTING",
            unionid="union_fde_existing",
            external_userid="wm_fde_existing",
            paid_at="2026-06-29T22:18:13+08:00",
            payer_name="大黑",
        )
        _insert_paid_order(
            conn,
            out_trade_no="WXP_FDE_NEW",
            unionid="union_fde_new",
            external_userid="wm_fde_new",
            paid_at="2026-06-30T15:26:41+08:00",
            payer_name="Shirley",
        )
        _insert_paid_order(
            conn,
            out_trade_no="WXP_FDE_LATER_DUPLICATE",
            unionid="union_fde_new",
            external_userid="wm_fde_new",
            paid_at="2026-07-01T10:00:00+08:00",
            payer_name="Shirley",
        )
        _insert_paid_order(
            conn,
            out_trade_no="WXP_FDE_REFUNDED",
            unionid="union_fde_refunded",
            external_userid="wm_fde_refunded",
            paid_at="2026-07-01T11:00:00+08:00",
            payer_name="Refunded",
            refunded_amount_total=199900,
        )
        original_start = datetime(2026, 6, 14, tzinfo=timezone.utc)
        original_end = datetime(2026, 8, 1, tzinfo=timezone.utc)
        existing_entitlement_id = conn.execute(
            """
            INSERT INTO service_period_entitlements (
                service_product_id, trade_product_id, unionid,
                external_userid_snapshot, membership_config_id,
                status, start_at, end_at, last_order_id,
                last_out_trade_no, renewal_count, metadata_json
            ) VALUES (
                %s, %s, 'union_fde_existing', 'wm_fde_existing',
                'default_service_period_membership', 'active', %s, %s,
                NULL, '', 3, '{"admin_remark":"找不到"}'::jsonb
            )
            RETURNING id
            """,
            (service_product_id, target_trade_product_id, original_start, original_end),
        ).fetchone()["id"]
        conn.execute(MIGRATION._SYNC_SQL)
        conn.commit()

        members = conn.execute(
            """
            SELECT id, unionid, start_at, end_at, last_order_id,
                   last_out_trade_no, renewal_count, metadata_json
            FROM service_period_entitlements
            WHERE service_product_id = %s
            ORDER BY unionid
            """,
            (service_product_id,),
        ).fetchall()
        events = conn.execute(
            """
            SELECT unionid, event_type, duration_days,
                   before_start_at, before_end_at, after_start_at, after_end_at,
                   payload_json
            FROM service_period_events
            WHERE payload_json ->> 'migration' = %s
            ORDER BY unionid
            """,
            (MIGRATION.MIGRATION_KEY,),
        ).fetchall()

        assert len(members) == 2
        assert members[0]["id"] == existing_entitlement_id
        assert members[0]["last_order_id"] == existing_order_id
        assert members[0]["start_at"] == datetime.fromisoformat("2026-06-29T22:18:13+08:00")
        assert members[0]["end_at"] == datetime.fromisoformat("2026-09-27T22:18:13+08:00")
        assert members[0]["renewal_count"] == 3
        assert members[0]["metadata_json"]["admin_remark"] == "找不到"
        assert members[1]["start_at"] == datetime.fromisoformat("2026-06-30T15:26:41+08:00")
        assert members[1]["end_at"] == datetime.fromisoformat("2026-09-28T15:26:41+08:00")
        assert members[1]["last_out_trade_no"] == "WXP_FDE_NEW"
        assert len(events) == 2
        assert {event["event_type"] for event in events} == {"admin_adjusted"}
        assert {event["duration_days"] for event in events} == {90}
        assert events[0]["payload_json"]["created_entitlement"] is False
        assert events[1]["payload_json"]["created_entitlement"] is True

        before_second_run = conn.execute(
            """
            SELECT id, updated_at FROM service_period_entitlements
            WHERE service_product_id = %s ORDER BY id
            """,
            (service_product_id,),
        ).fetchall()
        conn.execute(MIGRATION._SYNC_SQL)
        conn.commit()
        after_second_run = conn.execute(
            """
            SELECT id, updated_at FROM service_period_entitlements
            WHERE service_product_id = %s ORDER BY id
            """,
            (service_product_id,),
        ).fetchall()
        assert after_second_run == before_second_run
        assert conn.execute(
            "SELECT count(*) AS total FROM service_period_events WHERE payload_json ->> 'migration' = %s",
            (MIGRATION.MIGRATION_KEY,),
        ).fetchone()["total"] == 2

        conn.execute(MIGRATION._ROLLBACK_SQL)
        conn.commit()
        restored = conn.execute(
            """
            SELECT id, start_at, end_at, last_order_id, last_out_trade_no,
                   renewal_count, metadata_json
            FROM service_period_entitlements
            WHERE service_product_id = %s
            """,
            (service_product_id,),
        ).fetchall()
        assert restored == [
            {
                "id": existing_entitlement_id,
                "start_at": original_start,
                "end_at": original_end,
                "last_order_id": None,
                "last_out_trade_no": "",
                "renewal_count": 3,
                "metadata_json": {"admin_remark": "找不到"},
            }
        ]
        assert conn.execute(
            "SELECT count(*) AS total FROM service_period_events WHERE payload_json ->> 'migration' = %s",
            (MIGRATION.MIGRATION_KEY,),
        ).fetchone()["total"] == 0
