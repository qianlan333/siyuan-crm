from __future__ import annotations

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput

from tests.automation_runtime_v2_test_helpers import db, seed_agent, seed_program, seed_task


def _latest_plan(program_id: int) -> dict:
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


def _job_count_for_program(program_id: int) -> int:
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


def _agent_counts() -> dict[str, int]:
    return {
        "runs": int(db().execute("SELECT COUNT(*) AS count FROM automation_agent_run").fetchone()["count"]),
        "outputs": int(db().execute("SELECT COUNT(*) AS count FROM automation_agent_output").fetchone()["count"]),
        "llm_logs": int(db().execute("SELECT COUNT(*) AS count FROM automation_agent_llm_call_log").fetchone()["count"]),
    }


def _trigger(program_id: int, source_id: str = "agent-generation") -> dict:
    return process_event_payload(
        AutomationEventInput(
            event_type="questionnaire_submitted",
            source_type="questionnaire",
            source_id=source_id,
            program_id=program_id,
            external_userid=f"wm_{source_id}",
            payload_json={"answers": {"need": "想提升私域自动化转化", "stage": "已有社群和企微好友", "focus": "希望收到个性化建议"}},
        )
    )


def test_agent_generated_uses_gateway_output_and_writes_audit(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "fake")
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_FAKE_ALLOWED", "1")
    program_id = seed_program("runtime_v2_agent_generation_ok")
    seed_agent("qa_agent", task_prompt="需求={{questionnaire.answers.need}}")
    seed_task(
        program_id,
        trigger_type="on_event",
        content_mode="agent",
        agent_config={
            "agent_code": "qa_agent",
            "mock_output": "根据你的问卷，我建议你先解决私域自动化转化的问题。",
            "trigger_event_type": "questionnaire_submitted",
            "miniprogram_library_ids": [2],
        },
    )

    result = _trigger(program_id, "agent-generation-ok")

    plan = _latest_plan(program_id)
    assert result["counts"]["enqueued"] == 1
    assert plan["status"] == "enqueued"
    assert plan["rendered_content_json"]["content_text"] == "根据你的问卷，我建议你先解决私域自动化转化的问题。"
    assert plan["rendered_content_json"]["attachments"]["miniprogram_library_ids"] == [2]
    assert "{{问卷信息}}" not in plan["rendered_content_json"]["content_text"]
    assert "你将收到以下资料" not in plan["rendered_content_json"]["content_text"]
    assert plan["diagnostics_json"]["agent_code"] == "qa_agent"
    assert plan["diagnostics_json"]["agent_run_id"]
    assert plan["diagnostics_json"]["agent_output_id"]
    assert plan["diagnostics_json"]["llm_call_logged"] is True
    assert plan["diagnostics_json"]["fallback_used"] is False
    assert plan["diagnostics_json"]["questionnaire_answer_count"] == 3
    assert _agent_counts() == {"runs": 1, "outputs": 1, "llm_logs": 1}


def test_agent_gateway_config_missing_fails_without_outbox(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "production")
    monkeypatch.delenv("AICRM_RUNTIME_V2_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    program_id = seed_program("runtime_v2_agent_generation_no_config")
    seed_agent("qa_agent")
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "qa_agent", "trigger_event_type": "questionnaire_submitted"})

    _trigger(program_id, "agent-generation-no-config")

    plan = _latest_plan(program_id)
    assert plan["status"] == "failed"
    assert plan["skip_reason"] == "agent_gateway_config_missing"
    assert _job_count_for_program(program_id) == 0
    assert _agent_counts()["runs"] == 1
    assert _agent_counts()["llm_logs"] == 1


