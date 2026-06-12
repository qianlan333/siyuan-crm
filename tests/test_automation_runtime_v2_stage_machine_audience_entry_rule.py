from __future__ import annotations

import json

from aicrm_next.automation_runtime_v2.domain import EVENT_CHANNEL_ENTERED, EVENT_QUESTIONNAIRE_SUBMITTED
from aicrm_next.automation_runtime_v2.stage_machine import resolve_next_stage

from tests.automation_runtime_v2_test_helpers import db, seed_program


def _write_audience_entry_rule(program_id: int, payload: dict) -> None:
    conn = db()
    conn.execute(
        """
        INSERT INTO automation_program_config_block (program_id, block_key, payload_json, status)
        VALUES (?, 'audience_entry_rule', CAST(? AS jsonb), 'published')
        ON CONFLICT (program_id, block_key) DO UPDATE
        SET payload_json = EXCLUDED.payload_json,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(program_id), json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def _audience_rule(*, rules: list[dict] | None = None, review_enabled: bool = True, questionnaire_id: int = 21) -> dict:
    return {
        "rules": rules or [],
        "questionnaire_review": {
            "enabled": review_enabled,
            "selected_questionnaire_id": questionnaire_id,
        },
    }


def _membership(program_id: int, external: str = "wm_stage_rule", stage: str = "pending_questionnaire") -> dict:
    return {
        "id": 1,
        "program_id": int(program_id),
        "external_userid": external,
        "phone": "",
        "current_stage": stage,
        "current_stage_entry_id": None,
    }


def test_channel_entered_uses_channel_rule_pending_when_questionnaire_review_enabled(next_pg_schema):
    program_id = seed_program("runtime_v2_stage_rule_channel")
    _write_audience_entry_rule(
        program_id,
        _audience_rule(
            rules=[
                {
                    "event": "channel_enter",
                    "enabled": True,
                    "condition_type": "any_entry_channel",
                    "target_audience_code": "pending_questionnaire",
                }
            ]
        ),
    )

    result = resolve_next_stage(
        {"event_type": EVENT_CHANNEL_ENTERED, "program_id": program_id, "external_userid": "wm_rule_channel"},
        _membership(program_id, external="wm_rule_channel"),
        {},
    )

    assert result.target_stage == "pending_questionnaire"
    assert result.entry_reason == "audience_entry_rule_channel_entered"
    assert result.diagnostics["questionnaire_review_enabled"] is True
    assert result.diagnostics["matched_rule_event"] == "channel_enter"
    assert result.diagnostics["matched_rule_target"] == "pending_questionnaire"


def test_channel_entered_requires_questionnaire_even_without_rules(next_pg_schema):
    program_id = seed_program("runtime_v2_stage_rule_review_only")
    _write_audience_entry_rule(program_id, _audience_rule(review_enabled=True))

    result = resolve_next_stage(
        {"event_type": EVENT_CHANNEL_ENTERED, "program_id": program_id, "external_userid": "wm_review_only"},
        _membership(program_id, external="wm_review_only"),
        {},
    )

    assert result.target_stage == "pending_questionnaire"
    assert result.entry_reason == "channel_entered_requires_questionnaire"
    assert result.diagnostics["questionnaire_review_enabled"] is True


def test_channel_entered_successful_payment_still_wins(next_pg_schema):
    program_id = seed_program("runtime_v2_stage_rule_paid")
    external = "wm_rule_paid"
    _write_audience_entry_rule(program_id, _audience_rule(review_enabled=True))
    conn = db()
    conn.execute(
        """
        INSERT INTO wechat_pay_orders (out_trade_no, external_userid, status, trade_state)
        VALUES ('runtime-rule-paid', ?, 'paid', 'SUCCESS')
        """,
        (external,),
    )
    conn.commit()

    result = resolve_next_stage(
        {"event_type": EVENT_CHANNEL_ENTERED, "program_id": program_id, "external_userid": external},
        _membership(program_id, external=external),
        {},
    )

    assert result.target_stage == "converted"
    assert result.entry_reason == "payment_already_succeeded"


def test_channel_entered_existing_matching_questionnaire_submission_enters_operating(next_pg_schema):
    program_id = seed_program("runtime_v2_stage_rule_existing_questionnaire")
    external = "wm_rule_questionnaire"
    _write_audience_entry_rule(program_id, _audience_rule(review_enabled=True, questionnaire_id=21))
    conn = db()
    conn.execute(
        """
        INSERT INTO questionnaire_submissions (questionnaire_id, external_userid, respondent_key)
        VALUES (21, ?, 'runtime-rule-questionnaire')
        """,
        (external,),
    )
    conn.commit()

    result = resolve_next_stage(
        {"event_type": EVENT_CHANNEL_ENTERED, "program_id": program_id, "external_userid": external},
        _membership(program_id, external=external),
        {},
    )

    assert result.target_stage == "operating"
    assert result.entry_reason == "questionnaire_already_submitted"
    assert result.diagnostics["questionnaire_id_matched"] is True


def test_questionnaire_submitted_matching_id_enters_rule_target(next_pg_schema):
    program_id = seed_program("runtime_v2_stage_rule_questionnaire_match")
    _write_audience_entry_rule(
        program_id,
        _audience_rule(
            rules=[
                {
                    "event": "questionnaire_submitted",
                    "enabled": True,
                    "condition_type": "questionnaire_id_matched",
                    "target_audience_code": "operating",
                }
            ],
            questionnaire_id=21,
        ),
    )

    result = resolve_next_stage(
        {"event_type": EVENT_QUESTIONNAIRE_SUBMITTED, "program_id": program_id, "external_userid": "wm_match", "payload_json": {"questionnaire_id": 21}},
        _membership(program_id, external="wm_match"),
        {},
    )

    assert result.target_stage == "operating"
    assert result.entry_reason == "audience_entry_rule_questionnaire_submitted"
    assert result.diagnostics["event_questionnaire_id"] == 21
    assert result.diagnostics["questionnaire_id_matched"] is True


def test_questionnaire_submitted_non_matching_id_keeps_stage(next_pg_schema):
    program_id = seed_program("runtime_v2_stage_rule_questionnaire_mismatch")
    _write_audience_entry_rule(
        program_id,
        _audience_rule(
            rules=[
                {
                    "event": "questionnaire_submitted",
                    "enabled": True,
                    "condition_type": "questionnaire_id_matched",
                    "target_audience_code": "operating",
                }
            ],
            questionnaire_id=21,
        ),
    )

    result = resolve_next_stage(
        {"event_type": EVENT_QUESTIONNAIRE_SUBMITTED, "program_id": program_id, "external_userid": "wm_mismatch", "payload_json": {"questionnaire_id": 99}},
        _membership(program_id, external="wm_mismatch"),
        {},
    )

    assert result.target_stage == "pending_questionnaire"
    assert result.changed is False
    assert result.entry_reason == "questionnaire_id_not_matched"
    assert result.diagnostics["event_questionnaire_id"] == 99
    assert result.diagnostics["selected_questionnaire_id"] == 21
    assert result.diagnostics["questionnaire_id_matched"] is False
