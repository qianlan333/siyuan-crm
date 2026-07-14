# Ops Plan Broadcast Consumer Blocker Triage - 2026-06-23

Verdict: `run_due_ready_for_operator_preview`

This report triages the blocker found in
`docs/reports/evidence/ops_plan_to_broadcast_e2e_evidence_20260623.md`.
It is read-only. It does not execute the consumer, create a broadcast job,
trigger an external effect, write production DB rows, run migrations, modify
deploy/systemd/nginx/env, add routes, or enter P1 frontend work.

The production evidence already proves that an `ops_plan.approved` internal
event exists and that the `broadcast_task_planner_consumer` run row exists.
The blocker is that the planner consumer is still `pending` with
`attempt_count=0`, no error, no generated `broadcast_job` or
`external_effect_job`, and no Push Center projection.

## Scope

| Field | Evidence |
| --- | --- |
| Environment | production evidence from #1343, plus local read-only code/diagnostic review |
| Scenario | `ops_plan_to_broadcast` |
| Plan id | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| Approval event type | `ops_plan.approved` |
| Redacted internal event id | `iev_***fd6b` |
| Planner consumer | `broadcast_task_planner_consumer` |
| Planner consumer run id | `263` |
| Planner status | `pending` |
| Planner attempt count | `0` |
| Planner last error | none |
| Downstream `broadcast_job` | not found |
| Downstream `external_effect_job` | not found |
| Push Center projection | not found |

## Safety Attestation

| Field | Result |
| --- | --- |
| Runtime code changed | `false` |
| Route added or changed | `false` |
| Consumer executed | `false` |
| Broadcast job created | `false` |
| External effect triggered | `false` |
| Production DB write executed by this PR | `false` |
| Production migration executed | `false` |
| Production deploy/systemd/nginx/env modified | `false` |
| Real external call executed by diagnostics | `false` |
| Token or authorization header committed | `false` |
| Raw target list or customer/member identifier committed | `false` |

## Planner Consumer Pending Classification

Classification: `run_due_ready_for_operator_preview`

Reasoning:

- The expected consumer row exists.
- The row is `pending`.
- `attempt_count=0` and there is no recorded error.
- The event type is `ops_plan.approved`, which is the expected event for this
  chain.
- This does not look like `consumer_non_applicable`.
- This does not look like a terminal or retryable failure, because no attempt
  exists yet.
- This does not look like handler registration failure, because the consumer
  run row exists.

The safe next step is an operator-controlled single-consumer preview. The
generic run-due execute path has stronger auto-execute and allowlist gates, so
the preferred path is not a broad run-due batch.

## Run-Due / Preview Availability

Existing internal-event routes provide the required controls:

| Capability | Route | Availability | Notes |
| --- | --- | --- | --- |
| run-due preview | `POST /api/admin/internal-events/run-due/preview` | available | Historical evidence used the retired shared Bearer; current calls require an `automation_worker` short-lived JWT. |
| generic run-due | `POST /api/admin/internal-events/run-due` | available | Non-dry-run requires internal events enabled, auto-execute gate, and allowlists. |
| single-consumer preview/run | `POST /api/admin/internal-events/{event_id}/consumers/{consumer_name}/run` | available | Requires internal token or admin action token; `dry_run=true` previews without write. |
| retry | `POST /api/admin/internal-events/{event_id}/consumers/{consumer_name}/retry` | available | Useful only after retryable failure. |
| skip | `POST /api/admin/internal-events/{event_id}/consumers/{consumer_name}/skip` | available | Requires approved reason; not the first recommendation for this planner row. |

Diagnostic fields for the target planner row:

| Field | Triage result |
| --- | --- |
| `expected_consumer_names` | `audit_projection_consumer`, `automation_schedule_refresh_consumer`, `broadcast_task_planner_consumer`, `ops_plan_ai_assist_notify_consumer` |
| `actual_consumer_run_records` | four rows found in #1343 evidence |
| `broadcast_task_planner_consumer status` | `pending` |
| `attempt_count` | `0` |
| `last_error` | none |
| `next_run_at` | none recorded |
| `run_due_eligible` | `true` for preview triage, subject to token/config gates |
| `preview_route_available` | `true` |
| `run_route_available` | `true` |
| `retry_route_available` | `false` until a retryable attempt exists |
| `skip_route_available` | `true`, but only with approved reason |
| `required_token_or_gate` | internal token for run-due preview/run; internal token or admin action token for single-consumer run/retry/skip |
| `auto_execute_enabled` | must be confirmed by operator before generic execute |
| `allowlist_required` | `true` for production execute |
| `operator_action_required` | `true` |
| `can_execute_in_operator_window` | `true`, after preview and approval |
| `recommended_execution_mode` | `operator_preview_first_then_single_consumer_execute_after_approval` |

## External Effect Risk Analysis

The internal-event worker itself reports
`real_external_call_executed=false`. The risk is downstream behavior after the
planner consumer runs:

- Preview: no production write and no external effect.
- Single-consumer execute: writes consumer attempt state and may create a
  `broadcast_job`.
- Later broadcast processing may create an `external_effect_job`.
- Push Center visibility is expected only after a downstream job/effect exists.

This PR does not authorize direct execution. It only identifies the next safe
operator step.

## Sensitive-Data Redaction Evidence

Confirmed not committed:

- token
- secret
- `Authorization` header
- raw `external_userid`
- phone number
- raw target list
- raw member identifier
- raw customer identifier
- customer private request/response body

The report records only internal ids, redacted event ids, consumer names,
statuses, counts, route names, and non-secret operational metadata.

## Recommended Operator Action

1. Use a single-consumer preview for:
   `ops_plan.approved` + `broadcast_task_planner_consumer`.
2. Confirm the preview returns `would_execute=true`,
   `real_external_call_executed=false`, and no sensitive data.
3. If approved, execute only the one target consumer in an operator window.
4. Re-run Ops Plan -> Broadcast E2E evidence after execution.
5. Only then judge whether a `broadcast_job` or `external_effect_job` exists and
   whether Push Center can explain the resulting status.

Do not claim Ops Plan -> Broadcast E2E 90%+ from this report alone.

## Result

Result: `EVIDENCE_COLLECTED_NOT_READY`

The blocker has been narrowed from generic `consumer_pending` to:

```text
broadcast_task_planner_consumer pending / attempt_count=0
-> run_due_ready_for_operator_preview
```

This remains blocking until operator preview/execution evidence proves the
planner consumer can generate a downstream job and Push Center projection.

## Risk / Rollback

This PR adds a read-only diagnostic and report. Rollback is to revert the PR.
There is no runtime rollback, deploy rollback, DB rollback, or migration
rollback.

## Next Action

Create the next operator evidence PR after approved preview/execution:

```text
Ops Plan -> Broadcast planner consumer run-due evidence
```

That PR should attach the single-consumer preview/execution result, downstream
job id, Push Center projection, idempotency proof, and redaction confirmation.
