from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_STATIC = ROOT / "wecom_ability_service" / "static" / "admin_console"
ADMIN_TEMPLATES = ROOT / "wecom_ability_service" / "templates" / "admin_console"

CUSTOMER_PROFILE_MODULES = [
    "customer_profile_core.js",
    "customer_profile_sections.js",
    "customer_profile_pulse.js",
    "customer_profile_followup.js",
    "customer_profile_automation.js",
    "customer_profile.js",
]

CUSTOMER_PULSE_INBOX_MODULES = [
    "customer_pulse_inbox_core.js",
    "customer_pulse_inbox_renderers.js",
    "customer_pulse_inbox_actions.js",
    "customer_pulse_inbox_boot.js",
    "customer_pulse_inbox.js",
]

AUTOMATION_AUTO_REPLY_MODULES = [
    "automation_auto_reply_core.js",
    "automation_auto_reply_outputs.js",
    "automation_auto_reply_modal.js",
    "automation_auto_reply_actions.js",
    "automation_auto_reply.js",
]

AUTOMATION_OVERVIEW_MODULES = [
    "automation_overview_core.js",
    "automation_overview_renderers.js",
    "automation_overview_actions.js",
    "automation_overview.js",
]

AUTOMATION_AGENT_CONFIG_MODULES = [
    "automation_agent_config_core.js",
    "automation_agent_config_agents.js",
    "automation_agent_config_templates.js",
    "automation_agent_config_tag_picker.js",
    "automation_agent_config_channel_model.js",
    "automation_agent_config_boot.js",
    "automation_agent_config.js",
]

PROTECTED_MODULE_TEMPLATES = [
    "customer_detail.html",
    "customer_pulse_inbox.html",
    "automation_conversion_auto_reply_workspace.html",
    "automation_conversion_overview_workspace.html",
    "automation_conversion_agent_config_workspace.html",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_audit(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "audit_admin_static_js.py"), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _inline_script_blocks(source: str):
    return re.finditer(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>", source, re.IGNORECASE | re.DOTALL)


def test_base_template_loads_admin_api_client_before_page_scripts():
    source = _read(ADMIN_TEMPLATES / "base.html")

    admin_api_client_index = source.index("admin_console/admin_api_client.js")
    admin_console_index = source.index("admin_console/admin_console.js")
    scripts_extra_index = source.index("{% block scripts_extra %}")
    body_close_index = source.index("</body>")

    assert admin_api_client_index < admin_console_index
    assert admin_console_index < scripts_extra_index
    assert scripts_extra_index < body_close_index


def test_admin_api_client_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "admin_api_client.js")

    assert "window.AdminApi" in source
    assert "safeJsonParse" in source
    assert "escapeHtml" in source
    assert "requestJson" in source
    assert "isPermissionError" in source
    assert "normalizeRequestError" in source
    assert "credentials" in source
    assert "same-origin" in source
    assert "FormData" in source
    assert "URLSearchParams" in source
    assert "JSON.stringify" in source
    assert "response.text()" in source
    assert re.search(r"error\.status\s*=", source)
    assert re.search(r"error\.payload\s*=", source)
    assert re.search(r"error\.response\s*=", source)
    assert re.search(r"error\.url\s*=", source)
    assert re.search(r"error\.method\s*=", source)


def test_customer_detail_loads_customer_profile_modules_in_order():
    source = _read(ADMIN_TEMPLATES / "customer_detail.html")

    positions = [source.index(f"admin_console/{filename}") for filename in CUSTOMER_PROFILE_MODULES]

    assert positions == sorted(positions)
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])


def test_customer_profile_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in CUSTOMER_PROFILE_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.CustomerProfile" in source or "CustomerProfile" in source
        for token in forbidden_tokens:
            assert token not in source


