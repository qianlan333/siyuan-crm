from __future__ import annotations

import json

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.services import evaluate_customer_value_segment, save_signup_conversion_config


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "value-segment.sqlite3"
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
    yield app


def _seed_bound_person(
    app,
    *,
    person_id: int,
    external_userid: str,
    mobile: str,
    owner_userid: str = "sales_01",
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (person_id, mobile, f"tp-{person_id}"),
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (external_userid, person_id, owner_userid, owner_userid, owner_userid),
        )
        db.commit()


def _seed_signup_conversion_questionnaire(app, *, questionnaire_id: int = 31) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (questionnaire_id, f"value-segment-{questionnaire_id}", "价值分层问卷", "价值分层问卷"),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, dict[str, int]] = {}
        for index in range(1, 6):
            question_id = questionnaire_id * 100 + index
            hit_option_id = question_id * 10 + 1
            miss_option_id = question_id * 10 + 2
            db.execute(
                """
                INSERT INTO questionnaire_questions (
                    id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
                )
                VALUES (?, ?, 'single_choice', ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id, questionnaire_id, f"关键题{index}", index),
            )
            db.execute(
                """
                INSERT INTO questionnaire_options (
                    id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '[]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (hit_option_id, question_id, f"关键题{index}-命中", 10),
            )
            db.execute(
                """
                INSERT INTO questionnaire_options (
                    id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '[]', 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (miss_option_id, question_id, f"关键题{index}-未命中", 0),
            )
            question_ids.append(question_id)
            option_ids_by_question[question_id] = {"hit": hit_option_id, "miss": miss_option_id}
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
    }


def _save_config(app, questionnaire_seed: dict[str, object], *, core_threshold: int = 3, top_threshold: int = 4):
    with app.app_context():
        save_signup_conversion_config(
            {
                "enabled": True,
                "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
                "core_threshold": core_threshold,
                "top_threshold": top_threshold,
                "quiet_hour_start": 23,
                "timezone": "Asia/Shanghai",
                "question_rules": [
                    {
                        "questionnaire_question_id": question_id,
                        "hit_option_ids_json": [questionnaire_seed["option_ids_by_question"][question_id]["hit"]],
                        "sort_order": index,
                    }
                    for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1)
                ],
            }
        )


def _create_submission(
    app,
    questionnaire_seed: dict[str, object],
    *,
    submission_id: int,
    external_userid: str,
    mobile_snapshot: str,
    hit_question_count: int,
    submitted_at: str,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '[]', '', ?)
            """,
            (
                submission_id,
                int(questionnaire_seed["questionnaire_id"]),
                f"resp-{submission_id}",
                external_userid,
                mobile_snapshot,
                hit_question_count * 10,
                submitted_at,
            ),
        )
        for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1):
            option_key = "hit" if index <= hit_question_count else "miss"
            option_id = questionnaire_seed["option_ids_by_question"][question_id][option_key]
            db.execute(
                """
                INSERT INTO questionnaire_submission_answers (
                    submission_id, question_id, question_type, question_title_snapshot,
                    selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                    selected_option_tags_snapshot, text_value, score_contribution, created_at
                )
                VALUES (?, ?, 'single_choice', ?, ?, '[]', '[]', '[]', '', ?, CURRENT_TIMESTAMP)
                """,
                (
                    submission_id,
                    question_id,
                    f"关键题{index}",
                    json.dumps([option_id]),
                    10 if option_key == "hit" else 0,
                ),
            )
        db.commit()


