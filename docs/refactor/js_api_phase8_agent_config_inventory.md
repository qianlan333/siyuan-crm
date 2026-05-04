# JS/API Phase 8A: Agent Config Workspace Inventory

## Current Stage Goal

- Phase 8A is inventory-only.
- Do not split JavaScript in this phase.
- Do not change API paths or backend business logic.
- Prepare the Phase 8B module split for `automation_conversion_agent_config_workspace.html`.
- Include test-impact inventory using the PR #121 static-JS assertion migration pattern.

## Phase 8B-1 Follow-Up

- Phase 8B-1 extracted the Agent Config core, agent list/form, and prompt placeholder insertion logic into `automation_agent_config*.js`.
- Template/profile segment, tag picker, default channel, and model settings logic remain inline for later Phase 8B steps.
- The inventory below remains the Phase 8A baseline and should be read as historical input for the staged migration.

## Phase 8A 非目标 / Non-goals

- 不拆 JS：本阶段只做 inventory，不把 inline JS 迁移到静态文件。
- 不改 API：不修改任何 API path、method、payload 或 response contract。
- 不改后端：不修改 automation_conversion.py 或其他后端业务逻辑。
- 不改 Agent Config 模板行为：不修改 automation_conversion_agent_config_workspace.html 的运行行为。
- 不改数据库：不修改 schema、迁移或数据写入逻辑。
- 不改认证：不修改 session、RBAC、admin_action_token 或 internal token 逻辑。
- 不引入 Vite/TypeScript/React/Vue：本阶段仍然保持普通静态 JS 路线。

## Root Contract

- root id: `automation-agent-config-root`
- `data-admin-action-token`
- `data-api-urls`
- `data-selected-template-id`

## Initial JSON Blocks

- `automation-agent-config-initial-agents`
- `automation-agent-config-initial-templates`
- `automation-agent-config-initial-catalog`

## API URL Inventory

- `registry`
- `agents_options`
- `agent_create`
- `agent_detail_base`
- `agent_draft_base`
- `agent_delete_base`
- `agent_publish_base`
- `default_channel_settings`
- `default_channel_generate_qr`
- `wecom_tags`
- `model_settings`
- `model_settings_test`
- `profile_segment_templates`
- `profile_segment_template_detail_base`
- `profile_segment_template_catalog`

## DOM / Form / Modal Inventory

- summary grid: `agent-config-summary-grid` present - Agent/template/catalog counters at the page top.
- agent table: `agent-table-body` present - Current agent rows and edit/delete row actions.
- agent form panel: `agent-form-panel` present - Agent draft editor, prompt placeholders, save and publish controls.
- published preview: `agent-published-role-prompt` present - Published role/task prompt comparison area.
- draft diff summary: `agent-diff-summary` present - Draft versus published diff summary.
- profile segment template table: `template-table-body` present - Profile segment template list.
- template form panel: `template-form-panel` present - Profile segment template editor.
- tag picker modal: `default-channel-tag-modal-overlay` present - WeCom tag picker modal for default channel entry tag.
- default channel / QR card: `default-channel-qr-image` present - Default QR and welcome-message channel configuration.
- model infra settings: `model-settings-form` present - DeepSeek/model infra form and connection test.
- feedback / loading blocks: `agent-config-feedback` present - Top-level feedback and loading state blocks.

## Important ID Inventory

