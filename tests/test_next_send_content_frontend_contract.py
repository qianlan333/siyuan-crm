from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "aicrm_next" / "frontend_compat" / "static" / "admin_console"
AUTOMATION_STATIC = ROOT / "aicrm_next" / "automation_engine" / "static" / "admin_console"
AUTOMATION_TEMPLATES = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console"
TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "templates" / "admin_console" / "_automation_operation_orchestration_panel.html"
HXC_TEMPLATE = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console" / "hxc_dashboard.html"
CHANNEL_FORM_TEMPLATE = AUTOMATION_TEMPLATES / "channel_code_form.html"
GROUP_OPS_TEMPLATE = ROOT / "aicrm_next" / "automation_engine" / "group_ops" / "templates" / "admin_console" / "group_ops.html"
CLOUD_CAMPAIGNS_TEMPLATE = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console" / "cloud_campaigns_workspace.html"
OPERATION_JS = AUTOMATION_STATIC / "automation_operation_orchestration_panel.js"
MATERIAL_PICKER_CSS = STATIC / "material_picker.css"
SEND_CONTENT_ASSET_VERSION = "send-content-preview-ux-20260527"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_send_content_composer_exists_and_exposes_global_api() -> None:
    source = _read(STATIC / "send_content_composer.js")

    assert "window.AICRMSendContentComposer" in source
    assert ".open" in source or "{ open }" in source


def test_material_picker_exists_and_exposes_global_api() -> None:
    source = _read(STATIC / "material_picker.js")

    assert "window.AICRMMaterialPicker" in source
    assert ".open" in source or "{ open }" in source


def test_material_picker_hidden_empty_state_overrides_grid_display() -> None:
    source = _read(MATERIAL_PICKER_CSS)

    assert ".aicrm-material-picker__empty[hidden]" in source
    assert "display: none !important" in source


def test_standard_send_content_assets_are_cache_busted_on_migrated_surfaces() -> None:
    templates = [
        TEMPLATE,
        CHANNEL_FORM_TEMPLATE,
        GROUP_OPS_TEMPLATE,
        CLOUD_CAMPAIGNS_TEMPLATE,
        HXC_TEMPLATE,
    ]

    for path in templates:
        source = _read(path)
        assert "material_picker.css') }}?v=" in source
        assert "send_content_composer.css') }}?v=" in source
        assert "material_picker.js') }}?v=" in source
        assert "send_content_composer.js') }}?v=" in source
    assert SEND_CONTENT_ASSET_VERSION in _read(TEMPLATE)


def test_send_content_composer_excludes_non_standard_controls() -> None:
    source = _read(STATIC / "send_content_composer.js")

    for forbidden in ["插入班期", "插入顾问名", "AI 改写", "保存为话术模板"]:
        assert forbidden not in source


def test_send_content_composer_supports_text_disabled_agent_mode() -> None:
    source = _read(STATIC / "send_content_composer.js")

    assert "textEnabled" in source
    assert "textEnabled=false" not in source
    assert "Agent 将为每个客户生成个性化话术" in source
    assert 'content_text: textEnabled ? normalized.content_text : ""' in source


def test_send_content_composer_uses_direct_material_add_buttons() -> None:
    source = _read(STATIC / "send_content_composer.js")

    assert 'data-add-material="image"' in source
    assert 'data-add-material="miniprogram"' in source
    assert 'data-add-material="attachment"' in source
    assert "+图片" in source
    assert "+小程序" in source
    assert "+附件" in source
    assert "data-composer-type" not in source
    assert "activeType" not in source


def test_send_content_composer_preview_renders_visual_material_cards() -> None:
    source = _read(STATIC / "send_content_composer.js")
    css = _read(STATIC / "send_content_composer.css")

    assert "function materialPreviewCard" in source
    assert "item.thumbnail_url" in source
    assert '<img src="${escapeHtml(item.thumbnail_url)}"' in source
    assert "aicrm-send-composer__preview-material" in source
    assert "aicrm-send-composer__preview-thumb" in css
    assert "object-fit: cover" in css


