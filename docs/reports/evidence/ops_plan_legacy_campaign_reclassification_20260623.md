# Ops Plan Legacy Campaign Reclassification - 2026-06-23

Verdict: `legacy_event_non_applicable`

This report reclassifies the #1347 Ops Plan -> Broadcast evidence target. The
target approval event is a historical `legacy_campaign` event, while #1346
repaired the Next-native `cloud_plan` path for `broadcast_task_planner_consumer`.
These are different evidence scopes and must not be mixed when deciding whether
the Next-native Ops Plan -> Broadcast E2E chain can reach 90%+.

This report is documentation and readonly-diagnostic only. It does not execute a
consumer, create a `broadcast_job`, trigger an external effect, write production
data, run a migration, modify deploy/systemd/nginx/env, or claim `PASS_90_PLUS`.

## Reclassification

| Field | Evidence |
| --- | --- |
| Evidence source | #1347 after-planner-repair recollection |
| Target plan id | `external_daily_lesson_20260617_1230_huangyoucan_v1_b11` |
| Redacted internal event id | `iev_***fd6b` |
| Event type | `ops_plan.approved` |
| Event plan type | `legacy_campaign` |
| Event source | `legacy_campaign` |
| Planner consumer | `broadcast_task_planner_consumer` |
| Planner result | `planner_skipped_non_applicable` |
| Skip reason | `consumer_non_applicable` |
| Reclassification | `legacy_event_non_applicable` |

The #1347 target had no Next-native projection rows:

| Projection | Count |
| --- | ---: |
| `cloud_broadcast_plan_recipients` | `0` |
| recipients with external id | `0` |
| `cloud_broadcast_plan_recipient_messages` | `0` |

Because the event is a legacy campaign approval and lacks Next-native
recipient/message projections, the repaired planner correctly skipped it as
non-applicable. This is not evidence that the Next-native planner runtime failed.

## Scope Boundary

#1346 repaired the Next-native planner path:

```text
ops_plan.approved -> broadcast_task_planner_consumer -> cloud_plan repository -> broadcast_job
```

The #1347 target was instead:

```text
ops_plan.approved -> legacy_campaign event -> no Next-native recipients/messages
```

For 90%+ evidence, the next collection target must be a current Next-native
`cloud_plan` approval event, not this historical `legacy_campaign` event.

## Next-Native Target Selection Rules

A qualified Next-native evidence target must satisfy all of the following:

| Requirement | Required value |
| --- | --- |
| `plan_type` / source | `cloud_plan` or equivalent Next-native value |
| `plan_id` | present |
| approval event | `ops_plan.approved` exists or can be created by approved operator action |
| recipient projection | one or more `cloud_broadcast_plan_recipients` rows with non-rejected, non-cancelled recipients and redacted external id presence |
| message projection | one or more `cloud_broadcast_plan_recipient_messages` rows with non-cancelled send content |
| planner consumer | `broadcast_task_planner_consumer` can be previewed before execution |
| external effects | no real external effect is triggered during target selection |
| sensitive data | no raw target list, raw member/customer identifier, raw `external_userid`, phone, token, secret, or Authorization header |

The diagnostic output now separates:

- `legacy_event_non_applicable`
- `next_native_plan_ready_for_evidence`
- `next_native_plan_missing_recipients`
- `next_native_plan_missing_messages`
- `planner_created_broadcast_job`
- `planner_reused_broadcast_job`
- `planner_succeeded_downstream_pending`
- `BLOCKED_NEXT_NATIVE_TARGET_MISSING`

If no qualified Next-native target exists, the required operator action is:

```text
create_or_approve_next_native_test_plan
```

## Can Ops Plan E2E Be Recollected Now?

Not from the #1347 legacy target.

Ops Plan -> Broadcast E2E can be recollected only after a qualified Next-native
`cloud_plan` approval event is selected or created. Until then, the legacy target
must remain `legacy_event_non_applicable`, and the Ops Plan -> Broadcast chain
cannot be promoted to `PASS_90_PLUS_CANDIDATE`.

## Sensitive-Data Redaction

This report does not contain:

- token
- secret
- Authorization header
- raw `external_userid`
- phone number
- raw target list
- raw member identifier
- raw customer identifier
- customer private request/response body

Only plan id, redacted event id, event type, planner result, counts, and
non-secret operational metadata are recorded.

## Why Not PASS_90_PLUS

`PASS_90_PLUS` is not allowed because:

1. the #1347 event is historical `legacy_campaign`, not a Next-native
   `cloud_plan` target;
2. no Next-native recipient/message projection exists for that target;
3. no `broadcast_job`, `external_effect_job`, or Push Center projection exists;
4. a current Next-native evidence target has not yet been executed and collected.

## Risk / Rollback

This PR is documentation plus readonly diagnostic classification. Rollback is to
revert this report and the diagnostic/test changes. There is no runtime rollback.

## Next Action

Select or create a current Next-native `cloud_plan` approval event with
recipient and message projections, then run single-consumer preview for
`broadcast_task_planner_consumer`. Only after that target produces
`broadcast_job` and Push Center evidence should Ops Plan -> Broadcast E2E
evidence be recollected.
