from __future__ import annotations

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion import program_repo, repo
from wecom_ability_service.domains.automation_conversion.admission_service import admit_channel_contact_to_program
from wecom_ability_service.domains.automation_conversion.channel_binding_service import bind_channels_to_program
from wecom_ability_service.domains.automation_conversion.member_state_service import handle_channel_enter_from_callback


def _default_program_id() -> int:
    program = program_repo.get_default_program_row()
    if not program:
        program = program_repo.insert_program_row(
            {
                "program_code": "signup_conversion_v1",
                "program_name": "默认自动化转化方案",
                "description": "test default program",
                "status": "active",
                "config_json": {},
                "created_by": "test",
                "updated_by": "test",
            }
        )
        get_db().commit()
    return int(program["id"])


def _create_channel(code: str, *, program_id: int | None = None) -> dict:
    channel = repo.save_channel(
        {
            "program_id": program_id,
            "channel_code": code,
            "channel_name": code,
            "qr_url": "",
            "qr_ticket": "",
            "scene_value": f"scene_{code}",
            "welcome_message": "",
            "auto_accept_friend": False,
            "entry_tag_id": "",
            "entry_tag_name": "",
            "entry_tag_group_name": "",
            "owner_staff_id": "sales_01",
            "status": "active",
        }
    )
    get_db().commit()
    return channel


def _save_audience_entry_rule(program_id: int, payload: dict) -> None:
    program_repo.upsert_config_block_row(program_id, "audience_entry_rule", payload, status="saved")
    get_db().commit()


def _seed_questionnaire_submission(*, external_contact_id: str, submitted_at: str) -> int:
    db = get_db()
    questionnaire = db.execute(
        """
        INSERT INTO questionnaires (slug, name, title, description)
        VALUES ('admission-q', 'Admission Q', 'Admission Q', '')
        RETURNING id
        """
    ).fetchone()
    questionnaire_id = int(questionnaire["id"])
    db.execute(
        """
        INSERT INTO questionnaire_submissions (
            questionnaire_id, respondent_key, external_userid, mobile_snapshot,
            total_score, submitted_at
        )
        VALUES (?, ?, ?, '', 0, ?)
        """,
        (questionnaire_id, external_contact_id, external_contact_id, submitted_at),
    )
    db.commit()
    return questionnaire_id


def _seed_paid_order(*, external_contact_id: str, product_code: str, paid_at: str) -> None:
    get_db().execute(
        """
        INSERT INTO wechat_pay_orders (
            out_trade_no, product_code, product_name, amount_total, external_userid,
            status, trade_state, transaction_id, paid_at, created_at, updated_at
        )
        VALUES (?, ?, ?, 9900, ?, 'paid', 'SUCCESS', ?, ?, ?, ?)
        """,
        (
            f"order-{external_contact_id}-{product_code}",
            product_code,
            product_code,
            external_contact_id,
            f"tx-{external_contact_id}-{product_code}",
            paid_at,
            paid_at,
            paid_at,
        ),
    )
    get_db().commit()


def test_standalone_channel_enter_does_not_create_program_or_legacy_member(app):
    with app.app_context():
        channel = _create_channel("standalone-channel")

        result = handle_channel_enter_from_callback(
            external_contact_id="wm_standalone_001",
            payload_json={"state": channel["scene_value"]},
            channel=channel,
            follow_user_userid="sales_01",
        )

        assert result["handled"] is True
        assert result["mode"] == "standalone_channel"
        assert result["program_member_written"] is False
        assert get_db().execute("SELECT COUNT(*) AS total FROM automation_program_member").fetchone()["total"] == 0
        assert get_db().execute("SELECT COUNT(*) AS total FROM automation_member").fetchone()["total"] == 0
        contact = get_db().execute(
            """
            SELECT enter_count, external_contact_id
            FROM automation_channel_contact
            WHERE channel_id = ?
            """,
            (int(channel["id"]),),
        ).fetchone()
        assert contact["external_contact_id"] == "wm_standalone_001"
        assert int(contact["enter_count"]) == 1