def test_customer_profile_entrypoint_only_bootstraps_modules():
    source = _read(ADMIN_STATIC / "customer_profile.js")

    assert "DOMContentLoaded" in source
    assert "bootBasicSections" in source
    assert "bootCustomerPulse" in source
    assert "bootFollowupOrchestrator" in source
    assert "bootAutomation" in source
    assert not re.search(r"\bfunction\s+requestJson\s*\(", source)
    assert "fetch(" not in source
    assert "function renderCustomerPulse" not in source
    assert "function renderMessages" not in source
    assert "function executeAutomationAction" not in source


def test_customer_profile_core_exposes_shared_profile_contract():
    source = _read(ADMIN_STATIC / "customer_profile_core.js")

    assert "customerPulseAccessHeaders" in source
    assert "requestCustomerPulseJson" in source
    assert "showSectionError" in source
    assert "showSectionEmpty" in source
    assert "state" in source


def test_customer_profile_pulse_module_keeps_action_contract():
    source = _read(ADMIN_STATIC / "customer_profile_pulse.js")

    assert "loadCustomerPulse" in source
    assert "executeCustomerPulseAction" in source
    assert "submitCustomerPulseFeedback" in source
    assert "loadCustomerPulsePreview" in source
    assert "loadCustomerPulseEvidence" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_customer_profile_automation_module_keeps_action_contract():
    source = _read(ADMIN_STATIC / "customer_profile_automation.js")

    assert "loadAutomationMember" in source
    assert "executeAutomationAction" in source
    assert "data-automation-action" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_customer_profile_sections_module_keeps_basic_renderers():
    source = _read(ADMIN_STATIC / "customer_profile_sections.js")

    assert "renderLiveTags" in source
    assert "renderQuestionnaireAnswers" in source
    assert "renderMessages" in source


def test_customer_profile_followup_module_keeps_widget_contract():
    source = _read(ADMIN_STATIC / "customer_profile_followup.js")

    assert "renderFollowupOrchestratorWidget" in source
    assert "loadFollowupOrchestrator" in source


def test_customer_pulse_inbox_uses_admin_api_without_local_request_helper_copy():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox.js")

    assert "DOMContentLoaded" in source
    assert "CustomerPulseInbox.boot" in source
    assert not re.search(r"\bfunction\s+requestJson\s*\(", source)
    assert "fetch(" not in source
    assert "function renderDetail" not in source
    assert "function loadPreview" not in source
    assert "function submitAction" not in source


def test_customer_pulse_inbox_loads_modules_in_order():
    source = _read(ADMIN_TEMPLATES / "customer_pulse_inbox.html")

    positions = [source.index(f"admin_console/{filename}") for filename in CUSTOMER_PULSE_INBOX_MODULES]

    assert positions == sorted(positions)
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])
    for filename in CUSTOMER_PULSE_INBOX_MODULES:
        script_start = source.rfind("<script", 0, source.index(f"admin_console/{filename}"))
        script_end = source.index("</script>", source.index(f"admin_console/{filename}"))
        script_tag = source[script_start:script_end]
        assert "defer" in script_tag


def test_customer_pulse_inbox_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in CUSTOMER_PULSE_INBOX_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.CustomerPulseInbox" in source or "CustomerPulseInbox" in source
        for token in forbidden_tokens:
            assert token not in source


def test_customer_pulse_inbox_core_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_core.js")

    assert "store" in source
    assert "cardApiUrl" in source
    assert "customerPulseAccessHeaders" in source
    assert "setDetailState" in source
    assert "inlineStateHtml" in source


def test_customer_pulse_inbox_renderers_keep_detail_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_renderers.js")

    assert "renderDetail" in source
    assert "renderSelectedCard" in source
    assert "evidenceRefsHtml" in source
    assert "actionSlotHtml" in source
    assert "pulseFormFields" in source


