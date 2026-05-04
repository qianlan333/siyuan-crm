#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.infra.settings import set_settings
from wecom_ability_service.services import insert_archived_messages, upsert_customer_trial_opening_fact


DEMO_CUSTOMERS = [
    {
        "external_userid": "wm_demo_normal",
        "mobile": "13800138001",
        "customer_name": "普通路径客户",
        "owner_userid": "QianLan",
        "follow_user_userid": "QianLan",
        "unionid": "union-demo-normal",
        "openid": "openid-demo-normal",
    },
    {
        "external_userid": "wm_demo_focus",
        "mobile": "13800138002",
        "customer_name": "重点路径客户",
        "owner_userid": "sales_demo_02",
        "follow_user_userid": "sales_demo_02",
        "unionid": "union-demo-focus",
        "openid": "openid-demo-focus",
    },
]


def _create_app(database_path: str = ""):
    overrides: dict[str, object] = {"TESTING": True}
    if database_path:
        overrides["DATABASE_PATH"] = database_path
    return create_app(overrides)


def _seed_demo_customers(*, corp_id: str) -> None:
    db = get_db()
    for item in DEMO_CUSTOMERS:
        db.execute(
            """
            INSERT OR IGNORE INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            (item["owner_userid"], item["owner_userid"], "sales", 1),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                item["external_userid"],
                item["customer_name"],
                item["owner_userid"],
                f"{item['customer_name']}备注",
                item["external_userid"],
            ),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (item["mobile"], f"tp-{item['external_userid']}"),
        )
        person = db.execute("SELECT id FROM people WHERE mobile = ?", (item["mobile"],)).fetchone()
        person_id = int(person["id"])
        db.execute(
            """
            INSERT OR IGNORE INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                item["external_userid"],
                person_id,
                item["owner_userid"],
                item["owner_userid"],
                item["owner_userid"],
            ),
        )
        db.execute(
            """
            INSERT OR REPLACE INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (
                item["external_userid"],
                "lead",
                "报名引流品",
                item["customer_name"],
                item["owner_userid"],
                item["mobile"],
                item["owner_userid"],
                "success",
                "",
                "{}",
            ),
        )
        db.execute(
            """
            INSERT OR REPLACE INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                corp_id,
                item["external_userid"],
                item["unionid"],
                item["openid"],
                item["follow_user_userid"],
                item["customer_name"],
                "active",
                "{}",
            ),
        )
    db.commit()


def _mark_trial_opened(external_userid: str) -> dict[str, object]:
    item = next((customer for customer in DEMO_CUSTOMERS if customer["external_userid"] == external_userid), None)
    if item is None:
        raise ValueError(f"unknown demo external_userid: {external_userid}")
    return upsert_customer_trial_opening_fact(
        mobile=item["mobile"],
        external_userid=item["external_userid"],
        customer_name=item["customer_name"],
        owner_userid=item["owner_userid"],
        source_type="demo_seed",
        opened_at="2026-04-06 10:00:00",
    )


def _insert_focus_message() -> int:
    focus_customer = next(item for item in DEMO_CUSTOMERS if item["external_userid"] == "wm_demo_focus")
    return insert_archived_messages(
        [
            {
                "seq": 1,
                "msgid": "demo-focus-msg-001",
                "chat_type": "private",
                "external_userid": focus_customer["external_userid"],
                "owner_userid": focus_customer["owner_userid"],
                "sender": focus_customer["external_userid"],
                "receiver": focus_customer["owner_userid"],
                "msgtype": "text",
                "content": "老师，我已经提交问卷了，想继续了解",
                "send_time": "2026-04-06 10:20:00",
                "raw_payload": json.dumps(
                    {
                        "decrypted_message": {
                            "from": focus_customer["external_userid"],
                            "tolist": [focus_customer["owner_userid"]],
                            "roomid": "",
                        }
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed local demo data for automation conversion acceptance.")
    parser.add_argument("--database-path", default="", help="Optional sqlite DATABASE_PATH override")
    parser.add_argument("--corp-id", default="ww-local-demo", help="Corp id used for demo identity map rows")
    parser.add_argument("--init-db", action="store_true", help="Initialize database schema before seeding")
    parser.add_argument("--write-settings", action="store_true", help="Write local demo settings into app_settings")
    parser.add_argument("--internal-api-token", default="", help="Demo unified internal API token")
    parser.add_argument("--mcp-token", default="", help="Demo MCP token")
    parser.add_argument("--openclaw-webhook-url", default="", help="Demo OpenClaw focus webhook URL")
    parser.add_argument("--openclaw-webhook-token", default="", help="Demo OpenClaw focus webhook token")
    parser.add_argument("--activation-webhook-token", default="", help="Demo activation webhook token")
    parser.add_argument("--questionnaire-webhook-url", default="", help="Demo questionnaire submit webhook URL")
    parser.add_argument("--questionnaire-webhook-token", default="", help="Demo questionnaire submit webhook token")
    parser.add_argument("--mark-trial-opened", default="", help="Mark one demo customer as trial opened by external_userid")
    parser.add_argument("--insert-focus-message", action="store_true", help="Insert one inbound focus message for wm_demo_focus")
    args = parser.parse_args()

    app = _create_app(database_path=args.database_path)
    with app.app_context():
        if args.init_db:
            init_db()
        _seed_demo_customers(corp_id=args.corp_id)
        if args.write_settings:
            settings: dict[str, str] = {}
            if args.internal_api_token:
                settings["AUTOMATION_INTERNAL_API_TOKEN"] = args.internal_api_token
            if args.mcp_token:
                settings["MCP_BEARER_TOKEN"] = args.mcp_token
            if args.openclaw_webhook_url:
                settings["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_URL"] = args.openclaw_webhook_url
            if args.openclaw_webhook_token:
                settings["OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN"] = args.openclaw_webhook_token
            if args.activation_webhook_token:
                settings["AUTOMATION_ACTIVATION_WEBHOOK_TOKEN"] = args.activation_webhook_token
            if args.questionnaire_webhook_url:
                settings["QUESTIONNAIRE_SUBMIT_WEBHOOK_URL"] = args.questionnaire_webhook_url
            if args.questionnaire_webhook_token:
                settings["QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN"] = args.questionnaire_webhook_token
            if settings:
                set_settings(settings)
        if args.mark_trial_opened:
            result = _mark_trial_opened(args.mark_trial_opened)
            print(json.dumps({"trial_opened": result}, ensure_ascii=False, indent=2))
        if args.insert_focus_message:
            inserted = _insert_focus_message()
            print(json.dumps({"inserted_messages": inserted}, ensure_ascii=False, indent=2))
        print(json.dumps({"seeded_customers": DEMO_CUSTOMERS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
