from __future__ import annotations

from aicrm_next.channel_entry.identity_bridge import ensure_external_contact_identity_for_sidebar
from aicrm_next.channel_entry.application import process_wecom_external_contact_event
from aicrm_next.channel_entry.schemas import ProcessWeComExternalContactEventCommand
from aicrm_next.channel_entry.wecom_adapter import get_wecom_adapter, set_wecom_adapter
from aicrm_next.shared.postgres_connection import get_db
from scripts.run_identity_mobile_bridge_backfill import run_backfill


class DetailAdapter:
    def get_external_contact_detail(self, external_userid: str):
        return {
            "errcode": 0,
            "errmsg": "ok",
            "external_contact": {
                "external_userid": external_userid,
                "unionid": "union_bridge_001",
                "openid": "openid_bridge_001",
                "name": "桥接客户",
                "type": 1,
            },
            "follow_user": [
                {
                    "userid": "owner_bridge",
                    "remark": "桥接备注",
                    "description": "",
                    "state": "",
                    "createtime": 1780640000,
                }
            ],
        }


def test_next_external_contact_callback_syncs_identity_and_binds_orphan_mobile(app, monkeypatch):
    monkeypatch.setattr(
        "aicrm_next.channel_entry.application.process_channel_entry",
        lambda command: {"handled": False, "reason": "channel_entry_not_under_test"},
    )
    previous_adapter = get_wecom_adapter()
    set_wecom_adapter(DetailAdapter())
    try:
        with app.app_context():
            db = get_db()
            db.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("wm_bridge_001", "桥接客户", "owner_bridge", "桥接备注", ""),
            )
            db.execute(
                """
                INSERT INTO wechat_pay_orders (
                    out_trade_no, product_code, product_name, amount_total, currency,
                    payer_openid, unionid, external_userid, mobile_snapshot, status, trade_state,
                    transaction_id, paid_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::timestamptz, ?::timestamptz)
                """,
                (
                    "WXP_BRIDGE_001",
                    "subscription_trial_month",
                    "黄小璨首月体验",
                    990,
                    "CNY",
                    "openid_bridge_001",
                    "union_bridge_001",
                    "",
                    "185 6588 3798",
                    "paid",
                    "SUCCESS",
                    "4200003130202606052403665106",
                    "2026-06-05 06:02:08+00",
                    "2026-06-05 06:02:01+00",
                ),
            )
            questionnaire_id = db.execute(
                """
                INSERT INTO questionnaires (slug, name, title)
                VALUES (?, ?, ?)
                RETURNING id
                """,
                ("bridge-questionnaire", "桥接问卷", "桥接问卷"),
            ).fetchone()["id"]
            submission_id = db.execute(
                """
                INSERT INTO questionnaire_submissions (
                    questionnaire_id, respondent_key, openid, unionid, external_userid,
                    follow_user_userid, matched_by, mobile_snapshot, submitted_at
                ) VALUES (?, ?, ?, ?, '', '', '', ?, ?::timestamptz)
                RETURNING id
                """,
                (
                    questionnaire_id,
                    "union_bridge_001",
                    "openid_bridge_001",
                    "union_bridge_001",
                    "18565883798",
                    "2026-06-05 06:05:54+00",
                ),
            ).fetchone()["id"]
            db.commit()

        result = process_wecom_external_contact_event(
            ProcessWeComExternalContactEventCommand(
                corp_id="ww-bridge",
                event_data={
                    "Event": "change_external_contact",
                    "ChangeType": "add_external_contact",
                    "ExternalUserID": "wm_bridge_001",
                    "UserID": "owner_bridge",
                    "CreateTime": "1780640000",
                },
                payload_xml="<xml/>",
                route="/wecom/external-contact/callback",
            )
        )

        with app.app_context():
            db = get_db()
            identity = db.execute(
                """
                SELECT external_userid, unionid, openid, follow_user_userid, name, status
                FROM wecom_external_contact_identity_map
                WHERE corp_id = ? AND external_userid = ?
                """,
                ("ww-bridge", "wm_bridge_001"),
            ).fetchone()
            binding = db.execute(
                """
                SELECT b.external_userid, p.mobile, b.first_owner_userid, b.last_owner_userid
                FROM external_contact_bindings b
                JOIN people p ON p.id = b.person_id
                WHERE b.external_userid = ?
                """,
                ("wm_bridge_001",),
            ).fetchone()
            submission = db.execute(
                """
                SELECT external_userid, follow_user_userid, matched_by
                FROM questionnaire_submissions
                WHERE id = ?
                """,
                (submission_id,),
            ).fetchone()

        assert result["identity_sync"]["status"] == "success"
        assert result["identity_sync"]["unionid_present"] is True
        assert result["identity_sync"]["mobile_binding"]["status"] == "bound"
        assert dict(identity) == {
            "external_userid": "wm_bridge_001",
            "unionid": "union_bridge_001",
            "openid": "openid_bridge_001",
            "follow_user_userid": "owner_bridge",
            "name": "桥接客户",
            "status": "active",
        }
        assert dict(binding) == {
            "external_userid": "wm_bridge_001",
            "mobile": "18565883798",
            "first_owner_userid": "owner_bridge",
            "last_owner_userid": "owner_bridge",
        }
        assert dict(submission) == {
            "external_userid": "wm_bridge_001",
            "follow_user_userid": "owner_bridge",
            "matched_by": "mobile",
        }
    finally:
        set_wecom_adapter(previous_adapter)


