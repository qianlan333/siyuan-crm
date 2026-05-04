# JS/API Guardrails

## Completed Stages

- Phase 1: route inventory, focused admin API docs correction, and the first `AdminApi` shared client.
- Phase 2: stronger `AdminApi.requestJson` behavior and deeper reuse from customer admin JS.
- Phase 3: customer detail split into ordinary static JS files under `window.CustomerProfile`.
- Phase 4: Customer Pulse Inbox split into ordinary static JS files under `window.CustomerPulseInbox`.
- Phase 5: automation auto reply workspace inline JS extracted into ordinary static JS files under `window.AutomationAutoReply`.
- Phase 7: automation overview workspace inline JS extracted into ordinary static JS files under `window.AutomationOverview`.
- Phase 8A: automation Agent Config workspace inventory only; no JS extraction yet.
- Phase 8B-1: automation Agent Config core, agent list/form, and placeholder insertion extracted into ordinary static JS files under `window.AutomationAgentConfig`.
- Phase 8B-2: automation Agent Config profile segment template and tag picker logic extracted into ordinary static JS files under `window.AutomationAgentConfig`.
- Phase 8B-3: automation Agent Config default channel, QR, and model settings logic extracted; the workspace no longer carries large inline behavior JS.

## Shared Principles

- Flask remains the backend API/BFF layer.
- Jinja remains the page shell.
- Admin page JavaScript uses plain static files and a `window` namespace.
- The current stage does not use Vite, TypeScript, React, or Vue.
- Shared request, JSON parsing, and HTML escaping helpers go through `AdminApi`.
- Page-specific tenant, actor, and action-token behavior stays in the page namespace.
- API paths do not change as part of JS modularization.
- Authentication and RBAC do not change as part of JS modularization.
- Database schema does not change as part of JS modularization.

## Adding New Admin JS

- Do not put large inline JavaScript blocks in templates.
- Put new page scripts under `wecom_ability_service/static/admin_console/`.
- Use a page namespace such as `window.SomeWorkspace`.
- Prefer small files with clear responsibilities: `core`, `renderers`, `actions`, `boot`, and a small entrypoint.
- Load scripts from the template `scripts_extra` block in dependency order with `defer`.
- Do not use `import`, `export`, or `require` unless a separate PR introduces and documents frontend build tooling.
- Do not copy `requestJson`, `escapeHtml`, or `safeJsonParse`; reuse `AdminApi`.
- Keep page-specific action-token or tenant logic local to the page namespace.

## Current Guardrail Coverage

- Customer detail page script order and `CustomerProfile` modules.
- Customer Pulse Inbox script order and `CustomerPulseInbox` modules.
- Automation auto reply script order and `AutomationAutoReply` modules.
- Automation overview script order and `AutomationOverview` modules.
- Agent Config script order, no-large-inline-JS page contract, and `AutomationAgentConfig` agent, template, tag picker, channel/model, boot, and entrypoint modules.
- `AdminApi` shared-client contract.
- Base template order: `admin_api_client.js` before `admin_console.js`.
- No frontend build tooling in the repository root.

The executable audit is `scripts/audit_admin_static_js.py`. It is intentionally scoped to the protected Phase 3-8B pages and static JS files, including `automation_conversion_overview_workspace.html`, `automation_overview*.js`, `automation_conversion_agent_config_workspace.html`, and `automation_agent_config*.js`, not to every legacy admin template.

Agent Config is intentionally not in strict protected scope during Phase 8A. It remains a legacy inline-JS page until Phase 8B starts extracting `automation_conversion_agent_config_workspace.html`. Phase 8A adds `scripts/inventory_agent_config_workspace.py` and `docs/refactor/js_api_phase8_agent_config_inventory.md` so the large workspace can be split with a known DOM/API/test inventory before any behavior changes.

Phase 8B-1 starts partial Agent Config protection. The new `automation_agent_config*.js` files must pass namespace, no module-system, no duplicated helper, and action-token guardrails. The Agent Config template is checked for script order plus root/data/initial JSON markers, but it is not yet in the no-large-inline-JS strict list because template/profile-segment, tag picker, default channel, and model settings logic remain inline for later Phase 8B steps.

Phase 8B-2 extends partial Agent Config protection to `automation_agent_config_templates.js` and `automation_agent_config_tag_picker.js`. The Agent Config page still is not an entire no-inline-JS protected template because default channel / QR and model settings/test logic remain inline until Phase 8B-3.

Phase 8B-3 completes Agent Config modularization. `automation_agent_config_channel_model.js` is protected by the namespace, no module-system, no duplicated helper, and action-token checks. `automation_conversion_agent_config_workspace.html` is now part of the no-large-inline-JS protected template scope; only `application/json` initial data blocks and static script tags should remain.

For large legacy workspaces, do the inventory pass before extraction. When moving inline JavaScript into static files, migrate tests with the same pattern used after PR #121: HTML tests should assert root/data/script/initial JSON contracts, while button copy, `data-*` actions, placeholders, and modal copy that move into static JS should be asserted by reading the target static JS file.

## Next Steps

- Continue splitting automation conversion by small, bounded workspaces.
- Keep Vite or TypeScript proof-of-concept work in a separate PR from business migration work.
- If frontend build tooling is introduced later, update this guardrail document, the audit script, static tests, and deployment notes in the same PR.
