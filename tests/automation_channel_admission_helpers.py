from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.admin_auth import save_admin_user
from wecom_ability_service.domains.automation_conversion import program_repo, repo


def create_program(code: str = "program_p1", *, status: str = "active", config_json: dict | None = None) -> int:
    row = program_repo.insert_program_row(
        {
            "program_code": code,
            "program_name": code,
            "description": "test program",
            "status": status,
            "config_json": dict(config_json or {}),
            "created_by": "pytest",
            "updated_by": "pytest",
        }
    )
    get_db().commit()
    return int(row["id"])


def create_channel(code: str, *, status: str = "active", program_id: int | None = None) -> dict:
    channel = repo.save_channel(
        {
            "program_id": program_id,
            "channel_code": code,
            "channel_name": code,
            "qr_url": "",
            "qr_ticket": "",
            "scene_value": f"scene_{code}",
            "welcome_message": "",
            "welcome_attachment_library_ids": [],
            "auto_accept_friend": False,
            "entry_tag_id": "",
            "entry_tag_name": "",
            "entry_tag_group_name": "",
            "owner_staff_id": "sales_01",
            "status": status,
        }
    )
    get_db().commit()
    return channel


def save_audience_entry_rule(program_id: int, payload: dict) -> None:
    program_repo.upsert_config_block_row(program_id, "audience_entry_rule", payload, status="saved")
    get_db().commit()


def disabled_entry_rule() -> dict:
    return {
        "order_review": {"enabled": False},
        "questionnaire_review": {"enabled": False},
        "conversion_review": {"enabled": False},
    }


def create_choice_questionnaire(slug: str = "admission-q") -> dict:
    db = get_db()
    questionnaire_id = int(
        db.execute(
            """
            INSERT INTO questionnaires (slug, name, title, description)
            VALUES (?, ?, ?, '')
            RETURNING id
            """,
            (slug, slug, slug),
        ).fetchone()["id"]
    )
    question_id = int(
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                questionnaire_id, type, title, required, sort_order
            )
            VALUES (?, 'single_choice', '分层题目', TRUE, 1)
            RETURNING id
            """,
            (questionnaire_id,),
        ).fetchone()["id"]
    )
    option_a_id = int(
        db.execute(
            """
            INSERT INTO questionnaire_options (question_id, option_text, score, sort_order)
            VALUES (?, 'A 选项', 1, 1)
            RETURNING id
            """,
            (question_id,),
        ).fetchone()["id"]
    )
    option_b_id = int(
        db.execute(
            """
            INSERT INTO questionnaire_options (question_id, option_text, score, sort_order)
            VALUES (?, 'B 选项', 2, 2)
            RETURNING id
            """,
            (question_id,),
        ).fetchone()["id"]
    )
    db.commit()
    return {
        "id": questionnaire_id,
        "slug": slug,
        "title": slug,
        "question_id": question_id,
        "option_a_id": option_a_id,
        "option_b_id": option_b_id,
    }


def seed_questionnaire_submission(
    *,
    questionnaire_id: int,
    question_id: int | None = None,
    option_ids: list[int] | None = None,
    external_contact_id: str,
    submitted_at: str,
) -> int:
    db = get_db()
    submission_id = int(
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                questionnaire_id, respondent_key, external_userid, mobile_snapshot,
                total_score, submitted_at
            )
            VALUES (?, ?, ?, '', 0, ?)
            RETURNING id
            """,
            (int(questionnaire_id), external_contact_id, external_contact_id, submitted_at),
        ).fetchone()["id"]
    )
    if question_id and option_ids is not None:
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot,
                selected_option_scores_snapshot, selected_option_tags_snapshot,
                text_value, score_contribution
            )
            VALUES (?, ?, 'single_choice', '分层题目', CAST(? AS jsonb), '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '', 0)
            """,
            (submission_id, int(question_id), json.dumps([int(item) for item in option_ids])),
        )
    db.commit()
    return submission_id


def seed_order(
    *,
    external_contact_id: str,
    product_code: str,
    paid_at: str,
    status: str = "paid",
    trade_state: str = "SUCCESS",
    refunded_amount_total: int = 0,
) -> None:
    get_db().execute(
        """
        INSERT INTO wechat_pay_orders (
            out_trade_no, product_code, product_name, amount_total, refunded_amount_total,
            external_userid, status, trade_state, transaction_id, paid_at, created_at, updated_at
        )
        VALUES (?, ?, ?, 9900, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"order-{external_contact_id}-{product_code}-{paid_at}",
            product_code,
            product_code,
            int(refunded_amount_total),
            external_contact_id,
            status,
            trade_state,
            f"tx-{external_contact_id}-{product_code}-{paid_at}",
            paid_at,
            paid_at,
            paid_at,
        ),
    )
    get_db().commit()


def set_callback_now(monkeypatch, value: str) -> None:
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.member_state_service.service_seams._iso_now",
        lambda: value,
    )


def table_count(table_name: str, where_sql: str = "", params: tuple = ()) -> int:
    sql = f"SELECT COUNT(*) AS total FROM {table_name}"
    if where_sql:
        sql += f" WHERE {where_sql}"
    return int(get_db().execute(sql, params).fetchone()["total"])


def dt_text(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")[:19]


def fetch_program_member(external_contact_id: str, program_id: int | None = None) -> dict | None:
    sql = "SELECT * FROM automation_program_member WHERE external_contact_id = ?"
    params: list = [external_contact_id]
    if program_id:
        sql += " AND program_id = ?"
        params.append(int(program_id))
    sql += " ORDER BY id DESC LIMIT 1"
    row = get_db().execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None


def fetch_channel_contact(channel_id: int, external_contact_id: str) -> dict | None:
    row = get_db().execute(
        """
        SELECT *
        FROM automation_channel_contact
        WHERE channel_id = ? AND external_contact_id = ?
        LIMIT 1
        """,
        (int(channel_id), external_contact_id),
    ).fetchone()
    return dict(row) if row else None


def authorize_admin(app) -> None:
    save_admin_user(
        {
            "wecom_userid": "root.admin",
            "display_name": "Root Admin",
            "wecom_corpid": app.config["WECOM_CORP_ID"],
            "role_codes": ["super_admin"],
            "is_active": "1",
        },
        operator="test-suite",
    )


def login_admin(client, app, monkeypatch) -> None:
    with app.app_context():
        authorize_admin(app)
    start_response = client.get("/auth/wecom/start?mode=qr&next=/admin/automation-conversion", follow_redirects=False)
    state = parse_qs(urlparse(start_response.headers["Location"]).query)["state"][0]
    monkeypatch.setattr(
        "wecom_ability_service.http.internal_auth.exchange_code_for_wecom_user",
        lambda code: {
            "wecom_userid": "root.admin",
            "display_name": "Root Admin",
            "wecom_corpid": app.config["WECOM_CORP_ID"],
            "raw_identity": {"UserId": "root.admin"},
        },
    )
    response = client.get(f"/auth/wecom/callback?code=mock-code&state={state}", follow_redirects=False)
    assert response.status_code == 302


def admin_action_token(client) -> str:
    html = client.get("/admin/automation-conversion").get_data(as_text=True)
    match = re.search(r'name="admin_action_token" value="([^"]+)"', html)
    assert match
    return match.group(1)
