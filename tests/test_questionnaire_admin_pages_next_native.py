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
    assert ".questionnaire-toast.is-busy" in html
    assert "导出中，请稍候..." in html
    assert "导出中..." in html
    assert "function downloadQuestionnaireData(questionnaireId, button)" in html
    assert "downloadQuestionnaireData(item.id, button)" in html
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


def test_questionnaire_completion_target_ui_keeps_simple_h5_and_dynamic_url_link_modes() -> None:
    root = Path(__file__).resolve().parents[1]
    templates = [
        root / "aicrm_next/questionnaire/templates/admin_questionnaires.html",
        root / "aicrm_next/frontend_compat/templates/admin_console/questionnaire_detail.html",
    ]

    for template in templates:
        text = template.read_text(encoding="utf-8")
        assert "提交后跳转" in text
        assert "提交后动作" not in text
        assert "H5 跳转地址" in text
        assert "动态 URL Link 接口" in text
        assert "响应字段" in text
        assert "completion_url_link_response_key" in text
        assert "打开微信小程序" not in text
        assert "completion_target_type" in text
        assert "splitMiniProgramPathInput" not in text
        assert "小程序原始 ID" not in text
        assert "小程序页面路径" not in text
        assert "兜底链接" not in text

        assert "field-redirect-url" not in text
        assert "v2-basic-redirect" not in text
        assert "completion_open_strategy" not in text
        assert "data-open-strategy" not in text
        assert "target-desc" not in text
        assert "mode-note" not in text
        assert "mini_program_appid" not in text
        assert "mini_program_username" not in text
        assert "mini_program_path" not in text
        assert "completion_fallback_url" not in text
        assert "mini_program_env_version" not in text
        assert "mini_program_query" not in text
        assert "mini_program_url_link" not in text
        assert "data-h5-url-fields" in text
        assert "data-url-link-fields" in text
        assert "[data-h5-url-fields][hidden]" in text
        assert "[data-url-link-fields][hidden]" in text
        assert "打开小程序 URL Link" not in text
        assert "URL Link 兜底" not in text
