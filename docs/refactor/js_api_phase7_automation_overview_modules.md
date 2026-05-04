# JS/API Phase 7: Automation Overview Modules

## Current Goal

- Keep the admin UI framework-free: no React, Vue, Vite, TypeScript, or package.json.
- Keep Flask API paths, authentication, RBAC, and database behavior unchanged.
- Move the automation conversion overview workspace inline JavaScript into ordinary static JS files.
- Continue the Phase 3, Phase 4, and Phase 5 `window` namespace pattern with `window.AutomationOverview`.

## File Responsibilities

- `automation_overview_core.js`: root lookup, AdminApi helper wrapping, API URL parsing, action token lookup, DOM element lookup, feedback helpers, and shared state.
- `automation_overview_renderers.js`: member group rendering, additional stats computation, dashboard rendering, segmentation stats, and execution summary output.
- `automation_overview_actions.js`: dashboard loading, admin FormData action posting, accepted status handling, and refresh button orchestration.
- `automation_overview.js`: lightweight DOMContentLoaded entrypoint that calls `AutomationOverview.boot()`.

## Unchanged Contracts

- Existing `data-*` attributes remain the page contract, except the root now also exposes `data-admin-action-token`.
- API URLs still come from `data-api-urls`.
- `admin_action_token` is now read from the root dataset, but the payload field name and semantics remain unchanged.
- Jinja remains the page shell, and `AdminApi` remains the shared request/helper layer.
- Refresh order stays message activity sync, reply monitor capture, reply monitor run due, then dashboard reload.
- `automation_conversion.py` is not changed.

## Next Steps

- Extract the next bounded automation conversion workspace in a separate PR.
- Prepare any Vite or TypeScript proof of concept separately from business migration work.
- Continue splitting the automation conversion area by small workspaces instead of moving the full page at once.
