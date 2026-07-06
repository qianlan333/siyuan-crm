# Batch 3 Customer Read Model Readonly Canary Runbook

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
4. Run Customer parity.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
5. Run Customer gray smoke in dual mode.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
6. Run full readonly dual-run with customer sample coverage.
   ```bash
   .venv/bin/python retired readonly HTTP dual-run helper; see docs/archive/experiments_ai_crm_next/retired_tools.md \
     --old-base-url http://127.0.0.1:5001 \
     --next-testclient \
     --scope customer,user_ops \
     --output-md /tmp/readonly_dual_run_batch_3_customer.md \
     --output-json /tmp/readonly_dual_run_batch_3_customer.json
   ```
7. Confirm screenshot baseline includes `/admin/customers`.
8. Confirm real PostgreSQL integration evidence exists in `docs/archive/experiments_ai_crm_next/docs/real_postgres_integration_run.md`.
9. Confirm route flags dry-run:
   - `AICRM_NEXT_ROUTE_CUSTOMER_READONLY=true`
   - `AICRM_NEXT_ROUTE_CUSTOMER_WRITES=false`
   - `AICRM_NEXT_EXTERNAL_WECOM_SYNC=false`
   - `AICRM_NEXT_EXTERNAL_ARCHIVE_SYNC=false`
   - `AICRM_NEXT_EXTERNAL_TAG_REFRESH=false`
   - `AICRM_NEXT_EXTERNAL_OPENCLAW=false`
10. Confirm customer sample exists and is masked, for example `external_user_masked_001`.

## Execute

1. Choose canary mode: `staging_simulated`, `staging_proxy`, `header_allowlist`, or `cookie_allowlist`.
2. Set dry-run or staging-only route flags.
3. Start old Flask staging if GET comparison is needed.
4. Start AI-CRM Next staging, or use TestClient for local simulated canary.
5. Optionally start staging proxy/router. Do not use production Nginx.
6. Run Customer readonly smoke through the canary target.
7. Run full readonly dual-run if old Flask is available.
8. Run screenshot route check.
9. Generate gray release report.
10. Generate readiness report.

## Monitor

- route status per included route
- 4xx / 5xx counts
- sample-dependent detail/timeline/recent-message route results
- side-effect safety flags
- WeCom sync flag
- archive sync flag
- tag refresh flag
- OpenClaw flag
- old write endpoint flag

## Rollback

1. Disable customer readonly route flag.
   ```bash
   # PSEUDO ONLY - staging example
   AICRM_NEXT_ROUTE_CUSTOMER_READONLY=false
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
- sample external_userid
- rollback owner
- Go/No-Go decision
- production approval status

## Forbidden Actions

- Do not modify production Nginx or deploy configuration.
- Do not enable customer write routes.
- Do not connect production PostgreSQL.
- Do not execute old Flask write endpoints.
- Do not trigger real WeCom contact sync.
- Do not trigger archive sync.
- Do not refresh real WeCom tags.
- Do not call OpenClaw webhook or push.
- Do not represent masked local sample evidence as production data validation.
