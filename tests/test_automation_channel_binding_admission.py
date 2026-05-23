from __future__ import annotations

import json

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.admission_service import (
    admit_channel_contact_to_program,
    import_channel_contacts_to_program,
)
from wecom_ability_service.domains.automation_conversion.channel_binding_service import (
    archive_program_channel_binding,
    bind_channels_to_program,
)
from wecom_ability_service.domains.automation_conversion.member_state_service import handle_channel_enter_from_callback
from wecom_ability_service.domains.automation_conversion.program_setup_service import build_publish_check, publish_full, save_segmentation

from automation_channel_admission_helpers import (
    create_channel,
    create_choice_questionnaire,
    create_program,
    disabled_entry_rule,
    dt_text,
    fetch_channel_contact,
    fetch_program_member,
    save_audience_entry_rule,
    seed_order,
    seed_questionnaire_submission,
    set_callback_now,
    table_count,
)


T0 = "2026-05-22 09:00:00"
T1 = "2026-05-23 10:00:00"
T2 = "2026-05-24 11:30:00"


def _bind(program_id: int, channel_id: int, payload: dict | None = None) -> int:
    return int(bind_channels_to_program(program_id, [channel_id], payload or {}, "pytest")["bindings"][0]["id"])


def _scan(channel: dict, external_contact_id: str, monkeypatch, at: str = T1) -> dict:
    set_callback_now(monkeypatch, at)
    return handle_channel_enter_from_callback(
        external_contact_id=external_contact_id,
        payload_json={"state": channel["scene_value"], "event_log_id": f"event-{external_contact_id}-{at}"},
        channel=channel,
        follow_user_userid="sales_01",
    )


def _history(program_member_id: int) -> list[dict]:
    return [
        dict(row)
        for row in get_db()
        .execute(
            """
            SELECT stage_code, audience_code, entered_at, exited_at, entry_reason, source_event_type
            FROM automation_program_member_stage_history
            WHERE program_member_id = ?
            ORDER BY entered_at ASC, id ASC
            """,
            (int(program_member_id),),
        )
        .fetchall()
    ]


def test_scenario_1_standalone_channel_scan_only_records_channel_contact(app, monkeypatch):
    with app.app_context():
        create_program()
        channel = create_channel("ch_standalone")

        result = _scan(channel, "wm_user_001", monkeypatch, T1)

        assert result["mode"] == "standalone_channel"
        assert result["program_member_written"] is False
        contact = fetch_channel_contact(int(channel["id"]), "wm_user_001")
        assert contact is not None
        assert int(contact["enter_count"]) == 1
        assert dt_text(contact["first_channel_entered_at"]) == T1
        assert table_count("automation_program_member") == 0
        assert table_count("automation_program_member_stage_history") == 0
        attempts = get_db().execute("SELECT admission_status FROM automation_program_admission_attempt").fetchall()
        assert not attempts or attempts[0]["admission_status"] == "standalone_channel"


def test_scenario_2_binding_time_is_not_user_pool_time_when_rules_disabled(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_bound_before_scan")
        binding_id = _bind(program_id, int(channel["id"]))
        get_db().execute(
            "UPDATE automation_program_channel_binding SET bound_at = ? WHERE id = ?",
            (T0, binding_id),
        )
        get_db().commit()
        save_audience_entry_rule(program_id, disabled_entry_rule())

        result = admit_channel_contact_to_program(program_id, int(channel["id"]), binding_id, "wm_user_002", trigger_time=T1)

        assert result["admission_status"] == "accepted"
        assert result["reason"] == "audience_entry_rule_passed"
        member = result["program_member"]
        assert member["pool_entered_at"] == T1
        assert member["current_stage_code"] == "operating"
        assert member["current_audience_code"] == "operating"
        assert member["current_stage_entered_at"] == T1
        assert T0 not in {member["pool_entered_at"], member["current_stage_entered_at"]}


@pytest.mark.parametrize(
    ("order_kwargs", "case_label"),
    [
        ({}, "scenario_3_no_order"),
        ({"status": "pending", "trade_state": "NOTPAY"}, "scenario_4_unpaid_order"),
        ({"status": "paid", "trade_state": "SUCCESS", "refunded_amount_total": 9900}, "scenario_5_refunded_order"),
    ],
)
def test_scenarios_3_4_5_order_review_blocks_without_paid_unrefunded_order(app, order_kwargs, case_label):
    with app.app_context():
        program_id = create_program(f"p_{case_label}")
        channel = create_channel(f"ch_{case_label}")
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": True, "selected_product_id": "product_A"},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": False},
            },
        )
        if order_kwargs:
            seed_order(external_contact_id=f"wm_{case_label}", product_code="product_A", paid_at=T0, **order_kwargs)

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            f"wm_{case_label}",
            trigger_time=T1,
        )

        member = result["program_member"]
        assert result["admission_status"] == "waiting"
        assert result["reason"] == "order_review_pending"
        assert member["pool_entered_at"] == T1
        assert member["current_stage_code"] == "order_review"
        assert member["current_audience_code"] == "pending_questionnaire"
        assert member["current_stage_entered_at"] == T1
        assert table_count("automation_member_audience_entry", "audience_code = ?", ("operating",)) == 0


