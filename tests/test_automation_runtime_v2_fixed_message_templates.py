from __future__ import annotations

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.content_renderer import render_template_text
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

from tests.automation_runtime_v2_test_helpers import db, seed_program, seed_task


def test_render_template_text_unit_webhook_short_variable():
    rendered, diagnostics, reason = render_template_text(
        "note={{custom_note}}",
        {"webhook": {"variables": {"custom_note": "这是 webhook 推送测试"}}},
    )

    assert reason == ""
    assert rendered == "note=这是 webhook 推送测试"
    assert diagnostics["template_rendered"] is True
    assert diagnostics["template_variables_used"] == ["custom_note"]


def test_render_template_text_unit_missing_variable_fails():
    rendered, diagnostics, reason = render_template_text(
        "note={{missing_note}}",
        {"webhook": {"variables": {"custom_note": "exists"}}},
    )

    assert rendered == ""
    assert reason == "template_variable_missing"
    assert diagnostics["unresolved_template"] is True
    assert diagnostics["missing_variables"] == ["missing_note"]


def test_render_template_text_unit_rejects_unsafe_token():
    rendered, diagnostics, reason = render_template_text(
        "note={{custom_note.upper()}}",
        {"webhook": {"variables": {"custom_note": "exists"}}},
    )

    assert rendered == ""
    assert reason == "template_variable_missing"
    assert diagnostics["missing_variables"] == ["custom_note.upper()"]


def _plan(program_id: int) -> dict:
    row = db().execute(
        """
        SELECT *
        FROM automation_task_plan_v2
        WHERE program_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(program_id),),
    ).fetchone()
    return dict(row or {})


def _job_count(program_id: int) -> int:
    row = db().execute(
        """
        SELECT COUNT(*) AS count
        FROM broadcast_jobs bj
        INNER JOIN automation_task_plan_v2 tp ON (bj.content_payload->>'task_plan_id') = tp.id::text
        WHERE tp.program_id = ?
        """,
        (int(program_id),),
    ).fetchone()
    return int((row or {}).get("count") or 0)


def test_fixed_message_webhook_short_variable_renders(next_pg_schema):
    program_id = seed_program("runtime_v2_fixed_template_short")
    seed_task(program_id, trigger_type="webhook_push", content_text="【RuntimeV2真实链路测试】note={{custom_note}}", agent_config={"webhook_key": "demo"})

    result = process_event_payload(
        AutomationEventInput(
            event_type="webhook_received",
            source_type="webhook",
            source_id="fixed-template-short",
            program_id=program_id,
            external_userid="wm_template_short",
            payload_json={"webhook_key": "demo", "variables": {"custom_note": "这是 webhook 推送测试"}},
        )
    )

    plan = _plan(program_id)
    assert result["counts"]["enqueued"] == 1
    assert plan["rendered_content_json"]["content_text"] == "【RuntimeV2真实链路测试】note=这是 webhook 推送测试"
    assert "{{custom_note}}" not in plan["rendered_content_json"]["content_text"]
    assert plan["diagnostics_json"]["template_rendered"] is True
    assert plan["diagnostics_json"]["template_variables_used"] == ["custom_note"]


def test_fixed_message_webhook_explicit_variables_path_renders(next_pg_schema):
    program_id = seed_program("runtime_v2_fixed_template_explicit")
    seed_task(program_id, trigger_type="webhook_push", content_text="note={{webhook.variables.custom_note}}", agent_config={"webhook_key": "demo-explicit"})

    process_event_payload(
        AutomationEventInput(
            event_type="webhook_received",
            source_type="webhook",
            source_id="fixed-template-explicit",
            program_id=program_id,
            external_userid="wm_template_explicit",
            payload_json={"webhook_key": "demo-explicit", "variables": {"custom_note": "这是 webhook 推送测试"}},
        )
    )

    assert _plan(program_id)["rendered_content_json"]["content_text"] == "note=这是 webhook 推送测试"


def test_fixed_message_webhook_top_level_path_renders(next_pg_schema):
    program_id = seed_program("runtime_v2_fixed_template_top_level")
    seed_task(program_id, trigger_type="webhook_push", content_text="note={{webhook.custom_note}}", agent_config={"webhook_key": "demo-top"})

    process_event_payload(
        AutomationEventInput(
            event_type="webhook_received",
            source_type="webhook",
            source_id="fixed-template-top",
            program_id=program_id,
            external_userid="wm_template_top",
            payload_json={"webhook_key": "demo-top", "custom_note": "顶层 note"},
        )
    )

    assert _plan(program_id)["rendered_content_json"]["content_text"] == "note=顶层 note"


def test_fixed_message_missing_variable_fails_without_outbox(next_pg_schema):
    program_id = seed_program("runtime_v2_fixed_template_missing")
    seed_task(program_id, trigger_type="webhook_push", content_text="note={{missing_note}}", agent_config={"webhook_key": "demo-missing"})

    result = process_event_payload(
        AutomationEventInput(
            event_type="webhook_received",
            source_type="webhook",
            source_id="fixed-template-missing",
            program_id=program_id,
            external_userid="wm_template_missing",
            payload_json={"webhook_key": "demo-missing", "variables": {"custom_note": "exists"}},
        )
    )

    plan = _plan(program_id)
    assert result["counts"]["failed"] == 1
    assert plan["status"] == "failed"
    assert plan["skip_reason"] == "template_variable_missing"
    assert plan["diagnostics_json"]["unresolved_template"] is True
    assert plan["diagnostics_json"]["missing_variables"] == ["missing_note"]
    assert _job_count(program_id) == 0


def test_fixed_message_without_template_is_unchanged(next_pg_schema):
    program_id = seed_program("runtime_v2_fixed_template_plain")
    seed_task(program_id, trigger_type="on_event", content_text="普通固定话术", agent_config={"trigger_event_type": "channel_entered"})

    process_event_payload(
        AutomationEventInput(event_type="channel_entered", source_type="test", source_id="fixed-template-plain", program_id=program_id, external_userid="wm_template_plain")
    )

    plan = _plan(program_id)
    assert plan["rendered_content_json"]["content_text"] == "普通固定话术"
    assert plan["diagnostics_json"]["template_rendered"] is False


def test_fixed_message_questionnaire_answers_render(next_pg_schema):
    program_id = seed_program("runtime_v2_fixed_template_questionnaire")
    seed_task(program_id, trigger_type="on_event", content_text="需求={{questionnaire.answers.need}}", agent_config={"trigger_event_type": "questionnaire_submitted"})

    process_event_payload(
        AutomationEventInput(
            event_type="questionnaire_submitted",
            source_type="questionnaire",
            source_id="fixed-template-questionnaire",
            program_id=program_id,
            external_userid="wm_template_questionnaire",
            payload_json={"answers": {"need": "想提升私域自动化转化"}},
        )
    )

    assert _plan(program_id)["rendered_content_json"]["content_text"] == "需求=想提升私域自动化转化"


def test_fixed_message_payment_fields_render(next_pg_schema):
    program_id = seed_program("runtime_v2_fixed_template_payment")
    seed_task(program_id, trigger_type="on_event", content_text="订单={{payment.order_id}} 金额={{payment.amount}}", agent_config={"trigger_event_type": "payment_succeeded"})

    process_event_payload(
        AutomationEventInput(
            event_type="payment_succeeded",
            source_type="payment",
            source_id="fixed-template-payment",
            program_id=program_id,
            external_userid="wm_template_payment",
            payload_json={"order_id": "order_123", "amount": 88},
        )
    )

    assert _plan(program_id)["rendered_content_json"]["content_text"] == "订单=order_123 金额=88"
