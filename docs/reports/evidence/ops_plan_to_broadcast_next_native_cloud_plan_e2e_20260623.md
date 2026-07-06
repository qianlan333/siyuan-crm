# Ops Plan -> Broadcast Next-Native Cloud Plan E2E Evidence - 2026-06-23

Result: `EVIDENCE_COLLECTED`

This report records an operator-window E2E evidence collection for a
Next-native `cloud_plan` target after #1346 repaired
`broadcast_task_planner_consumer` and #1348 reclassified the prior historical
`legacy_campaign` target as non-applicable.

The evidence proves:

```text
cloud_plan approval
-> ops_plan.approved internal_event
-> broadcast_task_planner_consumer
-> broadcast_job
-> Push Center projection
```

The chain currently stops at `broadcast_job` / Push Center `pending`. No
downstream external-effect worker was executed in this PR, no `external_effect_job`
was created by this collection, and no real external call was triggered.

## Scope

| Field | Evidence |
| --- | --- |
| Environment | production |
| Review date | 2026-06-23 |
| Scenario | `ops_plan_to_broadcast` |
| Target plan id | `p0-1283-plan-20260615152503` |
| Target plan type | `cloud_plan` |
| Target source | Next-native `cloud_broadcast_plans` |
| Redacted internal event id | `iev_***96b3` |
| Consumer | `broadcast_task_planner_consumer` |
| Execution mode | single-consumer preview, then single-consumer execute |
| Broad run-due used | `false` |
| Batch consumer execution used | `false` |
| Route owner | `ai_crm_next` |

## Safety Attestation

| Field | Result |
| --- | --- |
| Legacy campaign target used | `false` |
| Legacy runtime restored | `false` |
| Route added or changed by this PR | `false` |
| Runtime code changed by this PR | `false` |
| Production deploy/systemd/nginx/env modified | `false` |
| Production migration executed | `false` |
| Broad run-due executed | `false` |
| Batch consumer execution used | `false` |
| Token / gate bypassed | `false` |
| Target consumer executed | `true`, only `broadcast_task_planner_consumer` |
| Other consumers executed | `false` |
| Broadcast job created | `true` |
| External effect job created | `false` |
| Real external call executed | `false` |
| Production write executed | `true`, limited to cloud-plan approval event, one consumer attempt, and one `broadcast_job` |
| Token or Authorization header committed | `false` |
| Raw target list or member/customer identifier committed | `false` |

## Next-Native Target Qualification

| Requirement | Evidence |
| --- | --- |
| Not a legacy event | `true` |
| Plan type | `cloud_plan` |
| Plan id present | `true` |
| Recipient projection present | `true`, count `1` |
| Message/send content projection present | `true`, count `1` |
| Approval route available | `POST /api/admin/cloud-orchestrator/plans/{plan_id}/approve` |
| Planner preview route available | `POST /api/admin/internal-events/{event_id}/consumers/broadcast_task_planner_consumer/run` |
| Raw target list output | `false` |
| Raw member/customer identifier output | `false` |
| Preview external call | `false` |

The target was selected because it was a Next-native `cloud_plan` with existing
recipient and message projections. Before approval, it had no
`ops_plan.approved` internal event; the operator approved the plan through the
existing admin action-token gate.

## Approval -> Internal Event Evidence

Plan approval was performed through the existing cloud plan approve route using
an admin action token generated in the production process. The token was not
printed, stored, or committed.

| Field | Evidence |
| --- | --- |
| Approval result | `ok=true` |
| Internal event status | `emitted` |
| Redacted internal event id | `iev_***96b3` |
| Consumer run count | `4` |
| Event type | `ops_plan.approved` |
| Event plan type | `cloud_plan` |
| Event source route | `/api/admin/cloud-orchestrator/plans/{plan_id}/approve` |
| Event target count | `1` |

The event payload summary recorded only operational metadata such as plan id,
plan type, stage, status, target count, and operator. No raw receiver list,
`external_userid`, mobile number, token, or secret is included in this report.

## Planner Preview Evidence

Preview request shape:

```text
POST /api/admin/internal-events/{event_id}/consumers/broadcast_task_planner_consumer/run
dry_run=true
force=true
```

Preview result:

| Field | Evidence |
| --- | --- |
| `ok` | `true` |
| `dry_run` | `true` |
| `force` | `true` |
| Consumer status before preview | `pending` |
| Attempt count before preview | `0` |
| Event plan type | `cloud_plan` |
| Real external call executed | `false` |

The preview confirmed that the selected event was not
`legacy_event_non_applicable`, not missing recipient projections, and not
missing message projections. Preview did not create a job or call any external
system.

## Planner Execution Evidence

Execution request shape:

