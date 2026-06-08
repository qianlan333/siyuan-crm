from __future__ import annotations

import pytest

from aicrm_next.automation_engine.repo import reset_automation_fixture_state


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_automation_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _create_task(client) -> int:
    response = client.post(
        "/api/admin/automation-conversion/tasks",
        json={
            "program_id": 9,
            "workflow_id": 9,
            "node_id": 9,
            "group_id": 9,
            "task_name": "Next send content test task",
            "task_code": "next_send_content_test_task",
            "task_type": "metadata",
            "idempotency_key": "next-send-content-test-task",
            "operator": "pytest",
        },
    )
    assert response.status_code == 201
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    return int(response.json()["task"]["id"])


def _operation_content(task: dict) -> dict:
    return task["config"]["operation_content"]


def test_send_strategy_unified_writes_content_mode(client) -> None:
    task_id = _create_task(client)

    response = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-strategy",
        json={"content_mode": "unified"},
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert _operation_content(response.json()["task"])["content_mode"] == "unified"


def test_profile_layered_requires_profile_segment_template_id(client) -> None:
    task_id = _create_task(client)

    response = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-strategy",
        json={"content_mode": "profile_layered"},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert "profile_segment_template_id" in response.json()["detail"]


def test_profile_layered_writes_profile_segment_template_id(client) -> None:
    task_id = _create_task(client)

    response = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-strategy",
        json={"content_mode": "profile_layered", "profile_segment_template_id": 1},
    )

    assert response.status_code == 200
    operation_content = _operation_content(response.json()["task"])
    assert operation_content["content_mode"] == "profile_layered"
    assert operation_content["profile_segment_template_id"] == 1


def test_save_unified_content_writes_unified_content_json(client) -> None:
    task_id = _create_task(client)

    response = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/unified",
        json={"content_package": {"content_text": "  统一内容  ", "image_library_ids": [12, "12"]}},
    )

    assert response.status_code == 200
    operation_content = _operation_content(response.json()["task"])
    assert operation_content["content_mode"] == "unified"
    assert operation_content["unified_content_json"] == {
        "content_text": "统一内容",
        "image_library_ids": [12],
        "miniprogram_library_ids": [],
        "attachment_library_ids": [],
    }


def test_profile_segment_content_upserts_without_duplicates_or_deleting_other_segments(client) -> None:
    task_id = _create_task(client)

    first = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/profile-segments/early_founder",
        json={
            "segment_name": "早期个体创业者",
            "profile_segment_template_id": 1,
            "content_package": {"content_text": "第一版"},
        },
    )
    assert first.status_code == 200

    second = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/profile-segments/mature_team",
        json={
            "segment_name": "成熟团队",
            "profile_segment_template_id": 1,
            "content_package": {"content_text": "其他分层"},
        },
    )
    assert second.status_code == 200

    upsert = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/profile-segments/early_founder",
        json={
            "segment_name": "早期个体创业者",
            "profile_segment_template_id": 1,
            "content_package": {"content_text": "第二版"},
        },
    )

    assert upsert.status_code == 200
    operation_content = _operation_content(upsert.json()["task"])
    assert operation_content["content_mode"] == "profile_layered"
    rows = operation_content["segment_contents_json"]
    assert [row["segment_key"] for row in rows].count("early_founder") == 1
    assert {row["segment_key"] for row in rows} == {"early_founder", "mature_team"}
    assert next(row for row in rows if row["segment_key"] == "early_founder")["content_package"]["content_text"] == "第二版"


def test_behavior_segment_lt_2_and_invalid_key(client) -> None:
    task_id = _create_task(client)

    response = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/behavior-segments/lt_2",
        json={"segment_name": "消息少于 2", "content_package": {"content_text": "低消息数"}},
    )

    assert response.status_code == 200
    operation_content = _operation_content(response.json()["task"])
    assert operation_content["content_mode"] == "behavior_layered"
    assert operation_content["segment_contents_json"][0]["segment_key"] == "lt_2"

    invalid = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/behavior-segments/invalid_key",
        json={"content_package": {}},
    )
    assert invalid.status_code == 400


def test_agent_materials_write_requirement_without_raw_content_text(client) -> None:
    task_id = _create_task(client)

    response = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/agent-materials",
        json={
            "agent_code": "hxc_activation",
            "content_package": {
                "content_text": "生成要求",
                "image_library_ids": [12],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56],
            },
        },
    )

    assert response.status_code == 200
    operation_content = _operation_content(response.json()["task"])
    assert operation_content["content_mode"] == "agent"
    assert operation_content["agent_config_json"] == {
        "agent_code": "hxc_activation",
        "image_library_ids": [12],
        "miniprogram_library_ids": [34],
        "attachment_library_ids": [56],
        "requirement": "生成要求",
        "fallback_content": "",
        "prompt": "",
        "material_prompt": "",
    }
    assert "content_text" not in operation_content["agent_config_json"]


def test_agent_send_strategy_switch_preserves_generation_config(client) -> None:
    task_id = _create_task(client)
    saved = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-content/agent-materials",
        json={
            "agent_code": "first_agent",
            "requirement": "结合问卷答案生成",
            "fallback_content": "兜底话术",
            "content_package": {"image_library_ids": [12]},
        },
    )
    assert saved.status_code == 200

    switched = client.put(
        f"/api/admin/automation-conversion/tasks/{task_id}/send-strategy",
        json={"content_mode": "agent", "agent_code": "second_agent"},
    )

    assert switched.status_code == 200
    agent_config = _operation_content(switched.json()["task"])["agent_config_json"]
    assert agent_config["agent_code"] == "second_agent"
    assert agent_config["requirement"] == "结合问卷答案生成"
    assert agent_config["fallback_content"] == "兜底话术"
    assert agent_config["image_library_ids"] == [12]


def test_behavior_segment_rules(client) -> None:
    response = client.get("/api/admin/automation-conversion/behavior-segment-rules")

    assert response.status_code == 200
    rule = response.json()["rules"][0]
    assert rule["rule_key"] == "default_message_count"
    assert [segment["segment_key"] for segment in rule["segments"]] == ["lt_2", "between_2_9", "gte_10"]
