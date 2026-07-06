# P0-2 Legacy 7-Day Observation Window

Observation start: 2026-06-16T09:55:43+0800
Observation end: 2026-06-23T09:55:43+0800

This document starts the P0-2 legacy-path observation window after the P0-2
Final Gate PASS and the #1294 authenticated External Effects run-due redaction
verification PASS. It does not authorize legacy deletion, External Effects real
execution, non-payment worker auto-execute, webhook delivery, WeCom, Feishu,
broadcast send, payment query, or refund.

## Baseline Version

- Baseline commit: `b8248a8b Redact external effect run due admin responses (#1294)`
- #1294 merge commit: `b8248a8bd6ec3bf81faa811db1864f1d4676ed16`
- Health: HTTP 200
- Route owner: `ai_crm_next`
- Runtime owner: `ai_crm_next`
- Production data ready: `true`
- Legacy runtime enabled: `false`
- Health release header note: `x-aicrm-release-sha` still reports
  `d996e6cd4eb08744d0a2568056ab9261f4bab394-hxc-backend-refresh-hotfix`;
  production `git-status` is the baseline source of truth for this window.

## Baseline Internal Events

- `internal_events_enabled=true`
- `pair_allowlist_enabled=true`
- `config_warnings=[]`
- `failed_terminal_count=0`
- SQL stale lock count: `0`
- `blocked_by_pair_allowlist_count=93`
- `real_external_call_executed=false`
- `legacy_path_markers_enabled=true`
- `legacy_path_retire_after_days=7`
- `legacy_path_invocation_count=0`
- `legacy_path_last_seen=""`
- `legacy_path_retire_candidate=false`

P0-2 feature flags:

- `payment_internal_events_enabled=true`
- `questionnaire_internal_events_enabled=true`
- `customer_tags_internal_events_enabled=true`
- `customer_identity_internal_events_enabled=true`
- `ai_campaign_internal_events_enabled=true`
- `ops_plan_internal_events_enabled=true`
- `broadcast_task_internal_events_enabled=true`
- `owner_migration_internal_events_enabled=true`

Allowed event types:

- `payment.succeeded`
- `questionnaire.submitted`
- `customer.tagged`
- `customer.untagged`
- `customer.phone_bound`
- `ai_campaign.created`
- `ai_campaign.approved`
- `ai_campaign.started`
- `ops_plan.approved`
- `broadcast_task.created`
- `owner_migration.executed`

Allowed event consumers remain payment-only:

- `payment.succeeded:order_projection_consumer`
- `payment.succeeded:customer_business_summary_consumer`
- `payment.succeeded:dnd_policy_consumer`
- `payment.succeeded:ai_assist_notify_consumer`
- `payment.succeeded:automation_payment_consumer`

Effective worker queue:

- `effective_queue_metrics.due_count=15`
- `effective_queue_metrics.due_count_by_event_type={"payment.succeeded": 15}`
- no non-payment event family is worker-auto-executable

## Baseline Event And Run Counts

| event_type | event_count | latest_event_id | expected_runs | latest_run_count | latest_run_count_by_status |
|---|---:|---|---:|---:|---|
| `payment.succeeded` | 5 | `iev_7758d4630a734d37ba930319b53c90ce` | 6 | 6 | `{"pending": 6}` |
| `questionnaire.submitted` | 3 | `iev_1c52a2452fbd424582f9b32ff0846503` | 5 | 5 | `{"pending": 5}` |
| `customer.tagged` | 3 | `iev_c8508601f2a546fc8593255029f2e509` | 3 | 3 | `{"pending": 1, "skipped": 1, "succeeded": 1}` |
| `customer.untagged` | 3 | `iev_f5910f11e59a4430ab0cfe48fccf729b` | 3 | 3 | `{"pending": 3}` |
| `customer.phone_bound` | 3 | `iev_e67d3a0af09f41cfb97e1f4b67b4c25c` | 4 | 4 | `{"pending": 4}` |
| `ai_campaign.created` | 1 | `iev_ddd54cd1ff1d460195ef1a158ed38693` | 4 | 4 | `{"pending": 3, "skipped": 1}` |
| `ai_campaign.approved` | 1 | `iev_caecec84c08d4b12b6aca4fec2792254` | 4 | 4 | `{"pending": 4}` |
| `ai_campaign.started` | 1 | `iev_d23df01af6da4a928a5b1b4366839818` | 4 | 4 | `{"pending": 4}` |
| `ops_plan.approved` | 2 | `iev_974c65ba814f4b218042fe402fb07d2e` | 4 | 4 | `{"pending": 3, "succeeded": 1}` |
| `broadcast_task.created` | 8 | `iev_3b85797b3f7641ed8da9b66e4d013da0` | 4 | 4 | `{"pending": 4}` |
| `owner_migration.executed` | 2 | `iev_594c41a15eab4d619b8dc7d82584c075` | 4 | 4 | `{"pending": 4}` |

