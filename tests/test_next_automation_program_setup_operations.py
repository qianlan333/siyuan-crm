from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from aicrm_next.automation_engine import application as automation_application
from aicrm_next.automation_engine import repo as automation_repo
from aicrm_next.automation_engine.repo import DEFAULT_AGENT_DEFINITIONS
from aicrm_next.automation_engine.repo import _sqlalchemy_database_url
from aicrm_next.main import app


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "_automation_operation_orchestration_panel.html"
OPERATION_JS = ROOT / "aicrm_next" / "automation_engine" / "static" / "admin_console" / "automation_operation_orchestration_panel.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operation_setup_panel_exposes_next_native_task_and_group_controls() -> None:
    template = _read(TEMPLATE)
    script = _read(OPERATION_JS)

    assert "data-create-task" in template
    assert "data-create-group" in template
    assert "data-delete-group" in template
    assert 'data-field="trigger_type"' in template
    assert 'data-field="target_stage_code"' in template
    assert 'data-field="behavior_filter"' in template
    assert "(() => {" not in template

    assert "/setup/operation-tasks" in script
    assert "/setup/operation-task-groups" in script
    assert "operation_task_base" in script
    assert "task_group_detail_base" in script
    assert 'data-task-action="copy"' in script
    assert "preview-audience" in script
    assert "collectOperationTaskPayload" in script
    assert "setupProfileSegments" in script
    assert "agentLoadStatus" in script
    assert "智能体列表加载失败，请检查 Agent 接口/生产数据源" in script
    assert "智能体列表为空，请检查 Agent 接口/生产数据源" in script
    assert "data-save-agent-text" in script
    assert "可使用 Agent 已发布提示词 + 问卷答案生成" in script
    assert "FALLBACK_AGENTS" not in script


def test_operation_setup_uses_psycopg3_sqlalchemy_urls() -> None:
    assert _sqlalchemy_database_url("postgres://u:p@db.local:5432/app") == "postgresql+psycopg://u:p@db.local:5432/app"
    assert _sqlalchemy_database_url("postgresql://u:p@db.local:5432/app") == "postgresql+psycopg://u:p@db.local:5432/app"
    assert _sqlalchemy_database_url("postgresql+psycopg://u:p@db.local:5432/app") == "postgresql+psycopg://u:p@db.local:5432/app"


def test_operation_setup_agent_options_are_next_postgres_backed_under_production_data_ready(monkeypatch) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_id INTEGER NOT NULL DEFAULT 0,
                    workflow_id INTEGER NOT NULL DEFAULT 0,
                    node_id INTEGER NOT NULL DEFAULT 0,
                    task_id INTEGER NOT NULL DEFAULT 0,
                    agent_code TEXT NOT NULL,
                    agent_name TEXT NOT NULL DEFAULT '',
                    agent_type TEXT NOT NULL DEFAULT 'assistant',
                    status TEXT NOT NULL DEFAULT 'active',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
        )
        for definition in DEFAULT_AGENT_DEFINITIONS:
            conn.execute(
                text(
                    """
                    INSERT INTO automation_agents (
                        program_id, workflow_id, node_id, task_id, agent_code, agent_name,
                        agent_type, status, sort_order, metadata_json, config_json, enabled,
                        created_by, updated_by
                    )
                    VALUES (
                        0, 0, 0, 0, :agent_code, :agent_name,
                        :agent_type, 'active', :sort_order, '{}', '{}', 1,
                        'test', 'test'
                    )
                    """
                ),
                definition,
            )

    monkeypatch.setattr(automation_application, "production_environment", lambda: True)
    monkeypatch.setattr(automation_application, "production_data_ready", lambda: True)
    monkeypatch.setattr(automation_application, "agent_postgres_enabled", lambda: True)
    monkeypatch.setattr(
        automation_application,
        "build_automation_repository",
        lambda **kwargs: automation_repo.build_automation_repository(
            agent_backend=kwargs.get("agent_backend") or "postgres",
            agent_engine=engine,
        ),
    )

    source = (ROOT / "aicrm_next" / "automation_engine" / "admin_pages.py").read_text(encoding="utf-8")
    assert '"agents_options": f"/api/admin/automation-conversion/agents/options?program_id={program_id}&limit=200"' in source

    client = TestClient(app)
    response = client.get("/api/admin/automation-conversion/agents/options?program_id=1&limit=200")
    assert response.status_code == 200
    payload = response.json()
    expected_codes = {item["agent_code"] for item in DEFAULT_AGENT_DEFINITIONS}
    returned_codes = {item["agent_code"] for item in payload["items"]}
    assert expected_codes <= returned_codes
    assert payload["count"] >= 5
    assert {item["value"] for item in payload["options"]} >= expected_codes
    assert all(item.get("label") and item.get("agent_name") for item in payload["options"])


