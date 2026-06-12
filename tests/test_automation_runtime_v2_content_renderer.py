from __future__ import annotations

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

from tests.automation_runtime_v2_test_helpers import db, seed_agent, seed_program, seed_task


def test_content_renderer_fixed_layered_and_agent_paths(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "fake")
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_FAKE_ALLOWED", "1")
    program_id = seed_program("runtime_v2_render")
    seed_task(program_id, trigger_type="on_event", content_text="固定", agent_config={"trigger_event_type": "questionnaire_submitted"})
    seed_task(program_id, trigger_type="on_event", content_mode="profile_layered", segment_contents=[{"segment_key": "default", "content_text": "分层"}], agent_config={"trigger_event_type": "questionnaire_submitted"})
    seed_agent("agent_ok", published=True)
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "agent_ok", "mock_output": "Agent 生成话术", "trigger_event_type": "questionnaire_submitted"})
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "", "trigger_event_type": "questionnaire_submitted"})
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "agent_ok", "force_fail": True, "fallback_content": "兜底", "trigger_event_type": "questionnaire_submitted"})

    result = process_event_payload(AutomationEventInput(event_type="questionnaire_submitted", source_type="questionnaire", source_id="render-sub", program_id=program_id, external_userid="wm_render", payload_json={"answers": {"need": "英语"}}))

    statuses = [plan["status"] for plan in result["plans"]]
    assert statuses.count("enqueued") == 4
    assert statuses.count("failed") == 1
    failed = db().execute("SELECT skip_reason FROM automation_task_plan_v2 WHERE status = 'failed' LIMIT 1").fetchone()
    assert failed["skip_reason"] == "agent_code_missing"
