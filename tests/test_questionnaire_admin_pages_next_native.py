from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_questionnaire_admin_list_page_exposes_next_read_status_without_facade() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    html = response.text
    assert "data-route-owner=\"ai_crm_next\"" in html
    assert "data-source-status=\"local_contract_probe\"" in html
    assert "data-read-model-status=\"fixture\"" in html
    assert "data-fallback-used=\"false\"" in html
    assert "hxc-activation-v1" in html
    assert "data-action=\"duplicate\"" in html
    assert "downloadQuestionnaireData" in html
    assert "data-admin-shell-source=\"next_admin_shell\"" in html


def test_questionnaire_admin_ui_alias_redirects_to_canonical_route() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires/ui", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/admin/questionnaires"


def test_questionnaire_admin_new_page_is_readonly_shell_without_write_execution() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires/new")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "新建问卷" in response.text
    assert "initialQuestionnaireId: null" in response.text


def test_questionnaire_admin_editor_exposes_other_option_controls() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires/new")

    assert response.status_code == 200
    html = response.text
    assert "设为其它选项" in html
    assert "data-option-field=\"is_other\"" in html
    assert "data-option-field=\"other_placeholder\"" in html
    assert "data-option-field=\"other_max_length\"" in html
    assert "validateOtherOptionsBeforeSave" in html


def test_questionnaire_admin_detail_page_uses_next_read_model_editor_payload() -> None:
    response = TestClient(create_app()).get("/admin/questionnaires/1")

    assert response.status_code == 200
    assert "X-AICRM-Compatibility-Facade" not in response.headers
    assert "黄小璨激活问卷" in response.text
    assert "hxc-activation-v1" in response.text
    assert "复制问卷" in response.text


def test_questionnaire_admin_pages_are_removed_from_frontend_compat_routes() -> None:
    root = Path(__file__).resolve().parents[1]

    assert not (root / "aicrm_next/frontend_compat/legacy_routes.py").exists()


def test_questionnaire_admin_templates_live_in_questionnaire_bundle() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "aicrm_next/questionnaire/templates/admin_console/questionnaires.html").exists()
    assert (root / "aicrm_next/questionnaire/templates/admin_questionnaires.html").exists()
    assert not (root / "aicrm_next/frontend_compat/templates/admin_console/questionnaires.html").exists()
    assert not (root / "aicrm_next/frontend_compat/templates/admin_questionnaires.html").exists()