def test_scenario_6_paid_order_before_pool_passes_without_backdating(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_paid_order")
        binding_id = _bind(program_id, int(channel["id"]))
        seed_order(external_contact_id="wm_user_006", product_code="product_A", paid_at=T0)
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": True, "selected_product_id": "product_A"},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": False},
            },
        )

        result = admit_channel_contact_to_program(program_id, int(channel["id"]), binding_id, "wm_user_006", trigger_time=T1)

        assert result["admission_status"] == "accepted"
        assert result["program_member"]["current_stage_code"] == "operating"
        assert result["program_member"]["pool_entered_at"] == T1
        assert result["program_member"]["current_stage_entered_at"] == T1


def test_scenario_7_paid_order_then_missing_questionnaire_waits_at_questionnaire_review(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_questionnaire_wait")
        binding_id = _bind(program_id, int(channel["id"]))
        questionnaire = create_choice_questionnaire("q_scenario_7")
        seed_order(external_contact_id="wm_user_007", product_code="product_A", paid_at=T0)
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": True, "selected_product_id": "product_A"},
                "questionnaire_review": {"enabled": True, "selected_questionnaire_id": questionnaire["id"]},
                "conversion_review": {"enabled": False},
            },
        )

        result = admit_channel_contact_to_program(program_id, int(channel["id"]), binding_id, "wm_user_007", trigger_time=T1)

        assert result["admission_status"] == "waiting"
        assert result["reason"] == "questionnaire_review_pending"
        assert result["program_member"]["current_stage_code"] == "questionnaire_review"
        assert result["program_member"]["current_audience_code"] == "pending_questionnaire"
        assert result["program_member"]["current_stage_entered_at"] == T1


def test_scenario_8_pre_pool_questionnaire_passes_but_day0_starts_at_pool_time(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_pre_pool_questionnaire")
        binding_id = _bind(program_id, int(channel["id"]))
        questionnaire = create_choice_questionnaire("q_scenario_8")
        seed_questionnaire_submission(
            questionnaire_id=questionnaire["id"],
            external_contact_id="wm_user_008",
            submitted_at=T0,
        )
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": True, "selected_questionnaire_id": questionnaire["id"]},
                "conversion_review": {"enabled": False},
            },
        )

        result = admit_channel_contact_to_program(program_id, int(channel["id"]), binding_id, "wm_user_008", trigger_time=T1)

        assert result["admission_status"] == "accepted"
        assert result["program_member"]["current_stage_code"] == "operating"
        assert result["program_member"]["pool_entered_at"] == T1
        assert result["program_member"]["current_stage_entered_at"] == T1
        legacy_entry = get_db().execute(
            """
            SELECT e.entered_at
            FROM automation_member_audience_entry e
            JOIN automation_member m ON m.id = e.member_id
            WHERE m.external_contact_id = 'wm_user_008' AND e.is_current = TRUE
            """
        ).fetchone()
        assert legacy_entry["entered_at"] == T1


def test_scenario_9_post_pool_questionnaire_event_moves_to_operating_at_event_time(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_post_pool_questionnaire")
        binding_id = _bind(program_id, int(channel["id"]))
        questionnaire = create_choice_questionnaire("q_scenario_9")
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": True, "selected_questionnaire_id": questionnaire["id"]},
                "conversion_review": {"enabled": False},
            },
        )
        first = admit_channel_contact_to_program(program_id, int(channel["id"]), binding_id, "wm_user_009", trigger_time=T1)
        seed_questionnaire_submission(
            questionnaire_id=questionnaire["id"],
            external_contact_id="wm_user_009",
            submitted_at=T2,
        )

        second = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_user_009",
            trigger_time=T2,
            trigger_type="questionnaire_submission",
        )

        assert first["program_member"]["current_stage_code"] == "questionnaire_review"
        assert second["admission_status"] == "accepted"
        assert second["program_member"]["pool_entered_at"] == T1
        assert second["program_member"]["current_stage_code"] == "operating"
        assert second["program_member"]["current_stage_entered_at"] == T2
        history = _history(int(second["program_member"]["id"]))
        assert [row["stage_code"] for row in history] == ["questionnaire_review", "operating"]
        assert dt_text(history[0]["exited_at"]) == T2
        assert dt_text(history[1]["entered_at"]) == T2