def test_send_content_composer_modal_fits_without_horizontal_scroll() -> None:
    css = _read(STATIC / "send_content_composer.css")

    assert "width: min(1180px, calc(100vw - 32px))" in css
    assert "overflow-x: hidden" in css
    assert "grid-template-columns: minmax(420px, 1fr) minmax(300px, 380px)" in css


def test_operation_panel_references_send_content_composer_assets() -> None:
    source = _read(TEMPLATE)

    assert "send_content_composer.js" in source
    assert "send_content_composer.css" in source
    assert "material_picker.js" in source
    assert "material_picker.css" in source
    assert "automation_operation_orchestration_panel.js" in source
    assert "(() => {" not in source


def test_operation_panel_does_not_prompt_for_material_ids() -> None:
    source = _read(TEMPLATE) + _read(OPERATION_JS)

    assert "请输入图片" + "素材编号" not in source
    assert "请输入小程序" + "素材编号" not in source
    assert "请输入附件" + "素材编号" not in source


def test_operation_panel_contains_profile_template_selector_logic() -> None:
    source = _read(OPERATION_JS)

    assert "profile-segment-templates/options" in source
    assert "data-profile-template-select" in source
    assert "profile_segment_template_id" in source
    assert "当前方案分层规则还没有可填写的分层" in source


def test_operation_panel_contains_behavior_rule_logic() -> None:
    source = _read(OPERATION_JS)

    assert "behavior-segment-rules" in source
    assert "data-behavior-rule-select" in source
    assert "lt_2" in source
    assert "between_2_9" in source
    assert "gte_10" in source


def test_operation_panel_contains_agent_selector_logic() -> None:
    source = _read(OPERATION_JS)

    assert "/api/admin/automation-conversion/agents" in source
    assert "data-agent-select" in source
    assert "textEnabled: true" in source
    assert "agent-materials" in source


def test_operation_panel_external_js_has_runtime_ready_and_composer_guard() -> None:
    source = _read(OPERATION_JS)

    assert "data-operation-panel-ready" in source or "operationPanelReady" in source
    assert "operationPanelError" in source
    assert "function openSendContentComposer" in source
    assert "标准内容编辑器未加载，请刷新页面后重试" in source
    assert "safeLoadAuxiliary" in source
    assert "data-config-unified" in source
    assert "配置话术和素材" in source


def test_material_selection_only_uses_material_picker_contract() -> None:
    panel = _read(TEMPLATE) + _read(OPERATION_JS)
    composer = _read(STATIC / "send_content_composer.js")
    picker = _read(STATIC / "material_picker.js")

    assert "AICRMMaterialPicker.open" in composer
    assert "素材选择器未加载，请刷新页面后重试" in composer
    assert "/api/admin/material-picker/items" in picker
    for source in [panel, composer, picker]:
        assert "/api/admin/image-library" not in source
        assert "/api/admin/miniprogram-library" not in source
        assert "/api/admin/attachment-library" not in source
        assert "hxc-" + "asset-grid" not in source
        assert "hxc-" + "img-grid" not in source
        assert "hxc-" + "mp-grid" not in source


def test_hxc_dashboard_uses_standard_composer_without_legacy_broadcast() -> None:
    source = _read(HXC_TEMPLATE)

    assert "AICRMSendContentComposer.open" in source
    assert "send_content_composer.js" in source
    assert "/api/admin/hxc-dashboard/broadcast-tasks" in source
    assert not re.search(r"fetch\([\"']/api/admin/hxc-dashboard/broadcast[\"']", source)
    assert "/api/admin/image-library" not in source
    assert "/api/admin/miniprogram-library" not in source
    assert "hxc-" + "asset-grid" not in source
    assert "hxc-" + "img-grid" not in source
    assert "hxc-" + "mp-grid" not in source
