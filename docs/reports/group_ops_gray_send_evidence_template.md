# Group Ops Gray Send Evidence Template

Status: `READINESS_ONLY` until an approved operator gray run supplies the
required job/effect/attempt evidence.

## Operator Window

- Evidence owner:
- Operator:
- Gray window:
- Approval record:
- Receiver allowlist proof:
- Diagnostic command:

Do not commit secrets or raw identifiers:

- 不得提交真实 receiver_token。
- 不得提交 raw external_userid。
- 不得提交 WeCom token、secret、cookie、Authorization header。
- Receiver allowlist values must be redacted or referenced by an approved
  operator-owned record outside git.

## Dry-Run Payload

Attach the output of:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario group_ops_gray_send
```

Required safety fields:

- `real_external_call_executed=false`
- `production_write_executed=false`
- `deploy_or_env_modified=false`
- `operator_evidence.evidence_status=READINESS_ONLY`

## Operator Readiness Payload

Attach the output of the readiness command after approval and receiver
allowlist are configured:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario group_ops_gray_send \
  --execute \
  --receiver-token '<redacted-approved-test-receiver>' \
  --plan-id '<plan id or not_provided>' \
  --effect-job-id '<external_effect_job id or not_provided>' \
  --attempt-id '<external_effect_attempt id or not_provided>' \
  --push-center-job-id '<push center job id or not_provided>'
```

The script still performs no real external call. It only confirms readiness and
prints a redacted evidence skeleton.

## Push Center Reconciliation

When a real approved gray run has produced a job, collect:

```text
/api/admin/push-center/jobs/{job_id}/reconciliation
```

Record only non-secret evidence:

- `plan_id`
- `effect_job_id`
- `attempt_id`
- `push_center_job_id`
- `push_center_status`
- `retryable`
- `operator_action_required`
- `business_explanation`
- `next_action_label`

## Failure / Retry / Compensation Evidence

- Blocked readiness reason:
- Provider/worker failure code:
- Retryable:
- Operator action required:
- Retry or cancel command used:
- Final reconciliation status:

## Decision

- `READINESS_ONLY`: readiness scaffolding exists, but no approved gray run has
  been completed.
- `GRAY_RUN_COLLECTED`: approved receiver gray run completed and reconciliation
  evidence is attached.
- `FAILED_NEEDS_FIX`: readiness or reconciliation found a blocking issue that
  must be fixed before counting the capability as 90%+.