- agent_related_ids: `agent-config-feedback`, `agent-config-loading`, `agent-config-summary-grid`, `agent-create-button`, `agent-diff-summary`, `agent-empty`, `agent-form`, `agent-form-cancel`, `agent-form-feedback`, `agent-form-meta`, `agent-form-panel`, `agent-form-submit`, `agent-form-title`, `agent-load-published-button`, `agent-meta-change-summary`, `agent-meta-draft-version`, `agent-meta-published-version`, `agent-meta-status`, `agent-publish-button`, `agent-published-context-sources`, `agent-published-role-prompt`, `agent-published-task-prompt`, `agent-published-total`, `agent-table-body`, `agent-total`, `automation-agent-config-initial-agents`, `automation-agent-config-initial-catalog`, `automation-agent-config-initial-templates`, `automation-agent-config-root`
- template_related_ids: `category-add-button`, `template-category-list`, `template-create-button`, `template-detail-categories`, `template-detail-code`, `template-detail-panel`, `template-detail-summary`, `template-detail-title`, `template-edit-button`, `template-empty`, `template-form`, `template-form-cancel`, `template-form-feedback`, `template-form-panel`, `template-form-submit`, `template-form-title`, `template-table-body`, `template-total`
- tag_picker_ids: `default-channel-entry-tag-clear-button`, `default-channel-entry-tag-display`, `default-channel-entry-tag-help`, `default-channel-entry-tag-pick-button`, `default-channel-tag-groups`, `default-channel-tag-manual-input`, `default-channel-tag-modal-cancel`, `default-channel-tag-modal-close`, `default-channel-tag-modal-confirm`, `default-channel-tag-modal-overlay`, `default-channel-tag-modal-title`, `default-channel-tag-search`, `default-channel-tag-selected`
- default_channel_ids: `default-channel-feedback`, `default-channel-field-statuses`, `default-channel-form`, `default-channel-generate-button`, `default-channel-name`, `default-channel-owner`, `default-channel-provider`, `default-channel-qr-empty`, `default-channel-qr-image`, `default-channel-qr-link`, `default-channel-status`
- model_infra_ids: `model-settings-api-key-mask`, `model-settings-enabled-label`, `model-settings-feedback`, `model-settings-form`, `model-settings-test-button`, `model-settings-test-result`, `model-settings-updated-at`
- misc_ids: `catalog-total`

## Inline JS Function Inventory

