# JS/API Phase 5: Auto Reply Modules

## Current Goal

- Keep the admin UI framework-free: no React, Vue, Vite, TypeScript, or package.json.
- Keep Flask API paths, authentication, RBAC, and database behavior unchanged.
- Move the auto reply workspace inline JavaScript into ordinary static JS files.
- Continue the Phase 3 and Phase 4 `window` namespace pattern with `window.AutomationAutoReply`.

## File Responsibilities

- `automation_auto_reply_core.js`: root lookup, AdminApi helper wrapping, API URL parsing, shared state, DOM element lookup, output URL helpers, clipboard helpers.
- `automation_auto_reply_outputs.js`: recent reply output rendering, output loading, copy / webhook / WeCom send click behavior.
- `automation_auto_reply_modal.js`: rejected modal open and close behavior, modal feedback, rejected submit, manual clipboard fallback.
- `automation_auto_reply_actions.js`: monitor toggle, capture, run-due button handling, FormData payloads, reload behavior.
- `automation_auto_reply.js`: lightweight DOMContentLoaded entrypoint that calls `AutomationAutoReply.boot()`.

## Unchanged Contracts

- Existing `data-*` attributes remain the page contract.
- API URLs still come from `data-api-urls`.
- `admin_action_token` is now exposed on the root dataset for external JS, but the payload field name and semantics remain unchanged.
- Jinja remains the page shell, and `AdminApi` remains the shared request/helper layer.
- `automation_conversion.py` is not changed.

## Next Steps

- Extract another bounded automation conversion workspace in a separate PR.
- Prepare any Vite or TypeScript proof of concept separately from business migration work.
- Continue splitting the automation conversion area by small workspaces instead of moving the full page at once.
