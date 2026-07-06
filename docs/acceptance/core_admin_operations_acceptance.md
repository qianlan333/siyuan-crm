# Core CRM Admin Operations Acceptance

Date: 2026-06-22

## Goal

Track the remaining core admin operation readiness needed before P1 frontend
foundation. This is not a UI rebuild; it is a trial-operation acceptance layer
for save/error/status clarity.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario core_admin_ops
```

## Acceptance Cases

- Channel save returns concrete FastAPI `detail` or business error.
- Static channel-admin JS cache behavior is handled before save-flow fixes ship.
- Runtime diagnosis explains config, provider, route owner, and blocked adapter
  state.
- Push Center and internal event status language can be understood without DB
  inspection.
- Old draft PR `#974` is closed or rebuilt from current `main`; do not merge the
  stale branch.

## Non-Goals

- No P1 TypeScript frontend foundation in this acceptance PR.
- No broad UI redesign.
- No production deploy/systemd/nginx/env change.
- No legacy compatibility shim.

## Next Action

Open a fresh current-main PR for the channel auto-accept save/error refresh, or
close old draft `#974` if the fix is no longer relevant.
