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


def test_setup_audience_entry_template_has_visual_review_flow() -> None:
    source = _read_template()

    assert "扫码进入" in source
    assert "订单审核" in source
    assert "问卷审核" in source
    assert "运营中" in source
    assert "已转化" in source
    assert "data-audience-rule-form" in source
    assert 'data-toggle-group="order_review"' in source
    assert 'data-toggle-group="questionnaire_review"' in source
    assert 'data-toggle-group="conversion_review"' in source
    assert 'data-open-picker="order_product"' in source
    assert 'data-open-picker="questionnaire"' in source
    assert "saveAudienceRules" in source
    assert "urls.audience_entry_rule" in source
    assert "入口进入后、问卷提交后的目标人群" not in source


def test_setup_audience_entry_api_saves_next_native_fixture_payload(client) -> None:
    response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/audience-entry-rule",
        json={
            "entry_source": "both",
            "order_review": {"enabled": False},
            "questionnaire_review": {
                "enabled": True,
                "selected_questionnaire_id": 21,
                "selected_questionnaire_snapshot": {"title": "信息收集测试"},
            },
            "operating": {"enabled": True, "fixed": True},
            "conversion_review": {"enabled": False},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    rule = payload["audience_entry_rule"]["payload"]
    assert rule["questionnaire_review"]["selected_questionnaire_id"] == 21
    assert rule["questionnaire_review"]["selected_questionnaire_snapshot"]["title"] == "信息收集测试"
    assert payload["next_steps"]["scan_enter"] == "问卷审核"
    assert rule["rules"][0]["event"] == "channel_enter"


@pytest.mark.parametrize(
    ("review_payload", "message"),
    [
        ({"order_review": {"enabled": True}}, "订单审核已启用，请先选择商品"),
        ({"questionnaire_review": {"enabled": True}}, "问卷审核已启用，请先选择问卷"),
        ({"conversion_review": {"enabled": True}}, "已转化判定已启用，请先选择成交商品"),
    ],
)
def test_setup_audience_entry_api_rejects_enabled_review_without_selection(client, review_payload, message) -> None:
    response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/audience-entry-rule",
        json={
            "entry_source": "both",
            "operating": {"enabled": True, "fixed": True},
            **review_payload,
        },
    )

    assert response.status_code == 400
    assert message in response.json()["detail"]
