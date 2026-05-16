from __future__ import annotations

import json
from datetime import datetime as real_datetime

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.services import (
    evaluate_customer_marketing_state,
    evaluate_customer_value_segment,
    save_signup_conversion_config,
    upsert_customer_trial_opening_fact,
)


@pytest.fixture()
def app(tmp_path):
    """PG-only：用顶层 build_pg_test_app helper 起 app（2026-05 砍 SQLite 后改造）。"""
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path) as app:
        yield app


def _freeze_state_time(monkeypatch, *, timestamp: str) -> None:
    from wecom_ability_service.domains.marketing_automation import service as marketing_service

    frozen = real_datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls(
                    frozen.year,
                    frozen.month,
                    frozen.day,
                    frozen.hour,
                    frozen.minute,
                    frozen.second,
                )
            return cls(
                frozen.year,
                frozen.month,
                frozen.day,
                frozen.hour,
                frozen.minute,
                frozen.second,
                tzinfo=tz,
            )

    monkeypatch.setattr(marketing_service, "datetime", FrozenDateTime)


def _seed_person(app, *, person_id: int, mobile: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (person_id, mobile, f"tp-{person_id}"),
        )
        db.commit()


def _seed_bound_external(
    app,
    *,
    person_id: int,
    external_userid: str,
    mobile: str,
    customer_name: str,
    owner_userid: str = "sales_01",
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name, owner_userid),
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
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active, updated_at)
            VALUES (?, ?, 'sales', true, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
            """,
            (owner_userid, owner_userid),
        )
        db.execute(
            """
            UPDATE people
            SET mobile = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (mobile, person_id),
        )
        db.commit()


def _seed_signup_conversion_questionnaire(
    app,
    *,
    questionnaire_id: int,
    question_count: int = 4,
) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', false, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"signup-conversion-{questionnaire_id}",
                "自动化转化问卷",
                "自动化转化问卷",
            ),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, list[int]] = {}
        for index in range(1, question_count + 1):
            question_id = questionnaire_id * 100 + index
            option_ids: list[int] = []
            db.execute(
                """
                INSERT INTO questionnaire_questions (
                    id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
                )
                VALUES (?, ?, 'single_choice', ?, true, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id, questionnaire_id, f"关键问题{index}", index),
            )
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
                    (
                        option_id,
                        question_id,
                        f"问题{index}-选项{option_index}",
                        option_index * 10,
                        option_index,
                    ),
                )
            question_ids.append(question_id)
            option_ids_by_question[question_id] = option_ids

        mobile_question_id = questionnaire_id * 100 + question_count + 1
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '手机号', true, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id, question_count + 1),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
    }


def _save_automation_config(
    app,
    questionnaire_seed: dict[str, object],
    *,
    silent_threshold_days_by_pool: dict[str, int] | None = None,
) -> None:
    with app.app_context():
        save_signup_conversion_config(
            {
                "enabled": True,
                "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
                "core_threshold": 3,
                "top_threshold": 4,
                "quiet_hour_start": 23,
                "timezone": "Asia/Shanghai",
                "silent_threshold_days_by_pool": silent_threshold_days_by_pool
                or {
                    "new_user": 7,
                    "inactive_normal": 7,
                    "inactive_focus": 7,
                    "active_normal": 7,
                    "active_focus": 7,
                },
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


def _create_questionnaire_submission(
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
            option_id = questionnaire_seed["option_ids_by_question"][question_id][0 if index <= hit_question_count else 1]
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
                    f"关键问题{index}",
                    json.dumps([option_id]),
                    10 if index <= hit_question_count else 0,
                ),
            )
        db.commit()


def test_repo_upsert_customer_marketing_state_current_nulls_blank_postgres_timestamps(monkeypatch):
    from wecom_ability_service.domains.marketing_automation import repo as marketing_repo

    captured: dict[str, object] = {}

    class _FakeCursor:
        def fetchone(self):
            return {"id": 1}

    class _FakeDb:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return _FakeCursor()

    monkeypatch.setattr(marketing_repo, "get_db", lambda: _FakeDb())
    monkeypatch.setattr(
        marketing_repo,
        "_list_customer_marketing_state_current_candidates",
        lambda **kwargs: [],
    )

    marketing_repo.upsert_customer_marketing_state_current(
        external_userid="wm_ext_001",
        person_id=None,
        automation_key="signup_conversion_v1",
        main_stage="pool",
        sub_stage="new_user",
        activated=False,
        converted=False,
        eligible_for_conversion=False,
        lifecycle_status="pool",
        last_activation_at="",
        last_conversion_marked_at="",
        last_message_at="2026-04-04 10:01:10",
        last_batch_id=None,
        last_batch_status="",
        last_batch_window_start="",
        last_batch_window_end="",
        last_trigger_message_at="2026-04-04 10:01:10",
        entered_at="2026-04-04 10:03:00",
        exited_at="",
        exit_reason="trial_not_opened",
        state_payload={"pool_key": "new_user"},
    )

    assert captured["params"][17] == "2026-04-04 10:03:00"
    assert captured["params"][18] is None
    assert "?::jsonb" in str(captured["sql"])


def _seed_activation_source(app, *, mobile: str, updated_at: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_huangxiaocan_activation_source (
                mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, 'activated', 'batch-seed', 'seed', true, ?, ?)
            """,
            (mobile, updated_at, updated_at),
        )
        db.commit()