def test_agent_gateway_empty_output_fails_without_outbox(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "fake")
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_FAKE_ALLOWED", "1")
    program_id = seed_program("runtime_v2_agent_generation_empty")
    seed_agent("qa_agent")
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "qa_agent", "mock_output": "", "trigger_event_type": "questionnaire_submitted"})

    _trigger(program_id, "agent-generation-empty")

    plan = _latest_plan(program_id)
    assert plan["status"] == "failed"
    assert plan["skip_reason"] == "agent_generation_empty"
    assert _job_count_for_program(program_id) == 0


def test_agent_output_that_matches_prompt_is_blocked(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "fake")
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_FAKE_ALLOWED", "1")
    task_prompt = "最终只输出一条可直接发送给用户的话术。不要输出 JSON。"
    program_id = seed_program("runtime_v2_agent_generation_prompt_echo")
    seed_agent("qa_agent", task_prompt=task_prompt)
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "qa_agent", "mock_output": task_prompt, "trigger_event_type": "questionnaire_submitted"})

    _trigger(program_id, "agent-generation-prompt-echo")

    plan = _latest_plan(program_id)
    assert plan["status"] == "failed"
    assert plan["skip_reason"] == "agent_output_looks_like_prompt"
    assert _job_count_for_program(program_id) == 0


def test_agent_prompt_variable_missing_fails_without_outbox(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "fake")
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_FAKE_ALLOWED", "1")
    program_id = seed_program("runtime_v2_agent_generation_missing_var")
    seed_agent("qa_agent", task_prompt="缺失={{questionnaire.answers.missing_field}}")
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "qa_agent", "mock_output": "不会执行", "trigger_event_type": "questionnaire_submitted"})

    _trigger(program_id, "agent-generation-missing-var")

    plan = _latest_plan(program_id)
    assert plan["status"] == "failed"
    assert plan["skip_reason"] == "agent_prompt_variable_missing"
    assert plan["diagnostics_json"]["missing_variables"] == ["questionnaire.answers.missing_field"]
    assert _job_count_for_program(program_id) == 0


def test_agent_generation_failure_can_use_explicit_fallback(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "production")
    monkeypatch.delenv("AICRM_RUNTIME_V2_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    program_id = seed_program("runtime_v2_agent_generation_fallback")
    seed_agent("qa_agent")
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "qa_agent", "fallback_content": "这是明确配置的兜底话术", "trigger_event_type": "questionnaire_submitted"})

    _trigger(program_id, "agent-generation-fallback")

    plan = _latest_plan(program_id)
    assert plan["status"] == "enqueued"
    assert plan["rendered_content_json"]["content_text"] == "这是明确配置的兜底话术"
    assert plan["diagnostics_json"]["fallback_used"] is True
    assert "{{" not in plan["rendered_content_json"]["content_text"]
    assert _job_count_for_program(program_id) == 1


def test_production_prompt_leak_regression_is_not_enqueued(next_pg_schema, monkeypatch):
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_MODE", "fake")
    monkeypatch.setenv("AICRM_RUNTIME_V2_AGENT_FAKE_ALLOWED", "1")
    incident_prompt = """你将收到以下资料（为空时按空处理）：

【问卷信息】
{{问卷信息}}

你的唯一任务是：
根据用户情况，推荐 2 到 3 个最适合立即开聊的话题。

最终只输出一条可直接发送给用户的话术。
不要解释你的判断过程。
不要输出 JSON。"""
    program_id = seed_program("runtime_v2_agent_generation_incident")
    seed_agent("qa_agent", task_prompt=incident_prompt)
    seed_task(program_id, trigger_type="on_event", content_mode="agent", agent_config={"agent_code": "qa_agent", "mock_output": incident_prompt, "trigger_event_type": "questionnaire_submitted"})

    _trigger(program_id, "agent-generation-incident")

    plan = _latest_plan(program_id)
    assert plan["status"] == "failed"
    assert plan["skip_reason"] in {"agent_prompt_variable_missing", "agent_output_looks_like_prompt"}
    assert plan["rendered_content_json"] == {}
    assert _job_count_for_program(program_id) == 0
