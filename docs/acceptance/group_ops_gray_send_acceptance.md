# Group Ops Gray Send Acceptance

Date: 2026-06-22

## Goal

Validate the Group Ops send loop at 90%+ trial-operation readiness without
defaulting to real outbound sends. The acceptance path starts with a dry-run
diagnostic and only permits operator-owned gray execution after explicit receiver
and environment approval.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario group_ops_gray_send
```

The script must report:

- `dry_run=true`
- `real_external_call_executed=false`
- `production_write_executed=false`
- required approval env names, redacted when configured
- Push Center reconciliation route coverage

An operator may request readiness for gray execution with `--execute`, but the
script still performs no external call. It only returns
`operator_execute_allowed=true` when:

- `AICRM_GROUP_OPS_GRAY_SEND_APPROVED` is configured.
- `AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST` is configured.
- `--receiver-token` is supplied and redacted in output.

Optional identifiers can be attached for the operator evidence record:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario group_ops_gray_send \
  --execute \
  --receiver-token '<redacted-approved-test-receiver>' \
  --plan-id '<plan id>' \
  --event-id '<event id>' \
  --effect-job-id '<external_effect_job id>' \
  --attempt-id '<external_effect_attempt id>' \
  --push-center-job-id '<push center job id>'
```

The output includes an `operator_evidence` skeleton with `plan_id`,
`effect_job_id`, `attempt_id`, `push_center_job_id`, `push_center_status`,
`retryable`, `operator_action_required`, `business_explanation`, and
`next_action_label`. Missing identifiers must be reported as `not_provided`;
the diagnostic must not fabricate success evidence.

## Acceptance Cases

- Positive dry-run: plan, webhook route, external effect job, worker, attempt,
  and Push Center reconciliation are all named before any real receiver action.
- Blocked readiness: missing approval, missing receiver allowlist, missing
  receiver token, or receiver not in allowlist blocks operator execution
  readiness with an explicit blocking reason.
- Retry/compensation: failed jobs must be inspected through
  `/api/admin/push-center/jobs/{job_id}/reconciliation` before retry.
- Reconciliation:
  - `succeeded` / `sent`: no operator action required.
  - `failed_retryable`: retryable and operator action required.
  - `dead_lettered` or terminal failure: manual handling required.
  - `sent_with_shadow_warning`: shadow failure must not be counted as business
    failure if the main broadcast job succeeded.

## Evidence Template

Use `docs/reports/group_ops_gray_send_evidence_template.md` for PR or operator
evidence. Until an approved gray run attaches real reconciliation output, mark
the evidence status as `READINESS_ONLY`; do not claim 90%+ real gray completion.

## Non-Goals

- No real WeCom send by default.
- No production deploy/systemd/nginx/env modification.
- No receiver identifier committed to git.
- No raw external_userid, receiver_token, token, or secret committed to git.
- No UI redesign.

## Next Action

After this dry-run acceptance is merged, run an approved gray-send PR with a
separate operator-owned evidence record.