def _seed_trial_opening_fact(
    app,
    *,
    mobile: str,
    external_userid: str,
    customer_name: str,
    owner_userid: str = "sales_01",
    opened_at: str,
):
    with app.app_context():
        upsert_customer_trial_opening_fact(
            mobile=mobile,
            external_userid=external_userid,
            customer_name=customer_name,
            owner_userid=owner_userid,
            source="test_seed",
            opened_at=opened_at,
        )
        get_db().commit()


def test_questionnaire_initial_split_enters_corresponding_pool(app, monkeypatch):
    _freeze_state_time(monkeypatch, timestamp="2026-04-04 10:00:00")
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=81)
    _save_automation_config(app, questionnaire_seed)

    _seed_person(app, person_id=401, mobile="13800138401")
    _seed_person(app, person_id=402, mobile="13800138402")
    _seed_bound_external(app, person_id=401, external_userid="wm_pool_normal", mobile="13800138401", customer_name="普通客户")
    _seed_bound_external(app, person_id=402, external_userid="wm_pool_focus", mobile="13800138402", customer_name="重点客户")
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=8101,
        external_userid="wm_pool_normal",
        mobile_snapshot="13800138401",
        hit_question_count=1,
        submitted_at="2026-04-04 09:10:00",
    )
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=8102,
        external_userid="wm_pool_focus",
        mobile_snapshot="13800138402",
        hit_question_count=4,
        submitted_at="2026-04-04 09:12:00",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800138401",
        external_userid="wm_pool_normal",
        customer_name="普通客户",
        opened_at="2026-04-04 09:10:00",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800138402",
        external_userid="wm_pool_focus",
        customer_name="重点客户",
        opened_at="2026-04-04 09:12:00",
    )

    with app.app_context():
        normal_state = evaluate_customer_marketing_state(external_userid="wm_pool_normal")
        focus_state = evaluate_customer_marketing_state(external_userid="wm_pool_focus")

        assert normal_state["stage_key"] == "pool/inactive_normal"
        assert normal_state["pool_key"] == "inactive_normal"
        assert normal_state["current_segment"] == "normal"
        assert normal_state["entered_at"] == "2026-04-04 10:00:00"

        assert focus_state["stage_key"] == "pool/inactive_focus"
        assert focus_state["pool_key"] == "inactive_focus"
        assert focus_state["current_segment"] == "focus"
        assert focus_state["entered_at"] == "2026-04-04 10:00:00"


def test_activation_moves_customer_from_inactive_pool_to_active_pool(app, monkeypatch):
    _freeze_state_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=82)
    _save_automation_config(app, questionnaire_seed)

    _seed_person(app, person_id=501, mobile="13800138501")
    _seed_bound_external(app, person_id=501, external_userid="wm_pool_upgrade", mobile="13800138501", customer_name="激活客户")
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=8201,
        external_userid="wm_pool_upgrade",
        mobile_snapshot="13800138501",
        hit_question_count=4,
        submitted_at="2026-04-04 09:20:00",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800138501",
        external_userid="wm_pool_upgrade",
        customer_name="激活客户",
        opened_at="2026-04-04 09:20:00",
    )

    with app.app_context():
        first = evaluate_customer_marketing_state(external_userid="wm_pool_upgrade")
        assert first["stage_key"] == "pool/inactive_focus"

    _seed_activation_source(app, mobile="13800138501", updated_at="2026-04-04 12:00:00")
    _freeze_state_time(monkeypatch, timestamp="2026-04-04 12:30:00")

    with app.app_context():
        second = evaluate_customer_marketing_state(external_userid="wm_pool_upgrade")
        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM customer_marketing_state_history WHERE external_userid = ?",
            ("wm_pool_upgrade",),
        ).fetchone()["total"]

        assert second["stage_key"] == "pool/active_focus"
        assert second["pool_key"] == "active_focus"
        assert second["last_activation_at"] == "2026-04-04 12:00:00"
        assert second["entered_at"] == "2026-04-04 12:30:00"
        assert int(history_total) == 2