def test_customer_pulse_inbox_actions_keep_api_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_actions.js")

    assert "ensureCardDetail" in source
    assert "loadCardDetail" in source
    assert "loadPreview" in source
    assert "loadEvidence" in source
    assert "submitAction" in source
    assert "submitFeedback" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_customer_pulse_inbox_boot_keeps_interaction_contract():
    source = _read(ADMIN_STATIC / "customer_pulse_inbox_boot.js")

    assert "wireInboxInteractions" in source or "wireInteractions" in source
    assert "data-card-select" in source
    assert "data-detail-action-form" in source
    assert "data-customer-pulse-inbox-json" in source
    assert "boot" in source


def test_automation_auto_reply_template_loads_modules_in_order_and_removes_inline_logic():
    source = _read(ADMIN_TEMPLATES / "automation_conversion_auto_reply_workspace.html")

    positions = [source.index(f"admin_console/{filename}") for filename in AUTOMATION_AUTO_REPLY_MODULES]

    assert positions == sorted(positions)
    assert "{{ super() }}" in source
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])
    for filename in AUTOMATION_AUTO_REPLY_MODULES:
        script_start = source.rfind("<script", 0, source.index(f"admin_console/{filename}"))
        script_end = source.index("</script>", source.index(f"admin_console/{filename}"))
        script_tag = source[script_start:script_end]
        assert "defer" in script_tag

    assert 'id="automation-auto-reply-root"' in source
    assert "data-api-urls" in source
    assert "data-admin-action-token" in source
    assert "function requestJson" not in source
    assert "function renderOutputs" not in source
    assert "function runAction" not in source
    assert "data-reply-action-url" in source
    assert "reply-output-modal" in source


def test_automation_auto_reply_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in AUTOMATION_AUTO_REPLY_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.AutomationAutoReply" in source or "AutomationAutoReply" in source
        for token in forbidden_tokens:
            assert token not in source


def test_automation_auto_reply_core_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_core.js")

    assert "getAdminActionToken" in source
    assert "getApiUrls" in source
    assert "withOutputId" in source
    assert "withWebhookOutputId" in source
    assert "withWecomOutputId" in source
    assert "copyClipboardText" in source
    assert "state" in source


def test_automation_auto_reply_outputs_keeps_review_output_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_outputs.js")

    assert "renderOutputs" in source
    assert "loadOutputs" in source
    assert "data-review-action" in source
    assert "webhook" in source
    assert "wecom_send" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_automation_auto_reply_modal_keeps_rejected_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_modal.js")

    assert "openRejectModal" in source
    assert "closeRejectModal" in source
    assert "setModalFeedback" in source
    assert "review_note" in source
    assert "decision" in source
    assert "rejected" in source


def test_automation_auto_reply_actions_keep_formdata_action_contract():
    source = _read(ADMIN_STATIC / "automation_auto_reply_actions.js")

    assert "runAction" in source
    assert "data-reply-action-url" in source
    assert "data-reply-toggle-enabled" in source
    assert "FormData" in source
    assert "admin_action_token" in source
    assert "X-Requested-With" in source


def test_automation_auto_reply_entrypoint_only_bootstraps_modules():
    source = _read(ADMIN_STATIC / "automation_auto_reply.js")

    assert "DOMContentLoaded" in source
    assert "boot" in source
    assert "function renderOutputs" not in source
    assert "function runAction" not in source
    assert "function requestJson" not in source


def test_automation_overview_template_loads_modules_in_order_and_removes_inline_logic():
    source = _read(ADMIN_TEMPLATES / "automation_conversion_overview_workspace.html")

    positions = [source.index(f"admin_console/{filename}") for filename in AUTOMATION_OVERVIEW_MODULES]

    assert positions == sorted(positions)
    assert "{{ super() }}" in source
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])
    for filename in AUTOMATION_OVERVIEW_MODULES:
        script_start = source.rfind("<script", 0, source.index(f"admin_console/{filename}"))
        script_end = source.index("</script>", source.index(f"admin_console/{filename}"))
        script_tag = source[script_start:script_end]
        assert "defer" in script_tag

    assert 'id="automation-overview-root"' in source
    assert "data-api-urls" in source
    assert "data-admin-action-token" in source
    assert "function requestJson" not in source
    assert "function renderDashboard" not in source
    assert "function renderMemberGroups" not in source
    assert "function postAdminAction" not in source
    assert "overview-refresh-button" in source
    assert "overview-member-groups" in source
    assert "overview-execution-body" in source


