from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aicrm_next.automation_engine.programs import (
    create_automation_program_operation_task,
    preview_automation_program_operation_task_audience,
)
from aicrm_next.automation_engine.automation_program_admission import admit_channel_contact_to_program
from aicrm_next.automation_engine.automation_program_admission import (
    run_audience_entered_operation_tasks,
)
from aicrm_next.main import create_app
from automation_channel_admission_helpers import (
    create_channel,
    create_choice_questionnaire,
    create_program,
    disabled_entry_rule,
    save_audience_entry_rule,
    table_count,
)
from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.channel_binding_service import bind_channels_to_program
from wecom_ability_service.domains.automation_conversion import operation_task_repo
from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job


ROOT = Path(__file__).resolve().parents[1]


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def _load_due_script():
    path = ROOT / "scripts" / "run_automation_conversion_due_jobs.py"
    spec = importlib.util.spec_from_file_location("run_automation_conversion_due_jobs_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _bind(program_id: int, channel_id: int) -> int:
    return int(bind_channels_to_program(program_id, [channel_id], {}, "pytest")["bindings"][0]["id"])


def _seed_agent_config(agent_code: str, *, role_prompt: str = "", task_prompt: str = "", variables: list[dict] | None = None) -> None:
    get_db().execute(
        """
        INSERT INTO automation_agent_config (
            agent_code, display_name, pool_keys_json, enabled,
            draft_role_prompt, draft_task_prompt, draft_variables_json, draft_output_schema_json,
            published_role_prompt, published_task_prompt, published_variables_json, published_output_schema_json,
            draft_version, published_version, last_change_summary, created_at, updated_at
        )
        VALUES (?, ?, '[]', true, '', '', '[]', '[]', ?, ?, ?, '[]', 1, 1, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(agent_code) DO UPDATE SET
            display_name = excluded.display_name,
            enabled = true,
            published_role_prompt = excluded.published_role_prompt,
            published_task_prompt = excluded.published_task_prompt,
            published_variables_json = excluded.published_variables_json,
            published_version = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            agent_code,
            agent_code,
            role_prompt,
            task_prompt,
            json.dumps(variables or [], ensure_ascii=False),
        ),
    )
    get_db().commit()


def _insert_agent_operation_task(program_id: int, *, agent_code: str, fallback_content: str = "") -> dict:
    task = operation_task_repo.insert_task(
        {
            "program_id": int(program_id),
            "task_name": f"agent runtime {agent_code}",
            "status": "active",
            "trigger_type": "audience_entered",
            "send_time": "10:00",
            "timezone": "Asia/Shanghai",
            "target_audience_code": "operating",
            "target_stage_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "agent",
            "unified_content_json": {},
            "segment_contents_json": [],
            "agent_config_json": {"agent_code": agent_code, "fallback_content": fallback_content},
            "created_by": "pytest",
            "updated_by": "pytest",
        }
    )
    get_db().commit()
    return task


def _seed_questionnaire_submission(external_contact_id: str) -> int:
    questionnaire = create_choice_questionnaire(f"runtime_agent_q_{external_contact_id[-8:]}")
    get_db().execute(
        """
        INSERT INTO questionnaire_submissions (
            questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, submitted_at
        )
        VALUES (?, ?, ?, '', 0, '[]', '2026-06-05 10:30:00')
        """,
        (int(questionnaire["id"]), external_contact_id, external_contact_id),
    )
    submission_id = int(get_db().execute("SELECT MAX(id) AS id FROM questionnaire_submissions").fetchone()["id"])
    get_db().execute(
        """
        INSERT INTO questionnaire_submission_answers (
            submission_id, question_id, question_type, question_title_snapshot,
            selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
            selected_option_tags_snapshot, text_value, score_contribution, created_at
        )
        VALUES (?, ?, 'single_choice', '业务现状', ?, ?, '[]', '[]', '', 0, CURRENT_TIMESTAMP)
        """,
        (
            submission_id,
            int(questionnaire["question_id"]),
            json.dumps([int(questionnaire["option_a_id"])]),
            json.dumps(["不知道做什么方向"], ensure_ascii=False),
        ),
    )
    get_db().commit()
    return submission_id


def test_operation_runtime_contract_rejects_unpublishable_active_content(app):
    with app.app_context():
        program_id = create_program("runtime_contract_validation")

        with pytest.raises(ValueError, match="统一内容"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "empty unified",
                    "status": "active",
                    "trigger_type": "audience_entered",
                    "target_stage_code": "operating",
                    "content_mode": "unified",
                    "unified_content_json": {},
                },
                operator_id="pytest",
            )

        with pytest.raises(ValueError, match="触发方式"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "bad trigger",
                    "status": "active",
                    "trigger_type": "unknown",
                    "content_mode": "unified",
                    "unified_content_json": {"content_text": "ok"},
                },
                operator_id="pytest",
            )

        with pytest.raises(ValueError, match="生成要求|Agent"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "agent without runtime body",
                    "status": "active",
                    "trigger_type": "audience_entered",
                    "target_stage_code": "operating",
                    "content_mode": "agent",
                    "agent_config_json": {"agent_code": "welcome_agent"},
                },
                operator_id="pytest",
            )

        with pytest.raises(ValueError, match="行为分层"):
            create_automation_program_operation_task(
                program_id,
                {
                    "task_name": "behavior without segment content",
                    "status": "active",
                    "trigger_type": "audience_entered",
                    "target_stage_code": "operating",
                    "behavior_filter": "between_2_9",
                    "content_mode": "behavior_layered",
                    "segment_contents_json": [],
                },
                operator_id="pytest",
            )


def test_operation_runtime_contract_preview_is_read_only_and_reports_reasons(app):
    with app.app_context():
        program_id = create_program("runtime_contract_preview")
        channel = create_channel("runtime_contract_preview_channel", program_id=program_id)
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())

        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_contract_preview",
            trigger_time="2026-06-05 10:00:00",
        )
        assert admitted["audience_code"] == "operating"

        payload = {
            "task_name": "preview task",
            "status": "draft",
            "trigger_type": "scheduled_daily",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": "hello"},
        }
        result = preview_automation_program_operation_task_audience(program_id, payload)

        preview = result["preview"]
        assert preview["target_count"] == 1
        assert preview["segment_counts"]["unified"] == 1
        assert preview["filtered_out_counts"] == {}
        assert preview["reasons"] == []

        missing_content = preview_automation_program_operation_task_audience(
            program_id,
            {**payload, "unified_content_json": {}},
        )["preview"]
        assert missing_content["target_count"] == 0
        assert missing_content["filtered_out_counts"]["content_missing"] == 1
        assert "content_missing" in missing_content["reasons"]


def test_operation_runtime_contract_preview_returns_diagnostics_for_invalid_active_task(app):
    with app.app_context():
        program_id = create_program("runtime_contract_preview_invalid_active")
        result = preview_automation_program_operation_task_audience(
            program_id,
            {
                "task_name": "invalid active preview",
                "status": "active",
                "trigger_type": "audience_entered",
                "target_stage_code": "operating",
                "behavior_filter": "between_2_9",
                "content_mode": "behavior_layered",
                "segment_contents_json": [],
            },
        )

        preview = result["preview"]
        assert preview["target_count"] == 0
        assert preview["content_diagnostics"]["ok"] is False
        assert "behavior_segment_content_missing" in preview["content_diagnostics"]["errors"]


def test_agent_questionnaire_prompt_context_materializes_and_enqueues(app, monkeypatch):
    with app.app_context():
        program_id = create_program("runtime_contract_agent_questionnaire")
        channel = create_channel("runtime_contract_agent_questionnaire_channel", program_id=program_id)
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())
        external_contact_id = "wm_runtime_contract_agent_questionnaire"
        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            external_contact_id,
            trigger_time="2026-06-05 10:00:00",
        )
        submission_id = _seed_questionnaire_submission(external_contact_id)
        _seed_agent_config(
            "questionnaire_followup_agent",
            role_prompt="你是问卷提交后的承接顾问",
            task_prompt="请基于{{问卷答案}}生成一条个性化承接话术",
            variables=[{"source": "questionnaire"}],
        )
        task = _insert_agent_operation_task(program_id, agent_code="questionnaire_followup_agent")

        preview = preview_automation_program_operation_task_audience(program_id, {**task})["preview"]
        assert preview["target_count"] == 1
        assert preview["agent_runtime_diagnostics"]["agent_published_prompt_present"] is True
        assert preview["agent_runtime_diagnostics"]["questionnaire_context_available"] is True
        assert preview["content_diagnostics"]["ok"] is True

        result = run_audience_entered_operation_tasks(
            member_id=int(admitted["member_id"]),
            audience_code="operating",
            audience_entry_id=int(admitted["audience_entry_id"]),
            operator_id="pytest_agent_questionnaire",
        )

        assert result["ok"] is True
        assert result["enqueued_count"] == 1
        execution_id = f"actask-event-{int(task['id'])}-{int(admitted['audience_entry_id'])}"
        item = get_db().execute(
            """
            SELECT rendered_content_text, content_snapshot_json
            FROM automation_operation_task_execution_item
            WHERE execution_id = ?
            LIMIT 1
            """,
            (execution_id,),
        ).fetchone()
        assert item
        assert item["rendered_content_text"] == ""
        assert item["content_snapshot_json"]["generation_source"] == "automation_operation_task"
        assert item["content_snapshot_json"]["content_source"] == "agent_runtime_plan"
        assert item["content_snapshot_json"]["fallback_reason"] == "agent_runtime_plan_pending"
        assert item["content_snapshot_json"]["agent_published_prompt_present"] is True
        assert item["content_snapshot_json"]["questionnaire_submission_id"] == submission_id
        assert item["content_snapshot_json"]["questionnaire_answer_count"] == 1
        assert item["content_snapshot_json"]["agent_runtime_planned"] is True
        assert item["content_snapshot_json"]["real_agent_runtime_executed"] is False
        assert item["content_snapshot_json"]["adapter_contract"]["side_effect_executed"] is False
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 1


def test_agent_prompt_without_questionnaire_answers_reports_context_missing(app, monkeypatch):
    with app.app_context():
        program_id = create_program("runtime_contract_agent_questionnaire_missing")
        channel = create_channel("runtime_contract_agent_questionnaire_missing_channel", program_id=program_id)
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())
        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_contract_agent_no_questionnaire",
            trigger_time="2026-06-05 10:00:00",
        )
        _seed_agent_config(
            "questionnaire_required_agent",
            role_prompt="你是问卷提交后的承接顾问",
            task_prompt="请基于{{问卷答案}}生成承接话术",
            variables=[{"source": "questionnaire"}],
        )
        task = _insert_agent_operation_task(program_id, agent_code="questionnaire_required_agent")
        called = {"value": False}

        result = run_audience_entered_operation_tasks(
            member_id=int(admitted["member_id"]),
            audience_code="operating",
            audience_entry_id=int(admitted["audience_entry_id"]),
            operator_id="pytest_agent_questionnaire_missing",
        )

        assert result["ok"] is True
        assert result["enqueued_count"] == 0
        assert called["value"] is False
        assert result["results"][0]["reason"] == "questionnaire_context_missing"
        assert table_count("automation_operation_task_execution_item", "task_id = ?", (int(task["id"]),)) == 0
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 0


def test_agent_runtime_failure_uses_task_fallback_without_real_send(app, monkeypatch):
    with app.app_context():
        program_id = create_program("runtime_contract_agent_fallback")
        channel = create_channel("runtime_contract_agent_fallback_channel", program_id=program_id)
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())
        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_contract_agent_fallback",
            trigger_time="2026-06-05 10:00:00",
        )
        _seed_agent_config("fallback_agent")
        task = _insert_agent_operation_task(program_id, agent_code="fallback_agent", fallback_content="兜底承接话术")

        result = run_audience_entered_operation_tasks(
            member_id=int(admitted["member_id"]),
            audience_code="operating",
            audience_entry_id=int(admitted["audience_entry_id"]),
            operator_id="pytest_agent_fallback",
        )

        assert result["ok"] is True
        assert result["enqueued_count"] == 1
        item = get_db().execute(
            """
            SELECT rendered_content_text, content_snapshot_json
            FROM automation_operation_task_execution_item
            WHERE task_id = ?
            LIMIT 1
            """,
            (int(task["id"]),),
        ).fetchone()
        assert item["rendered_content_text"] == "兜底承接话术"
        assert item["content_snapshot_json"]["fallback_reason"] == ""
        assert item["content_snapshot_json"]["agent_runtime_planned"] is True
        assert item["content_snapshot_json"]["real_agent_runtime_executed"] is False
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 1


def test_operation_runtime_contract_preview_uses_program_channel_binding(app):
    with app.app_context():
        old_program_id = create_program("runtime_contract_preview_old_channel_program")
        new_program_id = create_program("runtime_contract_preview_bound_program")
        channel = create_channel("runtime_contract_preview_bound_channel", program_id=old_program_id)
        binding_id = _bind(new_program_id, int(channel["id"]))
        save_audience_entry_rule(new_program_id, disabled_entry_rule())

        admitted = admit_channel_contact_to_program(
            new_program_id,
            int(channel["id"]),
            binding_id,
            "wm_runtime_contract_preview_binding",
            trigger_time="2026-06-05 10:00:00",
        )
        assert admitted["audience_code"] == "operating"

        result = preview_automation_program_operation_task_audience(
            new_program_id,
            {
                "task_name": "preview bound channel task",
                "status": "draft",
                "trigger_type": "audience_entered",
                "send_time": "10:00",
                "target_stage_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "none",
                "content_mode": "unified",
                "unified_content_json": {"content_text": "hello"},
            },
        )

        preview = result["preview"]
        assert preview["target_count"] == 1
        assert preview["segment_counts"]["unified"] == 1
        assert "program_channel_not_matched" not in preview["reasons"]


def test_operation_runtime_contract_preview_uses_program_member_profile_segment(app):
    with app.app_context():
        program_id = create_program("runtime_contract_preview_program_segment")
        channel = create_channel("runtime_contract_preview_program_segment_channel", program_id=program_id)
        binding_id = _bind(program_id, int(channel["id"]))
        save_audience_entry_rule(program_id, disabled_entry_rule())

        external_contact_id = "wm_runtime_contract_preview_program_segment"
        admitted = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            external_contact_id,
            trigger_time="2026-06-05 10:00:00",
        )
        assert admitted["audience_code"] == "operating"

        get_db().execute(
            """
            UPDATE automation_program_member
            SET state_payload_json = CAST(? AS jsonb)
            WHERE program_id = ?
              AND external_contact_id = ?
            """,
            (json.dumps({"profile_segment_key": "category_a"}), program_id, external_contact_id),
        )
        get_db().commit()

        result = preview_automation_program_operation_task_audience(
            program_id,
            {
                "task_name": "preview program segment task",
                "status": "draft",
                "trigger_type": "audience_entered",
                "send_time": "10:00",
                "target_stage_code": "operating",
                "audience_day_offset": 1,
                "behavior_filter": "none",
                "content_mode": "profile_layered",
                "profile_segment_template_id": 99,
                "segment_contents_json": [
                    {
                        "segment_key": "category_a",
                        "segment_name": "画像 A",
                        "content_text": "hello",
                    }
                ],
            },
        )

        preview = result["preview"]
        assert preview["target_count"] == 1
        assert preview["segment_counts"]["category_a"] == 1
        assert "profile_segment_not_matched" not in preview["reasons"]
        assert "content_missing" not in preview["reasons"]


def test_operation_runtime_contract_due_script_supports_operation_task_without_defaulting_it(monkeypatch):
    module = _load_due_script()
    captured: list[dict[str, object]] = []

    def fake_urlopen(request, *, timeout):
        captured.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "body": json.loads(request.data.decode("utf-8")),
            }
        )
        return _FakeResponse(b'{"ok": true, "enqueued_count": 2}')

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert "operation_task" in module.JOB_DEFINITIONS
    assert module.DEFAULT_JOB_CODES == ["sop", "conversion_workflow"]
    body = json.loads(module.run(jobs=["operation_task"]))

    assert captured[0]["body"] == {"operator": "automation_conversion_due_runner", "jobs": ["operation_task"]}
    assert body["requested_job_codes"] == ["operation_task"]
    assert body["jobs"][0]["job_code"] == "operation_task"


def test_operation_runtime_contract_next_jobs_route_is_plan_only_for_operation_task(monkeypatch):
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/admin/automation-conversion/jobs/run-due",
        json={"jobs": ["operation_task"], "dry_run": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jobs_run_due_executed"] is False
    assert body["operation_tasks_executed"] == 0
    assert body["planned_count"] >= 0
    assert body["actual_enqueued_count"] == 0
    assert body["blocked_reason"] == "next_plan_only_route"


def test_operation_runtime_contract_worker_routes_operation_task_handler(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_operation_task_broadcast_job(job):
        captured["job"] = dict(job)
        return {"ok": True, "sent_count": 1, "failed_count": 0, "outbound_task_id": 321}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.operation_task_service.run_operation_task_broadcast_job",
        fake_run_operation_task_broadcast_job,
    )

    result = execute_job({"id": 99, "source_type": "operation_task", "content_payload": {"task_id": 1}})

    assert result["ok"] is True
    assert result["sent_count"] == 1
    assert captured["job"]["source_type"] == "operation_task"
