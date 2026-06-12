from __future__ import annotations

from aicrm_next.automation_runtime_v2.runtime_check import check_task_runtime

from tests.automation_runtime_v2_test_helpers import seed_agent, seed_program, seed_task


def test_runtime_check_reports_blocked_reasons_and_ok_paths(next_pg_schema):
    program_id = seed_program("runtime_v2_check")
    ok_task = seed_task(program_id, content_text="ok")
    blocked_task = seed_task(program_id, content_text="", content_mode="agent", agent_config={"agent_code": "agent_missing"})
    seed_agent("agent_ready", published=True)
    agent_task = seed_task(program_id, content_text="", content_mode="agent", agent_config={"agent_code": "agent_ready"})

    assert check_task_runtime(ok_task, {})["ok"] is True
    blocked = check_task_runtime(blocked_task, {})
    assert blocked["ok"] is False
    assert "agent_published_prompt_missing" in blocked["blocked_reasons"]
    assert check_task_runtime(agent_task, {})["ok"] is True
