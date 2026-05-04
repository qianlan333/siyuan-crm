# JS/API Phase 2 Customer Admin

## Current Goal

This phase keeps the admin console on the current no-build frontend stack.

- Do not introduce React, Vue, Vite, TypeScript, or a new frontend package.
- Do not change Flask API paths.
- Move customer admin JavaScript request, parse, escape, and permission-error handling onto `window.AdminApi`.
- Keep Jinja as the page shell while making a later module or component migration easier.

## Completed In This Phase

- `AdminApi.requestJson` now handles JSON objects, `FormData`, `URLSearchParams`, strings, empty responses, and normalized request errors.
- `customer_profile.js` uses `AdminApi` for JSON requests, JSON parsing, HTML escaping, and permission-error checks.
- `customer_pulse_inbox.js` uses `AdminApi` for the same shared helper layer.
- Static contract tests protect the base script loading order, the `AdminApi` surface, and the helper consolidation in customer admin scripts.

## Unchanged Boundaries

- Flask remains the owner of business APIs.
- Jinja remains the admin page shell.
- Enterprise WeCom SSO, CRM RBAC, and `admin_action_token` behavior stay unchanged.
- Tenant and actor headers stay page-specific through `customerPulseAccessHeaders(root)`.
- `automation_conversion.py` is outside this PR and should not be mixed with customer admin migration work.

## Next Steps

- Split customer detail page JavaScript into smaller plain JS modules after this shared client boundary is stable.
- Continue componentizing the Customer Pulse Inbox behavior without changing API paths.
- Consider Vite or TypeScript only after no-build module boundaries are clear and covered by tests.
- Migrate automation conversion in separate, smaller PRs; do not combine it with customer detail or Customer Pulse Inbox work.
