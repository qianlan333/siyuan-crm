# Ops Plan To Broadcast E2E Evidence Template

Status: `READINESS_ONLY` until an approved plan can be linked to internal event,
consumer, generated job, and Push Center evidence.

## Operator Context

- Evidence owner:
- Operator:
- Plan owner:
- Acceptance window:
- Approval record:
- Diagnostic command:

Do not commit secrets or raw identifiers:

- 不得提交 token、secret、cookie、Authorization header。
- 不得提交 raw external_userid。
- 不得提交 customer mobile、openid、unionid or other direct personal data.
- Use internal IDs or redacted references only.

## Required Evidence Fields

- `plan_id`
- `approval_event_id`
- `internal_event_id`
- `consumer_run_id`
- `broadcast_job_id` or `external_effect_job_id`
- `push_center_job_id`
- `derived_status`
- `pending_reason`
- `retryable`
- `operator_action_required`
- `business_explanation`
- `real_external_call_executed=false`

## Dry-Run Payload

Attach the output of:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario ops_plan_to_broadcast
```

Expected status without plan evidence:

- `status=missing_plan_id`
- `e2e_evidence.evidence_status=READINESS_ONLY`
- `real_external_call_executed=false`
- `production_write_executed=false`

## E2E Evidence Payload

Attach a redacted diagnostic command with collected identifiers:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario ops_plan_to_broadcast \
  --plan-id '<plan id>' \
  --approval-status approved \
  --approval-event-id '<approval event id>' \
  --internal-event-id '<internal event id>' \
  --consumer-run-id '<consumer run id>' \
  --consumer-status succeeded \
  --broadcast-job-id '<broadcast job id or not_provided>' \
  --effect-job-id '<external_effect_job id or not_provided>' \
  --push-center-job-id '<push center job id or not_provided>' \
  --duplicate-handling '<reused_idempotency_key or not_collected>'
```

The script does not approve plans, dispatch consumers, create jobs, query
production DB, or execute external calls. It only shapes the evidence record.

## Blocking Reason Matrix

| Derived status | Meaning | Required action |
| --- | --- | --- |
| `missing_plan_id` | No plan id was supplied. | Attach plan id. |
| `pending_approval` | Plan exists but approval evidence is absent or pending. | Approve plan or attach approval proof. |
| `missing_internal_event` | Approval evidence exists but no internal event is attached. | Attach internal event reconciliation. |
| `consumer_pending` | Internal event exists but consumer evidence is incomplete. | Collect consumer run/status. |
| `consumer_failed` | Consumer failed or is blocked. | Retry if retryable, otherwise investigate manually. |
| `missing_business_job` | Consumer succeeded but no broadcast/effect job is attached. | Attach generated job id. |
| `job_linked` | Consumer and job evidence are linked. | Collect Push Center reconciliation. |

## Push Center Reconciliation

When `push_center_job_id` exists, collect:

```text
/api/admin/push-center/jobs/{job_id}/reconciliation
```

Record:

- effective status
- retryable
- operator action required
- business explanation
- linked broadcast/external-effect evidence

## Decision

- `READINESS_ONLY`: not enough evidence for a 90%+ E2E claim.
- `E2E_EVIDENCE_ATTACHED`: plan, approval, event, consumer, job, and Push Center
  references are attached.
- `FAILED_NEEDS_FIX`: a blocking state requires code, config, or operator
  action before the business loop can be considered 90%+.