def test_value_segment_service_covers_unknown_normal_core_top(app):
    questionnaire_seed = _seed_signup_conversion_questionnaire(app)
    _save_config(app, questionnaire_seed, core_threshold=3, top_threshold=4)

    _seed_bound_person(app, person_id=101, external_userid="wm_vs_unknown", mobile="13800138101")
    _seed_bound_person(app, person_id=102, external_userid="wm_vs_normal", mobile="13800138102")
    _seed_bound_person(app, person_id=103, external_userid="wm_vs_core", mobile="13800138103")
    _seed_bound_person(app, person_id=104, external_userid="wm_vs_top", mobile="13800138104")
    _seed_bound_person(app, person_id=105, external_userid="wm_vs_top_max", mobile="13800138105")

    _create_submission(
        app,
        questionnaire_seed,
        submission_id=1002,
        external_userid="wm_vs_normal",
        mobile_snapshot="13800138102",
        hit_question_count=2,
        submitted_at="2026-04-04 10:00:00",
    )
    _create_submission(
        app,
        questionnaire_seed,
        submission_id=1003,
        external_userid="wm_vs_core",
        mobile_snapshot="13800138103",
        hit_question_count=3,
        submitted_at="2026-04-04 10:01:00",
    )
    _create_submission(
        app,
        questionnaire_seed,
        submission_id=1004,
        external_userid="wm_vs_top",
        mobile_snapshot="13800138104",
        hit_question_count=4,
        submitted_at="2026-04-04 10:02:00",
    )
    _create_submission(
        app,
        questionnaire_seed,
        submission_id=1005,
        external_userid="wm_vs_top_max",
        mobile_snapshot="13800138105",
        hit_question_count=5,
        submitted_at="2026-04-04 10:03:00",
    )

    with app.app_context():
        unknown = evaluate_customer_value_segment(external_userid="wm_vs_unknown")
        normal = evaluate_customer_value_segment(external_userid="wm_vs_normal")
        core = evaluate_customer_value_segment(external_userid="wm_vs_core")
        top = evaluate_customer_value_segment(person_id=104)
        top_max = evaluate_customer_value_segment(external_userid="wm_vs_top_max")

        assert unknown["segment"] == "unknown"
        assert unknown["submission_id"] is None
        assert normal["segment"] == "normal"
        assert normal["hit_count"] == 2
        assert core["segment"] == "core"
        assert core["hit_count"] == 3
        assert top["segment"] == "top"
        assert top["hit_count"] == 4
        assert top["is_top"] is True
        assert top["submission_id"] == 1004
        assert top_max["segment"] == "top"
        assert top_max["hit_count"] == 5
        assert top["evaluated_at"] != ""

        top_current = get_db().execute(
            """
            SELECT segment, submission_id, matched_question_ids_json, evaluated_at
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_vs_top",),
        ).fetchone()
        assert top_current["segment"] == "top"
        assert top_current["submission_id"] == 1004
        assert json.loads(top_current["matched_question_ids_json"]) == questionnaire_seed["question_ids"][:4]
        assert top_current["evaluated_at"] != ""


def test_value_segment_service_returns_unknown_for_mobile_only_person_without_external_userid(app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (301, '13800138301', 'tp-301', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = evaluate_customer_value_segment(person_id=301)

        assert result["person_id"] == 301
        assert result["external_userid"] == ""
        assert result["segment"] == "unknown"
        assert result["computed_reason"] == "missing_external_userid"
        current_total = get_db().execute("SELECT COUNT(*) AS total FROM customer_value_segment_current").fetchone()["total"]
        history_total = get_db().execute("SELECT COUNT(*) AS total FROM customer_value_segment_history").fetchone()["total"]
        assert current_total == 0
        assert history_total == 0


def test_value_segment_service_recomputes_on_threshold_and_latest_submission_change_without_history_spam(app):
    questionnaire_seed = _seed_signup_conversion_questionnaire(app)
    _save_config(app, questionnaire_seed, core_threshold=2, top_threshold=4)
    _seed_bound_person(app, person_id=201, external_userid="wm_vs_recalc", mobile="13800138201")

    _create_submission(
        app,
        questionnaire_seed,
        submission_id=2001,
        external_userid="wm_vs_recalc",
        mobile_snapshot="13800138201",
        hit_question_count=2,
        submitted_at="2026-04-04 09:00:00",
    )

    with app.app_context():
        first = evaluate_customer_value_segment(external_userid="wm_vs_recalc")
        assert first["segment"] == "core"

        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_value_segment_history WHERE external_userid = ?",
            ("wm_vs_recalc",),
        ).fetchone()["total"]
        assert history_total == 1

    _create_submission(
        app,
        questionnaire_seed,
        submission_id=2002,
        external_userid="wm_vs_recalc",
        mobile_snapshot="13800138201",
        hit_question_count=1,
        submitted_at="2026-04-04 11:00:00",
    )

    with app.app_context():
        second = evaluate_customer_value_segment(person_id=201)
        assert second["segment"] == "normal"
        assert second["submission_id"] == 2002

        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_value_segment_history WHERE external_userid = ?",
            ("wm_vs_recalc",),
        ).fetchone()["total"]
        assert history_total == 2

        save_signup_conversion_config(
            {
                "enabled": True,
                "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
                "core_threshold": 1,
                "top_threshold": 1,
                "quiet_hour_start": 23,
                "timezone": "Asia/Shanghai",
                "question_rules": [
                    {
                        "questionnaire_question_id": question_id,
                        "hit_option_ids_json": [questionnaire_seed["option_ids_by_question"][question_id]["hit"]],
                        "sort_order": index,
                    }
                    for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1)
                ],
            }
        )

        third = evaluate_customer_value_segment(external_userid="wm_vs_recalc")
        assert third["segment"] == "top"
        assert third["submission_id"] == 2002

        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_value_segment_history WHERE external_userid = ?",
            ("wm_vs_recalc",),
        ).fetchone()["total"]
        assert history_total == 3

        fourth = evaluate_customer_value_segment(external_userid="wm_vs_recalc")
        assert fourth["segment"] == "top"

        history_total_after_repeat = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_value_segment_history WHERE external_userid = ?",
            ("wm_vs_recalc",),
        ).fetchone()["total"]
        assert history_total_after_repeat == 3

        current_row = get_db().execute(
            """
            SELECT segment, score, submission_id, matched_question_ids_json
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_vs_recalc",),
        ).fetchone()
        assert current_row["segment"] == "top"
        assert current_row["score"] == 1
        assert current_row["submission_id"] == 2002
        assert json.loads(current_row["matched_question_ids_json"]) == [questionnaire_seed["question_ids"][0]]
