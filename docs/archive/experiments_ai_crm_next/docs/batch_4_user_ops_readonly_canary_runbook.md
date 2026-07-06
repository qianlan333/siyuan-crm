# Batch 4 User Ops Readonly Canary Runbook

This runbook is for staging or production-like canary preparation/execution. It is not a production cutover instruction.

## Pre-Check

1. Confirm worktree state.
   ```bash
   git status --short --untracked-files=all
   ```
2. Run ordinary pytest.
   ```bash
   .venv/bin/python -m pytest -q
   ```
3. Run six parity tools.
4. Run User Ops parity.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
5. Run User Ops readonly gray smoke.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
6. Run readonly dual-run if old Flask is available.
   ```bash
   .venv/bin/python retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
     --old-base-url http://127.0.0.1:5001 \
     --next-testclient \
     --scope customer,user_ops \
     --output-md /tmp/readonly_dual_run_batch_4_user_ops.md \
     --output-json /tmp/readonly_dual_run_batch_4_user_ops.json
   ```
7. Confirm screenshot baseline includes `/admin/user-ops/ui`.
8. Confirm real PostgreSQL integration evidence exists.
9. Confirm route flags dry-run:
   - `AICRM_NEXT_ROUTE_USER_OPS_READONLY=true`
   - `AICRM_NEXT_ROUTE_USER_OPS_WRITES=false`
   - `AICRM_NEXT_USER_OPS_DND=false`
   - `AICRM_NEXT_USER_OPS_BATCH_SEND=false`
   - `AICRM_NEXT_USER_OPS_DEFERRED_JOBS=false`
   - `AICRM_NEXT_EXTERNAL_WECOM_DISPATCH=false`
   - `AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false`
10. Confirm accepted legacy drift is documented: old overview may miss `激活待录入`; Next must include it.

## Execute

1. Choose canary mode: `staging_simulated`, `staging_proxy`, `header_allowlist`, or `cookie_allowlist`.
2. Set dry-run or staging-only route flags.
3. Start old Flask staging if GET comparison is needed.
4. Start AI-CRM Next staging, or use TestClient for local simulated canary.
5. Optionally start staging proxy/router. Do not use production Nginx.
6. Run User Ops readonly smoke through the canary target.
7. Run readonly dual-run if old Flask is available.
8. Run screenshot route check.
9. Generate gray release report.
10. Generate readiness report.

## Monitor

- route status per included route
- 4xx / 5xx counts
- overview 8-card integrity, especially `激活待录入`
- list filter responses
- send-records response
- side-effect safety flags
- DND flag
- batch-send flag
- deferred jobs flag
- WeCom dispatch flag
- WeCom media flag

## Rollback

1. Disable User Ops readonly route flag.
   ```bash
   # PSEUDO ONLY - staging example
   AICRM_NEXT_ROUTE_USER_OPS_READONLY=false
   ```
2. Route owner returns to old Flask.
3. Re-run old route smoke if old Flask is available.
4. Record rollback result and reason.
5. Preserve generated reports.

## Signoff

Record:

- operator
- evidence links
- canary mode
- database target
- external adapters mode
- smoke result
- parity result
- readonly dual-run result
- accepted legacy drift
- rollback owner
- Go/No-Go decision
- production approval status

## Forbidden Actions

- Do not modify production Nginx or deploy configuration.
- Do not enable User Ops write routes.
- Do not execute DND writes.
- Do not execute batch-send preview.
- Do not execute batch-send execute.
- Do not execute deferred jobs.
- Do not execute internal User Ops jobs.
- Do not call real WeCom dispatch.
- Do not upload real WeCom media.
- Do not execute old Flask write endpoints.
- Do not represent staging-simulated evidence as production approval.
