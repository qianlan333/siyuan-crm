#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.customer_pulse.access import build_customer_pulse_legacy_tenant_context
from wecom_ability_service.domains.customer_pulse.service import refresh_customer_pulse_cards
from wecom_ability_service.infra.settings import set_settings


_DEMO_EXTERNAL_USERIDS = (
    "wm_pulse_demo_reply",
    "wm_pulse_demo_stalled",
    "wm_pulse_demo_risk",
)
_DUAL_TENANT_EXTERNAL_USERIDS = (
    "wm_pulse_demo_tenant_a_reply",
    "wm_pulse_demo_tenant_a_stalled",
    "wm_pulse_demo_tenant_b_risk",
    "wm_pulse_demo_tenant_b_reminder",
)
_DEMO_PERSON_IDS = (9001, 9002, 9003)
_DUAL_TENANT_PERSON_IDS = (9101, 9102, 9201, 9202)
_DEMO_OWNER_USERIDS = ("sales_pulse_01", "sales_pulse_02", "sales_pulse_03")
_DUAL_TENANT_OWNER_USERIDS = ("sales_tenant_a_01", "sales_tenant_a_02", "sales_tenant_b_01", "sales_tenant_b_02")
_DEMO_MOBILES = ("13800139001", "13800139002", "13800139003")
_DUAL_TENANT_MOBILES = ("13800139101", "13800139102", "13800139201", "13800139202")
_ALL_DEMO_EXTERNAL_USERIDS = _DEMO_EXTERNAL_USERIDS + _DUAL_TENANT_EXTERNAL_USERIDS
_ALL_DEMO_PERSON_IDS = _DEMO_PERSON_IDS + _DUAL_TENANT_PERSON_IDS
_ALL_DEMO_MOBILES = _DEMO_MOBILES + _DUAL_TENANT_MOBILES


def _fmt(moment: datetime) -> str:
    return moment.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _create_app(database_path: str = ""):
    overrides: dict[str, object] = {
        "TESTING": True,
        "WECOM_CORP_ID": "ww-customer-pulse-demo",
        "ai_customer_pulse": True,
    }
    if database_path:
        overrides["DATABASE_PATH"] = database_path
    return create_app(overrides)


def _seed_owner(db, userid: str, display_name: str) -> None:
    db.execute(
        """
        INSERT OR IGNORE INTO owner_role_map (userid, display_name, role, active)
        VALUES (?, ?, 'sales', 1)
        """,
        (userid, display_name),
    )