def test_automation_overview_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in AUTOMATION_OVERVIEW_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.AutomationOverview" in source or "AutomationOverview" in source
        for token in forbidden_tokens:
            assert token not in source


def test_automation_overview_core_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "automation_overview_core.js")

    assert "getAdminActionToken" in source
    assert "getApiUrls" in source
    assert "showFeedback" in source
    assert "requestJson" in source
    assert "escapeHtml" in source


def test_automation_overview_renderers_keep_dashboard_contract():
    source = _read(ADMIN_STATIC / "automation_overview_renderers.js")

    assert "renderDashboard" in source
    assert "renderMemberGroups" in source
    assert "computeAdditionalStats" in source
    assert "profileTemplateNote" in source
    assert "overview-execution-body" in source
    assert "overview-questionnaire-submitted" in source


def test_automation_overview_actions_keep_refresh_contract():
    source = _read(ADMIN_STATIC / "automation_overview_actions.js")

    assert "loadDashboard" in source
    assert "postAdminAction" in source
    assert "bindRefreshAction" in source
    assert "FormData" in source
    assert "admin_action_token" in source or "adminActionToken" in source
    assert "X-Requested-With" in source
    assert "message_activity_sync_run" in source
    assert "reply_monitor_capture" in source
    assert "reply_monitor_run_due" in source
    for status in ["disabled", "idle", "throttled", "quiet_hours"]:
        assert status in source


def test_automation_overview_entrypoint_only_bootstraps_modules():
    source = _read(ADMIN_STATIC / "automation_overview.js")

    assert "DOMContentLoaded" in source
    assert "boot" in source
    assert "function renderDashboard" not in source
    assert "function renderMemberGroups" not in source
    assert "function postAdminAction" not in source
    assert "function requestJson" not in source


def test_automation_agent_config_template_loads_agent_modules_in_order_and_keeps_partial_contract():
    source = _read(ADMIN_TEMPLATES / "automation_conversion_agent_config_workspace.html")

    positions = [source.index(f"admin_console/{filename}") for filename in AUTOMATION_AGENT_CONFIG_MODULES]

    assert positions == sorted(positions)
    assert "{{ super() }}" in source
    assert source.index("{% block scripts_extra %}") < positions[0]
    assert positions[-1] < source.index("{% endblock %}", positions[-1])
    for filename in AUTOMATION_AGENT_CONFIG_MODULES:
        script_start = source.rfind("<script", 0, source.index(f"admin_console/{filename}"))
        script_end = source.index("</script>", source.index(f"admin_console/{filename}"))
        script_tag = source[script_start:script_end]
        assert "defer" in script_tag

    assert 'id="automation-agent-config-root"' in source
    assert "data-api-urls" in source
    assert "data-selected-template-id" in source
    assert "data-admin-action-token" in source
    assert "automation-agent-config-initial-agents" in source
    assert "automation-agent-config-initial-templates" in source
    assert "automation-agent-config-initial-catalog" in source
    assert "function renderAgents" not in source
    assert "function refreshAgents" not in source
    assert "function loadAgentDetail" not in source
    assert "function collectAgentPayload" not in source
    assert "function insertPromptPlaceholder" not in source
    assert "function renderTemplateTable" not in source
    assert "function openTemplateForm" not in source
    assert "function loadTemplateDetail" not in source
    assert "function renderTagGroups" not in source
    assert "function openTagPicker" not in source
    assert "function saveDefaultChannelSettings" not in source
    assert "function loadModelSettings" not in source
    assert "document.addEventListener" not in source
    assert "template-table-body" in source
    assert "template-form-panel" in source
    assert "default-channel-tag-modal-overlay" in source
    assert "data-template-id" in source