def test_customer_marketing_state_current_keeps_single_pool_row(app, monkeypatch):
    _freeze_state_time(monkeypatch, timestamp="2026-04-10 09:00:00")
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=83)
    _save_automation_config(app, questionnaire_seed)

    _seed_person(app, person_id=601, mobile="13800138601")
    _seed_bound_external(app, person_id=601, external_userid="wm_pool_single", mobile="13800138601", customer_name="单池客户")
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=8301,
        external_userid="wm_pool_single",
        mobile_snapshot="13800138601",
        hit_question_count=1,
        submitted_at="2026-04-04 09:30:00",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800138601",
        external_userid="wm_pool_single",
        customer_name="单池客户",
        opened_at="2026-04-04 09:30:00",
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO customer_marketing_state_current (
                person_id, external_userid, automation_key, main_stage, sub_stage, activated, converted,
                eligible_for_conversion, lifecycle_status, last_activation_at, last_conversion_marked_at,
                last_message_at, last_batch_id, last_batch_status, last_batch_window_start, last_batch_window_end,
                last_trigger_message_at, entered_at, exited_at, exit_reason, state_payload_json, created_at, updated_at
            )
            VALUES (NULL, ?, 'signup_conversion_v1', 'pool', 'new_user', false, false, true, 'pool', '', '', '', NULL, '', '', '', '', '2026-04-04 09:00:00', NULL, '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_pool_single",),
        )
        db.commit()

        state = evaluate_customer_marketing_state(external_userid="wm_pool_single")
        rows = db.execute(
            """
            SELECT id, main_stage, sub_stage
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            ORDER BY id ASC
            """,
            ("wm_pool_single",),
        ).fetchall()

        assert state["stage_key"] == "pool/inactive_normal"
        assert len(rows) == 1
        assert f"{rows[0]['main_stage']}/{rows[0]['sub_stage']}" == "pool/inactive_normal"


def test_customer_enters_silent_pool_after_threshold_days(app, monkeypatch):
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=84)
    _save_automation_config(
        app,
        questionnaire_seed,
        silent_threshold_days_by_pool={
            "new_user": 7,
            "inactive_normal": 7,
            "inactive_focus": 1,
            "active_normal": 7,
            "active_focus": 7,
        },
    )

    _seed_person(app, person_id=701, mobile="13800138701")
    _seed_bound_external(app, person_id=701, external_userid="wm_pool_silent", mobile="13800138701", customer_name="沉默客户")
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=8401,
        external_userid="wm_pool_silent",
        mobile_snapshot="13800138701",
        hit_question_count=4,
        submitted_at="2026-04-04 10:00:00",
    )
    _seed_trial_opening_fact(
        app,
        mobile="13800138701",
        external_userid="wm_pool_silent",
        customer_name="沉默客户",
        opened_at="2026-04-04 10:00:00",
    )

    _freeze_state_time(monkeypatch, timestamp="2026-04-04 10:10:00")
    with app.app_context():
        first = evaluate_customer_marketing_state(external_userid="wm_pool_silent")
        assert first["stage_key"] == "pool/inactive_focus"
        assert first["entered_at"] == "2026-04-04 10:10:00"

    _freeze_state_time(monkeypatch, timestamp="2026-04-05 10:30:00")
    with app.app_context():
        second = evaluate_customer_marketing_state(external_userid="wm_pool_silent")
        value_segment = evaluate_customer_value_segment(external_userid="wm_pool_silent")

        assert second["stage_key"] == "pool/silent"
        assert second["pool_key"] == "silent"
        assert second["eligible_for_conversion"] is False
        assert second["entered_at"] == "2026-04-05 10:30:00"
        assert second["state_payload"]["silent_base_pool_key"] == "inactive_focus"
        assert second["state_payload"]["silent_base_pool_entered_at"] == "2026-04-04 10:10:00"
        assert value_segment["segment"] == "top"


def test_trial_opening_fact_controls_transition_into_inactive_pool(app, monkeypatch):
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=85)
    _save_automation_config(app, questionnaire_seed)

    _seed_person(app, person_id=801, mobile="13800138801")
    _seed_bound_external(app, person_id=801, external_userid="wm_trial_gate", mobile="13800138801", customer_name="试用门槛客户")
    _create_questionnaire_submission(
        app,
        questionnaire_seed,
        submission_id=8501,
        external_userid="wm_trial_gate",
        mobile_snapshot="13800138801",
        hit_question_count=4,
        submitted_at="2026-04-04 11:00:00",
    )
    _freeze_state_time(monkeypatch, timestamp="2026-04-04 11:15:00")

    with app.app_context():
        before = evaluate_customer_marketing_state(external_userid="wm_trial_gate")
        assert before["stage_key"] == "pool/new_user"
        assert before["eligible_for_conversion"] is False
        assert before["state_payload"]["trial_opened"] is False
        assert before["exit_reason"] == "trial_not_opened"

    _seed_trial_opening_fact(
        app,
        mobile="13800138801",
        external_userid="wm_trial_gate",
        customer_name="试用门槛客户",
        opened_at="2026-04-04 11:30:00",
    )
    _freeze_state_time(monkeypatch, timestamp="2026-04-04 11:35:00")

    with app.app_context():
        after = evaluate_customer_marketing_state(external_userid="wm_trial_gate")
        assert after["stage_key"] == "pool/inactive_focus"
        assert after["eligible_for_conversion"] is True
        assert after["entered_at"] == "2026-04-04 11:35:00"
        assert after["state_payload"]["trial_opened"] is True
        assert after["state_payload"]["trial_opened_source"] == "test_seed"