def _table_exists(db, table_name: str) -> bool:
    row = db.execute(
        "SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _delete_where_in(db, table_name: str, column_name: str, values: tuple[object, ...]) -> None:
    if not values or not _table_exists(db, table_name):
        return
    placeholders = ",".join(["?"] * len(values))
    db.execute(
        f"DELETE FROM {table_name} WHERE {column_name} IN ({placeholders})",
        values,
    )


def _cleanup_demo_rows(db) -> None:
    for table_name in (
        "customer_pulse_metric_events",
        "customer_pulse_signal_events",
        "customer_pulse_snapshots",
        "customer_pulse_cards",
        "automation_reply_monitor_queue",
        "archived_messages",
        "contact_tags",
        "customer_value_segment_current",
        "customer_marketing_state_current",
        "wecom_external_contact_follow_users",
        "wecom_external_contact_identity_map",
        "external_contact_bindings",
        "contacts",
    ):
        _delete_where_in(db, table_name, "external_userid", _ALL_DEMO_EXTERNAL_USERIDS)

    _delete_where_in(db, "customer_marketing_state_current", "person_id", _ALL_DEMO_PERSON_IDS)
    _delete_where_in(db, "external_contact_bindings", "person_id", _ALL_DEMO_PERSON_IDS)
    _delete_where_in(db, "people", "id", _ALL_DEMO_PERSON_IDS)
    _delete_where_in(db, "people", "mobile", _ALL_DEMO_MOBILES)

    if _table_exists(db, "outbound_tasks"):
        for external_userid in _ALL_DEMO_EXTERNAL_USERIDS:
            db.execute(
                """
                DELETE FROM outbound_tasks
                WHERE request_payload LIKE ?
                   OR response_payload LIKE ?
                """,
                (f"%{external_userid}%", f"%{external_userid}%"),
            )


def _seed_customer(
    db,
    *,
    person_id: int,
    external_userid: str,
    customer_name: str,
    owner_userid: str,
    owner_display_name: str,
    mobile: str,
    now: datetime,
) -> None:
    _seed_owner(db, owner_userid, owner_display_name)
    db.execute(
        """
        INSERT OR REPLACE INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            customer_name,
            owner_userid,
            "Customer Pulse Demo",
            "demo seed",
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT OR REPLACE INTO people (id, mobile, third_party_user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            person_id,
            mobile,
            f"tp-{external_userid}",
            _fmt(now),
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT OR REPLACE INTO external_contact_bindings (
            external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            person_id,
            owner_userid,
            owner_userid,
            owner_userid,
            _fmt(now - timedelta(days=15)),
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT OR REPLACE INTO wecom_external_contact_identity_map (
            corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'active', '{}', ?, ?)
        """,
        (
            "ww-customer-pulse-demo",
            external_userid,
            f"union-{external_userid}",
            f"openid-{external_userid}",
            owner_userid,
            customer_name,
            _fmt(now),
            _fmt(now),
        ),
    )
    db.execute(
        """
        INSERT OR REPLACE INTO wecom_external_contact_follow_users (
            corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user, created_at, updated_at
        )
        VALUES (?, ?, ?, 'active', 1, '主跟进', ?, '{}', ?, ?)
        """,
        (
            "ww-customer-pulse-demo",
            external_userid,
            owner_userid,
            customer_name,
            _fmt(now),
            _fmt(now),
        ),
    )


def _seed_marketing_state(
    db,
    *,
    person_id: int,
    external_userid: str,
    now: datetime,
    main_stage: str,
    sub_stage: str,
    last_message_at: datetime,
    entered_at: datetime,
    updated_at: datetime,
    followup_segment: str,
) -> None:
    db.execute(
        """
        INSERT OR REPLACE INTO customer_marketing_state_current (
            person_id, external_userid, automation_key, main_stage, sub_stage, activated, converted,
            eligible_for_conversion, lifecycle_status, last_message_at, entered_at, state_payload_json, created_at, updated_at
        )
        VALUES (?, ?, 'signup_conversion_v1', ?, ?, 1, 0, 1, 'pool', ?, ?, ?, ?, ?)
        """,
        (
            person_id,
            external_userid,
            main_stage,
            sub_stage,
            _fmt(last_message_at),
            _fmt(entered_at),
            json.dumps({"followup_segment": followup_segment}, ensure_ascii=False),
            _fmt(now),
            _fmt(updated_at),
        ),
    )


def _seed_value_segment(db, *, external_userid: str, segment: str, score: int, now: datetime) -> None:
    db.execute(
        """
        INSERT OR REPLACE INTO customer_value_segment_current (
            external_userid, segment, score, evaluated_at, computed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            segment,
            score,
            _fmt(now),
            _fmt(now),
            _fmt(now),
            _fmt(now),
        ),
    )


def _seed_tag(db, *, external_userid: str, owner_userid: str, tag_id: str, tag_name: str, created_at: datetime) -> None:
    db.execute(
        """
        INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            owner_userid,
            tag_id,
            tag_name,
            _fmt(created_at),
        ),
    )


def _seed_message(
    db,
    *,
    msgid: str,
    seq: int,
    external_userid: str,
    owner_userid: str,
    sender: str,
    receiver: str,
    content: str,
    send_time: datetime,
) -> None:
    db.execute(
        """
        INSERT INTO archived_messages (
            seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, raw_payload, send_time, created_at
        )
        VALUES (?, ?, 'private', ?, ?, ?, ?, 'text', ?, '{}', ?, ?)
        """,
        (
            seq,
            msgid,
            external_userid,
            owner_userid,
            sender,
            receiver,
            content,
            _fmt(send_time),
            _fmt(send_time),
        ),
    )