def test_scenarios_10_11_conversion_before_and_after_pool_use_correct_entered_at(app):
    with app.app_context():
        program_id = create_program()
        before_channel = create_channel("ch_conversion_before")
        before_binding_id = _bind(program_id, int(before_channel["id"]))
        save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": True, "selected_product_id": "product_C"},
            },
        )
        seed_order(external_contact_id="wm_user_010", product_code="product_C", paid_at=T0)

        before = admit_channel_contact_to_program(
            program_id,
            int(before_channel["id"]),
            before_binding_id,
            "wm_user_010",
            trigger_time=T1,
        )

        assert before["admission_status"] == "converted"
        assert before["reason"] == "conversion_product_paid"
        assert before["program_member"]["current_stage_code"] == "converted"
        assert before["program_member"]["current_audience_code"] == "converted"
        assert before["program_member"]["current_stage_entered_at"] == T1

        after_channel = create_channel("ch_conversion_after")
        after_binding_id = _bind(program_id, int(after_channel["id"]))
        after_first = admit_channel_contact_to_program(
            program_id,
            int(after_channel["id"]),
            after_binding_id,
            "wm_user_011",
            trigger_time=T1,
        )
        seed_order(external_contact_id="wm_user_011", product_code="product_C", paid_at=T2)
        after_second = admit_channel_contact_to_program(
            program_id,
            int(after_channel["id"]),
            after_binding_id,
            "wm_user_011",
            trigger_time=T2,
            trigger_type="payment_success",
        )

        assert after_first["program_member"]["current_stage_code"] == "operating"
        assert after_second["program_member"]["pool_entered_at"] == T1
        assert after_second["program_member"]["current_stage_code"] == "converted"
        assert after_second["program_member"]["current_stage_entered_at"] == T2
        history = _history(int(after_second["program_member"]["id"]))
        assert [row["stage_code"] for row in history] == ["operating", "converted"]
        assert dt_text(history[0]["exited_at"]) == T2


def test_scenarios_12_13_14_segmentation_does_not_block_admission_but_full_publish_checks_config(app):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_segmentation")
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())

        no_config = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_user_012",
            trigger_time=T1,
        )
        assert no_config["admission_status"] == "accepted"
        assert no_config["cleaning_result"]["segmentation"]["segmentation_status"] == "not_configured"

        get_db().execute(
            """
            INSERT INTO automation_program_config_block (program_id, block_key, payload_json, status)
            VALUES (?, 'questionnaire_segmentation', CAST(? AS jsonb), 'saved')
            ON CONFLICT (program_id, block_key) DO UPDATE
            SET payload_json = EXCLUDED.payload_json, status = EXCLUDED.status
            """,
            (
                program_id,
                json.dumps({"default_strategy": "normal_question_rules", "strategies": {"normal_question_rules": {"enabled": True}}}),
            ),
        )
        get_db().commit()
        check = build_publish_check(program_id)
        full_messages = {item["message"] for item in check["full"]["items"] if not item["passed"]}
        assert check["full"]["passed"] is False
        assert "请选择当前方案使用的问卷" in full_messages
        with pytest.raises(ValueError, match="完整自动化发布检查未通过"):
            publish_full(program_id, operator_id="pytest")

        questionnaire = create_choice_questionnaire("q_scenario_14")
        save_segmentation(
            program_id,
            {
                "questionnaire_id": questionnaire["id"],
                "default_strategy": "normal_question_rules",
                "strategies": {
                    "normal_question_rules": {
                        "enabled": True,
                        "mode": "option_category",
                        "segmentation_question_id": questionnaire["question_id"],
                        "categories": [
                            {
                                "category_key": "seg_a",
                                "category_name": "A 类",
                                "option_ids": [questionnaire["option_a_id"]],
                            }
                        ],
                    }
                },
            },
        )
        matched_missing = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_user_014",
            trigger_time=T1,
        )
        assert matched_missing["admission_status"] == "accepted"
        assert matched_missing["cleaning_result"]["segmentation"]["segmentation_status"] == "questionnaire_missing"


