from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.services import save_signup_conversion_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_marketing_automation_backfill.py"


def _seed_questionnaire(app, *, questionnaire_id: int = 61) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"backfill-{questionnaire_id}",
                "回填问卷",
                "回填问卷",
            ),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, list[int]] = {}
        for index in range(1, 6):
            question_id = questionnaire_id * 100 + index
            db.execute(
                """
                INSERT INTO questionnaire_questions (
                    id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
                )
                VALUES (?, ?, 'single_choice', ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id, questionnaire_id, f"关键问题{index}", index),
            )
            option_ids: list[int] = []
            for option_index in range(1, 3):
                option_id = question_id * 10 + option_index
                option_ids.append(option_id)
                db.execute(
                    """
                    INSERT INTO questionnaire_options (
                        id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, '[]', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (option_id, question_id, f"问题{index}-选项{option_index}", option_index * 10, option_index),
                )
            question_ids.append(question_id)
            option_ids_by_question[question_id] = option_ids
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
    }


def _save_config(app, questionnaire_seed: dict[str, object]) -> None:
    with app.app_context():
        save_signup_conversion_config(
            {
                "enabled": True,
                "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
                "core_threshold": 3,
                "top_threshold": 4,
                "quiet_hour_start": 23,
                "timezone": "Asia/Shanghai",
                "question_rules": [
                    {
                        "questionnaire_question_id": question_id,
                        "hit_option_ids_json": [questionnaire_seed["option_ids_by_question"][question_id][0]],
                        "sort_order": index,
                    }
                    for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1)
                ],
            }
        )


def _seed_bound_customer(app, questionnaire_seed: dict[str, object]) -> None:
    now = datetime.now().replace(microsecond=0)
    last_message_at = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    submission_at = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES ('wm_backfill_001', '回填客户', 'sales_61', '', '', CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (6101, '13800138611', 'tp-6101', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES ('wm_backfill_001', 6101, 'sales_61', 'sales_61', 'sales_61', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES ('wm_backfill_001', 'lead', '报名引流品', '回填客户', 'sales_61', '13800138611', 'sales_61', CURRENT_TIMESTAMP, 'success', '', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
            )
            VALUES (1, 'wm_backfill_001-msg-1', 'private', 'wm_backfill_001', 'sales_61', 'wm_backfill_001', 'sales_61', 'text', '我想报名', ?, ?)
            """,
            (
                last_message_at,
                json.dumps({"decrypted_message": {"from": "wm_backfill_001", "tolist": ["sales_61"], "roomid": ""}}, ensure_ascii=False),
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, 'wm_backfill_001', '13800138611', 40, '[]', '', ?)
            """,
            (61011, int(questionnaire_seed["questionnaire_id"]), "resp-61011", submission_at),
        )
        for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1):
            option_id = questionnaire_seed["option_ids_by_question"][question_id][0 if index <= 4 else 1]
            db.execute(
                """
                INSERT INTO questionnaire_submission_answers (
                    submission_id, question_id, question_type, question_title_snapshot,
                    selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                    selected_option_tags_snapshot, text_value, score_contribution, created_at
                )
                VALUES (?, ?, 'single_choice', ?, ?, '[]', '[]', '[]', '', ?, CURRENT_TIMESTAMP)
                """,
                (61011, question_id, f"关键问题{index}", json.dumps([option_id]), 10 if index <= 4 else 0),
            )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (6102, '13800138612', 'tp-6102', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()


def test_marketing_backfill_script_recomputes_all_targets(tmp_path):
    db_path = tmp_path / "marketing-backfill.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with app.app_context():
        init_db()
    questionnaire_seed = _seed_questionnaire(app, questionnaire_id=61)
    _save_config(app, questionnaire_seed)
    _seed_bound_customer(app, questionnaire_seed)

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--all", "--limit", "10", "--chunk-size", "1"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["mode"] == "backfill"
    assert payload["dry_run"] is False
    assert payload["selected_count"] == 2
    assert payload["processed_count"] == 2
    assert payload["success_count"] == 2
    assert payload["failure_count"] == 0
    assert payload["segment_distribution"] == {"top": 1, "unknown": 1}

    stage_map = {
        (
            item["resolved_customer"]["external_userid"],
            item["resolved_customer"]["person_id"],
        ): item["summary"]["current_stage"]
        for item in payload["items"]
    }
    segment_map = {
        (
            item["resolved_customer"]["external_userid"],
            item["resolved_customer"]["person_id"],
        ): item["summary"]["current_segment"]
        for item in payload["items"]
    }
    assert stage_map[("wm_backfill_001", 6101)] == "pool/new_user"
    assert segment_map[("wm_backfill_001", 6101)] == "top"
    assert stage_map[("", 6102)] == "pool/new_user"
    assert segment_map[("", 6102)] == "unknown"

    with app.app_context():
        db = get_db()
        current_state = db.execute(
            """
            SELECT main_stage, sub_stage
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            ("wm_backfill_001",),
        ).fetchone()
        current_segment = db.execute(
            """
            SELECT segment, score
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_backfill_001",),
        ).fetchone()
        mobile_only_state = db.execute(
            """
            SELECT main_stage, sub_stage, external_userid
            FROM customer_marketing_state_current
            WHERE person_id = ?
            """,
            (6102,),
        ).fetchone()

        assert f"{current_state['main_stage']}/{current_state['sub_stage']}" == "pool/new_user"
        assert current_segment["segment"] == "top"
        assert int(current_segment["score"]) == 4
        assert f"{mobile_only_state['main_stage']}/{mobile_only_state['sub_stage']}" == "pool/new_user"
        assert mobile_only_state["external_userid"] == ""


def test_marketing_backfill_script_dry_run_does_not_write_current_tables(tmp_path):
    db_path = tmp_path / "marketing-backfill-dry-run.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with app.app_context():
        init_db()
    questionnaire_seed = _seed_questionnaire(app, questionnaire_id=62)
    _save_config(app, questionnaire_seed)
    _seed_bound_customer(app, questionnaire_seed)

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--all", "--limit", "10", "--chunk-size", "1", "--dry-run"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["selected_count"] == 2
    assert payload["success_count"] == 2
    assert payload["failure_count"] == 0
    assert payload["segment_distribution"] == {"top": 1, "unknown": 1}

    with app.app_context():
        db = get_db()
        marketing_state_total = db.execute(
            "SELECT COUNT(*) AS total FROM customer_marketing_state_current"
        ).fetchone()["total"]
        value_segment_total = db.execute(
            "SELECT COUNT(*) AS total FROM customer_value_segment_current"
        ).fetchone()["total"]

    assert marketing_state_total == 0
    assert value_segment_total == 0