def _seed_reply_queue(
    db,
    *,
    external_userid: str,
    owner_userid: str,
    last_inbound_at: datetime,
    not_before: datetime,
    summary: str,
) -> None:
    db.execute(
        """
        INSERT INTO automation_reply_monitor_queue (
            external_userid, owner_userid, status, message_ids_json, message_count,
            first_inbound_at, last_inbound_at, not_before, payload_snapshot_json, created_at, updated_at
        )
        VALUES (?, ?, 'pending', '["demo-msg-1"]', 1, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_userid,
            owner_userid,
            _fmt(last_inbound_at),
            _fmt(last_inbound_at),
            _fmt(not_before),
            json.dumps({"latest_inbound_summary": summary}, ensure_ascii=False),
            _fmt(last_inbound_at),
            _fmt(not_before),
        ),
    )


def seed_demo_data() -> dict[str, object]:
    db = get_db()
    now = datetime.now().replace(microsecond=0)
    _cleanup_demo_rows(db)

    _seed_customer(
        db,
        person_id=9001,
        external_userid="wm_pulse_demo_reply",
        customer_name="报价跟进客户",
        owner_userid="sales_pulse_01",
        owner_display_name="销售一",
        mobile="13800139001",
        now=now,
    )
    _seed_marketing_state(
        db,
        person_id=9001,
        external_userid="wm_pulse_demo_reply",
        now=now,
        main_stage="pool",
        sub_stage="active_focus",
        last_message_at=now - timedelta(minutes=8),
        entered_at=now - timedelta(days=1),
        updated_at=now - timedelta(minutes=5),
        followup_segment="normal",
    )
    _seed_value_segment(db, external_userid="wm_pulse_demo_reply", segment="top", score=5, now=now - timedelta(minutes=5))
    _seed_tag(
        db,
        external_userid="wm_pulse_demo_reply",
        owner_userid="sales_pulse_01",
        tag_id="tag-pulse-high-intent",
        tag_name="高意向",
        created_at=now - timedelta(minutes=6),
    )
    _seed_message(
        db,
        msgid="pulse-demo-reply-in-1",
        seq=90001,
        external_userid="wm_pulse_demo_reply",
        owner_userid="sales_pulse_01",
        sender="wm_pulse_demo_reply",
        receiver="sales_pulse_01",
        content="老师，课程怎么收费，能先给我一个区间吗？",
        send_time=now - timedelta(minutes=9),
    )
    _seed_message(
        db,
        msgid="pulse-demo-reply-out-1",
        seq=90002,
        external_userid="wm_pulse_demo_reply",
        owner_userid="sales_pulse_01",
        sender="sales_pulse_01",
        receiver="wm_pulse_demo_reply",
        content="可以，我先看一下你的情况。",
        send_time=now - timedelta(minutes=7),
    )
    _seed_reply_queue(
        db,
        external_userid="wm_pulse_demo_reply",
        owner_userid="sales_pulse_01",
        last_inbound_at=now - timedelta(minutes=9),
        not_before=now - timedelta(minutes=2),
        summary="客户在继续追问价格区间",
    )

    _seed_customer(
        db,
        person_id=9002,
        external_userid="wm_pulse_demo_stalled",
        customer_name="停滞推进客户",
        owner_userid="sales_pulse_02",
        owner_display_name="销售二",
        mobile="13800139002",
        now=now,
    )
    _seed_marketing_state(
        db,
        person_id=9002,
        external_userid="wm_pulse_demo_stalled",
        now=now,
        main_stage="pool",
        sub_stage="active_focus",
        last_message_at=now - timedelta(days=9),
        entered_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=8),
        followup_segment="normal",
    )
    _seed_value_segment(db, external_userid="wm_pulse_demo_stalled", segment="top", score=5, now=now - timedelta(days=8))
    _seed_message(
        db,
        msgid="pulse-demo-stalled-1",
        seq=90003,
        external_userid="wm_pulse_demo_stalled",
        owner_userid="sales_pulse_02",
        sender="wm_pulse_demo_stalled",
        receiver="sales_pulse_02",
        content="我先看看安排，下周再说。",
        send_time=now - timedelta(days=9),
    )

    _seed_customer(
        db,
        person_id=9003,
        external_userid="wm_pulse_demo_risk",
        customer_name="投诉风险客户",
        owner_userid="sales_pulse_03",
        owner_display_name="销售三",
        mobile="13800139003",
        now=now,
    )
    _seed_marketing_state(
        db,
        person_id=9003,
        external_userid="wm_pulse_demo_risk",
        now=now,
        main_stage="pool",
        sub_stage="active_focus",
        last_message_at=now - timedelta(minutes=40),
        entered_at=now - timedelta(days=2),
        updated_at=now - timedelta(minutes=30),
        followup_segment="focus",
    )
    _seed_value_segment(db, external_userid="wm_pulse_demo_risk", segment="core", score=4, now=now - timedelta(minutes=30))
    _seed_message(
        db,
        msgid="pulse-demo-risk-1",
        seq=90004,
        external_userid="wm_pulse_demo_risk",
        owner_userid="sales_pulse_03",
        sender="wm_pulse_demo_risk",
        receiver="sales_pulse_03",
        content="昨天说好的回电一直没人联系，我现在很不满意。",
        send_time=now - timedelta(minutes=42),
    )
    db.commit()

    refresh_result = refresh_customer_pulse_cards(
        external_userids=list(_DEMO_EXTERNAL_USERIDS),
        operator="customer_pulse_demo_seed",
        tenant_context=dict(
            build_customer_pulse_legacy_tenant_context(
            operator="customer_pulse_demo_seed",
            source="legacy_internal_demo_seed",
            )
        ),
    )
    return {
        "seeded_external_userids": list(_DEMO_EXTERNAL_USERIDS),
        "refresh_result": refresh_result,
    }


def seed_dual_tenant_demo_data() -> dict[str, object]:
    db = get_db()
    now = datetime.now().replace(microsecond=0)
    _cleanup_demo_rows(db)

    _seed_customer(
        db,
        person_id=9101,
        external_userid="wm_pulse_demo_tenant_a_reply",
        customer_name="A租户报价客户",
        owner_userid="sales_tenant_a_01",
        owner_display_name="A租户销售一",
        mobile="13800139101",
        now=now,
    )
    _seed_marketing_state(
        db,
        person_id=9101,
        external_userid="wm_pulse_demo_tenant_a_reply",
        now=now,
        main_stage="pool",
        sub_stage="active_focus",
        last_message_at=now - timedelta(minutes=18),
        entered_at=now - timedelta(days=2),
        updated_at=now - timedelta(minutes=15),
        followup_segment="normal",
    )
    _seed_value_segment(
        db,
        external_userid="wm_pulse_demo_tenant_a_reply",
        segment="top",
        score=5,
        now=now - timedelta(minutes=15),
    )
    _seed_tag(
        db,
        external_userid="wm_pulse_demo_tenant_a_reply",
        owner_userid="sales_tenant_a_01",
        tag_id="tag-tenant-a-high-intent",
        tag_name="高意向",
        created_at=now - timedelta(minutes=16),
    )
    _seed_message(
        db,
        msgid="pulse-tenant-a-reply-in-1",
        seq=91001,
        external_userid="wm_pulse_demo_tenant_a_reply",
        owner_userid="sales_tenant_a_01",
        sender="wm_pulse_demo_tenant_a_reply",
        receiver="sales_tenant_a_01",
        content="我今天能确定试听时间吗？顺便把价格区间发我一下。",
        send_time=now - timedelta(minutes=19),
    )
    _seed_reply_queue(
        db,
        external_userid="wm_pulse_demo_tenant_a_reply",
        owner_userid="sales_tenant_a_01",
        last_inbound_at=now - timedelta(minutes=19),
        not_before=now - timedelta(minutes=5),
        summary="A租户客户还在追问试听与价格",
    )

    _seed_customer(
        db,
        person_id=9102,
        external_userid="wm_pulse_demo_tenant_a_stalled",
        customer_name="A租户停滞客户",
        owner_userid="sales_tenant_a_02",
        owner_display_name="A租户销售二",
        mobile="13800139102",
        now=now,
    )
    _seed_marketing_state(
        db,
        person_id=9102,
        external_userid="wm_pulse_demo_tenant_a_stalled",
        now=now,
        main_stage="pool",
        sub_stage="active_focus",
        last_message_at=now - timedelta(days=11),
        entered_at=now - timedelta(days=12),
        updated_at=now - timedelta(days=10),
        followup_segment="normal",
    )
    _seed_value_segment(
        db,
        external_userid="wm_pulse_demo_tenant_a_stalled",
        segment="focus",
        score=4,
        now=now - timedelta(days=10),
    )
    _seed_message(
        db,
        msgid="pulse-tenant-a-stalled-1",
        seq=91002,
        external_userid="wm_pulse_demo_tenant_a_stalled",
        owner_userid="sales_tenant_a_02",
        sender="wm_pulse_demo_tenant_a_stalled",
        receiver="sales_tenant_a_02",
        content="我先和家里商量一下，过几天再联系。",
        send_time=now - timedelta(days=11),
    )

    _seed_customer(
        db,
        person_id=9201,
        external_userid="wm_pulse_demo_tenant_b_risk",
        customer_name="B租户投诉客户",
        owner_userid="sales_tenant_b_01",
        owner_display_name="B租户销售一",
        mobile="13800139201",
        now=now,
    )
    _seed_marketing_state(
        db,
        person_id=9201,
        external_userid="wm_pulse_demo_tenant_b_risk",
        now=now,
        main_stage="pool",
        sub_stage="active_focus",
        last_message_at=now - timedelta(minutes=55),
        entered_at=now - timedelta(days=3),
        updated_at=now - timedelta(minutes=48),
        followup_segment="focus",
    )
    _seed_value_segment(
        db,
        external_userid="wm_pulse_demo_tenant_b_risk",
        segment="core",
        score=4,
        now=now - timedelta(minutes=48),
    )
    _seed_message(
        db,
        msgid="pulse-tenant-b-risk-1",
        seq=92001,
        external_userid="wm_pulse_demo_tenant_b_risk",
        owner_userid="sales_tenant_b_01",
        sender="wm_pulse_demo_tenant_b_risk",
        receiver="sales_tenant_b_01",
        content="昨天答应我的回访一直没来，我现在非常不满意。",
        send_time=now - timedelta(minutes=56),
    )

    _seed_customer(
        db,
        person_id=9202,
        external_userid="wm_pulse_demo_tenant_b_reminder",
        customer_name="B租户待提醒客户",
        owner_userid="sales_tenant_b_02",
        owner_display_name="B租户销售二",
        mobile="13800139202",
        now=now,
    )
    _seed_marketing_state(
        db,
        person_id=9202,
        external_userid="wm_pulse_demo_tenant_b_reminder",
        now=now,
        main_stage="pool",
        sub_stage="active_normal",
        last_message_at=now - timedelta(days=6),
        entered_at=now - timedelta(days=8),
        updated_at=now - timedelta(days=6),
        followup_segment="normal",
    )
    _seed_value_segment(
        db,
        external_userid="wm_pulse_demo_tenant_b_reminder",
        segment="normal",
        score=3,
        now=now - timedelta(days=6),
    )
    _seed_message(
        db,
        msgid="pulse-tenant-b-reminder-1",
        seq=92002,
        external_userid="wm_pulse_demo_tenant_b_reminder",
        owner_userid="sales_tenant_b_02",
        sender="sales_tenant_b_02",
        receiver="wm_pulse_demo_tenant_b_reminder",
        content="上次方案你先看一下，我们周三再对齐。",
        send_time=now - timedelta(days=6),
    )
    db.commit()

    tenant_results = {
        "tenant-alpha": refresh_customer_pulse_cards(
            external_userids=[
                "wm_pulse_demo_tenant_a_reply",
                "wm_pulse_demo_tenant_a_stalled",
            ],
            operator="customer_pulse_dual_tenant_seed",
            tenant_key="tenant-alpha",
            allowed_owner_userids=["sales_tenant_a_01", "sales_tenant_a_02"],
        ),
        "tenant-beta": refresh_customer_pulse_cards(
            external_userids=[
                "wm_pulse_demo_tenant_b_risk",
                "wm_pulse_demo_tenant_b_reminder",
            ],
            operator="customer_pulse_dual_tenant_seed",
            tenant_key="tenant-beta",
            allowed_owner_userids=["sales_tenant_b_01", "sales_tenant_b_02"],
        ),
    }
    return {
        "mode": "dual_tenant",
        "seeded_external_userids": list(_DUAL_TENANT_EXTERNAL_USERIDS),
        "tenant_results": tenant_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed local/test demo data for Customer Pulse Inbox.")
    parser.add_argument("--database-path", default="", help="Optional sqlite DATABASE_PATH override")
    parser.add_argument("--init-db", action="store_true", help="Initialize database schema before seeding")
    parser.add_argument("--write-settings", action="store_true", help="Write recommended local settings into app_settings")
    parser.add_argument("--dual-tenant", action="store_true", help="Seed request-scoped dual-tenant demo data")
    args = parser.parse_args()

    app = _create_app(database_path=args.database_path)
    with app.app_context():
        if args.init_db:
            init_db()
        if args.write_settings:
            settings_payload = {
                "ai_customer_pulse": "true",
                "CUSTOMER_PULSE_HIGH_PRIORITY_THRESHOLD": "70",
                "CUSTOMER_PULSE_SHOW_LOW_CONFIDENCE_SUGGESTIONS": "true",
                "CUSTOMER_PULSE_ALLOWED_ACTION_TYPES": (
                    "generate_reply_draft,create_followup_task,update_followup_segment,update_tags,set_followup_reminder"
                ),
            }
            if args.dual_tenant:
                settings_payload.update(
                    {
                        "CUSTOMER_PULSE_TENANT_MODE": "request_scoped",
                        "CUSTOMER_PULSE_TENANT_ACCESS_POLICY_JSON": json.dumps(
                            {
                                "tenant-alpha": {
                                    "owner_userids": ["sales_tenant_a_01", "sales_tenant_a_02"],
                                    "member_userids": ["sales_tenant_a_01", "sales_tenant_a_02", "ops_tenant_a"],
                                    "viewer_roles": ["sales", "ops", "admin"],
                                    "operator_roles": ["sales", "ops", "admin"],
                                    "internal_roles": ["ops", "admin"],
                                },
                                "tenant-beta": {
                                    "owner_userids": ["sales_tenant_b_01", "sales_tenant_b_02"],
                                    "member_userids": ["sales_tenant_b_01", "sales_tenant_b_02", "ops_tenant_b"],
                                    "viewer_roles": ["sales", "ops", "admin"],
                                    "operator_roles": ["sales", "ops", "admin"],
                                    "internal_roles": ["ops", "admin"],
                                },
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "CUSTOMER_PULSE_FLAG_POLICY_JSON": json.dumps(
                            {
                                "default_enabled": False,
                                "tenants": {
                                    "tenant-alpha": {"enabled": True, "roles": {"sales": True, "ops": True, "admin": True}},
                                    "tenant-beta": {"enabled": True, "roles": {"sales": True, "ops": True, "admin": True}},
                                },
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                )
            else:
                settings_payload["CUSTOMER_PULSE_TENANT_MODE"] = "legacy_internal"
            set_settings(settings_payload)
        result = seed_dual_tenant_demo_data() if args.dual_tenant else seed_demo_data()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