def test_automation_agent_config_module_files_exist_and_stay_plain_browser_js():
    forbidden_tokens = ["import ", "export ", "require(", 'from "', "from '"]

    for filename in AUTOMATION_AGENT_CONFIG_MODULES:
        source = _read(ADMIN_STATIC / filename)

        assert "window.AutomationAgentConfig" in source or "AutomationAgentConfig" in source
        for token in forbidden_tokens:
            assert token not in source


def test_automation_agent_config_core_exposes_shared_contract():
    source = _read(ADMIN_STATIC / "automation_agent_config_core.js")

    assert "getApiUrls" in source
    assert "getAdminActionToken" in source
    assert "parseJsonScript" in source
    assert "state" in source
    assert "showFeedback" in source
    assert "requestJson" in source
    assert "statusLabel" in source
    assert "updateSummaryCounters" in source


def test_automation_agent_config_agents_keep_agent_action_contract():
    source = _read(ADMIN_STATIC / "automation_agent_config_agents.js")

    assert "renderAgentTable" in source
    assert "openAgentForm" in source
    assert "loadAgentDetail" in source
    assert "collectAgentPayload" in source
    assert "saveAgentDraft" in source
    assert "publishAgent" in source
    assert "deleteAgent" in source
    assert "loadPublishedIntoDraft" in source
    assert "data-agent-edit" in source
    assert "data-agent-delete" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_automation_agent_config_templates_keep_profile_segment_contract():
    source = _read(ADMIN_STATIC / "automation_agent_config_templates.js")

    assert "renderTemplateTable" in source
    assert "openTemplateForm" in source
    assert "loadTemplateDetail" in source
    assert "collectTemplatePayload" in source
    assert "saveTemplate" in source
    assert "renderTemplateCategories" in source
    assert "addTemplateCategory" in source
    assert "removeTemplateCategory" in source
    assert "profile_segment_templates" in source
    assert "profile_segment_template_detail_base" in source
    assert "profile_segment_template_catalog" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_automation_agent_config_tag_picker_keeps_modal_contract():
    source = _read(ADMIN_STATIC / "automation_agent_config_tag_picker.js")

    assert "openTagPicker" in source
    assert "closeTagPicker" in source
    assert "loadWeComTags" in source
    assert "renderTagGroups" in source
    assert "renderSelectedTags" in source
    assert "confirmTagSelection" in source
    assert "wecom_tags" in source
    assert "data-tag-id" in source or "data-tag-picker" in source


def test_automation_agent_config_channel_model_keeps_channel_model_contract():
    source = _read(ADMIN_STATIC / "automation_agent_config_channel_model.js")

    assert "loadDefaultChannelSettings" in source
    assert "saveDefaultChannelSettings" in source
    assert "generateDefaultChannelQr" in source
    assert "renderDefaultChannelQr" in source
    assert "applyTagSelectionToDefaultChannel" in source
    assert "loadModelSettings" in source
    assert "saveModelSettings" in source
    assert "testModelSettings" in source
    assert "renderModelFieldStatus" in source
    assert "default_channel_settings" in source
    assert "default_channel_generate_qr" in source
    assert "model_settings" in source
    assert "model_settings_test" in source
    assert "admin_action_token" in source or "adminActionToken" in source


def test_automation_agent_config_boot_keeps_placeholder_and_partial_binding_contract():
    source = _read(ADMIN_STATIC / "automation_agent_config_boot.js")

    assert "boot" in source
    assert "data-agent-placeholder" in source
    assert "focusedPromptField" in source
    assert "role_prompt" in source
    assert "task_prompt" in source
    assert "bindTemplateInteractions" in source
    assert "bindTagPickerInteractions" in source
    assert "bindChannelModelInteractions" in source


