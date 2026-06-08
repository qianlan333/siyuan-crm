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


def _operation_content(task: dict) -> dict:
    return task["config"]["operation_content"]


def test_send_content_validate_normalizes_ids_and_agent_text(client) -> None:
    response = client.post(
        "/api/admin/send-content/validate",
        json={
            "content_package": {
                "content_text": "  必须被忽略  ",
                "image_library_ids": [12, 12, 13],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56, 56],
            },
            "text_enabled": False,
            "require_body": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["content_package"] == {
        "content_text": "",
        "image_library_ids": [12, 13],
        "miniprogram_library_ids": [34],
        "attachment_library_ids": [56],
    }


def test_send_content_validate_rejects_empty_required_body(client) -> None:
    response = client.post(
        "/api/admin/send-content/validate",
        json={"content_package": {}, "require_body": True},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "不能为空" in response.json()["error"]


def test_send_content_validate_rejects_non_positive_or_boolean_ids(client) -> None:
    response = client.post(
        "/api/admin/send-content/validate",
        json={"content_package": {"image_library_ids": [True]}, "require_body": False},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "正整数" in response.json()["error"]


def test_send_content_preview_and_material_picker_are_local_only(client) -> None:
    preview_response = client.post(
        "/api/admin/send-content/preview",
        json={
            "content_package": {
                "content_text": "  你好  ",
                "image_library_ids": [12],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56],
            }
        },
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    assert preview["content_text"] == "你好"
    assert preview["material_summary"] == {
        "image_count": 1,
        "miniprogram_count": 1,
        "attachment_count": 1,
    }
    assert {item["type"] for item in preview["materials"]} == {"image", "miniprogram", "attachment"}

    picker_response = client.get("/api/admin/material-picker/items?type=image&limit=500")
    assert picker_response.status_code == 200
    picker = picker_response.json()
    assert picker["limit"] == 100
    assert picker["items"][0]["thumbnail_url"].startswith("/api/admin/image-library/")


def test_material_picker_rejects_unknown_type_with_json(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=video")

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "素材类型必须是 image、miniprogram 或 attachment"}


def test_automation_task_detail_and_unified_send_content(client) -> None:
    response = client.put(
        "/api/admin/automation-conversion/tasks/1/send-content/unified",
        json={
            "content_package": {
                "content_text": "  统一内容  ",
                "image_library_ids": [12, 12],
                "miniprogram_library_ids": [],
                "attachment_library_ids": [56],
            }
        },
    )

    assert response.status_code == 200
    operation_content = _operation_content(response.json()["task"])
    assert operation_content["content_mode"] == "unified"
    assert operation_content["unified_content_json"]["content_text"] == "统一内容"
    assert operation_content["unified_content_json"]["image_library_ids"] == [12]

    detail_response = client.get("/api/admin/automation-conversion/tasks/1")
    assert detail_response.status_code == 200
    assert _operation_content(detail_response.json()["task"])["content_mode"] == "unified"


def test_automation_send_strategy_and_segment_content(client) -> None:
    strategy_response = client.put(
        "/api/admin/automation-conversion/tasks/1/send-strategy",
        json={"content_mode": "profile_layered", "profile_segment_template_id": 1},
    )
    assert strategy_response.status_code == 200
    assert _operation_content(strategy_response.json()["task"])["profile_segment_template_id"] == 1

    segment_response = client.put(
        "/api/admin/automation-conversion/tasks/1/send-content/profile-segments/early_founder",
        json={
            "segment_name": "早期个体创业者",
            "profile_segment_template_id": 1,
            "content_package": {"content_text": "画像分层内容"},
        },
    )

    assert segment_response.status_code == 200
    operation_content = _operation_content(segment_response.json()["task"])
    assert operation_content["content_mode"] == "profile_layered"
    assert operation_content["segment_contents_json"] == [
        {
            "segment_key": "early_founder",
            "segment_name": "早期个体创业者",
            "content_package": {
                "content_text": "画像分层内容",
                "image_library_ids": [],
                "miniprogram_library_ids": [],
                "attachment_library_ids": [],
            },
        }
    ]


def test_automation_behavior_rules_and_agent_materials(client) -> None:
    rules_response = client.get("/api/admin/automation-conversion/behavior-segment-rules")
    assert rules_response.status_code == 200
    assert [item["segment_key"] for item in rules_response.json()["rules"][0]["segments"]] == [
        "lt_2",
        "between_2_9",
        "gte_10",
    ]

    behavior_response = client.put(
        "/api/admin/automation-conversion/tasks/1/send-content/behavior-segments/between_2_9",
        json={"segment_name": "消息 2-9", "content_package": {"content_text": "消息数分层"}},
    )
    assert behavior_response.status_code == 200
    assert _operation_content(behavior_response.json()["task"])["content_mode"] == "behavior_layered"

    bad_behavior_response = client.put(
        "/api/admin/automation-conversion/tasks/1/send-content/behavior-segments/unknown",
        json={"content_package": {}},
    )
    assert bad_behavior_response.status_code == 400

    agent_response = client.put(
        "/api/admin/automation-conversion/tasks/1/send-content/agent-materials",
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
    assert agent_response.status_code == 200
    agent_config = _operation_content(agent_response.json()["task"])["agent_config_json"]
    assert agent_config == {
        "agent_code": "hxc_activation",
        "image_library_ids": [12],
        "miniprogram_library_ids": [34],
        "attachment_library_ids": [56],
        "requirement": "生成要求",
        "fallback_content": "",
        "prompt": "",
        "material_prompt": "",
    }
    assert "content_text" not in agent_config
