# Ops Plan -> Broadcast E2E Evidence After Planner Repair - 2026-06-23

Verdict: `BLOCKED`

This report records a production operator-window recollection after #1346
repaired `broadcast_task_planner_consumer` for Next-native cloud plans.

The target `ops_plan.approved` event was previewed and then executed through the
single-consumer route only. The preview was executable and did not perform any
external call. The execution completed at the worker-control level, but the
planner result was `planner_skipped_non_applicable` because the production event
payload is still `plan_type=legacy_campaign`. No `broadcast_job`,
`external_effect_job`, or Push Center projection was created.

This report does not contain tokens, secrets, `Authorization` headers, raw
`external_userid`, phone numbers, raw target lists, raw member/customer
identifiers, or customer private request/response bodies.

## Scope

| Field | Evidence |
| --- | --- |
| Environment | production |
| Review date | 2026-06-23 |
| Scenario | `ops_plan_to_broadcast` |
| Plan id | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| Redacted internal event id | `iev_***fd6b` |
| Consumer | `broadcast_task_planner_consumer` |
| Execution mode | single-consumer preview, then force single-consumer execute |
| Runtime repair deployed | `true`, production checkout at #1346 merge commit |
| Broad run-due used | `false` |
| Batch consumer execution used | `false` |
| Route owner | `ai_crm_next` |

## Safety Attestation

| Field | Result |
| --- | --- |
| Route added or changed by this PR | `false` |
| Runtime code changed by this PR | `false` |
| Production deploy/systemd/nginx/env modified | `false` |
| Production migration executed | `false` |
| Broad run-due executed | `false` |
| Batch consumer execution used | `false` |
| Target consumer executed | `true` |
| Other consumers executed | `false` |
| Broadcast job created | `false` |
| External effect triggered | `false` |
| Real external call executed | `false` |
| Production write executed | `true`, limited to single consumer attempt/run state |
| Token or authorization header committed | `false` |
| Raw target list or customer/member identifier committed | `false` |

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
| `would_execute` | `true` |
| `real_external_call_executed` | `false` |
| `candidate_count` | `1` |
| `processed_count` | `0` |
| `skipped_count` | `0` |

The preview confirmed that the target consumer could be run in an operator
window. Preview did not create a job, write the business queue, or call any
external system.

## Planner Execution Evidence

Execution request shape:

```text
POST /api/admin/internal-events/{event_id}/consumers/broadcast_task_planner_consumer/run
dry_run=false
force=true
```

Execution result:

| Field | Before | After |
| --- | --- | --- |
| consumer status | `skipped` | `skipped` |
| attempt count | `1` | `2` |
| worker `ok` | n/a | `true` |
| attempt status | n/a | `skipped` |
| planner result | n/a | `planner_skipped_non_applicable` |
| skip reason | n/a | `consumer_non_applicable` |
| plan type | n/a | `legacy_campaign` |
| real external call executed | `false` | `false` |

The consumer execution did not fail technically. It completed with an explicit
non-applicable planner result for this target event.

## Broadcast Job Creation/Reuse Evidence

No `broadcast_job` was created or reused for the target approval chain.

| Field | Evidence |
| --- | --- |
| `planner_result` | `planner_skipped_non_applicable` |
| `duplicate_handling` | not available |
| `idempotency_key` | not available from planner result |
| `broadcast_job_id` | not found |
| `broadcast_job_count` for target plan/trace | `0` |
| `downstream_status` | not available |

Additional read-only production checks found that this target has no
Next-native `cloud_broadcast_plan_recipients` or
`cloud_broadcast_plan_recipient_messages` rows:

| Field | Evidence |
| --- | --- |
| event payload `plan_type` | `legacy_campaign` |
| event payload `source` | `legacy_campaign` |
| event payload `target_count` | `47` |
| cloud plan recipients | `0` |
| cloud plan recipients with external id | `0` |
| cloud plan recipient messages | `0` |

This explains why the #1346 Next-native planner repair did not create a
`broadcast_job` for this specific historical approval event.

## Push Center / Downstream Evidence

| Field | Evidence |
| --- | --- |
| `push_center_job_id` | not found |
| `push_center_status` | not available |
| `external_effect_job_id` | not found |
| `external_effect_job_count` for target plan/event | `0` |
| downstream worker completed | `false` |
| downstream pending | `false`; no downstream job exists yet |
| business explanation | The chain still stops at the planner consumer because this target event is a legacy-campaign approval without Next-native recipient/message projection rows. |

No Push Center projection can be formed until a `broadcast_job` or equivalent
Next-native business job exists.

## External Effect Safety

This recollection did not trigger real external effects:

- `real_external_call_executed=false` in preview.
- `real_external_call_executed=false` in execution.
- No `external_effect_job` was created for the target plan/event.
- No downstream worker or external-effect run-due was executed.

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

The report records only the plan id, redacted event id, consumer name, statuses,
counts, route names, and non-secret operational metadata.

## Result

Result: `BLOCKED`

Reasoning:

- The target single-consumer preview was valid.
- The target single-consumer execution was performed exactly for
  `broadcast_task_planner_consumer`.
- The repaired planner did not create a `broadcast_job` because the target event
  is `plan_type=legacy_campaign`.
- There are no Next-native cloud plan recipient/message rows for the target
  plan id.
- No `broadcast_job`, `external_effect_job`, or Push Center projection exists
  after recollection.

This cannot be promoted to `EVIDENCE_COLLECTED`,
`PASS_WITH_NOTES`, or `PASS_90_PLUS_CANDIDATE`.

## Why Not Global PASS_90_PLUS Yet

Global `PASS_90_PLUS` is not allowed because Ops Plan -> Broadcast E2E still
lacks generated business job and Push Center visibility evidence. This report
also shows that the remaining blocker is not run-due execution anymore; it is a
legacy-campaign source/projection gap for the target approval event.

## Risk / Rollback

This PR is a documentation-only evidence report. The production action already
performed was a single-consumer force execution that added one skipped attempt
for the target consumer and did not create downstream jobs.

Rollback for this PR is to revert this report. Runtime rollback is not part of
this PR.

## Next Action

Recommended next PR:

```text
Ops Plan -> Broadcast legacy campaign projection repair / reclassification
```

That PR should decide one of the following paths:

1. materialize legacy-campaign approval targets into Next-native cloud plan
   recipient/message projection rows before planner execution;
2. implement a safe, explicit legacy-campaign planning adapter inside the
   existing repository boundary; or
3. reclassify this historical legacy-campaign event as non-applicable and
   collect Ops Plan -> Broadcast E2E evidence from a current Next-native
   `cloud_plan` approval event.

After that repair or reclassification, recollect evidence again and only then
consider `EVIDENCE_COLLECTED` or `PASS_90_PLUS_CANDIDATE`.