def test_automation_agent_config_entrypoint_only_bootstraps_modules():
    source = _read(ADMIN_STATIC / "automation_agent_config.js")

    assert "DOMContentLoaded" in source
    assert "boot" in source
    assert "function renderAgentTable" not in source
    assert "function saveAgentDraft" not in source
    assert "function publishAgent" not in source
    assert "function deleteAgent" not in source
    assert "function renderTemplateTable" not in source
    assert "function openTagPicker" not in source
    assert "function saveDefaultChannelSettings" not in source
    assert "function loadModelSettings" not in source


def test_audit_admin_static_js_script_json_contract():
    result = _run_audit("--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["blocking_count"] == 0
    assert "checks" in payload
    assert payload["checks"]


def test_audit_admin_static_js_script_strict_passes():
    result = _run_audit("--strict")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "admin static JS audit: OK" in result.stdout


def test_guardrails_protected_templates_have_no_large_inline_js():
    for filename in PROTECTED_MODULE_TEMPLATES:
        source = _read(ADMIN_TEMPLATES / filename)
        for match in _inline_script_blocks(source):
            attrs = match.group("attrs")
            body = match.group("body").strip()
            if "src=" in attrs or "application/json" in attrs or not body:
                continue
            assert len(body) <= 160
            assert "function " not in body
            assert "=>" not in body
            assert "addEventListener" not in body

    auto_reply_source = _read(ADMIN_TEMPLATES / "automation_conversion_auto_reply_workspace.html")
    assert "function requestJson" not in auto_reply_source
    assert "function renderOutputs" not in auto_reply_source
    assert "function runAction" not in auto_reply_source

    overview_source = _read(ADMIN_TEMPLATES / "automation_conversion_overview_workspace.html")
    assert "function requestJson" not in overview_source
    assert "function renderDashboard" not in overview_source
    assert "function renderMemberGroups" not in overview_source
    assert "function postAdminAction" not in overview_source

    agent_config_source = _read(ADMIN_TEMPLATES / "automation_conversion_agent_config_workspace.html")
    assert "function requestJson" not in agent_config_source
    assert "function renderAgentTable" not in agent_config_source
    assert "function renderTemplateTable" not in agent_config_source
    assert "function saveDefaultChannelSettings" not in agent_config_source
    assert "function loadModelSettings" not in agent_config_source
    assert "document.addEventListener" not in agent_config_source


def test_guardrails_action_token_contract():
    expectations = [
        (ADMIN_STATIC / "customer_profile_pulse.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_STATIC / "customer_pulse_inbox_actions.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_STATIC / "automation_auto_reply_actions.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_STATIC / "automation_auto_reply_outputs.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_TEMPLATES / "automation_conversion_auto_reply_workspace.html", ("data-admin-action-token",)),
        (ADMIN_STATIC / "automation_overview_actions.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_TEMPLATES / "automation_conversion_overview_workspace.html", ("data-admin-action-token",)),
        (ADMIN_STATIC / "automation_agent_config_agents.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_STATIC / "automation_agent_config_templates.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_STATIC / "automation_agent_config_channel_model.js", ("admin_action_token", "adminActionToken")),
        (ADMIN_TEMPLATES / "automation_conversion_agent_config_workspace.html", ("data-admin-action-token",)),
    ]

    for path, markers in expectations:
        source = _read(path)
        assert any(marker in source for marker in markers), path


def test_guardrails_no_frontend_build_tooling():
    forbidden_paths = [
        ROOT / "package.json",
        ROOT / "vite.config.ts",
        ROOT / "tsconfig.json",
        ROOT / "node_modules",
        ROOT / "web" / "package.json",
    ]

    assert not [path for path in forbidden_paths if path.exists()]
