# JS/API Phase 3 Customer Profile Modules

## Current Goal

This phase keeps the customer detail page on the current no-build admin console stack.

- Do not introduce React, Vue, Vite, TypeScript, or a new frontend package.
- Do not change Flask API paths.
- Do not change authentication, RBAC, database schema, or route behavior.
- Split `customer_profile.js` into ordinary static JS files under `window.CustomerProfile`.
- Prepare for a later TypeScript or Vite migration without introducing those tools in this phase.

## File Responsibilities

- `customer_profile_core.js`: owns the page root lookup, shared AdminApi wrappers, Customer Pulse tenant and actor headers, `requestCustomerPulseJson`, shared state, common section state rendering, and initial-section scrolling.
- `customer_profile_sections.js`: owns live tags, questionnaire answers, chat messages, and the fetch-all-messages button.
- `customer_profile_pulse.js`: owns the Customer Pulse / AI next-step widget, evidence rendering, action preview, action execution, and feedback submission.
- `customer_profile_followup.js`: owns the followup orchestrator widget rendering and loading.
- `customer_profile_automation.js`: owns the automation conversion sidebar state, action buttons, cooldown rendering, and automation action calls.
- `customer_profile.js`: remains the lightweight `DOMContentLoaded` entrypoint that calls each module boot function.

## Unchanged Contracts

- Existing `data-*` attributes in `customer_detail.html` remain unchanged.
- API URLs still come from the same `root.dataset.*` values rendered by Jinja.
- `admin_action_token` behavior is unchanged.
- Customer Pulse tenant and actor headers are still page-specific and injected through `requestCustomerPulseJson`.
- Jinja remains the customer detail page shell.
- `AdminApi` remains the shared request, parse, escape, and permission-error layer.

## Next Steps

- Apply the same no-build module split to Customer Pulse Inbox after this customer detail split is stable.
- Consider Vite or TypeScript only after plain module-by-file boundaries have stayed covered by static contracts.
- Keep automation conversion page migration separate; do not combine it with customer detail or Customer Pulse Inbox work.