- `escapeHtml`: core/helpers; request=False; token=False; dom=False; html=False; state=False
- `withId`: core/helpers; request=False; token=False; dom=False; html=False; state=False
- `withCode`: core/helpers; request=False; token=False; dom=False; html=False; state=False
- `requestJson`: core/helpers; request=True; token=False; dom=False; html=False; state=False
- `prettyJson`: core/helpers; request=False; token=False; dom=False; html=False; state=False
- `normalizeTagId`: tag picker; request=False; token=False; dom=False; html=False; state=False
- `buildUnknownTag`: tag picker; request=False; token=False; dom=False; html=False; state=False
- `ensureTagKnown`: tag picker; request=False; token=False; dom=False; html=False; state=False
- `formatTagGroupName`: tag picker; request=False; token=False; dom=False; html=False; state=False
- `formatTagLabel`: tag picker; request=False; token=False; dom=False; html=False; state=False
- `buildTagBadge`: tag picker; request=False; token=False; dom=False; html=True; state=False
- `contextSourceSpecs`: placeholder insertion; request=False; token=False; dom=False; html=False; state=False
- `detectContextSourcesFromPrompt`: placeholder insertion; request=False; token=False; dom=False; html=False; state=False
- `formatContextSourcesFromPrompt`: placeholder insertion; request=False; token=False; dom=False; html=False; state=False
- `insertPromptPlaceholder`: placeholder insertion; request=False; token=False; dom=True; html=False; state=False
- `statusLabel`: core/helpers; request=False; token=False; dom=False; html=False; state=False
- `statusBadgeClass`: core/helpers; request=False; token=False; dom=False; html=False; state=False
- `renderAgentPublishedSnapshot`: agent save/publish/delete; request=False; token=False; dom=True; html=True; state=False
- `showFeedback`: core/helpers; request=False; token=False; dom=True; html=False; state=False
- `showAgentFormFeedback`: agent list/detail/form; request=False; token=False; dom=True; html=False; state=False
- `showTemplateFormFeedback`: template list/detail/form; request=False; token=False; dom=True; html=False; state=False
- `showDefaultChannelFeedback`: default channel/QR; request=False; token=False; dom=True; html=False; state=False
- `showModelSettingsFeedback`: model settings/test; request=False; token=False; dom=True; html=False; state=False
- `normalizeAgentItem`: agent list/detail/form; request=False; token=False; dom=False; html=False; state=False
- `selectedCatalogQuestionnaire`: template list/detail/form; request=False; token=False; dom=False; html=False; state=False
- `selectedCatalogQuestion`: template list/detail/form; request=False; token=False; dom=False; html=False; state=False
- `currentQuestionOptions`: template category/options; request=False; token=False; dom=False; html=False; state=False
- `renderSummary`: unknown; request=False; token=False; dom=True; html=False; state=True
- `renderAgents`: agent list/detail/form; request=False; token=False; dom=True; html=True; state=True
- `renderQuestionnaireOptions`: template category/options; request=False; token=False; dom=False; html=True; state=True
- `renderQuestionOptions`: template category/options; request=False; token=False; dom=False; html=True; state=False
- `renderCategoryDrafts`: template category/options; request=False; token=False; dom=True; html=True; state=True
- `renderTemplateTable`: template list/detail/form; request=False; token=False; dom=True; html=True; state=True
- `renderTemplateDetail`: template list/detail/form; request=False; token=False; dom=True; html=True; state=False
- `resetAgentForm`: agent list/detail/form; request=False; token=False; dom=True; html=False; state=True
- `normalizeTemplateBundle`: template list/detail/form; request=False; token=False; dom=False; html=False; state=False
- `channelFieldStatusLabel`: default channel/QR; request=False; token=False; dom=False; html=False; state=False
- `renderDefaultChannelSelectedTag`: tag picker; request=False; token=False; dom=True; html=True; state=False
- `setDefaultChannelSelectedTag`: tag picker; request=False; token=False; dom=False; html=False; state=True
- `currentTagModalSelection`: tag picker; request=False; token=False; dom=True; html=False; state=False
- `groupedTagsForModal`: tag picker; request=False; token=False; dom=False; html=False; state=True
- `renderTagModal`: tag picker; request=False; token=False; dom=True; html=True; state=False
- `openTagModal`: tag picker; request=False; token=False; dom=True; html=False; state=False
- `closeTagModal`: tag picker; request=False; token=False; dom=True; html=False; state=False
- `confirmDefaultChannelTagSelection`: tag picker; request=False; token=False; dom=True; html=False; state=False
- `loadAvailableTags`: tag picker; request=True; token=False; dom=True; html=False; state=True
- `renderDefaultChannel`: default channel/QR; request=False; token=False; dom=True; html=True; state=False
- `renderModelSettings`: model settings/test; request=False; token=False; dom=True; html=False; state=False
- `syncInitialState`: boot/event wiring; request=False; token=False; dom=False; html=False; state=True
- `refreshAgents`: agent list/detail/form; request=True; token=False; dom=False; html=False; state=True
- `fillAgentForm`: agent list/detail/form; request=False; token=False; dom=True; html=False; state=True
- `loadAgentDetail`: agent list/detail/form; request=True; token=False; dom=False; html=False; state=False
- `openAgentCreateForm`: agent list/detail/form; request=False; token=False; dom=True; html=False; state=True
- `openAgentEditForm`: agent list/detail/form; request=False; token=False; dom=True; html=False; state=False
- `deleteAgent`: agent save/publish/delete; request=True; token=True; dom=False; html=False; state=True
- `closeAgentForm`: agent list/detail/form; request=False; token=False; dom=True; html=False; state=False
- `collectAgentPayload`: agent save/publish/delete; request=False; token=True; dom=False; html=False; state=True
- `refreshTemplates`: template list/detail/form; request=True; token=False; dom=False; html=False; state=True
- `refreshDefaultChannel`: default channel/QR; request=True; token=False; dom=False; html=False; state=True
- `refreshModelSettings`: model settings/test; request=True; token=False; dom=False; html=False; state=True
- `collectDefaultChannelPayload`: default channel/QR; request=False; token=True; dom=False; html=False; state=False
- `collectModelSettingsPayload`: model settings/test; request=False; token=True; dom=False; html=False; state=False
- `resetTemplateForm`: template list/detail/form; request=False; token=False; dom=True; html=False; state=True
- `openTemplateForm`: template list/detail/form; request=False; token=False; dom=True; html=False; state=True
- `closeTemplateForm`: template list/detail/form; request=False; token=False; dom=True; html=False; state=False
- `collectTemplatePayload`: template list/detail/form; request=False; token=False; dom=False; html=False; state=True
- `loadTemplateDetail`: template list/detail/form; request=True; token=True; dom=True; html=False; state=True

## Request/action Inventory

