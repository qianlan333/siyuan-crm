# Batch 5 Questionnaire Readonly Canary Runbook

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
4. Run Questionnaire parity.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
5. Run Questionnaire readonly gray smoke.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
6. Confirm screenshot baseline includes:
   - `/admin/questionnaires`
   - `/admin/questionnaires/ui`
   - `/s/hxc-activation-v1`
7. Confirm real PostgreSQL integration evidence exists.
8. Confirm route flags dry-run:
   - `AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=true`
   - `AICRM_NEXT_ROUTE_QUESTIONNAIRE_WRITES=false`
   - `AICRM_NEXT_QUESTIONNAIRE_SUBMIT=false`
   - `AICRM_NEXT_QUESTIONNAIRE_OAUTH=false`
   - `AICRM_NEXT_EXTERNAL_WECOM_TAG=false`
   - `AICRM_NEXT_EXTERNAL_WEBHOOK=false`
9. Confirm accepted legacy drift is documented:
   - old non-WeChat public API may return `403 please_open_in_wechat`
   - old result page route differs from the Next JSON result API

## Execute

1. Choose canary mode: `staging_simulated`, `staging_proxy`, `header_allowlist`, or `cookie_allowlist`.
2. Set dry-run or staging-only route flags.
3. Start old Flask staging if GET comparison is needed.
4. Start AI-CRM Next staging, or use TestClient for local simulated canary.
5. Optionally start staging proxy/router. Do not use production Nginx.
6. Run Questionnaire readonly smoke through the canary target.
7. Run screenshot route check.
8. Generate gray release report.
9. Generate readiness report.

## Monitor

- route status per included route
- 4xx / 5xx counts
- admin list/detail/export/debug response shape
- public page/read/result response shape
- legacy WeChat gate drift
- legacy result route drift
- side-effect safety flags
- submit flag
- OAuth flag
- WeCom tag flag
- webhook flag

## Rollback

1. Disable Questionnaire readonly route flag.
   ```bash
   # PSEUDO ONLY - staging example
   AICRM_NEXT_ROUTE_QUESTIONNAIRE_READONLY=false
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
- accepted legacy drift
- rollback owner
- Go/No-Go decision
- production approval status

## Forbidden Actions

- Do not modify production Nginx or deploy configuration.
- Do not enable Questionnaire admin write routes.
- Do not execute H5 submit.
- Do not execute old Flask submit.
- Do not execute real OAuth start/callback.
- Do not mutate WeCom tags.
- Do not send external webhooks.
- Do not execute old Flask write endpoints.
- Do not represent staging-simulated evidence as production approval.
