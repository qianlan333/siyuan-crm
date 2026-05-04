# JS/API Phase 8B-2: Agent Config Templates And Tag Picker Modules

## Goal

- Extract the Agent Config profile segment template and tag picker logic into ordinary static JavaScript files.
- Continue using plain browser JavaScript with the `window.AutomationAgentConfig` namespace.
- Keep this phase scoped to template/profile-segment and tag picker behavior only.
- Do not introduce Vite, TypeScript, React, Vue, or `package.json`.
- Do not change API paths, backend business logic, database schema, authentication, or RBAC.

## Migrated Scope

- Profile segment template table rendering and row selection.
- Template detail loading and detail panel rendering.
- Template create/edit form open, close, population, validation, payload collection, create, and update.
- Questionnaire/catalog dropdown rendering, segmentation question options, category rendering, category add/remove, and option selection.
- Tag picker modal open, close, search, group rendering, chip selection, selected-tag display, manual/fallback tag input, confirm, cancel, backdrop, and Escape handling.
- Static script loading in `automation_conversion_agent_config_workspace.html`.

## Not Migrated

- Default channel settings save.
- Default channel QR generation.
- Default channel welcome message save.
- Model settings load/save/test.
- Model infra connection test.

Those legacy blocks remain inline for Phase 8B-3.

## Files

- `automation_agent_config_templates.js`: profile segment template table, detail, form, category/options, create/update, and template refresh behavior.
- `automation_agent_config_tag_picker.js`: reusable tag picker state, WeCom tag loading, filtering, modal rendering, selected-tag display, and modal interaction binding.
- `automation_agent_config_boot.js`: now initializes and binds agent, template, tag picker, and placeholder interactions.
- `automation_conversion_agent_config_workspace.html`: loads the new template/tag picker scripts in dependency order while keeping default channel and model settings inline.

## Preserved Contracts

- `automation-agent-config-root` remains the root node.
- `data-api-urls`, `data-selected-template-id`, and `data-admin-action-token` remain on the root node.
- Initial JSON blocks remain in the template:
  - `automation-agent-config-initial-agents`
  - `automation-agent-config-initial-templates`
  - `automation-agent-config-initial-catalog`
- Template API URL sources still come from `data-api-urls`:
  - `profile_segment_templates`
  - `profile_segment_template_detail_base`
  - `profile_segment_template_catalog`
- Tag picker API URL source still comes from `data-api-urls`:
  - `wecom_tags`
- Template payload fields remain the legacy JSON payload fields used by the existing backend API.
- Default channel save and QR payloads remain in the legacy inline block for Phase 8B-3.
- Jinja remains the page shell.
- `AdminApi` remains the shared request/JSON/HTML helper layer.
- `automation_conversion.py` is not changed.

## Test Migration Rule

HTML tests should continue checking the root/data/script/initial JSON contract. Assertions for migrated template/table/category/tag-picker button copy, data actions, placeholders, and modal text should read the new static JavaScript files instead of expecting those markers to remain in inline JavaScript.

API response, route status, and database contract tests should not change.

## Guardrails

Phase 8B-2 extends partial Agent Config protection:

- `automation_agent_config_templates.js` and `automation_agent_config_tag_picker.js` are protected by namespace, no module-system, no duplicated request helper, and module marker checks.
- `automation_conversion_agent_config_workspace.html` is checked for the expanded script order plus root/data/initial JSON markers.
- The full Agent Config template is still not part of the no-large-inline-JS strict template list because default channel and model settings logic remain inline for Phase 8B-3.

## Next Step

Phase 8B-3 should migrate default channel, QR, and model settings/test logic into a focused static module, then decide whether Agent Config can enter the no-large-inline-JS protected template scope.
