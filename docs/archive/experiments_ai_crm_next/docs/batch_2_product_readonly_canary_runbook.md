# Batch 2 Product Management Readonly Canary Runbook

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
4. Run Commerce parity.
   ```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
5. Run Product gray smoke.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
6. Confirm screenshot baseline includes:
   - `/admin/wechat-pay/products`
   - `/p/course-masked-001`
7. Confirm route flags dry-run:
   - `AICRM_NEXT_ROUTE_PRODUCT_READONLY=true`
   - `AICRM_NEXT_ROUTE_PRODUCT_WRITES=false`
   - `AICRM_NEXT_ROUTE_CHECKOUT=false`
   - `AICRM_NEXT_EXTERNAL_WECHAT_PAY=false`
   - `AICRM_NEXT_EXTERNAL_ALIPAY=false`
8. Confirm checkout/payment disabled.

## Execute

1. Choose canary mode: `staging_simulated`, `staging_proxy`, `header_allowlist`, or `cookie_allowlist`.
2. Set dry-run or staging-only route flags.
3. Start old Flask staging if GET comparison is needed.
4. Start AI-CRM Next staging, or use TestClient for local simulated canary.
5. Optionally start staging proxy/router. Do not use production Nginx.
6. Run Product readonly smoke through the canary target.
7. Run screenshot route check.
8. Generate gray release report.
9. Generate readiness report.

## Monitor

- route status per included route
- 4xx / 5xx counts
- side-effect safety flags
- checkout flag
- payment provider flags
- old write endpoint flag
- payment notify and return route absence

## Rollback

1. Disable product readonly route flag.
   ```bash
   # PSEUDO ONLY - staging example
   AICRM_NEXT_ROUTE_PRODUCT_READONLY=false
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
- checkout/payment disabled status
- rollback owner
- Go/No-Go decision
- production approval status

## Forbidden Actions

- Do not modify production Nginx or deploy configuration.
- Do not enable product write routes.
- Do not execute checkout.
- Do not execute payment notify.
- Do not call real WeChat Pay.
- Do not call real Alipay.
- Do not execute old Flask write endpoints.
- Do not represent fake payment adapters as production validation.
