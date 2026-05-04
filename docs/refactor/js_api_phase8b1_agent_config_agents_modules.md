# JS/API Phase 8B-1: Agent Config Agent Modules

## Goal

- Extract the Agent Config workspace core, agent list/form, and placeholder insertion logic into ordinary static JavaScript files.
- Keep the page on plain browser JavaScript with the `window.AutomationAgentConfig` namespace.
- Do not introduce Vite, TypeScript, React, Vue, or `package.json`.
- Do not change API paths, backend business logic, database schema, authentication, or RBAC.
- Keep this stage narrow; do not migrate the whole Agent Config workspace in one PR.

## Migrated Scope

- Core/shared page helpers: root lookup, `AdminApi` helper wrapping, JSON script parsing, API URL lookup, action-token lookup, shared state, feedback helpers, URL helpers, status labels, and summary counters.
- Agent list and form behavior: table rendering, create/edit form opening, detail loading, draft population, draft save, publish, delete, published-preview copy-back, and diff summary rendering.
- Prompt placeholder insertion: `data-agent-placeholder` click handling, `role_prompt` / `task_prompt` focus tracking, and insertion into the focused prompt textarea.
- Static script loading in `automation_conversion_agent_config_workspace.html`.

## Not Migrated

- Profile segment template list/detail/form/category/options logic.
- Tag picker modal logic.
- Default channel and QR configuration logic.
- Model settings and model connectivity test logic.
- Template form submission or template detail loading.
- Default channel tag selection.

Those legacy blocks remain inline for later Phase 8B work.

## Files

- `automation_agent_config_core.js`: defines `window.AutomationAgentConfig`, shared state, root/API/action-token helpers, `AdminApi` wrappers, initial JSON parsing, feedback helpers, URL helpers, status helpers, and summary counters.
- `automation_agent_config_agents.js`: renders and manages the agent table, agent editor form, draft save, publish, delete, published preview, and diff summary.
- `automation_agent_config_boot.js`: initializes Agent Config state for the migrated agent area, binds agent interactions, binds prompt placeholder insertion, and refreshes the agent list.
- `automation_agent_config.js`: small `DOMContentLoaded` entrypoint that calls `AutomationAgentConfig.boot()`.

## Preserved Contracts

- `automation-agent-config-root` remains the root node.
- `data-api-urls`, `data-selected-template-id`, and `data-admin-action-token` remain on the root node.
- Initial JSON blocks remain in the template:
  - `automation-agent-config-initial-agents`
  - `automation-agent-config-initial-templates`
  - `automation-agent-config-initial-catalog`
- Agent API URL sources still come from `data-api-urls`.
- `admin_action_token` payload field and semantics are unchanged.
- Agent destructive action confirmation text and flow are unchanged.
- Jinja remains the page shell.
- `AdminApi` remains the shared request/JSON/HTML helper layer.
- `automation_conversion.py` is not changed.

## Test Migration Rule

For this stage, HTML tests should keep checking the root/data/script/initial JSON contract. Assertions for migrated agent button actions, placeholders, and agent form behavior markers should read the new static JavaScript files instead of expecting those markers to remain only in inline HTML.

API response, route status, and database contract tests should not change.

## Guardrails

Phase 8B-1 adds partial Agent Config protection:

- `automation_agent_config*.js` are protected by namespace, no module-system, no duplicated request helper, and action-token marker checks.
- `automation_conversion_agent_config_workspace.html` is protected for script order and root/data/initial JSON markers.
- The full Agent Config template is not yet part of the no-large-inline-JS strict template list because template/profile-segment, tag picker, default channel, and model settings logic still remain inline for later phases.

## Next Step

Phase 8B-2 should migrate profile segment template and tag picker logic into separate static files, with matching tests moved from inline HTML assertions to static JS assertions where needed.