- line 167: `dynamic` via `requestJson(url)`; payload=options passthrough; token=False; state/list=False
- line 166: `GET` via `url`; payload=none_or_query; token=False; state/list=True
- line 705: `GET` via `apiUrls.wecom_tags`; payload=none_or_query; token=False; state/list=True
- line 827: `GET` via `apiUrls.agents_options`; payload=none_or_query; token=False; state/list=True
- line 874: `GET` via `withCode(apiUrls.agent_detail_base`; payload=none_or_query; token=False; state/list=True
- line 913: `DELETE` via `withCode(apiUrls.agent_delete_base`; payload=JSON; token=True; state/list=True
- line 959: `GET` via `apiUrls.profile_segment_templates`; payload=none_or_query; token=False; state/list=True
- line 960: `GET` via `apiUrls.profile_segment_template_catalog`; payload=none_or_query; token=False; state/list=True
- line 983: `GET` via `apiUrls.default_channel_settings`; payload=none_or_query; token=False; state/list=True
- line 990: `GET` via `apiUrls.model_settings`; payload=none_or_query; token=True; state/list=True
- line 1109: `GET` via `withId(apiUrls.profile_segment_template_detail_base`; payload=none_or_query; token=False; state/list=True
- line 1182: `POST` via `withCode(apiUrls.agent_publish_base`; payload=JSON; token=True; state/list=True
- line 1335: `GET` via `url`; payload=JSON; token=False; state/list=True
- line 1359: `PUT` via `apiUrls.default_channel_settings`; payload=JSON; token=False; state/list=True
- line 1379: `POST` via `apiUrls.default_channel_generate_qr`; payload=JSON; token=True; state/list=True
- line 1454: `PUT` via `apiUrls.model_settings`; payload=JSON; token=False; state/list=True
- line 1473: `POST` via `apiUrls.model_settings_test`; payload=JSON; token=True; state/list=False

## State Inventory

- `agents`: present; agent list state
- `templates`: present; profile segment template list state
- `templateCatalog`: present; initial/catalog questionnaire state
- `selectedAgentCode`: present; selected agent state
- `selectedAgentDetail`: present; selected agent detail state
- `selectedTemplateId`: present; selected template state
- `selectedTemplateDetail`: present; selected template detail state
- `tagModal`: present; tag picker modal state
- `categoryDrafts`: present; template form category draft state
- `defaultChannel`: present; default channel state
- `defaultChannelSelectedTag`: present; default channel selected tag state
- `modelSettings`: present; model/default channel state

## Test Impact Inventory / Test impact inventory

Phase 8B migration rules:

- HTML should keep checking root/data/script/initial JSON blocks.
- Button copy, data-action markers, placeholders, and modal text moved to static JS should be asserted from the target JS file.
- API response, route status, and DB contract tests should not change.
- Follow the PR #121 pattern: page HTML checks script references, while moved copy/actions are checked in static JS.

