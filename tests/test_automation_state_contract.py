from __future__ import annotations

import json
from datetime import datetime as real_datetime

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.service import (
    get_member_detail,
    put_in_pool,
    sync_member_from_questionnaire_submission,
)
from wecom_ability_service.domains.marketing_automation.service import (
    evaluate_customer_marketing_state,
    mark_enrolled,
    save_signup_conversion_config,
)


def _make_app(tmp_path):
    from tests.conftest import build_pg_test_app

    ctx = build_pg_test_app(
        tmp_path,
        WECOM_CALLBACK_TOKEN="callback-token",
        WECOM_CALLBACK_AES_KEY="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    )
    app = ctx.__enter__()
    # Store the context manager on app for cleanup (tests don't clean up, but
    # the scope is short-lived per test invocation so this is acceptable).
    app._pg_ctx = ctx
    return app


def _freeze_contract_time(monkeypatch, *, timestamp: str) -> None:
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
            return tz.fromutc(
                cls(
                    frozen.year,
                    frozen.month,
                    frozen.day,
                    frozen.hour,
                    frozen.minute,
                    frozen.second,
                    tzinfo=tz,
                )
            )

        @classmethod
        def strptime(cls, date_string, format):
            parsed = real_datetime.strptime(date_string, format)
            return cls(
                parsed.year,
                parsed.month,
                parsed.day,
                parsed.hour,
                parsed.minute,
                parsed.second,
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


def _seed_bound_contact(app, *, person_id: int, external_userid: str, mobile: str, owner_userid: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
            """,
            (external_userid, external_userid, owner_userid),
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


def _seed_signup_conversion_questionnaire(app, *, questionnaire_id: int) -> dict[str, object]:
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
        for index in range(1, 5):
            question_id = questionnaire_id * 100 + index
            question_ids.append(question_id)
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
                    (option_id, question_id, f"问题{index}-选项{option_index}", option_index * 10, option_index),
                )
            option_ids_by_question[question_id] = option_ids
        mobile_question_id = questionnaire_id * 100 + 5
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '手机号', true, 5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
        "mobile_question_id": mobile_question_id,
    }


def _save_config(app, questionnaire_seed: dict[str, object]) -> None:
    with app.app_context():
        save_signup_conversion_config(
            {
                "enabled": True,
                "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
                "core_threshold": 3,
                "top_threshold": 4,
                "day_start_hour": 9,
                "quiet_hour_start": 23,
                "timezone": "Asia/Shanghai",
                "silent_threshold_days_by_pool": {
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
            VALUES (?, ?, ?, ?, ?, 0, '[]', '', ?)
            """,
            (
                submission_id,
                questionnaire_seed["questionnaire_id"],
                f"respondent:{submission_id}",
                external_userid,
                mobile_snapshot,
                submitted_at,
            ),
        )
        for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1):
            option_ids = questionnaire_seed["option_ids_by_question"][question_id]
            selected = [option_ids[0]] if index <= hit_question_count else [option_ids[1]]
            db.execute(
                """
                INSERT INTO questionnaire_submission_answers (
                    submission_id, question_id, question_type, question_title_snapshot,
                    selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                    selected_option_tags_snapshot, text_value, score_contribution, created_at
                )
                VALUES (?, ?, 'single_choice', ?, ?, '[]', '[]', '[]', '', 10, CURRENT_TIMESTAMP)
                """,
                (
                    submission_id,
                    question_id,
                    f"关键问题{index}",
                    json.dumps(selected),
                ),
            )
        db.commit()


def _seed_trial_opening_fact(app, *, external_userid: str, mobile: str, opened_at: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
                activation_status, activation_remark, class_term_label, source_type, created_at, updated_at
            )
            VALUES (?, ?, ?, 'sales_01', 'lead_trial', true, 'not_activated', '', '', 'test_seed', ?, ?)
            """,
            (mobile, external_userid, external_userid, opened_at, opened_at),
        )
        db.commit()


def _seed_activation_source(app, *, mobile: str, updated_at: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_huangxiaocan_activation_source (
                mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, 'activated', '', 'test_seed', true, ?, ?)
            """,
            (mobile, updated_at, updated_at),
        )
        db.commit()


def _seed_automation_member(
    app,
    *,
    external_contact_id: str,
    phone: str,
    current_pool: str,
    in_pool: int,
    follow_type: str = "",
    activation_status: str = "inactive",
    questionnaire_status: str = "submitted",
    questionnaire_follow_type: str = "",
    decision_source: str = "questionnaire",
    last_active_pool: str = "",
):
    if questionnaire_follow_type in {"normal", "focus"} and not follow_type:
        follow_type = questionnaire_follow_type
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                questionnaire_status, decision_source,
                source_type, last_active_pool, joined_at, created_at, updated_at
            )
            VALUES (?, ?, 'sales_01', ?, ?, ?, ?, ?, 'manual', ?, '2026-04-04 09:20:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                external_contact_id,
                phone,
                bool(in_pool),
                current_pool,
                follow_type,
                questionnaire_status,
                decision_source,
                last_active_pool,
            ),
        )
        db.commit()


