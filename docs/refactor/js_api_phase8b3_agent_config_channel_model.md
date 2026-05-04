# JS/API Phase 8B-3: Agent Config Channel And Model Modules

## Goal

- Extract the remaining Agent Config default channel, QR, and model settings logic into an ordinary static JavaScript file.
- Remove the remaining large inline JavaScript from `automation_conversion_agent_config_workspace.html`.
- Continue using plain browser JavaScript with the `window.AutomationAgentConfig` namespace.
- Do not introduce Vite, TypeScript, React, Vue, or `package.json`.
- Do not change API paths, backend business logic, database schema, authentication, or RBAC.

## Migrated Scope

- Default channel settings load and form population.
- Default channel welcome message, auto-accept, and selected tag payload collection.
- Default channel settings save.
- Default channel QR generation and QR preview rendering.
- Default channel field status rendering.
- Model settings load and form population.
- Model settings payload collection and save.
- Model connection test and status rendering.
- Final Agent Config boot wiring for the channel/model module.

## Files

- `automation_agent_config_channel_model.js`: default channel, QR, model settings, model test, feedback, and related interaction binding.
- `automation_agent_config_boot.js`: now binds and loads agent, template, tag picker, channel/model, and placeholder interactions from `AutomationAgentConfig.boot()`.
- `automation_conversion_agent_config_workspace.html`: now only loads static scripts and keeps the initial application/json data blocks.

## Preserved Contracts

- `automation-agent-config-root` remains the root node.
- `data-api-urls`, `data-selected-template-id`, and `data-admin-action-token` remain on the root node.
- Initial JSON blocks remain in the template:
  - `automation-agent-config-initial-agents`
  - `automation-agent-config-initial-templates`
  - `automation-agent-config-initial-catalog`
- Channel/model API URL sources still come from `data-api-urls`:
  - `default_channel_settings`
  - `default_channel_generate_qr`
  - `model_settings`
  - `model_settings_test`
- Write payloads still include `admin_action_token` where the legacy inline code sent it.
- Default channel payload fields are unchanged.
- Model settings payload fields are unchanged.
- Jinja remains the page shell.
- `AdminApi` remains the shared request/JSON/HTML helper layer.
- `automation_conversion.py` is not changed.

## Test Migration Rule

HTML tests should check the root/data/script/initial JSON contract and the stable DOM shell. Assertions for moved channel/model copy, action markers, and behavior markers should read `automation_agent_config_channel_model.js`.

API response, route status, and database contract tests should not change.

## Guardrails

Phase 8B-3 completes Agent Config modularization:

- `automation_agent_config_channel_model.js` enters protected static JS scope.
- `automation_conversion_agent_config_workspace.html` enters the no-large-inline-JS protected template scope.
- The protected template may keep `application/json` initial data blocks, but not large inline behavior scripts.
- All `automation_agent_config*.js` files remain protected by namespace, no module-system, no duplicated request helper, script-order, and action-token checks.

## Next Step

- Phase 8C can do cleanup and final hardening around Agent Config contracts.
- A Vite or TypeScript proof of concept should remain a separate PR and should update guardrails and deployment notes before changing the build model.