- `tests/test_api.py:93` `automation-conversion/shared/agents` (unknown): def _admin_action_token(client, path: str = "/admin/automation-conversion/shared/agents") -> str: -- Review during Phase 8B test migration.
- `tests/test_api.py:112` `profile_segment` (unknown): def _seed_profile_segment_questionnaire(app, *, questionnaire_id: int = 901) -> dict[str, int | list[int]]: -- Review during Phase 8B test migration.
- `tests/test_api.py:126` `agent-config` (unknown): f"agent-config-{questionnaire_id}", -- Review during Phase 8B test migration.
- `tests/test_api.py:127` `agent-config` (unknown): f"agent-config-{questionnaire_id}", -- Review during Phase 8B test migration.
- `tests/test_api.py:383` `agent_create` (unknown): def test_automation_conversion_agent_create_and_edit_flow(client): -- Review during Phase 8B test migration.
- `tests/test_api.py:390` `conversion_followup_agent` (unknown): "agent_code": "conversion_followup_agent", -- Review during Phase 8B test migration.
- `tests/test_api.py:403` `conversion_followup_agent` (unknown): assert created["agent"]["agent_code"] == "conversion_followup_agent" -- Review during Phase 8B test migration.
- `tests/test_api.py:410` `conversion_followup_agent` (api_contract_assertion): detail_response = client.get("/api/admin/automation-conversion/agents/conversion_followup_agent") -- API response and payload contract assertions should not change in Phase 8B.
- `tests/test_api.py:412` `conversion_followup_agent` (api_contract_assertion): assert detail_response.get_json()["item"]["agent_code"] == "conversion_followup_agent" -- API response and payload contract assertions should not change in Phase 8B.
- `tests/test_api.py:417` `conversion_followup_agent` (unknown): assert "conversion_followup_agent" in option_codes -- Review during Phase 8B test migration.
- `tests/test_api.py:420` `conversion_followup_agent` (api_contract_assertion): "/api/admin/automation-conversion/agents/conversion_followup_agent/draft", -- API response and payload contract assertions should not change in Phase 8B.
- `tests/test_api.py:476` `profile_segment` (unknown): def test_automation_conversion_profile_segment_template_detail_returns_template_bundle(client, app): -- Review during Phase 8B test migration.
- `tests/test_api.py:477` `profile_segment` (unknown): questionnaire = _seed_profile_segment_questionnaire(app, questionnaire_id=902) -- Review during Phase 8B test migration.
- `tests/test_api.py:480` `profile-segment` (api_contract_assertion): "/api/admin/automation-conversion/profile-segment-templates", -- API response and payload contract assertions should not change in Phase 8B.
- `tests/test_api.py:503` `profile-segment` (api_contract_assertion): detail_response = client.get(f"/api/admin/automation-conversion/profile-segment-templates/{template_id}") -- API response and payload contract assertions should not change in Phase 8B.
- `tests/test_api.py:1494` `删除` (html_contract_assertion): assert "删除问卷" in text -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_api.py:2875` `删除` (api_contract_assertion): assert enabled_delete_response.get_json()["error"] == "请先停用问卷后再删除" -- API response and payload contract assertions should not change in Phase 8B.
- `tests/test_automation_conversion_v1.py:21` `profile_segment` (unknown): create_conversion_profile_segment_template, -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:30` `profile_segment` (unknown): get_conversion_profile_segment_template_bundle, -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:40` `profile_segment` (unknown): update_conversion_profile_segment_template, -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:345` `profile_segment` (unknown): def _seed_profile_segment_template( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:353` `profile_segment` (unknown): result = create_conversion_profile_segment_template( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:739` `profile_segment` (unknown): profile_segment_template_id: int | None = None, -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:743` `profile_segment` (unknown): content_profile_segment_template_id: int | None = None, -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:753` `profile_segment` (unknown): "profile_segment_template_id": profile_segment_template_id, -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:763` `profile_segment` (unknown): if content_profile_segment_template_id is not None: -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:764` `profile_segment` (unknown): payload["content_profile_segment_template_id"] = content_profile_segment_template_id -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:859` `profile_segment` (unknown): template_seed = _seed_profile_segment_template(app, questionnaire_id=711, template_name="拆维度画像模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:870` `profile_segment` (unknown): content_profile_segment_template_id=template_seed["template_id"], -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:890` `profile_segment` (unknown): assert workflow["content_profile_segment_template_id"] == template_seed["template_id"] -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:892` `profile_segment` (unknown): assert workflow["profile_segment_template_id"] == template_seed["template_id"] -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:900` `profile_segment` (unknown): template_seed = _seed_profile_segment_template(app, questionnaire_id=712, template_name="行为筛选画像发内容") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:933` `profile_segment` (unknown): content_profile_segment_template_id=template_seed["template_id"], -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:962` `profile_segment` (unknown): "wecom_ability_service.domains.automation_conversion.workflow_runtime._resolve_profile_segment_match", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:1507` `profile_segment` (unknown): template_seed = _seed_profile_segment_template(app, questionnaire_id=739, template_name="画像分层 fallback 模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:1526` `profile_segment` (unknown): profile_segment_template_id=int(template_seed["template_id"]), -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:1730` `profile_segment` (unknown): template_seed = _seed_profile_segment_template(app, questionnaire_id=731, template_name="概览画像模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:1808` `profile_segment` (html_contract_assertion): assert detail["profile_segment_template"]["template_name"] == "概览画像模板" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:1823` `profile_segment` (unknown): "profile_segment_key", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:1824` `profile_segment` (unknown): "profile_segment_label", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:1831` `profile_segment` (unknown): assert pending_item["profile_segment_label"] == "" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:1838` `profile_segment` (html_contract_assertion): assert operating_item["profile_segment_label"] == "效率型" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:2003` `profile_segment` (unknown): "profile_segment_key", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2004` `profile_segment` (unknown): "profile_segment_label", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2076` `profile_segment` (unknown): def test_invalid_enabled_profile_segment_template_is_exposed_without_silent_dashboard_fallback(app): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2077` `profile_segment` (unknown): template_seed = _seed_profile_segment_template(app, questionnaire_id=733, template_name="脏启用模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2113` `profile_segment` (unknown): template_bundle = get_conversion_profile_segment_template_bundle(int(template_seed["template_id"])) -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2123` `profile_segment` (unknown): assert detail["profile_segment_template"]["valid"] is False -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2124` `profile_segment` (unknown): assert detail["profile_segment_template"]["selection_status"] == "no_valid_enabled_template" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2125` `profile_segment` (unknown): assert detail["profile_segment_template"]["skipped_invalid_enabled_template_count"] == 1 -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2126` `profile_segment` (unknown): assert operating_item["profile_segment_label"] == "" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2129` `profile_segment` (unknown): def test_invalid_latest_enabled_profile_segment_template_is_skipped_in_dashboard_selection(app): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2130` `profile_segment` (unknown): valid_seed = _seed_profile_segment_template(app, questionnaire_id=734, template_name="有效模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2131` `profile_segment` (unknown): invalid_seed = _seed_profile_segment_template(app, questionnaire_id=735, template_name="后建脏模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2173` `profile_segment` (html_contract_assertion): assert detail["profile_segment_template"]["template_name"] == "有效模板" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:2174` `profile_segment` (unknown): assert detail["profile_segment_template"]["valid"] is True -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2175` `profile_segment` (unknown): assert detail["profile_segment_template"]["selection_status"] == "selected" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2176` `profile_segment` (unknown): assert detail["profile_segment_template"]["skipped_invalid_enabled_template_count"] == 1 -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2177` `profile_segment` (html_contract_assertion): assert operating_item["profile_segment_label"] == "效率型" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:2180` `profile_segment` (unknown): def test_dashboard_profile_segment_selection_prefers_latest_valid_enabled_template(app): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2183` `profile_segment` (unknown): create_conversion_profile_segment_template( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2204` `profile_segment` (unknown): latest_template = create_conversion_profile_segment_template( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2261` `profile_segment` (html_contract_assertion): assert detail["profile_segment_template"]["template_name"] == "新模板" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:2262` `profile_segment` (unknown): assert detail["profile_segment_template"]["selection_strategy"] == "latest_valid_enabled" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2263` `profile_segment` (unknown): assert detail["profile_segment_template"]["selection_status"] == "selected" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2264` `profile_segment` (unknown): assert detail["profile_segment_template"]["id"] == int( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2267` `profile_segment` (html_contract_assertion): assert operating_item["profile_segment_label"] == "效率型新版" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:2270` `profile_segment` (unknown): def test_update_invalid_profile_segment_template_can_disable_it_without_repairing_structure(app): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2271` `profile_segment` (unknown): template_seed = _seed_profile_segment_template(app, questionnaire_id=737, template_name="待停用脏模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2280` `profile_segment` (unknown): result = update_conversion_profile_segment_template( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2294` `profile_segment` (unknown): def test_create_enabled_profile_segment_template_requires_enabled_category_mappings(app): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2299` `profile_segment` (unknown): create_conversion_profile_segment_template( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2549` `automation-conversion/shared/agents` (behavior_flow_test): response = client.get("/admin/automation-conversion/shared/agents") -- Route/page status and navigation behavior should not change in Phase 8B.
- `tests/test_automation_conversion_v1.py:2553` `data-agent-delete` (html_contract_assertion): assert 'data-agent-delete="custom_delete_agent"' in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:2558` `automation-conversion/shared/agents` (unknown): action_token = _admin_action_token(client, "/admin/automation-conversion/shared/agents") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2581` `删除` (unknown): workflow_name="引用删除校验任务流", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2591` `automation-conversion/shared/agents` (unknown): action_token = _admin_action_token(client, "/admin/automation-conversion/shared/agents") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2602` `删除` (html_contract_assertion): assert "引用删除校验任务流" in payload["error"] -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:2779` `profile_segment` (unknown): template_seed = _seed_profile_segment_template(app, questionnaire_id=713, template_name="节点分层录入模板") -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2785` `profile_segment` (unknown): profile_segment_template_id=template_seed["template_id"], -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:2786` `profile_segment` (unknown): content_profile_segment_template_id=template_seed["template_id"], -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:3997` `agent_create` (unknown): "idx_automation_agent_run_agent_created", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4577` `default_channel` (unknown): def test_generate_default_channel_generates_real_channel_via_wecom_provider(app, client, monkeypatch): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4670` `default_channel` (unknown): def test_default_channel_settings_save_and_readback_welcome_and_auto_accept(app, client): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4703` `default_channel` (html_contract_assertion): assert payload["settings"]["default_channel"]["welcome_message"] == "这里是默认渠道欢迎语" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:4704` `default_channel` (unknown): assert payload["settings"]["default_channel"]["auto_accept_friend"] is True -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4705` `default_channel` (unknown): assert payload["settings"]["default_channel"]["field_statuses"]["welcome_message"]["status"] == "pending" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4706` `default_channel` (unknown): assert payload["settings"]["default_channel"]["field_statuses"]["auto_accept_friend"]["status"] == "pending" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4732` `default_channel` (unknown): def test_default_channel_settings_save_and_readback_entry_tag(app): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4733` `default_channel` (unknown): from wecom_ability_service.domains.automation_conversion.service import save_default_channel_settings -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4739` `default_channel` (unknown): original = save_default_channel_settings.__globals__["list_available_wecom_tags"] -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4740` `default_channel` (unknown): save_default_channel_settings.__globals__["list_available_wecom_tags"] = lambda: list(saved_tags) -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4742` `default_channel` (unknown): payload = save_default_channel_settings( -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4749` `default_channel` (unknown): save_default_channel_settings.__globals__["list_available_wecom_tags"] = original -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4751` `default_channel` (unknown): default_channel = payload["default_channel"] -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4752` `default_channel` (unknown): assert default_channel["entry_tag_id"] == "tag-channel-001" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4753` `default_channel` (html_contract_assertion): assert default_channel["entry_tag_name"] == "渠道报名" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:4754` `default_channel` (html_contract_assertion): assert default_channel["entry_tag_group_name"] == "渠道来源" -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:4755` `default_channel` (unknown): assert default_channel["field_statuses"]["entry_tag"]["status"] == "applied" -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4771` `default_channel` (unknown): def test_generate_default_channel_reports_config_incomplete_when_wecom_config_missing(app, client, monkeypatch): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4797` `default_channel` (unknown): def test_generate_default_channel_blocks_invalid_state_before_calling_wecom(app, client, monkeypatch): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:4813` `default_channel` (unknown): "wecom_ability_service.domains.automation_conversion.provider.build_default_channel_state_token", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5433` `发布` (html_contract_assertion): assert "发布管理" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:5439` `default_channel` (unknown): def test_agent_config_page_renders_entry_tag_fields_for_default_channel(app, client): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5452` `automation-conversion/shared/agents` (behavior_flow_test): response = client.get("/admin/automation-conversion/shared/agents") -- Route/page status and navigation behavior should not change in Phase 8B.
- `tests/test_automation_conversion_v1.py:5476` `agent-config` (unknown): "/admin/automation-conversion/agent-config", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5517` `automation-conversion/shared/agents` (unknown): "/admin/automation-conversion/shared/agents", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5538` `agent-config` (unknown): "/admin/automation-conversion/agent-config", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5612` `default_channel` (unknown): def test_admin_generate_default_channel_error_keeps_channel_section(app, client, monkeypatch): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5614` `default_channel` (unknown): "wecom_ability_service.http.automation_conversion.generate_default_channel_qr", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5629` `default_channel` (unknown): def test_admin_generate_default_channel_requires_action_token(app, client): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5719` `agent_draft` (unknown): def test_save_model_infra_prompt_syncs_child_agent_draft_config(app): -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:5855` `智能体` (html_contract_assertion): assert "智能体编排" in model_infra_html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:5876` `智能体` (html_contract_assertion): assert "智能体编排" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:6016` `智能体` (html_contract_assertion): assert "子智能体列表" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:6017` `智能体` (html_contract_assertion): assert "智能体详情" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:6022` `发布` (html_contract_assertion): assert "草稿态 / 已发布态" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:8846` `智能体` (html_contract_assertion): assert "智能体编排" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_conversion_v1.py:9746` `发布` (unknown): "task_prompt": "待发布查询测试", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:9755` `发布` (unknown): change_summary="提交发布申请", -- Review during Phase 8B test migration.
- `tests/test_automation_conversion_v1.py:9917` `发布` (html_contract_assertion): assert "发布管理" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_program_phase1.py:111` `automation-conversion/shared/agents` (html_contract_assertion): assert "/admin/automation-conversion/shared/agents" in html -- If this asserts moved button copy/data-action/placeholder/modal text in HTML, Phase 8B should check the page script reference plus the target static JS file.
- `tests/test_automation_program_phase1.py:212` `agent-config` (behavior_flow_test): legacy_agent_config = client.get("/admin/automation-conversion/agent-config", follow_redirects=False) -- Route/page status and navigation behavior should not change in Phase 8B.
- `tests/test_automation_program_phase1.py:214` `automation-conversion/shared/agents` (behavior_flow_test): shared_agents = client.get("/admin/automation-conversion/shared/agents", follow_redirects=False) -- Route/page status and navigation behavior should not change in Phase 8B.

## Phase 8B Module Plan

- `automation_agent_config_core.js`
- `automation_agent_config_agents.js`
- `automation_agent_config_templates.js`
- `automation_agent_config_tag_picker.js`
- `automation_agent_config_channel_model.js`
- `automation_agent_config_boot.js`
- `automation_agent_config.js`

## Risk Flags

- very large inline script
- duplicate requestJson / escapeHtml
- many API endpoints in one page
- admin_action_token required for writes
- tag picker modal state
- JSON editor or prompt textarea state
- publish/delete destructive actions
- backend API paths should not change
- page has initial JSON blocks that must be preserved
- tests may assert inline HTML that will move into static JS after Phase 8B

## Phase 8B Forbidden Changes

- Do not change backend APIs.
- Do not change the root data contract.
- Do not change the initial JSON blocks.
- Do not change `admin_action_token` payload semantics.
- Do not change destructive action confirm flows.
- Do not introduce Vite, TypeScript, React, or Vue.

## Recommended Order for Phase 8B

- Phase 8B-1: core + boot + agent list/form + related test migration. Completed in `docs/refactor/js_api_phase8b1_agent_config_agents_modules.md`.
- Phase 8B-2: templates + tag picker + related test migration. Completed in `docs/refactor/js_api_phase8b2_agent_config_templates_tag_picker.md`.
- Phase 8B-3: default channel + model settings + guardrails. Completed in `docs/refactor/js_api_phase8b3_agent_config_channel_model.md`.

## Phase 8B-2 Status

Phase 8B-2 migrated the profile segment template list/detail/form/category/options logic and the tag picker modal into `automation_agent_config_templates.js` and `automation_agent_config_tag_picker.js`.

The remaining inline scope is intentionally limited to default channel / QR and model settings/test behavior. The Phase 8B test migration rule remains the PR #121 pattern: HTML checks root/data/script/initial JSON contracts, while moved button copy, `data-*` actions, placeholders, modal copy, and static behavior markers are checked in the corresponding static JS files.

## Phase 8B-3 Status

Phase 8B-3 migrated default channel settings, QR generation, model settings, and model connection testing into `automation_agent_config_channel_model.js`.

The remaining inline scope should now be empty except for the three `application/json` initial data blocks. Agent Config can be part of the strict no-large-inline-JS protected template scope in `scripts/audit_admin_static_js.py`. The Phase 8B test migration rule remains the PR #121 pattern: HTML checks root/data/script/initial JSON contracts, while moved button copy, `data-*` actions, placeholders, modal copy, and static behavior markers are checked in the corresponding static JS files.
