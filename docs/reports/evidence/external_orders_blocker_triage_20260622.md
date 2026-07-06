# External Orders Blocker Triage - 2026-06-22

Verdict: `BLOCKED_TRIAGE_COMPLETE`

This report classifies the two blockers found in
`docs/reports/evidence/external_orders_enablement_evidence_20260622.md`.
It is a readonly triage record. It does not repair production data, execute
internal event consumers, trigger external effects, modify deployment files,
change environment variables, run migrations, or enable any new external call.

## Scope

- Evidence packet: External Orders enablement evidence collected on 2026-06-22.
- Order evidence: internal order id `156`.
- Push Center projection: `external_effect_job:96`.
- External effect status: jobs `95` and `96` succeeded; attempts `96` and `97`
  succeeded with recorded HTTP 200 responses.
- Internal event: redacted `payment.succeeded` event `iev_***dff3`.
- Sensitive data policy: no token, `Authorization` header, raw
  `external_userid`, phone number, `unionid`/`openid`, full order number,
  customer secret, or payment credential is included.

## Triage Result

| Area | Classification | Blocking? | Evidence |
| --- | --- | --- | --- |
| Internal event consumers | `consumer_run_pending_due_to_config` | Yes | Six expected consumers are present but remain `pending` with `attempt_count=0` and no recorded error. |
| External effect / Push Center | `expected_not_applicable` | No | External effect jobs and attempts succeeded; Push Center shows `sent` and no retry is required. |
| Customer read model linkage | `linkage_missing` | Yes | Channel contact linkage exists, but `customer_list_index_next` has no linked customer row for this order. |

## Internal Event Consumer Pending Classification

The `payment.succeeded` internal event exists and is linked to order `156`, so
the blocker is not `missing_internal_event`.

Observed consumer runs:

| Consumer | Status | Attempt count | Error | Triage |
| --- | --- | --- | --- | --- |
| `order_projection_consumer` | `pending` | `0` | none | `consumer_run_pending_due_to_config` |
| `webhook_order_paid_consumer` | `pending` | `0` | none | `consumer_run_pending_due_to_config` |
| `automation_payment_consumer` | `pending` | `0` | none | `consumer_run_pending_due_to_config` |
| `customer_business_summary_consumer` | `pending` | `0` | none | `consumer_run_pending_due_to_config` |
| `dnd_policy_consumer` | `pending` | `0` | none | `consumer_run_pending_due_to_config` |
| `ai_assist_notify_consumer` | `pending` | `0` | none | `consumer_run_pending_due_to_config` |

Reasoning:

- Expected consumer run records exist, so this is not currently classified as
  `consumer_not_registered`.
- No consumer has a recorded failure, so this is not currently classified as
  `runtime_bug`.
- Every listed consumer is still pending with no attempt, so this remains a
  blocking status until the run scheduler/configuration is confirmed or the
  pending state is formally classified as non-applicable for this order flow.

Recommended next PR:

- `consumer pending classification/repair`
- Confirm whether these consumers are intentionally disabled for External Orders
  production evidence or whether a run-due/scheduler/consumer configuration
  repair is required.
- If they are intentionally not applicable, add an explicit evidence
  reclassification note before recollecting External Orders evidence.

## Customer Read Model Linkage Classification

The order has channel evidence, but the customer read model is not linked.

Observed linkage:

| Evidence | Status |
| --- | --- |
| External user id present on payment order | present, redacted |
| Channel contact linkage | present |
| Channel id evidence | present, redacted |
| `customer_list_index_next` linkage | missing |
| `customer_detail_snapshot_next` linkage | not confirmed |

Classification: `linkage_missing`

Reasoning:

- Because channel contact linkage exists, the order has enough channel evidence
  to expect a customer projection or an explicit explanation for why this order
  should not appear in the customer read model.
- The missing `customer_list_index_next` row blocks External Orders 90%+
  evidence because operators cannot prove the order is connected to the
  customer-facing read model.

Recommended next PR:

- `customer read-model linkage projection/backfill triage`
- Determine whether the missing customer read model row is an expected
  non-applicable case, a projection gap, or a data backfill requirement.
- Do not write production data until an approved backfill or runtime repair path
  exists.

## External Effect Linkage Classification

Classification: `expected_not_applicable` for blocker purposes.

The external effect and Push Center portions are not blocking this evidence
packet:

- `external_effect_job:96` is visible in Push Center.
- Effective status is `sent`.
- Push Center says no operator action is required for that job.
- Linked jobs `95` and `96` succeeded.
- Linked attempts `96` and `97` succeeded.
- Recorded attempts show HTTP 200 responses.

This triage did not execute any external call. It only classifies recorded
evidence from the previous readonly evidence packet.

## Diagnostic Script

This PR adds a readonly classifier:

```bash
.venv/bin/python scripts/diagnose_external_orders_blockers.py --help
```

The script can classify a redacted evidence JSON fixture, or, when executed in
an approved environment with `DATABASE_URL`, perform readonly `SELECT`
diagnostics inside a read-only transaction. It always reports:

- `real_external_call_executed=false`
- `production_write_executed=false`
- `deploy_or_env_modified=false`

## Conclusion

`External Orders` cannot be reclassified to `PASS_WITH_NOTES`,
`PASS_90_PLUS_CANDIDATE`, or `PASS_90_PLUS` yet.

Blocking classifications:

1. `consumer_run_pending_due_to_config`
2. `linkage_missing`

Recommended next PR:

```text
consumer pending classification/repair plus customer read-model linkage projection/backfill triage
```

After both blockers are resolved or explicitly accepted as non-blocking,
recollect External Orders evidence and re-run the Business Closure closeout
summary.

## Safety / Rollback

This is a report and readonly diagnostic PR. Rollback is reverting the PR. There
is no runtime rollback, data rollback, deploy rollback, env rollback, or
migration rollback.
