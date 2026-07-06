# Ops Plan -> Broadcast E2E Evidence - 2026-06-23

Verdict: `EVIDENCE_COLLECTED_NOT_READY`

This report records read-only production evidence for the
`ops_plan.approved -> internal_event -> consumer_run -> broadcast/external
effect job -> Push Center` chain.

The evidence proves that an approved ops plan produced an `ops_plan.approved`
internal event and four consumer-run records. It does not prove the full E2E
broadcast loop, because the broadcast planner consumer is still pending with
`attempt_count=0`, no generated `broadcast_job` or `external_effect_job` was
found for the approval event, and no Push Center projection exists for that
approval chain.

This report does not contain tokens, secrets, `Authorization` headers, raw
`external_userid`, phone numbers, full order numbers, customer private
request/response bodies, or direct personal data.

## Scope

- Environment: production
- Review date: 2026-06-23
- Scenario: `ops_plan_to_broadcast`
- Plan id: `external_daily_lesson_20260617_1230_huangyoucan_v1_b11`
- Approval event type: `ops_plan.approved`
- Redacted internal event id: `iev_***fd6b`
- Aggregate type: `cloud_orchestrator_plan`
- Source module: `cloud_orchestrator.application`
- Source route: `/api/admin/cloud-orchestrator/plans/{plan_id}/approve`
- Approval actor: `admin_ui`
- Approval occurred_at: `2026-06-17T09:51:08+08:00`
- Internal event route owner from reconciliation: `ai_crm_next`

## Safety Attestation

| Field | Result |
| --- | --- |
| Runtime code changed | `false` |
| Route added or changed | `false` |
| Production deploy/systemd/nginx/env modified | `false` |
| Production migration executed | `false` |
| Production DB write executed by this report | `false` |
| Consumer executed by this report | `false` |
| External effect triggered by this report | `false` |
| Real external call executed by diagnostics/read path | `false` |
| Token or authorization header logged | `false` |
| Raw customer identifier committed | `false` |

## Operator Evidence Supplied

| Required field | Evidence |
| --- | --- |
| `plan_id` | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| `approval_event_id` | `iev_***fd6b` |
| `internal_event_id` | `iev_***fd6b` |
| `consumer_run_id` | planner consumer run `263`; see all consumer runs below |
| `consumer_status` | `pending` |
| `broadcast_job_id` | `not_provided` / not found |
| `external_effect_job_id` | `not_provided` / not found |
| `push_center_job_id` | `not_provided` / not found |
| `push_center_status` | `not_collected` |
| `derived_status` | `consumer_pending` |
| `pending_reason` | `broadcast_task_planner_consumer_pending_attempt_count_0` |
| `retryable` | `false` for this report; no consumer attempt exists to retry yet |
| `operator_action_required` | `true` |
| `business_explanation` | Approval event exists, but downstream consumers have not run, so no business job or Push Center status can be claimed. |
| `duplicate_approval_handling` | Approval idempotency key produced exactly one internal event. |
| `real_external_call_executed` | `false` |
| `production_write_executed` | `false` for this read-only evidence collection |
| `sensitive_data_redaction_confirmed` | `true` |

## Approval -> Internal Event Evidence

Approval internal event:

| Field | Evidence |
| --- | --- |
| event_type | `ops_plan.approved` |
| redacted event_id | `iev_***fd6b` |
| aggregate_type | `cloud_orchestrator_plan` |
| aggregate_id | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| subject_type | `ops_plan` |
| subject_id | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| idempotency_key | `ops_plan.approved:cloud_orchestrator_plan:external_daily_lesson_20260617_1230_huangyoucan_v1_b11:approved` |
| actor_id | `admin_ui` |
| actor_type | `admin` |
| source_command_id | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| trace_id | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| payload stage/status | `approved` / `approved` |
| payload target_count | `47` |

This satisfies the first half of the chain:

```text
ops_plan approval -> internal_event
```

## Consumer Run Evidence

The approval event created four consumer-run records. All remain pending with no
attempt and no error:

