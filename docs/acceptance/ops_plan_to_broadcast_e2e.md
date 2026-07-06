# Ops Plan To Broadcast E2E Acceptance

Date: 2026-06-22

## Goal

Prove the event / approval / task loop can be explained from plan approval to
Push Center visibility. This document defines acceptance for
`ops_plan.approved` or equivalent approval events without changing runtime
worker behavior.

## Diagnostic

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario ops_plan_to_broadcast \
  --plan-id <plan_id> \
  --event-id <internal_event_id>
```

The diagnostic is dry-run by default and must not dispatch workers or external
effects. It checks readiness for:

- internal event creation/reuse
- consumer-run visibility
- generated broadcast/external-effect job correlation
- Push Center reconciliation

Attach collected identifiers through the same diagnostic when evidence exists:

```bash
.venv/bin/python scripts/diagnose_business_closure_acceptance.py \
  --scenario ops_plan_to_broadcast \
  --plan-id <plan_id> \
  --approval-status approved \
  --approval-event-id <approval_event_id> \
  --internal-event-id <internal_event_id> \
  --consumer-run-id <consumer_run_id> \
  --consumer-status succeeded \
  --broadcast-job-id <broadcast_job_id> \
  --effect-job-id <external_effect_job_id> \
  --push-center-job-id <push_center_job_id> \
  --duplicate-handling reused_idempotency_key
```

The diagnostic only shapes evidence. It must not approve a plan, dispatch a
consumer, create a job, read production DB directly, or execute any real
external call.

## Acceptance Cases

- Positive: one approval produces or reuses one internal event, one consumer run,
  and one expected business job/effect.
- Duplicate: repeated approval reuses the idempotency key and does not duplicate
  jobs.
- Failure: missing config, invalid target, downstream job create failure, and
  worker exception have distinct reasons.
- Retry: only the failed consumer/job is retried, with operator audit context.
- Blocking reasons:
  - missing plan id -> `missing_plan_id`
  - plan not approved -> `pending_approval`
  - approved plan without event evidence -> `missing_internal_event`
  - event without consumer run -> `consumer_pending`
  - failed consumer -> `consumer_failed`
  - succeeded consumer without job evidence -> `missing_business_job`
  - linked consumer/job evidence -> `job_linked`

## Operator Explanation Fields

The final E2E evidence should expose:

- `derived_status`
- `pending_reason`
- `effect_job_status`
- `retryable`
- `operator_action_required`
- `next_action_label`
- `linked_push_center_job`
- `business_explanation`
- `real_external_call_executed=false`

## Evidence Template

Use `docs/reports/ops_plan_to_broadcast_e2e_evidence_template.md` for PR or
operator evidence. Until plan, approval, internal event, consumer run,
broadcast/external-effect job, and Push Center references are attached, mark
the evidence as `READINESS_ONLY`; do not claim the loop has reached 90%+.

## Non-Goals

- No production migration.
- No direct DB inspection requirement for the operator.
- No real WeCom/Payment/OAuth external call.
- No token, secret, raw external_userid, or direct personal data committed to
  git.

## Next Action

Add an event business explanation payload if any of the fields above are missing
from the current admin/event details.
