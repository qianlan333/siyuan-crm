# Push Center Reconciliation Acceptance

Date: 2026-06-22

## Summary

This acceptance note defines the first 90%+ Push Center / Group Ops closure
slice after P0 closeout. It adds a read-only reconciliation payload for a Push
Center job so operators can understand source, effective status, linked records,
retryability, and next action without querying the database.

This PR does not enable real external calls, does not modify
deploy/systemd/nginx/env, and does not change worker/runtime execution.

## Read-Only API

`GET /api/admin/push-center/jobs/{job_id}/reconciliation`

The endpoint returns:

- `projection_id` and `display_id`
- `effective_status` and label
- `business_explanation`
- `retryable`
- `operator_action_required`
- `next_action_label`
- `last_error`
- `business_context`
- `linked_record_counts`
- redacted evidence summaries for:
  - `external_effect_jobs`
  - `external_effect_attempts`
  - `broadcast_jobs`
  - `outbound_tasks`

The payload uses the existing Push Center projection. It does not read raw
secrets or full payload bodies, and it sets `real_external_call_executed=false`.

## Acceptance Coverage

| Scenario | Expected business interpretation |
| --- | --- |
| `sent` | Main delivery completed; no operator action required. |
| `sent_with_shadow_warning` | Main delivery completed; shadow/observation failed and must not be counted as business failure. |
| `shadow_failed_not_business_failed` | Shadow failed and no primary send record was found; operator should confirm the primary send path. |
| `failed` with retryable external job | Operator can retry through the existing Push Center retry command. |
| `failed` without retryable job | Operator action is required; manual handling is safer than blind retry. |
| `pending` / `running` | Wait for scheduler, approval, or worker completion. |

## Operator Checklist

For a suspicious Push Center task, the operator should:

1. Open the job detail or call the reconciliation endpoint.
2. Check `effective_status` before checking raw provider status.
3. Read `business_explanation`.
4. Confirm linked record counts:
   - external effect job exists for external side effects.
   - attempt exists only after worker execution.
   - broadcast job/outbound task exists for main send queue paths.
5. Follow `next_action_label`:
   - `无需操作`
   - `等待调度`
   - `等待执行完成`
   - `重试`
   - `人工处理`
   - `检查影子链路`
   - `确认主发送记录`

## Non-Goals

- No UI redesign.
- No real group send or real WeCom/Payment/OAuth external call.
- No change to retry/cancel command semantics.
- No production migration or deploy/systemd/nginx/env change.
- No claim that gray-send production acceptance has completed.

## Rollback

The change is a read-only API and documentation slice. Rollback by reverting the
PR. Runtime worker rollback is not required.

## Next Action

Add Group Ops gray-send acceptance with default dry-run behavior and explicit
approved receiver gates before any real send evidence is recorded.
