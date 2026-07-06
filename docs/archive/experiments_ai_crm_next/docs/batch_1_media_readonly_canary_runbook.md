# Batch 1 Media Library Readonly Canary Runbook

This runbook is for staging or production-like canary preparation. It is not a production cutover instruction.

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
4. Run Media parity.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
5. Run Media gray smoke.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
6. Confirm screenshot baseline.
   - `docs/archive/experiments_ai_crm_next/docs/frontend_screenshot_baseline.md`
   - `historical removed reference (route_status.json)`
7. Confirm Batch 1 rehearsal report.
   - `/tmp/gray_rehearsal_batch_1_media_readonly_audit.json`
   - `docs/archive/experiments_ai_crm_next/docs/gray_rehearsal_batch_1_media_readonly.md`
8. Confirm dry-run route flags.
   - `AICRM_NEXT_ROUTE_MEDIA_READONLY=true`
   - `AICRM_NEXT_ROUTE_MEDIA_WRITES=false`
   - `AICRM_NEXT_EXTERNAL_CLOUD_STORAGE=false`
   - `AICRM_NEXT_EXTERNAL_WECOM_MEDIA=false`

## Execute

1. Choose canary mode: `dry_run`, `staging_shadow`, `header_allowlist`, or `cookie_allowlist`.
2. Set dry-run or staging-only route flags.
3. Start old Flask staging if GET comparison is needed.
4. Start AI-CRM Next staging, or use TestClient for local readiness.
5. Optionally start staging proxy/router. Do not use production Nginx.
6. Run Media smoke through the canary target.
7. Confirm screenshot baseline route status.
8. Generate readiness report.
   ```bash
   # Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
   ```
9. Generate gray release report if a selected smoke/parity pair needs aggregation.

## Monitor

- route status per included route
- 4xx / 5xx counts
- side-effect safety flags
- external adapter flags
- cloud upload flag
- WeCom media flag
- rollback owner and rollback instruction

## Rollback

1. Disable route flag.
   ```bash
   # PSEUDO ONLY - staging example
   AICRM_NEXT_ROUTE_MEDIA_READONLY=false
   ```
2. Route owner returns to old Flask.
3. Re-run old route smoke or staging proxy smoke.
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
- screenshot baseline reference
- rollback owner
- Go/No-Go decision

## Forbidden Actions

- Do not modify production Nginx or deploy configuration.
- Do not enable media write routes.
- Do not upload to real cloud storage.
- Do not upload media to real WeCom.
- Do not execute old Flask write endpoints.
- Do not represent fake adapters as production validation.