| Consumer | Run id | Status | Attempt count | Last error |
| --- | --- | --- | --- | --- |
| `audit_projection_consumer` | `262` | `pending` | `0` | none |
| `automation_schedule_refresh_consumer` | `260` | `pending` | `0` | none |
| `broadcast_task_planner_consumer` | `263` | `pending` | `0` | none |
| `ops_plan_ai_assist_notify_consumer` | `261` | `pending` | `0` | none |

Internal event reconciliation endpoint:

```text
GET /api/admin/internal-events/{event_id}/reconciliation
```

Read-only reconciliation summary:

| Field | Evidence |
| --- | --- |
| HTTP status | `200` |
| `ok` | `true` |
| `derived_status` | `noop` |
| consumer states | 4 pending |
| external_effects_count | `0` |
| route_owner | `ai_crm_next` |
| real_external_call_executed | `false` |

This does not satisfy the downstream E2E requirement, because
`broadcast_task_planner_consumer` has not produced a business job.

## Broadcast / External Effect Job Evidence

Read-only searches for the approved plan id, approval event id, trace id, and
idempotency key found:

| Artifact | Evidence |
| --- | --- |
| `broadcast_job_id` | none found |
| `external_effect_job_id` | none found |
| `external_effect_attempt` | none found |
| generated business job | not proven |

Therefore the chain currently stops here:

```text
ops_plan approval -> internal_event -> consumer_run pending
```

It has not reached:

```text
broadcast_job / external_effect_job -> Push Center reconciliation
```

## Push Center Visibility Evidence

No Push Center job id is available for this approval event.

| Field | Evidence |
| --- | --- |
| `push_center_job_id` | `not_provided` |
| `push_center_status` | `not_collected` |
| `retryable` | `false` |
| `operator_action_required` | `true` |
| `next_action_label` | run or triage `broadcast_task_planner_consumer` |

## Idempotency Evidence

The approval idempotency key produced exactly one internal event:

| Field | Evidence |
| --- | --- |
| idempotency key count | `1` |
| first created_at | `2026-06-17T09:51:08+08:00` |
| last created_at | `2026-06-17T09:51:08+08:00` |
| duplicate approval created duplicate event | `false` |

This proves duplicate approval handling at the internal-event boundary for this
approval key, but it does not prove duplicate-safe job creation because the
planner consumer has not run.

## Sensitive-Data Redaction Evidence

Confirmed not committed:

- token
- secret
- `Authorization` header
- raw `external_userid`
- phone number
- full order number
- customer private request/response body
- raw target list
- raw customer/member identifier

The report records only internal ids, redacted event ids, consumer names,
statuses, counts, route names, and non-secret business metadata.

## Result

Result: `EVIDENCE_COLLECTED_NOT_READY`

Reasoning:

- The plan approval event exists.
- The internal event exists and is idempotent.
- Consumer-run rows exist.
- The planner consumer is still `pending` with `attempt_count=0`.
- No generated `broadcast_job` or `external_effect_job` was found.
- No Push Center projection is available for this approval chain.

This is not `PASS_WITH_NOTES` or `PASS_90_PLUS_CANDIDATE`.

## Why Not Global PASS_90_PLUS Yet

Global `PASS_90_PLUS` still requires all core scenarios to have complete
evidence and no blocking reasons:

- Group Ops / Push Center
- Ops Plan -> Broadcast E2E
- External Orders
- WeCom Auth / Callback

This report shows the Ops Plan E2E chain is still blocked at consumer execution.
It cannot be counted as 90%+ until the planner consumer runs or is explicitly
reclassified as expected-not-applicable with an approved replacement path.

## Risk / Rollback

This is a documentation-only evidence report. Rollback is to revert this PR.
There is no runtime rollback, no deploy rollback, and no database rollback.

## Next Action

Run a dedicated, approved, single-event triage for
`broadcast_task_planner_consumer` on `ops_plan.approved` events:

1. Preview the target event and consumer without writes.
2. Confirm whether the consumer is disabled by config, scheduler-not-running, or
   pending because run-due has not executed.
3. If approved, execute one consumer in a controlled operator window.
4. Recollect evidence only after a `broadcast_job` or `external_effect_job` is
   generated and visible in Push Center.