```text
POST /api/admin/internal-events/{event_id}/consumers/broadcast_task_planner_consumer/run
dry_run=false
force=false
```

Execution result:

| Field | Before | After |
| --- | --- | --- |
| Consumer status | `pending` | `succeeded` |
| Attempt count | `0` | `1` |
| Attempt status | n/a | `succeeded` |
| Planner result | n/a | `planner_created_broadcast_job` |
| Duplicate handling | n/a | `created` |
| Broadcast job id | n/a | `3644` |
| Push Center job id | n/a | `broadcast_job:3644` |
| Downstream status | n/a | `broadcast_job_queued` |
| External effect job created | n/a | `false` |
| Real external call executed | n/a | `false` |

The planner consumer succeeded and created a Next-native `broadcast_job`
idempotency record. The idempotency key was present in production diagnostics
and is intentionally not repeated verbatim here.

## Broadcast Job Creation / Reuse Evidence

| Field | Evidence |
| --- | --- |
| Planner result | `planner_created_broadcast_job` |
| Duplicate handling | `created` |
| Broadcast job id | `3644` |
| Push Center job id | `broadcast_job:3644` |
| Downstream status | `broadcast_job_queued` |
| External effect job id | not found |

Read-only downstream diagnostics after execution:

| Linked record type | Count |
| --- | ---: |
| Broadcast jobs for the plan trace | `2` |
| External effect jobs for the plan trace | `0` |

One older recipient-level `broadcast_job` existed for the same plan trace before
this collection and was already `cancelled`. The newly created planner job is
`broadcast_job:3644`.

## Push Center / Downstream Evidence

Push Center reconciliation for `broadcast_job:3644` returned:

| Field | Evidence |
| --- | --- |
| Projection id | `broadcast_job:3644` |
| Effective status | `pending` |
| Effective status label | `待执行` |
| Business explanation | `任务已进入推送中心，等待调度器扫描、审批或前置条件满足。` |
| Retryable | `false` |
| Operator action required | `false` |
| Next action label | `等待调度` |
| Linked broadcast jobs | `1` |
| Linked external effect jobs | `0` |
| Linked external effect attempts | `0` |
| Linked outbound tasks | `0` |
| Reconciliation real external call executed | `false` |

This is a valid E2E evidence chain through Push Center visibility. It is not a
sent/delivered evidence chain. Downstream worker execution and any external
effect execution require a separate operator action and are intentionally not
performed by this PR.

## External Effect Safety

No external effect was triggered during this evidence collection:

- planner preview: `real_external_call_executed=false`
- planner execution: `real_external_call_executed=false`
- `external_effect_job_created=false`
- Push Center reconciliation: `real_external_call_executed=false`
- no downstream external-effect worker was run

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

The report records only plan id, redacted event id, counts, consumer name,
statuses, job id, Push Center projection id, and non-secret operational metadata.

## Result

Result: `EVIDENCE_COLLECTED`

Reasoning:

- The target is a Next-native `cloud_plan`, not `legacy_campaign`.
- The plan had recipient and message projections.
- Approval emitted `ops_plan.approved`.
- `broadcast_task_planner_consumer` preview was safe and did not call externally.
- Single-consumer execution succeeded.
- A new `broadcast_job` was created.
- Push Center shows the job as `pending` with a business explanation.
- No external effect job or external call was created in this PR.

This should not be promoted to global `PASS_90_PLUS`. It is a valid Ops Plan ->
Broadcast E2E evidence collection up to Push Center pending/downstream queued.

## Why Not Global PASS_90_PLUS Yet

Global `PASS_90_PLUS` is not allowed because:

1. this report covers only the Ops Plan -> Broadcast chain;
2. Push Center status is `pending`, not sent or completed;
3. no downstream worker/external-effect evidence was collected here;
4. Group Ops still lacks independent approval/allowlist/gray-window evidence;
5. global Business Closure requires all four core scenarios to be complete.

## Risk / Rollback

This PR is documentation-only. The production operator actions already performed
were:

1. approved one Next-native cloud plan through the existing admin action-token
   gate;
2. ran one dry-run preview for `broadcast_task_planner_consumer`;
3. executed only `broadcast_task_planner_consumer` once;
4. created one `broadcast_job`.

Rollback for this PR is to revert the evidence report. Runtime rollback is not
part of this PR. If the business wants to cancel the pending broadcast job, that
requires a separate approved operator action through the existing broadcast job
admin controls.

## Next Action

Decide whether to keep `broadcast_job:3644` pending as evidence only, cancel it
through an approved operator action, or run the downstream broadcast/external
effect worker in a separate explicitly approved window. Do not treat this report
as global `PASS_90_PLUS`.