def test_sidebar_identity_refresh_binds_missing_identity_on_access(app):
    previous_adapter = get_wecom_adapter()
    set_wecom_adapter(DetailAdapter())
    try:
        with app.app_context():
            db = get_db()
            db.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("wm_bridge_001", "桥接客户", "owner_bridge", "桥接备注", ""),
            )
            db.execute(
                """
                INSERT INTO wechat_pay_orders (
                    out_trade_no, product_code, product_name, amount_total, currency,
                    payer_openid, unionid, external_userid, mobile_snapshot, status, trade_state,
                    transaction_id, paid_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::timestamptz, ?::timestamptz)
                """,
                (
                    "WXP_BRIDGE_SIDEBAR",
                    "subscription_trial_month",
                    "黄小璨首月体验",
                    990,
                    "CNY",
                    "openid_bridge_001",
                    "union_bridge_001",
                    "",
                    "18565883798",
                    "paid",
                    "SUCCESS",
                    "4200003130202606052403665107",
                    "2026-06-05 06:02:08+00",
                    "2026-06-05 06:02:01+00",
                ),
            )
            db.commit()

        result = ensure_external_contact_identity_for_sidebar(
            external_userid="wm_bridge_001",
            owner_userid="owner_bridge",
            corp_id="ww-bridge",
            min_interval_seconds=60,
        )

        with app.app_context():
            db = get_db()
            binding = db.execute(
                """
                SELECT b.external_userid, p.mobile, b.first_owner_userid
                FROM external_contact_bindings b
                JOIN people p ON p.id = b.person_id
                WHERE b.external_userid = ?
                """,
                ("wm_bridge_001",),
            ).fetchone()

        assert result["status"] == "attempted"
        assert result["reason"] == "identity_missing"
        assert result["sync_status"] == "success"
        assert result["mobile_binding_status"] == "bound"
        assert dict(binding) == {
            "external_userid": "wm_bridge_001",
            "mobile": "18565883798",
            "first_owner_userid": "owner_bridge",
        }
    finally:
        set_wecom_adapter(previous_adapter)


def test_identity_mobile_bridge_backfill_repairs_historical_unbound_rows(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_bridge_history", "历史桥接客户", "owner_history", "历史备注", ""),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ww-bridge",
                "wm_bridge_history",
                "union_bridge_history",
                "openid_bridge_history",
                "owner_history",
                "历史桥接客户",
            ),
        )
        db.execute(
            """
            INSERT INTO wechat_pay_orders (
                out_trade_no, product_code, product_name, amount_total, currency,
                payer_openid, unionid, external_userid, mobile_snapshot, status, trade_state,
                transaction_id, paid_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?::timestamptz, ?::timestamptz)
            """,
            (
                "WXP_BRIDGE_HISTORY",
                "subscription_trial_month",
                "黄小璨首月体验",
                990,
                "CNY",
                "openid_bridge_history",
                "union_bridge_history",
                "18565883799",
                "paid",
                "SUCCESS",
                "4200003130202606052403665199",
                "2026-06-05 06:02:08+00",
                "2026-06-05 06:02:01+00",
            ),
        )
        questionnaire_id = db.execute(
            """
            INSERT INTO questionnaires (slug, name, title)
            VALUES (?, ?, ?)
            RETURNING id
            """,
            ("bridge-history-questionnaire", "历史桥接问卷", "历史桥接问卷"),
        ).fetchone()["id"]
        submission_id = db.execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, openid, unionid, external_userid,
                follow_user_userid, matched_by, mobile_snapshot, submitted_at
            ) VALUES (?, ?, ?, ?, '', '', '', ?, ?::timestamptz)
            RETURNING id
            """,
            (
                questionnaire_id,
                "union_bridge_history",
                "openid_bridge_history",
                "union_bridge_history",
                "18565883799",
                "2026-06-05 06:05:54+00",
            ),
        ).fetchone()["id"]
        db.commit()

        dry_run = run_backfill(execute=False, limit=50, external_userids=["wm_bridge_history"])
        executed = run_backfill(execute=True, limit=50, external_userids=["wm_bridge_history"])

        binding = db.execute(
            """
            SELECT b.external_userid, p.mobile, b.first_owner_userid
            FROM external_contact_bindings b
            JOIN people p ON p.id = b.person_id
            WHERE b.external_userid = ?
            """,
            ("wm_bridge_history",),
        ).fetchone()
        submission = db.execute(
            """
            SELECT external_userid, follow_user_userid, matched_by
            FROM questionnaire_submissions
            WHERE id = ?
            """,
            (submission_id,),
        ).fetchone()

    assert dry_run["summary"] == {"would_bind": 1}
    assert executed["summary"] == {"bound": 1}
    assert dict(binding) == {
        "external_userid": "wm_bridge_history",
        "mobile": "18565883799",
        "first_owner_userid": "owner_history",
    }
    assert dict(submission) == {
        "external_userid": "wm_bridge_history",
        "follow_user_userid": "owner_history",
        "matched_by": "mobile",
    }