def test_scenario_15_duplicate_scan_updates_channel_contact_but_not_pool_or_stage(app, monkeypatch):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_duplicate")
        _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())

        first = _scan(channel, "wm_user_015", monkeypatch, T1)
        second = _scan(channel, "wm_user_015", monkeypatch, T2)

        assert first["mode"] == "program_admission"
        assert second["admission_results"][0]["admission_status"] == "duplicate_active"
        contact = fetch_channel_contact(int(channel["id"]), "wm_user_015")
        assert int(contact["enter_count"]) == 2
        assert dt_text(contact["last_channel_entered_at"]) == T2
        member = second["admission_results"][0]["program_member"]
        assert member["pool_entered_at"] == T1
        assert member["current_stage_entered_at"] == T1
        assert table_count("automation_program_member_stage_history", "program_member_id = ? AND exited_at IS NULL", (member["id"],)) == 1
        assert table_count("automation_member_audience_entry", "is_current = TRUE") == 1


def test_scenarios_16_17_binding_later_does_not_import_until_next_scan(app, monkeypatch):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_bind_later")
        save_audience_entry_rule(program_id, disabled_entry_rule())

        _scan(channel, "wm_user_016", monkeypatch, T0)
        assert fetch_channel_contact(int(channel["id"]), "wm_user_016") is not None
        assert table_count("automation_program_member") == 0

        _bind(program_id, int(channel["id"]))
        assert table_count("automation_program_member") == 0
        assert table_count("automation_program_admission_attempt", "admission_status IN ('accepted', 'waiting')") == 0

        result = _scan(channel, "wm_user_016", monkeypatch, T2)
        member = result["admission_results"][0]["program_member"]
        assert result["admission_results"][0]["admission_status"] == "accepted"
        assert member["pool_entered_at"] == T2
        assert member["current_stage_code"] == "operating"


