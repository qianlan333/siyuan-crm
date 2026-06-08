from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.questionnaire.h5_write import get_questionnaire_h5_side_effect_plans


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app())


def test_h5_submit_returns_side_effect_plan_only(client: TestClient) -> None:
    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"q_activation": "activated"}, "identity": {"external_userid": "wx_ext_001"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["real_external_call_executed"] is False
    plan = body["side_effect_plan"]
    assert plan["adapter_mode"] == "real_blocked"
    assert plan["requires_approval"] is True
    assert plan["real_external_call_executed"] is False
    assert plan["payload"]["real_external_call_executed"] is False
    assert "wecom.tag.plan" in plan["payload"]["planned_effects"]

    plans = get_questionnaire_h5_side_effect_plans()
    assert all(item["real_external_call_executed"] is False for item in plans)


def test_h5_write_source_has_no_real_external_call_markers() -> None:
    for path in [
        Path("aicrm_next/questionnaire/h5_write.py"),
        Path("aicrm_next/questionnaire/api.py"),
    ]:
        text = path.read_text(encoding="utf-8")
        forbidden = [
            '"real_external_call_executed": True',
            "'real_external_call_executed': True",
            "requests.post(",
            "httpx.post(",
            "X-AICRM-Compatibility-Facade",
        ]
        for marker in forbidden:
            assert marker not in text


def test_public_h5_read_source_has_no_legacy_public_identity_helpers() -> None:
    combined = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in [
            "aicrm_next/questionnaire/api.py",
            "aicrm_next/questionnaire/application.py",
            "aicrm_next/questionnaire/public_access.py",
            "aicrm_next/integration_gateway/legacy_flask_facade.py",
        ]
    )
    assert not (Path("aicrm_next/integration_gateway") / "legacy_questionnaire_facade.py").exists()
    for marker in [
        "get_public_questionnaire_from_legacy",
        "get_public_questionnaire_submission_status_from_legacy",
        "legacy_questionnaire_session_identity",
        "legacy_questionnaire_oauth_is_configured",
    ]:
        assert marker not in combined


def test_production_compat_no_longer_registers_h5_submit_or_diagnostics_exact_routes() -> None:
    assert not (Path("aicrm_next/production_compat") / "api.py").exists()
