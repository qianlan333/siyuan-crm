from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "automation_program_setup_next.html"


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def _read_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_setup_segmentation_template_has_visual_question_and_category_editor() -> None:
    source = _read_template()

    assert "问卷选择器" in source
    assert "data-questionnaire-select" in source
    assert "data-questions" in source
    assert "data-segmentation-question-select" in source
    assert "data-normal-category-editor" in source
    assert "未分配选项" in source
    assert "可加入此分类的未分配选项" in source
    assert "saveSegmentation" in source
    assert "normal_question_categories" in source
    assert "hit_option_ids" not in source
    assert "规则 JSON" not in source


def test_setup_segmentation_api_saves_next_native_fixture_payload(client) -> None:
    response = client.post(
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
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    normal = payload["segmentation"]["payload"]["strategies"]["normal_question_rules"]
    assert normal["segmentation_question_id"] == 301
    assert normal["categories"][0]["category_name"] == "职场人"
    assert normal["categories"][0]["option_snapshots"][0]["option_text"] == "还在职场安心升级打怪"


def test_setup_segmentation_api_rejects_duplicate_option_assignment(client) -> None:
    response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/segmentation",
        json={
            "questionnaire_id": 21,
            "segmentation_question_id": 301,
            "normal_question_categories": [
                {"category_key": "a", "category_name": "A", "option_ids": [401]},
                {"category_key": "b", "category_name": "B", "option_ids": [401]},
            ],
        },
    )

    assert response.status_code == 400
    assert "同一个选项不能同时属于多个分类" in response.json()["detail"]