Global SQL counters:

- `internal_event_consumer_run.failed_terminal=0`
- `internal_event_consumer_run.stale_lock=0`
- `internal_event_consumer_run.total=135`
- `internal_event_consumer_attempt.total=28`

## Baseline External Effects

- `real_execution_enabled=false`
- `execution_mode=disabled`
- `allowed_effect_types=[]`
- `real_external_call_executed=false`
- `failed_terminal_count=0`
- `dispatching_count=0`
- `eligible_due_count=2`

External Effects count baseline:

- `total=41`
- `queued=2`
- `blocked=1`
- `failed=0`
- `succeeded=31`
- `cancelled=7`

## Baseline Legacy Marker Status

Internal Events marker diagnostics:

- `legacy_path_markers_enabled=true`
- `legacy_path_retire_after_days=7`
- `legacy_path_invocation_count=0`
- `legacy_path_last_seen=""`
- `legacy_path_retire_candidate=false`
- `legacy_paths=[]`

Legacy cleanup status:

- `total=10`
- `deprecated=10`
- `scheduled=10`
- `deleted=0`
- `failed=0`
- `runtime_observation.window_days=7`
- `runtime_observation.legacy_path_invoked_count=2`
- `runtime_observation.legacy_real_execution_count=0`
- `runtime_observation.no_recent_real_execution=true`
- `next_delete_scheduled_at=2026-06-21T09:42:59.462982Z`

Operational note: marker diagnostics counters are in-process and can reset on
app restart. Structured application logs are the durable source when reviewing
legacy marker hits over the 7-day window.

## Daily Check Template

Run the check once per calendar day during the observation window and record the
result in the control issue or operations log.

| Item | Expected result | Actual | Notes |
|---|---|---|---|
| Health | HTTP 200, route owner `ai_crm_next` |  |  |
| External Effects | `real_execution_enabled=false`, `execution_mode=disabled`, `allowed_effect_types=[]` |  |  |
| Worker allowlist | `allowed_event_consumers` payment-only |  |  |
| Internal Event failures | `failed_terminal_count=0` |  |  |
| SQL stale locks | stale lock count `0` |  |  |
| External attempts | no unexpected `external_effect_attempt` delta |  |  |
| P0-2 emit continuity | all P0-2 event families continue to emit normally |  |  |
| Legacy marker count | no unexpected increase |  |  |
| Marker detail if increased | capture path, time, source, replacement event, test vs real hit |  |  |
| Incidents | no user complaint, ops incident, payment anomaly, or broadcast anomaly |  |  |
| Redaction gate | no admin API raw sensitive data regression |  |  |

If a legacy marker hit appears, record:

- `legacy_path`
- timestamp
- `source_module`
- `source_route`
- `replacement_event_type`
- `replacement_consumer`
- whether it was a safety test
- whether it was a real business hit
- whether it blocks or extends deletion planning

## End-Of-Window Decision Rules

A legacy deletion PR may be proposed after the observation window only if all of
the following are true:

1. `legacy_path_invocation_count` is 0 during the window, or the only hits are
   confirmed safety tests.
2. Replacement `internal_event` rows continue to be generated for the relevant
   P0-2 event families.
3. Replacement consumers have passed P1 cutover, or product/operations confirm
   that the consumer is no longer needed.
4. `failed_terminal_count=0`.
5. SQL stale lock count is 0.
6. External Effects remain disabled, or target real execution has separate
   approval.
7. No user complaint, operations incident, payment anomaly, or broadcast anomaly
   occurred.
8. Redaction gate has no regression.
9. `allowed_event_consumers` was not unexpectedly expanded.

If any condition fails:

- do not delete the legacy path
- extend the observation window
- publish the blocking reason and owner

## Explicit Non-Authorization

During this observation window, do not:

- delete legacy code
- run a migration to remove legacy paths
- enable External Effects real execution
- enable real webhook, WeCom, Feishu, broadcast send, payment query, or refund
- expand non-payment worker allowlist pairs
- call non-dry-run `run_due`
- use `force=true`
