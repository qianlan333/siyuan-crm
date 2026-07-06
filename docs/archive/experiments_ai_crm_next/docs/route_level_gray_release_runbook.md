# Route-Level Gray Release Runbook

This runbook is for controlled route-level gray execution planning. It is not a production traffic switch by itself. Do not apply proxy or route changes until the release owner approves a specific batch signoff.

## Preflight

1. Confirm scope.
   - Select exactly one batch from `docs/archive/experiments_ai_crm_next/docs/route_level_gray_release_batches.md`.
   - Confirm included and excluded routes.
   - Confirm the current old route owner and Next route owner from the relevant route cutover manifest.
2. Check the worktree.
   ```bash
   git status --short --untracked-files=all
   ```
   Old production entrypoints must be reviewed and unrelated dirty files isolated before any real cutover.
3. Run global validation.
   ```bash
   .venv/bin/python -m pytest -q
   ```
4. Run six parity commands.
   - User Ops
   - Customer Read Model
   - Questionnaire
   - Automation Conversion
   - Commerce
   - Media Library
5. Confirm evidence availability.
   - real local PostgreSQL integration evidence
   - frontend screenshot baseline
   - selected batch gray smoke report
   - readonly dual-run report where applicable
6. Confirm external adapter mode.
   - WeCom disabled/fake unless separately approved.
   - OAuth disabled/fake unless separately approved.
   - payment providers disabled/fake unless separately approved.
   - OpenClaw disabled/fake unless separately approved.
   - cloud storage disabled/fake unless separately approved.

## Execution Steps

1. Choose one batch only.
2. Open the selected module route cutover manifest.
3. Confirm no excluded routes are enabled.
4. Prepare route flag or proxy rule from `docs/archive/experiments_ai_crm_next/docs/route_level_proxy_template.md`.
5. Record operator, timestamp, git commit, old service version, Next service version, database target, and external adapter mode in `docs/archive/experiments_ai_crm_next/docs/gray_release_signoff_template.md`.
6. Apply the approved route flag or proxy rule in the approved environment only.
7. Run the selected batch smoke command immediately.
8. Observe logs and route status.
9. Generate a gray release report with `retired gray-release report helper; see docs/archive/experiments_ai_crm_next/retired_tools.md`.
10. Record human signoff and Go/No-Go decision.

## Smoke After Route Change

Run the selected batch smoke command from `docs/archive/experiments_ai_crm_next/docs/route_level_gray_release_batches.md`. Then run:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

The report must show:

- no blockers
- no old write endpoint
- no real external call unless that adapter has separate production approval
- rollback owner recorded

For a local rehearsal before any route change, use:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

This command does not modify proxy configuration and does not switch traffic.

For Batch 1 staging canary readiness, use existing Media smoke, Media parity, and Batch 1 rehearsal JSON:

```bash
# Historical command retired; see docs/archive/experiments_ai_crm_next/retired_tools.md
```

This checker only reads existing reports and the screenshot route status. It does not modify proxy configuration, switch traffic, or call external providers.

## Rollback Steps

1. Disable the selected route flag.
2. Restore route owner to old Flask.
3. Verify the old route returns `200` or the documented expected redirect.
4. Re-run the selected smoke in old-route mode if available.
5. Record rollback reason and operator.
6. Preserve Next logs and generated reports for diagnosis.
7. Do not retry until the module owner writes a fix or accepted-risk note.

Rollback command placeholder:

```bash
# PSEUDO ONLY
export AICRM_NEXT_ROUTE_<MODULE>_READONLY=false
# Restore the approved proxy/app route mapping to old Flask.
# Validate with the selected batch smoke command.
```

## Forbidden Actions

- Do not gray multiple batches at once.
- Do not skip smoke.
- Do not enable write routes in a readonly batch.
- Do not let fake adapters stand in for real provider validation.
- Do not enable unapproved real WeCom, OAuth, payment, OpenClaw, webhook, or cloud adapters.
- Do not modify production Nginx from this repository task.
- Do not delete old Flask routes during gray release.
- Do not change old production service logic to make a gray report pass.
