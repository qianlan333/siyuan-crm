# JS/API Phase 4: Customer Pulse Inbox Modules

## Current Goal

- Keep the admin UI framework-free: no React, Vue, Vite, TypeScript, or package.json.
- Keep Flask API paths, authentication, RBAC, and database behavior unchanged.
- Split `customer_pulse_inbox.js` into ordinary static JS files that share a single `window.CustomerPulseInbox` namespace.
- Continue the Phase 3 modules-by-file pattern so later build-tool or TypeScript work can start from clearer file boundaries.

## File Responsibilities

- `customer_pulse_inbox_core.js`: root lookup, AdminApi helper wrapping, tenant and actor headers, card API URL construction, shared store, detail state helpers, inline state HTML.
- `customer_pulse_inbox_renderers.js`: evidence HTML, action forms, selected-card rendering, card lookup, selected-card highlighting, stored-card updates.
- `customer_pulse_inbox_actions.js`: card detail loading, preview loading, evidence loading, action execution, feedback submission, form payload collection.
- `customer_pulse_inbox_boot.js`: event binding, initial JSON payload read, empty state handling, first-card load.
- `customer_pulse_inbox.js`: lightweight DOMContentLoaded entrypoint that calls `CustomerPulseInbox.boot()`.

## Unchanged Contracts

- `data-*` attributes in `customer_pulse_inbox.html` remain the page contract.
- API URLs still come from the existing template dataset values.
- `admin_action_token` stays in execute and feedback payloads.
- Tenant and actor headers stay page-specific and are injected by the inbox request wrapper.
- Jinja remains the page shell, and `AdminApi` remains the shared request/helper layer.

## Next Steps

- Apply the same small-file approach only to a bounded automation conversion work area.
- Prepare any Vite or TypeScript proof of concept separately from business migration work.
- Keep automation conversion page migration in its own PR, not mixed with Customer Pulse Inbox changes.