def test_operation_setup_next_api_creates_groups_tasks_and_status_actions() -> None:
    client = TestClient(app)

    group_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/operation-task-groups",
        json={"group_name": "首日触达"},
    )
    assert group_response.status_code == 200
    group = group_response.json()["group"]
    assert group["group_name"] == "首日触达"

    task_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/operation-tasks",
        json={
            "task_name": "新运营任务",
            "group_id": group["id"],
            "status": "draft",
            "trigger_type": "scheduled_daily",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "target_audience_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": "欢迎"},
        },
    )
    assert task_response.status_code == 200
    task = task_response.json()["task"]
    assert task["task_name"] == "新运营任务"
    assert task["group_id"] == group["id"]
    assert task["target_audience_code"] == "operating"
    assert task["content_mode"] == "unified"

    update_response = client.put(
        f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}",
        json={**task, "trigger_type": "audience_entered", "target_stage_code": "converted", "behavior_filter": "gte_10"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()["task"]
    assert updated["trigger_type"] == "audience_entered"
    assert updated["target_audience_code"] == "converted"
    assert updated["behavior_filter"] == "gte_10"

    activate_response = client.post(f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/activate")
    assert activate_response.status_code == 200
    assert activate_response.json()["task"]["status"] == "active"

    copy_response = client.post(f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/copy")
    assert copy_response.status_code == 200
    assert "复制" in copy_response.json()["task"]["task_name"]

    archive_response = client.delete(f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}")
    assert archive_response.status_code == 200
    assert archive_response.json()["task"]["status"] == "archived"


def test_operation_setup_send_content_routes_bind_to_operation_task() -> None:
    client = TestClient(app)

    task_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/operation-tasks",
        json={"task_name": "内容任务", "content_mode": "unified"},
    )
    task = task_response.json()["task"]
    content_response = client.put(
        f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/send-content/unified",
        json={"content_package": {"content_text": "统一话术", "image_library_ids": [1]}},
    )
    assert content_response.status_code == 200
    updated = content_response.json()["task"]
    assert updated["content_mode"] == "unified"
    assert updated["unified_content_json"]["content_text"] == "统一话术"
    assert updated["unified_content_json"]["image_library_ids"] == [1]


def test_operation_setup_agent_materials_merge_generation_fields() -> None:
    client = TestClient(app)

    task_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/operation-tasks",
        json={"task_name": "Agent 内容任务", "content_mode": "agent", "agent_config_json": {"agent_code": "first_agent"}},
    )
    task = task_response.json()["task"]
    content_response = client.put(
        f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/send-content/agent-materials",
        json={
            "agent_code": "first_agent",
            "requirement": "结合问卷答案生成",
            "fallback_content": "兜底话术",
            "content_package": {"image_library_ids": [1]},
        },
    )

    assert content_response.status_code == 200
    agent_config = content_response.json()["task"]["agent_config_json"]
    assert agent_config["agent_code"] == "first_agent"
    assert agent_config["requirement"] == "结合问卷答案生成"
    assert agent_config["fallback_content"] == "兜底话术"
    assert agent_config["image_library_ids"] == [1]

    strategy_response = client.put(
        f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/send-strategy",
        json={"content_mode": "agent", "agent_code": "second_agent"},
    )
    switched_config = strategy_response.json()["task"]["agent_config_json"]
    assert switched_config["agent_code"] == "second_agent"
    assert switched_config["requirement"] == "结合问卷答案生成"
    assert switched_config["fallback_content"] == "兜底话术"
    assert switched_config["image_library_ids"] == [1]


def test_operation_setup_profile_mode_reuses_saved_segmentation_categories() -> None:
    client = TestClient(app)

    save_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/segmentation",
        json={
            "questionnaire_id": 21,
            "default_strategy": "normal_question_rules",
            "normal_question_mode": "single_question_option_category",
            "segmentation_question_id": 301,
            "normal_question_categories": [
                {
                    "category_key": "workplace",
                    "category_name": "职场人",
                    "option_ids": [401, 402],
                    "option_snapshots": [
                        {"id": 401, "option_text": "还在职场安心升级打怪"},
                        {"id": 402, "option_text": "正在面对转型焦虑"},
                    ],
                },
                {
                    "category_key": "founder",
                    "category_name": "创业者",
                    "option_ids": [403],
                    "option_snapshots": [{"id": 403, "option_text": "主副业两手抓"}],
                },
            ],
        },
    )
    assert save_response.status_code == 200

    operations_response = client.get("/api/admin/automation-conversion/programs/1/setup/operation-tasks")
    assert operations_response.status_code == 200
    payload = operations_response.json()
    assert payload["profile_templates"][0]["source"] == "setup_segmentation"
    assert payload["profile_segments"] == [
        {
            "segment_key": "workplace",
            "segment_name": "职场人",
            "category_key": "workplace",
            "category_name": "职场人",
            "description": "",
            "option_ids": [401, 402],
            "option_snapshots": [
                {"id": 401, "option_text": "还在职场安心升级打怪"},
                {"id": 402, "option_text": "正在面对转型焦虑"},
            ],
            "source": "setup_segmentation",
        },
        {
            "segment_key": "founder",
            "segment_name": "创业者",
            "category_key": "founder",
            "category_name": "创业者",
            "description": "",
            "option_ids": [403],
            "option_snapshots": [{"id": 403, "option_text": "主副业两手抓"}],
            "source": "setup_segmentation",
        },
    ]
