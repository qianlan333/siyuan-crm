from __future__ import annotations

import json

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

from tests.automation_runtime_v2_test_helpers import count, db, seed_program, seed_task


def _write_audience_entry_rule(program_id: int) -> None:
    payload = {
        "rules": [
            {
                "event": "channel_enter",
                "enabled": True,
                "condition_type": "any_entry_channel",
                "target_audience_code": "pending_questionnaire",
            },
            {
                "event": "questionnaire_submitted",
                "enabled": True,
                "condition_type": "questionnaire_id_matched",
                "target_audience_code": "operating",
            },
        ],
        "questionnaire_review": {
            "enabled": True,
            "selected_questionnaire_id": 21,
        },
    }
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


def test_channel_enter_waits_for_matching_questionnaire_before_operating_plan(next_pg_schema):
    program_id = seed_program("runtime_v2_requires_questionnaire_chain")
    _write_audience_entry_rule(program_id)
    seed_task(
        program_id,
        trigger_type="audience_entered",
        target_stage="operating",
        content_text="提交问卷后进入运营",
        agent_config={"sender_userid": "HuangYouCan"},
    )

    channel = process_event_payload(
        AutomationEventInput(
            event_type="channel_entered",
            source_type="test",
            source_id="requires-questionnaire-channel",
            program_id=program_id,
            external_userid="wm_requires_questionnaire",
        )
    )

    assert channel["membership"]["current_stage"] == "pending_questionnaire"
    assert channel["stage_entry"]["stage_code"] == "pending_questionnaire"
    assert channel["stage_entry"]["entry_reason"] == "audience_entry_rule_channel_entered"
    assert count("automation_task_plan_v2") == 0
    assert count("broadcast_jobs") == 0
    assert (
        db()
        .execute(
            """
            SELECT COUNT(*) AS count
            FROM automation_stage_entry_v2
            WHERE program_id = ? AND stage_code = 'operating'
            """,
            (program_id,),
        )
        .fetchone()["count"]
        == 0
    )

    questionnaire = process_event_payload(
        AutomationEventInput(
            event_type="questionnaire_submitted",
            source_type="questionnaire",
            source_id="requires-questionnaire-submission",
            program_id=program_id,
            external_userid="wm_requires_questionnaire",
            payload_json={"questionnaire_id": 21, "answers": {"need": "想提升私域自动化转化"}},
        )
    )

    assert questionnaire["membership"]["current_stage"] == "operating"
    assert questionnaire["stage_entry"]["stage_code"] == "operating"
    assert questionnaire["stage_entry"]["entry_reason"] == "audience_entry_rule_questionnaire_submitted"
    assert count("automation_task_plan_v2") == 1
    assert count("broadcast_jobs") == 1


def test_non_matching_questionnaire_does_not_trigger_operating_plan(next_pg_schema):
    program_id = seed_program("runtime_v2_requires_questionnaire_mismatch_chain")
    _write_audience_entry_rule(program_id)
    seed_task(
        program_id,
        trigger_type="audience_entered",
        target_stage="operating",
        content_text="提交问卷后进入运营",
        agent_config={"sender_userid": "HuangYouCan"},
    )

    process_event_payload(
        AutomationEventInput(
            event_type="channel_entered",
            source_type="test",
            source_id="mismatch-channel",
            program_id=program_id,
            external_userid="wm_questionnaire_mismatch",
        )
    )
    mismatch = process_event_payload(
        AutomationEventInput(
            event_type="questionnaire_submitted",
            source_type="questionnaire",
            source_id="mismatch-submission",
            program_id=program_id,
            external_userid="wm_questionnaire_mismatch",
            payload_json={"questionnaire_id": 99, "answers": {"need": "不匹配问卷"}},
        )
    )

    assert mismatch["membership"]["current_stage"] == "pending_questionnaire"
    assert mismatch["stage_entry"] is None
    assert count("automation_task_plan_v2") == 0
    assert count("broadcast_jobs") == 0