def test_scenarios_18_19_manual_import_defaults_to_import_time_and_marks_historical_override(app, monkeypatch):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_import")
        save_audience_entry_rule(program_id, disabled_entry_rule())
        _scan(channel, "wm_user_018", monkeypatch, T0)
        binding_id = _bind(program_id, int(channel["id"]))
        monkeypatch.setattr(
            "wecom_ability_service.domains.automation_conversion.admission_service._iso_now",
            lambda: T2,
        )

        dry_run = import_channel_contacts_to_program(program_id, channel_id=int(channel["id"]), operator_id="pytest", dry_run=True)
        assert dry_run["dry_run"] is True
        assert dry_run["planned_count"] == 1
        assert table_count("automation_program_member") == 0

        imported = import_channel_contacts_to_program(program_id, channel_id=int(channel["id"]), operator_id="pytest")
        assert imported["imported_count"] == 1
        member = fetch_program_member("wm_user_018", program_id)
        assert dt_text(member["pool_entered_at"]) == T2
        attempt = get_db().execute(
            "SELECT trigger_type, trigger_payload_json FROM automation_program_admission_attempt WHERE trigger_type = 'manual_import' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert attempt["trigger_type"] == "manual_import"

        historical_channel = create_channel("ch_import_historical")
        _scan(historical_channel, "wm_user_019", monkeypatch, T0)
        _bind(program_id, int(historical_channel["id"]))
        historical = import_channel_contacts_to_program(
            program_id,
            channel_id=int(historical_channel["id"]),
            operator_id="pytest",
            use_historical_channel_entered_at=True,
        )
        assert historical["historical_time_used"] is True
        assert historical["risk_acknowledged"] is True
        historical_member = fetch_program_member("wm_user_019", program_id)
        assert dt_text(historical_member["pool_entered_at"]) == T0
        last_attempt = get_db().execute(
            "SELECT trigger_payload_json FROM automation_program_admission_attempt ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert last_attempt["trigger_payload_json"]["historical_time_used"] is True
        assert binding_id > 0


def test_scenario_20_phase1_rejects_two_active_program_bindings_for_same_channel(app):
    with app.app_context():
        p1 = create_program("p1_multi")
        p2 = create_program("p2_multi")
        channel = create_channel("ch_multi")
        _bind(p1, int(channel["id"]))

        with pytest.raises(ValueError, match="Phase 1 暂不支持一个渠道码同时绑定多个自动化运营方案"):
            _bind(p2, int(channel["id"]))
        assert table_count(
            "automation_program_channel_binding",
            "channel_id = ? AND binding_status = 'active'",
            (int(channel["id"]),),
        ) == 1


def test_scenario_21_unbind_archives_binding_and_channel_remains_standalone(app, monkeypatch):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_unbind")
        binding_id = _bind(program_id, int(channel["id"]))
        archive_program_channel_binding(program_id, binding_id, "pytest")

        assert table_count("automation_channel", "id = ?", (int(channel["id"]),)) == 1
        binding = get_db().execute("SELECT binding_status FROM automation_program_channel_binding WHERE id = ?", (binding_id,)).fetchone()
        assert binding["binding_status"] == "archived"
        result = _scan(channel, "wm_user_021", monkeypatch, T1)
        assert result["mode"] == "standalone_channel"
        assert table_count("automation_program_member") == 0


def test_scenario_22_auto_enter_pool_false_records_manual_review_without_workflow_member(app, monkeypatch):
    with app.app_context():
        program_id = create_program()
        channel = create_channel("ch_manual_review")
        _bind(program_id, int(channel["id"]), {"auto_enter_pool": False})

        result = _scan(channel, "wm_user_022", monkeypatch, T1)

        admission = result["admission_results"][0]
        assert admission["admission_status"] == "manual_review"
        assert admission["reason"] == "auto_enter_pool_disabled"
        assert fetch_channel_contact(int(channel["id"]), "wm_user_022") is not None
        assert table_count("automation_program_member") == 0
        assert table_count("automation_member_audience_entry") == 0


def test_scenarios_23_24_reentry_policy_deny_and_new_cycle(app, monkeypatch):
    with app.app_context():
        deny_program_id = create_program("p_reentry_deny")
        deny_channel = create_channel("ch_reentry_deny")
        _bind(deny_program_id, int(deny_channel["id"]))
        save_audience_entry_rule(deny_program_id, disabled_entry_rule())
        first = _scan(deny_channel, "wm_user_023", monkeypatch, T1)["admission_results"][0]
        get_db().execute(
            "UPDATE automation_program_member SET in_program = FALSE, exited_at = ?, exit_reason = 'manual_exit' WHERE id = ?",
            (T2, first["program_member"]["id"]),
        )
        get_db().commit()

        denied = _scan(deny_channel, "wm_user_023", monkeypatch, "2026-05-25 12:00:00")["admission_results"][0]

        assert denied["admission_status"] == "rejected"
        stored = fetch_program_member("wm_user_023", deny_program_id)
        assert dt_text(stored["pool_entered_at"]) == T1
        assert stored["in_program"] is False

        new_cycle_program_id = create_program("p_reentry_new_cycle", config_json={"admission": {"reentry_policy": "new_cycle"}})
        new_cycle_channel = create_channel("ch_reentry_new_cycle")
        _bind(new_cycle_program_id, int(new_cycle_channel["id"]))
        save_audience_entry_rule(new_cycle_program_id, disabled_entry_rule())
        first_cycle = _scan(new_cycle_channel, "wm_user_024", monkeypatch, T1)["admission_results"][0]
        get_db().execute(
            "UPDATE automation_program_member SET in_program = FALSE, exited_at = ?, exit_reason = 'manual_exit' WHERE id = ?",
            (T2, first_cycle["program_member"]["id"]),
        )
        get_db().commit()

        second_cycle = _scan(new_cycle_channel, "wm_user_024", monkeypatch, "2026-05-25 12:00:00")["admission_results"][0]

        assert second_cycle["admission_status"] == "accepted"
        assert second_cycle["program_member"]["pool_entered_at"] == "2026-05-25 12:00:00"
        assert int(second_cycle["program_member"]["reentry_count"]) == 1
        assert table_count(
            "automation_program_member_stage_history",
            "program_member_id = ?",
            (int(second_cycle["program_member"]["id"]),),
        ) == 2


def test_scenario_25_multiple_channels_keep_first_source_and_update_latest_without_restart(app, monkeypatch):
    with app.app_context():
        program_id = create_program()
        ch1 = create_channel("ch_first_source")
        ch2 = create_channel("ch_latest_source")
        _bind(program_id, int(ch1["id"]))
        _bind(program_id, int(ch2["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())

        first = _scan(ch1, "wm_user_025", monkeypatch, T1)["admission_results"][0]
        second = _scan(ch2, "wm_user_025", monkeypatch, T2)["admission_results"][0]

        member = second["program_member"]
        assert first["admission_status"] == "accepted"
        assert second["admission_status"] == "duplicate_active"
        assert int(member["first_source_channel_id"]) == int(ch1["id"])
        assert int(member["latest_source_channel_id"]) == int(ch2["id"])
        assert member["pool_entered_at"] == T1
        assert table_count("automation_member_audience_entry", "is_current = TRUE") == 1