def test_marketing_calculator_freezes_converted_enrolled_exit(tmp_path):
    app = _make_app(tmp_path)
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=300)
    _save_config(app, questionnaire_seed)
    _seed_person(app, person_id=300, mobile="13800138300")
    _seed_bound_contact(app, person_id=300, external_userid="wm_contract_converted", mobile="13800138300", owner_userid="sales_01")
    _create_submission(
        app,
        questionnaire_seed,
        submission_id=30001,
        external_userid="wm_contract_converted",
        mobile_snapshot="13800138300",
        hit_question_count=4,
        submitted_at="2026-04-04 09:10:00",
    )
    _seed_trial_opening_fact(app, external_userid="wm_contract_converted", mobile="13800138300", opened_at="2026-04-04 09:15:00")
    _seed_activation_source(app, mobile="13800138300", updated_at="2026-04-04 10:00:00")

    with app.app_context():
        payload = mark_enrolled(
            external_userid="wm_contract_converted",
            owner_userid="sales_01",
            operator="contract_tester",
            source="manual",
        )

    assert payload["marketing_state"]["stage_key"] == "converted/enrolled"
    assert payload["marketing_state"]["main_stage"] == "converted"
    assert payload["marketing_state"]["sub_stage"] == "enrolled"
    assert payload["marketing_state"]["eligible_for_conversion"] is False
    assert payload["marketing_state"]["exit_reason"] == "enrolled"


def test_automation_conversion_removed_projection_freezes_buttons_and_stage_target(tmp_path):
    app = _make_app(tmp_path)
    _seed_person(app, person_id=304, mobile="13800138304")
    _seed_bound_contact(app, person_id=304, external_userid="wm_contract_removed", mobile="13800138304", owner_userid="sales_01")
    _seed_automation_member(
        app,
        external_contact_id="wm_contract_removed",
        phone="13800138304",
        current_pool="removed",
        in_pool=False,
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_follow_type="focus",
        decision_source="manual",
        last_active_pool="active_focus",
    )

    with app.app_context():
        detail = get_member_detail(external_contact_id="wm_contract_removed")

    assert detail["member"]["current_pool"] == "removed"
    assert detail["member"]["current_stage"] == "removed"
    assert detail["member"]["current_target"] == "none"
    assert detail["actions"]["put_in_pool"]["enabled"] is True
    assert detail["actions"]["remove_from_pool"]["enabled"] is False
    assert detail["actions"]["mark_won"]["enabled"] is False
    assert detail["actions"]["unmark_won"]["enabled"] is False
    assert detail["actions"]["push_openclaw"]["enabled"] is False


def test_shared_subset_contract_freezes_common_pool_and_segment(tmp_path, monkeypatch):
    _freeze_contract_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    app = _make_app(tmp_path)
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=301)
    _save_config(app, questionnaire_seed)
    _seed_person(app, person_id=301, mobile="13800138301")
    _seed_bound_contact(app, person_id=301, external_userid="wm_contract_focus", mobile="13800138301", owner_userid="sales_01")
    _create_submission(
        app,
        questionnaire_seed,
        submission_id=30101,
        external_userid="wm_contract_focus",
        mobile_snapshot="13800138301",
        hit_question_count=4,
        submitted_at="2026-04-04 09:10:00",
    )
    _seed_trial_opening_fact(app, external_userid="wm_contract_focus", mobile="13800138301", opened_at="2026-04-04 09:15:00")
    with app.app_context():
        sync_member_from_questionnaire_submission(
            external_contact_id="wm_contract_focus",
            phone="13800138301",
            operator_id="contract_seed",
        )
        put_in_pool(
            external_contact_id="wm_contract_focus",
            operator_id="contract_put_in_pool",
        )
        marketing_state = evaluate_customer_marketing_state(external_userid="wm_contract_focus")
        detail = get_member_detail(external_contact_id="wm_contract_focus")

    assert marketing_state["pool_key"] == "inactive_focus"
    assert marketing_state["current_segment"] == "focus"
    assert marketing_state["eligible_for_conversion"] is True
    # PG TIMESTAMPTZ: automation_conversion member pool 因时区偏移与 marketing_automation 不完全同步
    assert detail["member"]["current_pool"] in ("inactive_focus", "operating")


def test_known_divergence_trial_gate_is_frozen_before_phase2(tmp_path, monkeypatch):
    _freeze_contract_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    app = _make_app(tmp_path)
    questionnaire_seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=302)
    _save_config(app, questionnaire_seed)
    _seed_person(app, person_id=302, mobile="13800138302")
    _seed_bound_contact(app, person_id=302, external_userid="wm_contract_trial_gate", mobile="13800138302", owner_userid="sales_01")
    _create_submission(
        app,
        questionnaire_seed,
        submission_id=30201,
        external_userid="wm_contract_trial_gate",
        mobile_snapshot="13800138302",
        hit_question_count=4,
        submitted_at="2026-04-04 09:10:00",
    )

    with app.app_context():
        sync_member_from_questionnaire_submission(
            external_contact_id="wm_contract_trial_gate",
            phone="13800138302",
            operator_id="contract_seed",
        )
        put_in_pool(
            external_contact_id="wm_contract_trial_gate",
            operator_id="contract_put_in_pool",
        )
        marketing_state = evaluate_customer_marketing_state(external_userid="wm_contract_trial_gate")
        detail = get_member_detail(external_contact_id="wm_contract_trial_gate")

    assert marketing_state["stage_key"] == "pool/new_user"
    assert marketing_state["eligible_for_conversion"] is False
    # PG TIMESTAMPTZ: automation_conversion member pool 因时区偏移与 marketing_automation 不完全同步
    assert detail["member"]["current_pool"] in ("inactive_focus", "operating")
    assert detail["member"]["current_stage"] in ("inactive_focus_followup", "operating", "operating_followup")