def test_historical_questionnaire_fact_passes_without_backdating_operating_time(app):
    with app.app_context():
        program_id = _default_program_id()
        channel = _create_channel("questionnaire-pass-channel")
        bind_result = bind_channels_to_program(program_id, [int(channel["id"])], {}, "tester")
        binding_id = int(bind_result["bindings"][0]["id"])
        questionnaire_id = _seed_questionnaire_submission(
            external_contact_id="wm_questionnaire_before_pool",
            submitted_at="2026-01-02 09:00:00",
        )
        _save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": True, "selected_questionnaire_id": questionnaire_id},
                "conversion_review": {"enabled": False},
            },
        )

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_questionnaire_before_pool",
            follow_user_userid="sales_01",
            trigger_time="2026-05-23 10:00:00",
        )

        assert result["admission_status"] == "accepted"
        assert result["program_member"]["current_stage_code"] == "operating"
        assert result["program_member"]["current_stage_entered_at"] == "2026-05-23 10:00:00"
        legacy_entry = get_db().execute(
            """
            SELECT ae.entered_at, ae.audience_code
            FROM automation_member_audience_entry ae
            INNER JOIN automation_member m ON m.id = ae.member_id
            WHERE m.external_contact_id = ?
              AND ae.is_current = TRUE
            """,
            ("wm_questionnaire_before_pool",),
        ).fetchone()
        assert legacy_entry["audience_code"] == "operating"
        assert legacy_entry["entered_at"] == "2026-05-23 10:00:00"


def test_order_review_waiting_and_duplicate_scan_keep_entry_times(app):
    with app.app_context():
        program_id = _default_program_id()
        channel = _create_channel("order-review-channel")
        binding_id = int(bind_channels_to_program(program_id, [int(channel["id"])], {}, "tester")["bindings"][0]["id"])
        _save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": True, "selected_product_id": "intro_product"},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": False},
            },
        )

        first = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_order_waiting",
            follow_user_userid="sales_01",
            trigger_time="2026-05-23 10:00:00",
        )
        second = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_order_waiting",
            follow_user_userid="sales_01",
            trigger_time="2026-05-23 11:00:00",
        )

        assert first["admission_status"] == "waiting"
        assert first["program_member"]["current_stage_code"] == "order_review"
        assert second["admission_status"] == "duplicate_active"
        assert second["program_member"]["pool_entered_at"] == "2026-05-23 10:00:00"
        assert second["program_member"]["current_stage_entered_at"] == "2026-05-23 10:00:00"
        history_total = get_db().execute(
            "SELECT COUNT(*) AS total FROM automation_program_member_stage_history"
        ).fetchone()["total"]
        assert int(history_total) == 1


def test_conversion_product_paid_before_pool_enters_converted_at_pool_time(app):
    with app.app_context():
        program_id = _default_program_id()
        channel = _create_channel("converted-channel")
        binding_id = int(bind_channels_to_program(program_id, [int(channel["id"])], {}, "tester")["bindings"][0]["id"])
        _seed_paid_order(
            external_contact_id="wm_converted_before_pool",
            product_code="consult_product",
            paid_at="2026-01-03 08:30:00",
        )
        _save_audience_entry_rule(
            program_id,
            {
                "order_review": {"enabled": False},
                "questionnaire_review": {"enabled": False},
                "conversion_review": {"enabled": True, "selected_product_id": "consult_product"},
            },
        )

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_converted_before_pool",
            follow_user_userid="sales_01",
            trigger_time="2026-05-23 12:00:00",
        )

        assert result["admission_status"] == "converted"
        assert result["program_member"]["current_stage_code"] == "converted"
        assert result["program_member"]["current_audience_code"] == "converted"
        assert result["program_member"]["current_stage_entered_at"] == "2026-05-23 12:00:00"
